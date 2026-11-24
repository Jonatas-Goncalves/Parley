from __future__ import annotations

import pytest

from parley.core.config import SUPPORTED_LANGUAGES, language_name
from parley.core.parser import parse_response
from parley.core.prompts import build_system_prompt
from parley.core.scenarios import get_scenario


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_prompt_is_built_for_every_language(language: str) -> None:
    scenario = get_scenario("plan_a_trip")
    prompt = build_system_prompt(
        scenario,
        scenario.level,
        reply_language=language,
        target_language=language,
        native_language="pt",
    )
    assert scenario.persona in prompt
    assert language_name(language) in prompt
    assert "<MAIN>" in prompt and "<NOTE>" in prompt


def test_prompt_uses_the_scenario_persona() -> None:
    scenario = get_scenario("customer_complaint")
    prompt = build_system_prompt(scenario, scenario.level)
    assert "unhappy but reasonable customer" in prompt


def test_prompt_forbids_repeating_questions() -> None:
    scenario = get_scenario("daily_routine")
    prompt = build_system_prompt(
        scenario,
        scenario.level,
        asked_questions=["Where do you live?", "What do you do for work?"],
    )
    assert "CONVERSATION RULES" in prompt
    assert "Never repeat a question" in prompt
    assert "QUESTIONS ALREADY ASKED" in prompt
    assert "Where do you live?" in prompt
    assert "What do you do for work?" in prompt


def test_prompt_without_history_has_no_asked_block() -> None:
    scenario = get_scenario("daily_routine")
    prompt = build_system_prompt(scenario, scenario.level)
    assert "QUESTIONS ALREADY ASKED" not in prompt


def test_parser_separates_main_reply_and_note() -> None:
    raw = (
        "<MAIN>Buongiorno, come posso aiutarla?</MAIN>"
        "<NOTE>- **errore** -> correzione\n- **nota** -> spiegazione</NOTE>"
    )
    parsed = parse_response(raw, main_lang="it", note_lang="pt")
    assert parsed.english == "Buongiorno, come posso aiutarla?"
    assert "errore" in parsed.portuguese
    assert parsed.display


def test_parser_handles_plain_text() -> None:
    parsed = parse_response("Olá, tudo bem?", main_lang="pt", note_lang="en")
    assert parsed.english == "Olá, tudo bem?"
    assert parsed.portuguese == ""
