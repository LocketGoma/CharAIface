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
from shared.file_intake import render_attachment_intake_block
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
    "- file_analyze: Reads and analyzes an attached file. It supports table/spreadsheet summaries, CSV/TSV/XLSX value frequencies, row appearance probabilities, JSON/text summaries, and source-code structure.\n\n"
    "Call file_analyze when the user asks to inspect, analyze, calculate, summarize, aggregate, transform, or reason from the attached file.\n"
    "Do not call a tool for casual conversation or questions unrelated to the attached file.\n\n"
    "JSON schema:\n"
    "{\"tool\":\"file_analyze\",\"arguments\":{\"sample_size\":10,\"include_value_frequencies\":true,\"save_result\":false,\"output_format\":\"json\",\"preferred_result\":\"auto\",\"response_mode\":\"model_final\"},\"request_intent\":{\"intent\":\"short intent label\",\"expected_outcome\":\"what the user wants\",\"answer_strategy\":\"how the final assistant should use the tool result\",\"forbidden_behavior\":\"what the final assistant must avoid\"},\"reason\":\"short reason\"}\n"
    "or\n"
    "{\"tool\":\"none\",\"arguments\":{},\"request_intent\":{\"intent\":\"short intent label\",\"expected_outcome\":\"what the user wants\",\"answer_strategy\":\"how the assistant should answer\",\"forbidden_behavior\":\"what the assistant must avoid\"},\"reason\":\"short reason\"}\n\n"
    "The request_intent object is required. Infer it from the user's request, not from hard-coded examples.\n"
    "Use intent='statistics_or_counting' when the user asks for computed counts, frequencies, distributions, probabilities, totals, or other statistics from data.\n"
    "Use intent='summary' only when the user asks to summarize or describe the file.\n"
    "Use preferred_result='numeric_value_frequency_csv' for per-number or numeric frequency/probability CSV requests.\n"
    "Use preferred_result='all_cell_value_frequency_csv' for general cell value frequency/probability CSV requests.\n"
    "Use preferred_result='column_summary_csv' for column overview, schema, missing value, example, or numeric-stat summary requests.\n"
    "Use preferred_result='per_column_value_frequency_csv' for counts or distributions grouped by each column.\n"
    "For exact count, frequency, distribution, or probability requests, select the most specific preferred_result that already contains the computed result.\n"
    "Always use response_mode='model_final'. The model must answer after reading the backend tool result and request intent."
)
DEFAULT_TOOL_RESULT_PREFIX = (
    "[Tool Result: file_analyze]\n"
    "The model requested this backend tool call, and the app executed it deterministically.\n"
    "Use the tool result below to answer the user's original request.\n"
    "For exact counts, frequencies, distributions, probabilities, schema summaries, or table transformations, use the deterministic tool blocks instead of estimating from sample rows.\n"
    "For item-by-item, value-by-value, category-by-category, or column-specific count requests, convert the matching frequency CSV block into the final answer.\n"
    "Follow the final response language instruction below. "
    "If the user requested CSV output, output only CSV text without explanations, Markdown, code fences, XML-like tags, or comments."
)
DEFAULT_TOOL_ERROR_PROMPT = (
    "[Tool Result: file_analyze]\n"
    "status: error\nerror: {error}\n\n"
    "{language_instruction}\n"
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


def _format_prompt_template(template: str, **values: Any) -> str:
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        text = template
        for key, value in values.items():
            text = text.replace("{" + key + "}", str(value))
        return text


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
        used_default_tool_call = False
        if not tool_call or tool_call.get("tool") != "file_analyze":
            tool_call = self._default_file_analyze_tool_call(
                original_user_content=self._original_user_content(latest_user_message)
            )
            used_default_tool_call = True
        print(
            "[ToolLoop] file_analyze "
            f"{'defaulted' if used_default_tool_call else 'selected'} "
            f"for {Path(file_path).name}"
        )

        tool_result = self._execute_file_analyze_tool_call(
            file_path=file_path,
            tool_call=tool_call,
        )
        print(f"[ToolLoop] file_analyze status: {tool_result.get('status')}")

        tool_result_prompt = self._build_tool_result_prompt(
            tool_call=tool_call,
            tool_result=tool_result,
            app_language=app_language,
            original_user_content=self._original_user_content(latest_user_message),
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
                "tool_call_defaulted": used_default_tool_call,
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
        original_user_content = self._original_user_content(latest_user_message)

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
                    f"{render_attachment_intake_block(file_name, file_type, original_user_content)}\n\n"
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

    def _original_user_content(self, message: ChatMessage) -> str:
        metadata = getattr(message, "metadata", {}) or {}
        return str(
            metadata.get("transient_original_user_content")
            or message.content
            or ""
        ).strip()

    def _default_file_analyze_tool_call(self, *, original_user_content: str) -> dict[str, Any]:
        return {
            "tool": "file_analyze",
            "arguments": {
                "sample_size": 10,
                "include_value_frequencies": True,
                "save_result": False,
                "output_format": "json",
                "preferred_result": "auto",
                "response_mode": "model_final",
            },
            "request_intent": {
                "intent": "attached_file_task",
                "expected_outcome": (
                    "The user wants the assistant to answer the request using the attached file."
                ),
                "answer_strategy": (
                    "Use the backend file analysis result as evidence and follow the original user request."
                ),
                "forbidden_behavior": (
                    "Do not ignore the attached file or claim it cannot be read when backend analysis is available."
                ),
                "original_user_request": str(original_user_content or "").strip(),
            },
            "reason": (
                "Attached file context is present, so the backend should analyze the file "
                "before the assistant answers."
            ),
        }

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

    def _request_intent_block(
        self,
        *,
        tool_call: dict[str, Any],
        original_user_content: str,
    ) -> str:
        request_intent = tool_call.get("request_intent")
        if isinstance(request_intent, dict):
            intent = str(request_intent.get("intent") or "attached_file_task").strip()
            expected_outcome = str(request_intent.get("expected_outcome") or "").strip()
            answer_strategy = str(request_intent.get("answer_strategy") or "").strip()
            forbidden_behavior = str(request_intent.get("forbidden_behavior") or "").strip()
            return "\n".join(
                [
                    "[Request Intent]",
                    f"- intent: {intent}",
                    f"- user_expected_outcome: {expected_outcome or 'Answer the user request using the attached file.'}",
                    f"- required_behavior: {answer_strategy or 'Use the backend file analysis result as evidence.'}",
                    f"- forbidden_behavior: {forbidden_behavior or 'Do not ignore the attached file or invent unsupported facts.'}",
                ]
            )
        return "\n".join(
            [
                "[Request Intent]",
                "- intent: attached_file_task",
                f"- user_expected_outcome: Infer the requested operation from this user request: {str(original_user_content or '').strip()}",
                "- required_behavior: Prefer deterministic backend analysis fields over guessing from sample rows.",
            ]
        )

    def _build_tool_result_prompt(
        self,
        *,
        tool_call: dict[str, Any],
        tool_result: dict[str, Any],
        app_language: str,
        original_user_content: str,
    ) -> str:
        language_instruction = self._final_response_language_instruction(app_language)
        if tool_result.get("status") != "ok":
            return _format_prompt_template(
                _prompt_text(
                    "tool_error_prompt",
                    DEFAULT_TOOL_ERROR_PROMPT,
                ),
                error=tool_result.get("error", ""),
                language_instruction=language_instruction,
            )

        result = tool_result.get("result") if isinstance(tool_result.get("result"), dict) else {}
        formatted_result = self._format_analysis_context(
            result,
            language_instruction=language_instruction,
        )
        return (
            _prompt_text("tool_result_prefix", DEFAULT_TOOL_RESULT_PREFIX)
            + "\n"
            f"{language_instruction}\n"
            f"App language code: {app_language}\n"
            f"Tool call reason: {tool_call.get('reason', '')}\n\n"
            f"{self._request_intent_block(tool_call=tool_call, original_user_content=original_user_content)}\n\n"
            "Original user request to answer exactly:\n"
            "<USER_REQUEST>\n"
            f"{str(original_user_content or '').strip()}\n"
            "</USER_REQUEST>\n\n"
            "Do not summarize the attached file unless the user requested a summary. "
            "Use the backend tool result to perform the exact requested operation. "
            "If the request asks for item/value/category/column counts, use a frequency CSV block as the answer source.\n\n"
            f"{formatted_result}"
        ).strip()

    def _format_analysis_context(
        self,
        analysis: dict[str, Any],
        *,
        language_instruction: str = "",
    ) -> str:
        file_info = analysis.get("file") if isinstance(analysis.get("file"), dict) else {}
        analysis_info = (
            analysis.get("analysis") if isinstance(analysis.get("analysis"), dict) else {}
        )
        analysis_type = str(analysis_info.get("type") or "")
        language_instruction = language_instruction.strip()

        if analysis_type in {"table", "workbook"}:
            lines = [
                "[Backend File Analysis Tool Result]",
                "The backend has already read and analyzed the attached table/spreadsheet file. Treat these blocks as deterministic tool output.",
                language_instruction,
                "Answer the user's request directly. Do not summarize these field names or explain the tool result.",
                "For exact counts, frequencies, distributions, probabilities, or schema summaries, use the deterministic CSV blocks below and do not estimate from sample rows.",
                "For item-by-item, value-by-value, category-by-category, or column-specific count requests, convert the matching frequency CSV block into the final answer.",
                "For CSV output requests, return only CSV text without explanations, Markdown, or comments.",
                f"- filename: {file_info.get('name', '')}",
                f"- table_engine: {analysis_info.get('engine', '')}",
                f"- row_count: {analysis_info.get('row_count', '')}",
                f"- column_count: {analysis_info.get('column_count', '')}",
            ]
            if analysis_type == "workbook":
                lines.extend(
                    [
                        f"- workbook_sheet_count: {analysis_info.get('sheet_count', '')}",
                        f"- primary_sheet: {analysis_info.get('primary_sheet', '')}",
                    ]
                )
                sheet_inventory = self._format_workbook_sheet_inventory(analysis_info)
                if sheet_inventory:
                    lines.extend(
                        [
                            "",
                            "Workbook sheets:",
                            sheet_inventory,
                            "",
                            "The CSV/tool blocks below describe primary_sheet unless a block explicitly names another sheet.",
                        ]
                    )
            numeric_frequency_csv = str(
                analysis_info.get("numeric_value_frequency_csv") or ""
            ).strip()
            all_frequency_csv = str(
                analysis_info.get("all_cell_value_frequency_csv") or ""
            ).strip()
            column_summary_csv = str(
                analysis_info.get("column_summary_csv") or ""
            ).strip()
            per_column_frequency_csv = str(
                analysis_info.get("per_column_value_frequency_csv") or ""
            ).strip()
            reasoning_hints = analysis_info.get("table_reasoning_hints")
            if isinstance(reasoning_hints, list) and reasoning_hints:
                lines.extend(
                    [
                        "",
                        "Table reasoning hints:",
                        *[f"- {hint}" for hint in reasoning_hints if str(hint).strip()],
                    ]
                )
            if per_column_frequency_csv:
                lines.extend(
                    [
                        "",
                        "Use this block when the user asks for counts, distributions, or probabilities within each specific column.",
                        "<PER_COLUMN_VALUE_FREQUENCY_CSV>",
                        per_column_frequency_csv,
                        "</PER_COLUMN_VALUE_FREQUENCY_CSV>",
                    ]
                )
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
            if column_summary_csv:
                lines.extend(
                    [
                        "",
                        "Use this block for schema, column overview, missing value, example, top value, or numeric-stat summary requests.",
                        "<COLUMN_SUMMARY_CSV>",
                        column_summary_csv,
                        "</COLUMN_SUMMARY_CSV>",
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
            f"{language_instruction}\n"
            "Use deterministic fields from FILE_ANALYSIS_JSON for exact requests; do not invent values or infer totals from samples.\n"
            "Answer the user's request directly. Do not summarize these field names or explain the tool result.\n"
            "<FILE_ANALYSIS_JSON>\n"
            f"{json.dumps(compact_analysis, ensure_ascii=False)}\n"
            "</FILE_ANALYSIS_JSON>"
        )

    def _final_response_language_instruction(self, app_language: str) -> str:
        normalized = str(app_language or "").strip().lower()
        if normalized.startswith("ko"):
            return (
                "Final response language: Korean. "
                "Unless the user explicitly requested another language or raw data only, write the final answer in Korean."
            )
        if normalized.startswith("ja"):
            return (
                "Final response language: Japanese. "
                "Unless the user explicitly requested another language or raw data only, write the final answer in Japanese."
            )
        return (
            "Final response language: English. "
            "Unless the user explicitly requested another language or raw data only, write the final answer in English."
        )

    def _format_tool_call_trace(self, tool_call: dict[str, Any]) -> str:
        return (
            "[Tool Call]\n"
            f"{json.dumps({'tool': 'file_analyze', 'arguments': tool_call.get('arguments', {})}, ensure_ascii=False)}"
        )

    def _format_workbook_sheet_inventory(self, analysis_info: dict[str, Any]) -> str:
        sheets = analysis_info.get("sheets")
        if not isinstance(sheets, list):
            return ""

        lines: list[str] = []
        for index, sheet in enumerate(sheets[:20], start=1):
            if not isinstance(sheet, dict):
                continue
            sheet_name = str(sheet.get("sheet_name") or f"sheet_{index}")
            row_count = sheet.get("row_count", "")
            column_count = sheet.get("column_count", "")
            columns = sheet.get("columns")
            column_text = ""
            if isinstance(columns, list) and columns:
                visible_columns = [str(column) for column in columns[:8]]
                suffix = ", ..." if len(columns) > len(visible_columns) else ""
                column_text = f"; columns: {', '.join(visible_columns)}{suffix}"
            lines.append(
                f"- {sheet_name}: {row_count} rows x {column_count} columns{column_text}"
            )

        if len(sheets) > 20:
            lines.append(f"- ... {len(sheets) - 20} more sheet(s) omitted from inventory")

        return "\n".join(lines)

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
