from __future__ import annotations

from parley.core.text import (
    clean_cjk_punctuation,
    ensure_terminal,
    expand_hyphen_runs,
    extract_questions,
    limit_sentences,
    shorten_to_words,
    split_sentences,
)


def test_hyphen_runs_are_expanded() -> None:
    text = "I'm-ready-to-buy-a-new-shirt."
    assert expand_hyphen_runs(text) == "I'm ready to buy a new shirt."


def test_real_compounds_survive() -> None:
    text = "A well-known state-of-the-art example."
    assert expand_hyphen_runs(text) == "A well-known state of the art example."


def test_clean_cjk_punctuation_removes_mixed_marks() -> None:
    text = "こんにちは。、. 元気ですか？、。"
    assert clean_cjk_punctuation(text) == "こんにちは。元気ですか？"


def test_terminal_punctuation_matches_the_script() -> None:
    assert ensure_terminal("Hello there") == "Hello there."
    assert ensure_terminal("こんにちは") == "こんにちは。"
    assert ensure_terminal("Really?") == "Really?"


def test_sentence_helpers_keep_cjk_joined() -> None:
    sentences = split_sentences("こんにちは。元気ですか？")
    assert sentences == ["こんにちは。", "元気ですか？"]
    assert limit_sentences("こんにちは。元気ですか？", 1) == "こんにちは。"


def test_limit_sentences_keeps_the_requested_count() -> None:
    text = "First sentence. Second sentence. Third sentence."
    assert limit_sentences(text, 2) == "First sentence. Second sentence."


def test_shorten_to_words_limits_english() -> None:
    text = (
        "Every morning I wake up early and walk to the small bakery near my "
        "house to buy fresh bread for breakfast."
    )
    result = shorten_to_words(text, 12)
    assert len(result.split()) <= 12
    assert result.endswith(".")


def test_shorten_to_words_limits_cjk_characters() -> None:
    text = "毎朝早く起きて、近くの小さなパン屋まで歩いて、朝ごはんのパンを買います。"
    result = shorten_to_words(text, 10)
    assert result.endswith("。")


def test_extract_questions_finds_only_questions() -> None:
    text = "Hello there. How are you? I am fine. Where do you live?"
    assert extract_questions(text) == ["How are you?", "Where do you live?"]
