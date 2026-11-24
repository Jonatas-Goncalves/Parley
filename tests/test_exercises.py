from __future__ import annotations

from parley.core.exercises import (
    _normalize_generated_text,
    check_cloze,
    compare_reading,
    generate_text,
    make_cloze,
    normalize_word,
    words,
)
from parley.core.scenarios import get_scenario


def test_normalize_word_ignores_case_and_accents() -> None:
    assert normalize_word("Café") == "cafe"
    assert normalize_word("PERCHÉ") == "perche"


def test_words_keeps_apostrophes() -> None:
    assert words("L'uomo non c'è") == ["L'uomo", "non", "c'è"]


def test_reading_marks_missing_words() -> None:
    results, accuracy = compare_reading("Il gatto dorme sul tavolo", "Il gatto dorme")
    assert [result.ok for result in results] == [True, True, True, False, False]
    assert accuracy == 60.0


def test_reading_is_accent_insensitive() -> None:
    _results, accuracy = compare_reading("perché", "perche")
    assert accuracy == 100.0


def test_cloze_creates_the_requested_number_of_blanks() -> None:
    text = "She goes to the market every morning and buys fresh bread for dinner."
    masked, answers = make_cloze(text, count=4)
    assert masked.count("____") == 4
    assert len(answers) == 4
    for answer in answers:
        assert answer in text


def test_cloze_check_is_accent_and_case_insensitive() -> None:
    assert check_cloze(["Café", "perché"], ["cafe", "PERCHE"]) == [True, True]
    assert check_cloze(["casa"], [""]) == [False]


def test_generated_text_gets_terminal_punctuation() -> None:
    text = _normalize_generated_text(
        "Good morning, how are you\nI am fine, thank you"
    )
    assert text == "Good morning, how are you. I am fine, thank you."


def test_generated_text_removes_list_markers() -> None:
    text = _normalize_generated_text("- First sentence!\n- Second sentence?")
    assert text == "First sentence! Second sentence?"


def test_generate_text_requests_punctuation(monkeypatch) -> None:
    import parley.core.exercises as exercises_module

    captured: dict[str, object] = {}

    def fake_complete(*args, **_kwargs):
        captured["messages"] = args[-1]
        return "Hello there, how are you"

    monkeypatch.setattr(exercises_module, "complete_chat", fake_complete)
    text = generate_text(
        get_scenario("daily_routine"), "en", "B1", 1, "ollama", "", "test-model"
    )
    assert text == "Hello there, how are you."
    messages = captured["messages"]
    prompt = messages[-1]["content"]
    assert "Punctuation is essential" in prompt
    assert "commas" in prompt


def test_generate_text_keeps_one_sentence_for_pronunciation(monkeypatch) -> None:
    import parley.core.exercises as exercises_module

    monkeypatch.setattr(
        exercises_module,
        "complete_chat",
        lambda *_args, **_kwargs: "This is the first sentence. This is the second one!",
    )
    text = generate_text(
        get_scenario("daily_routine"), "en", "B1", 1, "ollama", "", "test-model"
    )
    assert text == "This is the first sentence."


def test_generate_text_shortens_a_long_phrase(monkeypatch) -> None:
    import parley.core.exercises as exercises_module

    monkeypatch.setattr(
        exercises_module,
        "complete_chat",
        lambda *_args, **_kwargs: (
            "Every single morning I wake up very early and walk slowly to the "
            "small bakery around the corner to buy fresh bread for my family."
        ),
    )
    text = generate_text(
        get_scenario("daily_routine"),
        "en",
        "B1",
        1,
        "ollama",
        "",
        "test-model",
        max_words=12,
    )
    assert len(text.split()) <= 12
    assert text.endswith(".")


def test_generate_text_expands_hyphen_runs(monkeypatch) -> None:
    import parley.core.exercises as exercises_module

    monkeypatch.setattr(
        exercises_module,
        "complete_chat",
        lambda *_args, **_kwargs: "I'm-ready-to-buy-a-new-shirt.",
    )
    text = generate_text(
        get_scenario("daily_routine"), "en", "B1", 1, "ollama", "", "test-model"
    )
    assert "-" not in text
    assert text == "I'm ready to buy a new shirt."
