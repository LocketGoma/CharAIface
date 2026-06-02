import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from backend.app.services.web_search_context import WebSearchContextBuilder


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "resources" / "data" / "search_context" / "web_search_context_cases.json"


def _web_search_context() -> WebSearchContextBuilder:
    return WebSearchContextBuilder(PROJECT_ROOT)


def _fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_auto_web_search_triggers_for_current_external_requests() -> None:
    context = _web_search_context()
    cases = _fixture()

    for text in cases["auto_search_trigger_examples"]:
        assert context.should_auto_search(text, cases["auto_search_enabled_settings"]), text


def test_auto_web_search_avoids_personal_or_explanatory_requests() -> None:
    context = _web_search_context()
    cases = _fixture()

    for text in cases["auto_search_non_trigger_examples"]:
        assert not context.should_auto_search(text, cases["auto_search_enabled_settings"]), text


def test_auto_web_search_respects_auto_setting() -> None:
    context = _web_search_context()
    cases = _fixture()

    assert not context.should_auto_search(
        cases["auto_search_disabled_example"],
        cases["auto_search_disabled_settings"],
    )


def test_web_search_unit_preference_prompts_include_required_terms() -> None:
    context = _web_search_context()
    cases = _fixture()

    for case in cases["unit_prompt_cases"]:
        prompt = context.unit_preference_prompt(case["settings"], case["language"])
        for expected_term in case["expected_terms"]:
            assert expected_term in prompt


def test_weather_search_query_adds_unit_hints() -> None:
    context = _web_search_context()
    cases = _fixture()

    for case in cases["weather_query_cases"]:
        query = context.normalize_query_for_region(
            query=case["query"],
            original_text=case["original_text"],
            config=SimpleNamespace(**case["config"]),
            settings=case["settings"],
        )
        for expected_term in case["expected_terms"]:
            assert expected_term in query
