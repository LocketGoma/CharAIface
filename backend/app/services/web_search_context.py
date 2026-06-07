from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.app.services.web_search_service import WebSearchConfig, WebSearchResult
from shared.schema.chat import ChatMessage, ChatRequest


CHAT_SERVICE_MARKERS_FILENAME = "chat_service_markers.json"
SEARCH_CONTEXT_RESOURCE_DIR = "search_context"


class WebSearchContextBuilder:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.markers_path = (
            self.project_root
            / "resources"
            / "data"
            / SEARCH_CONTEXT_RESOURCE_DIR
            / CHAT_SERVICE_MARKERS_FILENAME
        )
        self.markers = self._load_markers()

    def _load_markers(self) -> dict[str, tuple[str, ...]]:
        markers: dict[str, tuple[str, ...]] = {}
        self._merge_marker_file(markers, self.markers_path)
        return markers

    def _merge_marker_file(self, markers: dict[str, tuple[str, ...]], path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            print(f"[WebSearchContextBuilder] Failed to load {path.name}: {error}")
            return

        if not isinstance(data, dict):
            return

        for category, raw_values in data.items():
            if not isinstance(category, str) or not isinstance(raw_values, list):
                continue

            values: list[str] = list(markers.get(category, ()))
            for value in raw_values:
                if not isinstance(value, str):
                    continue
                normalized = self.compact_text(value)
                if normalized:
                    values.append(normalized)

            markers[category] = tuple(dict.fromkeys(values))

    def resolve_contextual_query(
        self,
        query: str,
        request: ChatRequest,
    ) -> tuple[str, str]:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return normalized_query, "direct"

        if not self.looks_like_contextual_retry_query(normalized_query):
            return normalized_query, "direct"

        prior_topic = self.find_previous_search_topic(request)
        if not prior_topic:
            return normalized_query, "direct"

        modifiers = self.contextual_retry_modifiers(normalized_query)
        resolved = prior_topic
        if modifiers:
            lowered = resolved.lower()
            additions = [modifier for modifier in modifiers if modifier.lower() not in lowered]
            if additions:
                resolved = f"{resolved} {' '.join(additions)}".strip()

        return resolved, "previous_conversation"

    def looks_like_contextual_retry_query(self, query: str) -> bool:
        text = str(query or "").strip().lower()
        if not text:
            return False

        compact = " ".join(text.split())
        if compact in self.markers_for("web_search_contextual_retry_exact"):
            return True

        has_context = self.has_any_marker(
            compact,
            self.markers_for("web_search_contextual_retry_context"),
        )
        has_new_topic = self.has_any_marker(
            compact,
            self.markers_for("web_search_contextual_retry_new_topic"),
        )
        return has_context and not has_new_topic and len(compact) <= 40

    def contextual_retry_modifiers(self, query: str) -> list[str]:
        text = self.compact_text(query)
        modifiers: list[str] = []
        if self.has_any_marker(text, self.markers_for("web_search_contextual_retry_latest")):
            modifier = self.first_marker("web_search_contextual_retry_latest_append")
            if modifier:
                modifiers.append(modifier)
        if self.has_any_marker(text, self.markers_for("web_search_contextual_retry_alternate_source")):
            modifier = self.first_marker("web_search_contextual_retry_alternate_source_append")
            if modifier:
                modifiers.append(modifier)
        return modifiers

    def find_previous_search_topic(self, request: ChatRequest) -> str:
        latest_user = self.find_latest_user_message(request)
        latest_user_id = id(latest_user) if latest_user is not None else None

        for message in reversed(request.messages):
            if id(message) == latest_user_id:
                continue
            if str(message.role) != "user":
                continue
            content = str(message.content or "").strip()
            if not content:
                continue

            manual_query = self.manual_query(content)
            candidate = manual_query.strip() if manual_query is not None else content
            if not candidate:
                continue
            if self.looks_like_contextual_retry_query(candidate):
                continue
            if candidate.startswith("/"):
                continue
            return candidate

        return ""

    def normalize_query_for_region(
        self,
        query: str,
        original_text: str,
        config: WebSearchConfig,
        settings: dict[str, Any],
    ) -> str:
        normalized = str(query or original_text or "").strip()
        if not normalized:
            return normalized

        lowered = normalized.lower()
        country_code = str(getattr(config, "country_code", "") or "").upper()
        location = str(getattr(config, "location", "") or "").strip()

        if self.looks_like_weather_request(lowered):
            additions: list[str] = []
            if country_code == "KR" and not self.has_any_marker(
                lowered,
                self.markers_for("web_search_region_kr_existing"),
            ):
                additions.extend(self.markers_for("web_search_region_kr_append")[:1])
            elif country_code == "JP" and not self.has_any_marker(
                lowered,
                self.markers_for("web_search_region_jp_existing"),
            ):
                additions.extend(self.markers_for("web_search_region_jp_append")[:1])
            elif country_code == "US" and not self.has_any_marker(
                lowered,
                self.markers_for("web_search_region_us_existing"),
            ):
                additions.extend(self.markers_for("web_search_region_us_append")[:1])
            elif location and location.lower() not in lowered:
                additions.append(location)

            now = datetime.now(timezone.utc).astimezone()
            compact = self.compact_text(normalized)
            if self.has_any_marker(compact, self.markers_for("web_search_relative_tomorrow")):
                additions.append((now + timedelta(days=1)).strftime("%Y-%m-%d"))
            elif self.has_any_marker(compact, self.markers_for("web_search_relative_today")):
                additions.append(now.strftime("%Y-%m-%d"))
            elif self.has_relative_time_reference(compact):
                additions.append(now.strftime("%Y-%m-%d"))

            unit_hint = self.weather_unit_query_hint(settings)
            if unit_hint and unit_hint.lower() not in lowered:
                additions.append(unit_hint)

            if additions:
                normalized = f"{normalized} {' '.join(additions)}".strip()

        return normalized

    def weather_unit_query_hint(self, settings: dict[str, Any]) -> str:
        unit_system = self.preferred_unit_system(settings)
        if unit_system == "imperial":
            return "fahrenheit"
        return "섭씨 celsius"

    def manual_query(self, text: str) -> str | None:
        stripped = str(text or "").strip()
        lowered = stripped.lower()
        prefixes = ("/search", "/web", "/검색")
        for prefix in prefixes:
            if lowered == prefix:
                return ""
            if lowered.startswith(prefix + " "):
                return stripped[len(prefix):].strip()
        return None

    def should_auto_search(self, text: str, settings: dict[str, Any]) -> bool:
        if not bool(settings.get("web_search_auto_enabled")):
            return False

        stripped = str(text or "").strip()
        if not stripped or stripped.startswith("/"):
            return False

        compact = self.compact_text(stripped)
        if self.looks_like_local_context_request(compact):
            return False

        if self.looks_like_explicit_request(compact):
            return True

        if self.looks_like_current_info_request(compact):
            return True

        if not self.has_any_marker(compact, self.markers_for("web_search_current")):
            return False

        if not self.has_any_marker(compact, self.markers_for("web_search_current_topics")):
            return False

        if self.looks_like_explanation_only_request(compact):
            return False

        return self.has_any_marker(compact, self.markers_for("web_search_request"))

    def auto_query(self, text: str) -> str:
        return str(text or "").strip()

    def compact_text(self, text: str) -> str:
        return " ".join(str(text or "").strip().lower().split())

    def has_any_marker(self, text: str, markers: tuple[str, ...]) -> bool:
        return any(marker in text for marker in markers)

    def markers_for(self, category: str) -> tuple[str, ...]:
        return self.markers.get(category, ())

    def first_marker(self, category: str) -> str:
        markers = self.markers_for(category)
        return markers[0] if markers else ""

    def looks_like_explicit_request(self, text: str) -> bool:
        return self.has_any_marker(text, self.markers_for("web_search_directive"))

    def looks_like_local_context_request(self, text: str) -> bool:
        return self.has_any_marker(text, self.markers_for("web_search_local_context"))

    def looks_like_explanation_only_request(self, text: str) -> bool:
        if not self.has_any_marker(text, self.markers_for("web_search_explanation_only")):
            return False
        return not self.looks_like_explicit_request(text)

    def looks_like_current_info_request(self, text: str) -> bool:
        compact = self.compact_text(text)
        if not compact or self.looks_like_explanation_only_request(compact):
            return False
        if not self.has_relative_time_reference(compact):
            return False
        return self.looks_like_answer_request(compact) or len(compact) <= 40

    def looks_like_weather_request(self, text: str) -> bool:
        return bool(
            re.search(
                r"(\b(weather|forecast)\b|날씨|기상|예보)",
                self.compact_text(text),
                flags=re.IGNORECASE,
            )
        )

    def has_relative_time_reference(self, text: str) -> bool:
        return bool(
            re.search(
                r"(\b(today|tomorrow|current|now|latest|recent|this\s+week|this\s+month)\b|"
                r"\d{4}[-./]\d{1,2}[-./]\d{1,2}|"
                r"오늘|내일|현재|지금|최신|최근|이번\s*주|이번\s*달|이번\s*분기|올해)",
                text,
                flags=re.IGNORECASE,
            )
        )

    def looks_like_answer_request(self, text: str) -> bool:
        if "?" in text:
            return True
        return bool(
            re.search(
                r"(\b(tell me|what is|what are|find|check|summarize)\b|"
                r"알려\s*줘|알려줘|찾아\s*줘|찾아줘|확인\s*해\s*줘|확인해줘|"
                r"정리\s*해\s*줘|정리해줘|요약\s*해\s*줘|요약해줘|어때|뭐야|뭔가)",
                text,
                flags=re.IGNORECASE,
            )
        )

    def config_from_settings(self, settings: dict[str, Any]) -> WebSearchConfig:
        provider = str(settings.get("web_search_provider") or "tavily").strip().lower()
        country_code, location, tavily_country = self.region_from_settings(settings)
        return WebSearchConfig(
            enabled=bool(settings.get("web_search_enabled")),
            provider=provider,
            auth_mode=str(settings.get("web_search_auth_mode") or "secure_store").strip().lower(),
            credential_id=str(
                settings.get("web_search_credential_id")
                or self.default_credential_id(provider)
            ).strip(),
            api_key_env=str(
                settings.get("web_search_api_key_env")
                or self.default_api_key_env(provider)
            ).strip() or None,
            base_url=str(settings.get("web_search_base_url") or "").strip(),
            max_results=int(settings.get("web_search_max_results") or 5),
            timeout_seconds=float(settings.get("web_search_timeout_seconds") or 20),
            country_code=country_code,
            location=location,
            tavily_country=tavily_country,
        )

    def region_from_settings(self, settings: dict[str, Any]) -> tuple[str, str, str]:
        preset = str(settings.get("user_country_preset") or "auto_language").strip().lower()
        if preset == "auto_language":
            language = str(settings.get("language") or "ko").lower()
            preset = "kr" if language.startswith("ko") else "us"

        mapping = {
            "kr": ("KR", "South Korea", "south korea"),
            "jp": ("JP", "Japan", "japan"),
            "us": ("US", "United States", "united states"),
            "eu": ("", "Europe", ""),
        }
        if preset in mapping:
            return mapping[preset]

        country_code = str(settings.get("user_country_code") or "").strip().upper()
        location = str(settings.get("user_country_location") or "").strip()
        tavily_country = self.tavily_country_from_code_or_location(country_code, location)
        if preset == "ip_auto" and not country_code and not location:
            language = str(settings.get("language") or "ko").lower()
            return mapping["kr" if language.startswith("ko") else "us"]
        return country_code, location, tavily_country

    def tavily_country_from_code_or_location(self, country_code: str, location: str) -> str:
        code = str(country_code or "").strip().upper()
        by_code = {
            "KR": "south korea",
            "JP": "japan",
            "US": "united states",
            "DE": "germany",
            "FR": "france",
            "GB": "united kingdom",
            "UK": "united kingdom",
        }
        if code in by_code:
            return by_code[code]

        normalized = str(location or "").strip().lower()
        by_location = {
            "south korea": "south korea",
            "korea": "south korea",
            "republic of korea": "south korea",
            "japan": "japan",
            "united states": "united states",
            "usa": "united states",
            "us": "united states",
            "germany": "germany",
            "france": "france",
            "united kingdom": "united kingdom",
            "uk": "united kingdom",
        }
        return by_location.get(normalized, "")

    def default_credential_id(self, provider: str) -> str:
        provider = (provider or "tavily").strip().lower()
        if provider == "firecrawl":
            return "CharAIface/firecrawl/api_key"
        if provider == "none":
            return ""
        return "CharAIface/tavily/api_key"

    def default_api_key_env(self, provider: str) -> str:
        provider = (provider or "tavily").strip().lower()
        if provider == "firecrawl":
            return "FIRECRAWL_API_KEY"
        if provider == "none":
            return ""
        return "TAVILY_API_KEY"

    def build_prompt(
        self,
        web_search_context: dict[str, Any] | None,
        app_language: str,
    ) -> str:
        if not web_search_context or not web_search_context.get("used"):
            return ""

        result = web_search_context.get("result")
        if not isinstance(result, WebSearchResult):
            return ""

        if app_language.startswith("ko"):
            lines = [
                "\n[HIGH PRIORITY WEB SEARCH TOOL RESULT]",
                "백엔드가 이미 실제 검색 API를 호출했고, 아래 WEB_SEARCH_RESULTS는 이번 답변에 반드시 사용해야 하는 도구 실행 결과다.",
                f"Search provider: {result.provider}",
                f"Search query: {result.query}",
                f"Search region: {web_search_context.get('region_country_code') or '-'} {web_search_context.get('region_location') or ''}".strip(),
                self.unit_preference_prompt(web_search_context, app_language),
                "최신 사용자 메시지가 /search, /web, /검색 형태여도, 이것은 도구를 직접 실행하라는 요청이 아니라 이미 완료된 검색 결과를 바탕으로 답하라는 요청이다.",
                "절대 '검색할 수 없다', '인터넷에 접속할 수 없다', '외부 검색 API를 사용할 수 없다', '실시간 연결이 제한되어 있다'라고 말하지 마라.",
                "반드시 WEB_SEARCH_RESULTS에 있는 내용만 근거로 한국어로 답하라.",
                "검색 결과가 부족하면 '제공된 검색 결과만으로는 부족합니다'라고 말하되, 검색 기능이 없다고 말하지 마라.",
                "출처 URL이 유용하면 함께 적어라.",
                "캐릭터 말투보다 이 검색 결과 사용 규칙이 우선한다.",
            ]
        else:
            lines = [
                "\n[HIGH PRIORITY WEB SEARCH TOOL RESULT]",
                "The backend has already called a real web search API. The WEB_SEARCH_RESULTS below are tool results that MUST be used for this response.",
                f"Search provider: {result.provider}",
                f"Search query: {result.query}",
                f"Search region: {web_search_context.get('region_country_code') or '-'} {web_search_context.get('region_location') or ''}".strip(),
                self.unit_preference_prompt(web_search_context, app_language),
                "Even if the latest user message starts with /search, /web, or /검색, treat it as a request to answer using the completed search results, not as a request for you to run a tool.",
                "Never say that you cannot search the web, cannot access the internet, cannot use an external search API, or that real-time access is restricted.",
                "Answer using only the WEB_SEARCH_RESULTS below as evidence.",
                "If the results are insufficient, say that the provided search results are insufficient; do not say that web search is unavailable.",
                "Mention source URLs when useful.",
                "These web-search rules override character style instructions.",
            ]

        if result.answer:
            lines.append(f"Provider answer: {result.answer}")

        if result.warning:
            lines.append(f"Provider warning: {result.warning}")

        lines.append("Search results:")
        lines.extend(self.format_result_lines(result))

        if not result.results:
            lines.append("No search results were returned.")

        return "\n".join(lines).strip()

    def build_final_user_message(
        self,
        latest_user_message: ChatMessage | None,
        web_search_context: dict[str, Any] | None,
        app_language: str,
    ) -> str:
        if not latest_user_message or not web_search_context or not web_search_context.get("used"):
            return ""

        result = web_search_context.get("result")
        if not isinstance(result, WebSearchResult):
            return ""

        original_text = str(latest_user_message.content or "").strip()
        user_query = str(web_search_context.get("query") or result.query or original_text).strip()
        region = f"{web_search_context.get('region_country_code') or '-'} {web_search_context.get('region_location') or ''}".strip()
        unit_prompt = self.unit_preference_prompt(web_search_context, app_language)

        result_lines = []
        if result.answer:
            result_lines.append(f"Provider answer: {result.answer.strip()}")
        if result.warning:
            result_lines.append(f"Provider warning: {result.warning.strip()}")

        result_lines.extend(self.format_result_lines(result))

        if not result_lines:
            result_lines.append("No search results were returned.")

        results_block = "\n\n".join(result_lines)

        if app_language.startswith("ko"):
            return (
                "아래는 백엔드가 이미 완료한 웹 검색 결과입니다. 이 메시지를 일반 대화가 아니라 최우선 도구 결과로 처리하세요.\n"
                "당신은 검색을 직접 실행할 필요가 없습니다. 이미 주어진 결과를 근거로 답해야 합니다.\n"
                "'검색할 수 없다', '실시간 정보에 접근할 수 없다', '검색 API를 사용할 수 없다' 같은 문구는 출력하지 마세요.\n"
                "검색 결과만으로 부족하면 '제공된 검색 결과만으로는 부족합니다'라고만 말하세요.\n\n"
                f"원래 사용자 입력: {original_text}\n"
                f"답해야 할 검색어: {user_query}\n"
                f"검색 제공자: {result.provider}\n"
                f"검색 지역: {region}\n\n"
                f"{unit_prompt}\n\n"
                "WEB_SEARCH_RESULTS:\n"
                f"{results_block}\n\n"
                "위 검색 결과를 바탕으로 한국어로 답하세요."
            ).strip()

        return (
            "The backend has already completed web search. Treat this message as the highest-priority tool result, not as normal chat.\n"
            "You do not need to run search yourself. You must answer using the given results.\n"
            "Do not say you cannot search, cannot access real-time information, or cannot use a search API.\n"
            "If the results are insufficient, say that the provided search results are insufficient.\n\n"
            f"Original user input: {original_text}\n"
            f"Search query to answer: {user_query}\n"
            f"Search provider: {result.provider}\n"
            f"Search region: {region}\n\n"
            f"{unit_prompt}\n\n"
            "WEB_SEARCH_RESULTS:\n"
            f"{results_block}\n\n"
            "Answer using the search results above."
        ).strip()

    def preferred_unit_system(self, settings: dict[str, Any]) -> str:
        unit_system = str(settings.get("preferred_unit_system") or "metric").strip().lower()
        if unit_system not in {"metric", "imperial"}:
            return "metric"
        return unit_system

    def unit_preference_prompt(
        self,
        web_search_context: dict[str, Any] | None,
        app_language: str,
    ) -> str:
        unit_system = str(
            (web_search_context or {}).get("preferred_unit_system") or "metric"
        ).strip().lower()
        if unit_system == "imperial":
            if app_language.startswith("ko"):
                return (
                    "단위 표기 우선순위: 화씨/야드파운드법을 우선 사용하라. "
                    "날씨 온도는 화씨(°F)를 먼저 쓰고, 거리/길이/무게는 가능한 경우 야드파운드법을 우선하라. "
                    "단, 원문 출처나 공식 규격에서 특정 단위 자체가 의미를 가지는 경우에는 그 원 단위를 보존하고 임의 변환하지 마라. "
                    "날씨 출처의 숫자가 다른 단위로 보이면 숫자만 유지한 채 단위 기호를 바꾸지 말고, 변환이 필요하면 계산한 변환값을 근사치로 표시하라."
                )
            return (
                "Unit preference: prefer Fahrenheit and imperial/US customary units. "
                "For weather, put Fahrenheit (°F) first; prefer imperial units for distance, length, and weight when appropriate. "
                "However, preserve source-specific or official units when the original unit itself is meaningful; do not force a conversion. "
                "If a weather source number appears to use another unit, do not keep the number and only relabel the unit symbol; calculate and label the approximate converted value when conversion is needed."
            )

        if app_language.startswith("ko"):
            return (
                "단위 표기 우선순위: 섭씨/미터법을 우선 사용하라. "
                "날씨 답변에서는 사용자가 명시적으로 요청하지 않는 한 화씨(°F)를 쓰지 말고 섭씨(°C)만 사용하라. "
                "검색 결과가 화씨를 포함하면 섭씨로 환산한 근사치만 표시하고, 화씨 원문 숫자를 병기하지 마라. "
                "화씨 숫자만 유지한 채 °C로 바꾸는 것은 금지한다."
            )
        return (
            "Unit preference: prefer Celsius and metric units. "
            "For weather answers, use Celsius (°C) only unless the user explicitly asks for Fahrenheit. "
            "If search results include Fahrenheit, show only the approximate Celsius conversion and do not include the original Fahrenheit value. "
            "Never keep a Fahrenheit number and merely relabel it as °C."
        )

    def normalize_weather_units_in_response(
        self,
        content: str,
        web_search_context: dict[str, Any] | None,
    ) -> str:
        if not content or not web_search_context or not web_search_context.get("used"):
            return content
        if str(web_search_context.get("preferred_unit_system") or "metric") != "metric":
            return content

        query = str(web_search_context.get("query") or "")
        if not self.looks_like_weather_request(query):
            return content

        normalized = re.sub(
            r"\s*/\s*(?:체감\s*)?(?:온도\s*)?(?:약\s*)?\d+(?:\.\d+)?\s*°F",
            "",
            content,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            r"\(?\s*(?:화씨|fahrenheit)\s*(?:약\s*)?\d+(?:\.\d+)?\s*(?:°F)?\s*\)?",
            "",
            normalized,
            flags=re.IGNORECASE,
        )

        def convert_suspicious_celsius(match: re.Match[str]) -> str:
            value = float(match.group(1))
            suffix = match.group(2)
            if value < 55:
                return match.group(0)
            celsius = round((value - 32) * 5 / 9)
            return f"{celsius}°C{suffix}"

        return re.sub(
            r"(\d+(?:\.\d+)?)\s*°C(\s*[~～-]?)",
            convert_suspicious_celsius,
            normalized,
        )

    def format_result_lines(
        self,
        result: WebSearchResult,
        limit: int = 10,
    ) -> list[str]:
        lines: list[str] = []
        for index, item in enumerate(result.results[:limit], start=1):
            title = str(item.title or "").strip() or "Untitled"
            url = str(item.url or "").strip()
            snippet = str(item.content or "").strip() or "No snippet."
            lines.append(f"[{index}] {title}\nURL: {url}\nSnippet: {snippet}")
        return lines

    def looks_like_refusal(
        self,
        content: str,
        web_search_context: dict[str, Any] | None,
    ) -> bool:
        if not web_search_context or not web_search_context.get("used"):
            return False
        if int(web_search_context.get("result_count") or 0) <= 0:
            return False

        lowered = str(content or "").lower()
        return self.has_any_marker(lowered, self.markers_for("web_search_refusal"))

    def fallback_answer(
        self,
        web_search_context: dict[str, Any] | None,
        app_language: str,
        developer_mode: bool = False,
    ) -> str:
        if not web_search_context:
            return ""

        result = web_search_context.get("result")
        if not isinstance(result, WebSearchResult):
            return ""

        items = result.results[:5]
        if app_language.startswith("ko"):
            lines = []
            if developer_mode:
                lines.extend([
                    "검색 결과는 정상적으로 전달됐지만, 선택된 AI 모델이 검색 결과를 무시하는 답변을 생성해서 검색 결과 요약으로 대체합니다.",
                    "",
                ])
            lines.extend([
                f"검색어: {result.query}",
                f"검색 제공자: {result.provider}",
                f"검색 지역: {web_search_context.get('region_country_code') or '-'} {web_search_context.get('region_location') or ''}".strip(),
                "",
            ])
            if result.answer:
                lines.extend(["제공자 요약:", result.answer.strip(), ""])
            lines.append("검색 결과:")
            for index, item in enumerate(items, start=1):
                snippet = item.content.strip() or "요약 없음"
                lines.append(f"{index}. {item.title}\n   {item.url}\n   {snippet}")
            return "\n".join(lines).strip()

        lines = []
        if developer_mode:
            lines.extend([
                "Search results were retrieved, but the selected AI model ignored them and generated a browsing-unavailable answer. Showing the retrieved search summary instead.",
                "",
            ])
        lines.extend([
            f"Query: {result.query}",
            f"Provider: {result.provider}",
            f"Region: {web_search_context.get('region_country_code') or '-'} {web_search_context.get('region_location') or ''}".strip(),
            "",
        ])
        if result.answer:
            lines.extend(["Provider answer:", result.answer.strip(), ""])
        lines.append("Search results:")
        for index, item in enumerate(items, start=1):
            snippet = item.content.strip() or "No snippet."
            lines.append(f"{index}. {item.title}\n   {item.url}\n   {snippet}")
        return "\n".join(lines).strip()

    def metadata(self, web_search_context: dict[str, Any] | None) -> dict[str, Any]:
        if not web_search_context:
            return {}
        # TODO: When developer debug messages are added, expose provider result snippets here too.
        metadata: dict[str, Any] = {
            "web_search_used": bool(web_search_context.get("used")),
        }
        if web_search_context.get("provider"):
            metadata["web_search_provider"] = web_search_context.get("provider")
        if web_search_context.get("query"):
            metadata["web_search_query"] = web_search_context.get("query")
        if web_search_context.get("result_count") is not None:
            metadata["web_search_result_count"] = web_search_context.get("result_count")
        if web_search_context.get("region_country_code"):
            metadata["web_search_region_country_code"] = web_search_context.get("region_country_code")
        if web_search_context.get("region_location"):
            metadata["web_search_region_location"] = web_search_context.get("region_location")
        if web_search_context.get("error"):
            metadata["web_search_error"] = web_search_context.get("error")
        return metadata

    def find_latest_user_message(
        self,
        request: ChatRequest,
    ) -> ChatMessage | None:
        for message in reversed(request.messages):
            if message.role == "user":
                return message
        return None
