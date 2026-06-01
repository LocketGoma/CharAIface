from backend.app.services.chat_service import ChatService


def _auto_search_enabled_settings() -> dict[str, object]:
    return {
        "web_search_auto_enabled": True,
    }


def test_auto_web_search_triggers_for_current_external_requests() -> None:
    service = ChatService()
    settings = _auto_search_enabled_settings()

    trigger_examples = [
        "오늘 서울 날씨 알려줘",
        "오늘 서울 날씨 어때?",
        "엔비디아 주가 최신으로 알려줘",
        "이번 주 게임업계 뉴스 찾아줘",
        "OpenAI Codex 최신 변경점 검색해줘",
        "지금 환율 얼마야",
        "What is the latest OpenAI Codex update?",
    ]

    for text in trigger_examples:
        assert service._should_auto_web_search(text, settings), text


def test_auto_web_search_avoids_personal_or_explanatory_requests() -> None:
    service = ChatService()
    settings = _auto_search_enabled_settings()

    non_trigger_examples = [
        "오늘 기분이 안 좋다",
        "내일 할 일 정리해줘",
        "최근에 내가 말한 설정 정리해줘",
        "가격이 비싸게 느껴지는 이유를 설명해줘",
        "Explain why premium pricing feels expensive.",
    ]

    for text in non_trigger_examples:
        assert not service._should_auto_web_search(text, settings), text


def test_auto_web_search_respects_auto_setting() -> None:
    service = ChatService()

    assert not service._should_auto_web_search(
        "오늘 서울 날씨 알려줘",
        {"web_search_auto_enabled": False},
    )


def test_web_search_unit_preference_prompt_uses_metric_without_forced_conversion() -> None:
    service = ChatService()

    prompt = service._web_search_unit_preference_prompt(
        {"preferred_unit_system": "metric"},
        "ko",
    )

    assert "섭씨" in prompt
    assert "미터법" in prompt
    assert "임의 변환하지 마라" in prompt
    assert "숫자만 유지한 채 °C로 바꾸지 말고" in prompt


def test_web_search_unit_preference_prompt_uses_imperial_without_forced_conversion() -> None:
    service = ChatService()

    prompt = service._web_search_unit_preference_prompt(
        {"preferred_unit_system": "imperial"},
        "en",
    )

    assert "Fahrenheit" in prompt
    assert "imperial" in prompt
    assert "do not force a conversion" in prompt
    assert "do not keep the number and only relabel" in prompt


def test_weather_search_query_adds_metric_unit_hint() -> None:
    service = ChatService()
    config = type("Config", (), {"country_code": "KR", "location": "Republic of Korea"})()

    query = service._normalize_web_search_query_for_region(
        query="이번주 서울 날씨",
        original_text="이번주 서울 날씨",
        config=config,
        request=None,  # type: ignore[arg-type]
        settings={"preferred_unit_system": "metric"},
    )

    assert "대한민국" in query
    assert "섭씨 celsius" in query
