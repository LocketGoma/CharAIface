from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import re
from pathlib import Path
from typing import Any, Callable

from backend.app.services.file_analysis_service import (
    FileAnalysisError,
    FileAnalysisRequest,
    FileAnalysisService,
)
from shared.schema.chat import ChatMessage


ModelCaller = Callable[[list[dict[str, str]]], str]
PROMPT_CONFIG_PATH = (
    Path(__file__).resolve().parents[3]
    / "resources"
    / "app"
    / "file_tool_loop_prompts.json"
)
DEFAULT_PLANNER_SYSTEM_PROMPT = (
    "You are a tool-use planner for CharAIface.\n"
    "Decide whether the assistant should call a backend tool before answering.\n"
    "Return strict JSON only. Do not use Markdown.\n\n"
    "Available tool:\n"
    "- file_analyze: Reads and analyzes an attached file. It supports table summaries, CSV/TSV value frequencies, row appearance probabilities, JSON/text summaries, and source-code structure.\n\n"
    "Call file_analyze when the user asks to inspect, analyze, calculate, summarize, aggregate, transform, or reason from the attached file.\n"
    "Do not call a tool for casual conversation or questions unrelated to the attached file.\n\n"
    "JSON schema:\n"
    "{\"tool\":\"file_analyze\",\"arguments\":{\"sample_size\":10,\"include_value_frequencies\":true,\"save_result\":false,\"output_format\":\"json\",\"preferred_result\":\"auto\",\"response_mode\":\"model_final\"},\"reason\":\"short reason\"}\n"
    "or\n"
    "{\"tool\":\"none\",\"arguments\":{},\"reason\":\"short reason\"}\n\n"
    "Use preferred_result='numeric_value_frequency_csv' for per-number or numeric frequency/probability CSV requests.\n"
    "Use preferred_result='all_cell_value_frequency_csv' for general cell value frequency/probability CSV requests.\n"
    "Use response_mode='direct_tool_result' only when the user asks for raw CSV/table output that the tool result can provide directly.\n"
    "Otherwise use response_mode='model_final'."
)
DEFAULT_TOOL_RESULT_PREFIX = (
    "[Tool Result: file_analyze]\n"
    "The model requested this backend tool call, and the app executed it deterministically.\n"
    "Use the tool result below to answer the user's original request.\n"
    "If the user requested CSV output, output only CSV text without explanations, Markdown, code fences, XML-like tags, or comments."
)
DEFAULT_TOOL_ERROR_PROMPT = (
    "[Tool Result: file_analyze]\n"
    "status: error\nerror: {error}\n\n"
    "The backend tool failed. Answer the user honestly and briefly."
)


@lru_cache(maxsize=1)
def _load_prompt_config() -> dict[str, Any]:
    try:
        with PROMPT_CONFIG_PATH.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        print(f"[ToolLoop] Failed to load prompt config: {error}")
        return {}

    return payload if isinstance(payload, dict) else {}


def _prompt_text(key: str, fallback: str) -> str:
    value = _load_prompt_config().get(key)
    text = str(value or "").strip()
    return text or fallback


@dataclass(frozen=True)
class FileToolResponse:
    content: str
    metadata: dict[str, Any]


class FileToolLoop:
    def __init__(self, file_analysis_service: FileAnalysisService) -> None:
        self.file_analysis_service = file_analysis_service

    def try_create_augmented_content(
        self,
        *,
        latest_user_message: ChatMessage,
        base_messages: list[dict[str, str]],
        app_language: str,
        call_model: ModelCaller,
    ) -> FileToolResponse | None:
        metadata = getattr(latest_user_message, "metadata", {}) or {}
        file_path = str(metadata.get("file_path") or "").strip()
        if not metadata.get("transient_file_context") or not file_path:
            return None

        tool_call = self._request_tool_call_decision(
            latest_user_message=latest_user_message,
            app_language=app_language,
            call_model=call_model,
        )
        if not tool_call or tool_call.get("tool") != "file_analyze":
            return None

        tool_result = self._execute_file_analyze_tool_call(
            file_path=file_path,
            tool_call=tool_call,
        )
        direct_content = self._direct_response_content(
            tool_call=tool_call,
            tool_result=tool_result,
        )
        if direct_content:
            return FileToolResponse(
                content=direct_content,
                metadata={
                    "tool_loop_used": True,
                    "tool_name": "file_analyze",
                    "tool_status": tool_result.get("status"),
                    "tool_response_mode": "direct_tool_result",
                },
            )

        tool_result_prompt = self._build_tool_result_prompt(
            tool_call=tool_call,
            tool_result=tool_result,
            app_language=app_language,
        )
        final_messages = [
            *base_messages,
            {
                "role": "assistant",
                "content": self._format_tool_call_trace(tool_call),
            },
            {
                "role": "user",
                "content": tool_result_prompt,
            },
        ]
        content = call_model(final_messages)
        if not str(content or "").strip():
            return None

        return FileToolResponse(
            content=content,
            metadata={
                "tool_loop_used": True,
                "tool_name": "file_analyze",
                "tool_status": tool_result.get("status"),
                "tool_response_mode": "model_final",
            },
        )

    def _request_tool_call_decision(
        self,
        *,
        latest_user_message: ChatMessage,
        app_language: str,
        call_model: ModelCaller,
    ) -> dict[str, Any] | None:
        metadata = getattr(latest_user_message, "metadata", {}) or {}
        file_name = str(metadata.get("file_name") or Path(str(metadata.get("file_path") or "")).name)
        file_type = str(metadata.get("file_type") or Path(file_name).suffix)
        original_user_content = str(
            metadata.get("transient_original_user_content")
            or latest_user_message.content
            or ""
        ).strip()

        planner_messages = [
            {
                "role": "system",
                "content": _prompt_text("planner_system_prompt", DEFAULT_PLANNER_SYSTEM_PROMPT),
            },
            {
                "role": "user",
                "content": (
                    f"App language: {app_language}\n"
                    f"Attached file name: {file_name}\n"
                    f"Attached file type: {file_type}\n\n"
                    "User request:\n"
                    f"{original_user_content}"
                ),
            },
        ]
        raw_decision = call_model(planner_messages)
        decision = self._parse_tool_call_json(raw_decision)
        if not isinstance(decision, dict):
            print(f"[ToolLoop] Ignoring non-JSON tool decision: {raw_decision[:200]}")
            return None

        tool_name = str(decision.get("tool") or "").strip()
        if tool_name not in {"file_analyze", "none"}:
            return None
        if tool_name == "none":
            return None

        arguments = decision.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        decision["arguments"] = arguments
        return decision

    def _execute_file_analyze_tool_call(
        self,
        *,
        file_path: str,
        tool_call: dict[str, Any],
    ) -> dict[str, Any]:
        arguments = tool_call.get("arguments") if isinstance(tool_call.get("arguments"), dict) else {}
        try:
            analysis = self.file_analysis_service.analyze(
                FileAnalysisRequest(
                    file_path=file_path,
                    sample_size=self._bounded_int(
                        arguments.get("sample_size"),
                        default=10,
                        minimum=0,
                        maximum=100,
                    ),
                    include_value_frequencies=bool(arguments.get("include_value_frequencies", True)),
                    save_result=bool(arguments.get("save_result", False)),
                    output_format=str(arguments.get("output_format") or "json"),
                )
            )
        except FileAnalysisError as error:
            return {
                "status": "error",
                "error": str(error),
            }

        return {
            "status": "ok",
            "result": analysis,
        }

    def _direct_response_content(
        self,
        *,
        tool_call: dict[str, Any],
        tool_result: dict[str, Any],
    ) -> str:
        if tool_result.get("status") != "ok":
            return ""

        arguments = tool_call.get("arguments") if isinstance(tool_call.get("arguments"), dict) else {}
        response_mode = str(arguments.get("response_mode") or "").strip()
        if response_mode != "direct_tool_result":
            return ""

        result = tool_result.get("result") if isinstance(tool_result.get("result"), dict) else {}
        analysis_info = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
        preferred_result = str(arguments.get("preferred_result") or "auto").strip()
        candidates: list[str] = []
        if preferred_result and preferred_result != "auto":
            candidates.append(preferred_result)
        candidates.extend(
            [
                "numeric_value_frequency_csv",
                "all_cell_value_frequency_csv",
            ]
        )

        for key in candidates:
            content = str(analysis_info.get(key) or "").strip()
            if content:
                return content
        return ""

    def _build_tool_result_prompt(
        self,
        *,
        tool_call: dict[str, Any],
        tool_result: dict[str, Any],
        app_language: str,
    ) -> str:
        if tool_result.get("status") != "ok":
            return _prompt_text(
                "tool_error_prompt",
                DEFAULT_TOOL_ERROR_PROMPT,
            ).format(error=tool_result.get("error", ""))

        result = tool_result.get("result") if isinstance(tool_result.get("result"), dict) else {}
        formatted_result = self._format_analysis_context(result)
        return (
            _prompt_text("tool_result_prefix", DEFAULT_TOOL_RESULT_PREFIX)
            + "\n"
            f"App language: {app_language}\n"
            f"Tool call reason: {tool_call.get('reason', '')}\n\n"
            f"{formatted_result}"
        ).strip()

    def _format_analysis_context(self, analysis: dict[str, Any]) -> str:
        file_info = analysis.get("file") if isinstance(analysis.get("file"), dict) else {}
        analysis_info = (
            analysis.get("analysis") if isinstance(analysis.get("analysis"), dict) else {}
        )
        analysis_type = str(analysis_info.get("type") or "")

        if analysis_type == "table":
            lines = [
                "[Backend File Analysis Tool Result]",
                "The backend has already read and analyzed the attached table file. Treat these blocks as deterministic tool output.",
                "Answer the user's request directly. Do not summarize these field names or explain the tool result.",
                "For CSV output requests, return only CSV text without explanations, Markdown, or comments.",
                f"- filename: {file_info.get('name', '')}",
                f"- table_engine: {analysis_info.get('engine', '')}",
                f"- row_count: {analysis_info.get('row_count', '')}",
                f"- column_count: {analysis_info.get('column_count', '')}",
            ]
            numeric_frequency_csv = str(
                analysis_info.get("numeric_value_frequency_csv") or ""
            ).strip()
            all_frequency_csv = str(
                analysis_info.get("all_cell_value_frequency_csv") or ""
            ).strip()
            if numeric_frequency_csv:
                lines.extend(
                    [
                        "",
                        "Use this block when the user asks for per-number counts, total appearances, row appearances, or per-row appearance probabilities.",
                        "<NUMERIC_VALUE_FREQUENCY_CSV>",
                        numeric_frequency_csv,
                        "</NUMERIC_VALUE_FREQUENCY_CSV>",
                    ]
                )
            if all_frequency_csv:
                lines.extend(
                    [
                        "",
                        "Use this block when the user asks for general CSV cell value counts or probabilities.",
                        "<ALL_CELL_VALUE_FREQUENCY_CSV>",
                        all_frequency_csv,
                        "</ALL_CELL_VALUE_FREQUENCY_CSV>",
                    ]
                )

            sample_rows = analysis_info.get("sample_rows")
            if isinstance(sample_rows, list) and sample_rows:
                lines.extend(
                    [
                        "",
                        "Sample rows for context only:",
                        "<SAMPLE_ROWS_JSON>",
                        json.dumps(sample_rows, ensure_ascii=False),
                        "</SAMPLE_ROWS_JSON>",
                    ]
                )
            return "\n".join(lines).strip()

        compact_analysis = {
            "file": file_info,
            "analysis": analysis_info,
        }
        return (
            "[Backend File Analysis Tool Result]\n"
            "The backend has already read and analyzed the attached file. Treat this as deterministic tool data.\n"
            "Answer the user's request directly. Do not summarize these field names or explain the tool result.\n"
            "<FILE_ANALYSIS_JSON>\n"
            f"{json.dumps(compact_analysis, ensure_ascii=False)}\n"
            "</FILE_ANALYSIS_JSON>"
        )

    def _format_tool_call_trace(self, tool_call: dict[str, Any]) -> str:
        return (
            "[Tool Call]\n"
            f"{json.dumps({'tool': 'file_analyze', 'arguments': tool_call.get('arguments', {})}, ensure_ascii=False)}"
        )

    def _parse_tool_call_json(self, content: str) -> dict[str, Any] | None:
        text = str(content or "").strip()
        if not text:
            return None
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"\s*```$", "", text).strip()

        candidates = [text]
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            candidates.append(match.group(0))

        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        return None

    def _bounded_int(
        self,
        value: Any,
        *,
        default: int,
        minimum: int,
        maximum: int,
    ) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, min(maximum, parsed))
