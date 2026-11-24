from __future__ import annotations

from parley.core.scoring import (
    TurnMetrics,
    band_key_for_score,
    history_for_language,
    languages_with_history,
    load_history,
    save_session,
    score_transcript,
    score_turns,
    summarize,
)


def test_empty_turns_score_zero() -> None:
    result = score_turns([])
    assert result.score == 0
    assert result.band_key == "score_band_1"
    assert result.turns == 0


def test_spoken_session_produces_a_bounded_score() -> None:
    turns = [
        TurnMetrics(
            text="Hello my name is Ana and I live near the coast",
            words=10,
            speech_seconds=4.5,
            pause_ratio=0.1,
            words_per_minute=133.0,
            confidence=0.9,
        ),
        TurnMetrics(
            text="I work as a designer and I read every weekend",
            words=9,
            speech_seconds=4.0,
            pause_ratio=0.2,
            words_per_minute=135.0,
            confidence=0.8,
        ),
    ]
    result = score_turns(turns)
    assert 0 < result.score <= 100
    assert result.turns == 2
    assert result.words == 21
    assert result.band_key == band_key_for_score(result.score)


def test_band_thresholds_are_ordered() -> None:
    assert band_key_for_score(100) == "score_band_6"
    assert band_key_for_score(85) == "score_band_6"
    assert band_key_for_score(70) == "score_band_5"
    assert band_key_for_score(55) == "score_band_4"
    assert band_key_for_score(40) == "score_band_3"
    assert band_key_for_score(25) == "score_band_2"
    assert band_key_for_score(0) == "score_band_1"


def test_score_transcript_measures_words() -> None:
    result = score_transcript(["Hello there, how are you today", "I am fine thank you"])
    assert result.words == 11
    assert result.turns == 2
    assert result.score > 0


def test_history_round_trip_and_summary(tmp_path, monkeypatch) -> None:
    scores = tmp_path / "scores.json"
    monkeypatch.setenv("PARLEY_SCORES", str(scores))
    result = score_transcript(["This is a complete spoken sentence for the test"])
    save_session("en", "meeting_someone_new", "Meeting someone new", result)
    save_session("pt", "daily_routine", "Daily routine", result, mode="level_test")

    history = load_history()
    assert len(history) == 2
    assert history[0]["language"] == "en"
    assert history[1]["mode"] == "level_test"

    english = history_for_language(history, "en")
    assert len(english) == 1
    summary = summarize(english)
    assert summary["count"] == 1
    assert summary["average"] == result.score

    grouped = languages_with_history(history)
    assert set(grouped) == {"en", "pt"}
    assert grouped["pt"]["count"] == 1


def test_missing_history_file_is_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PARLEY_SCORES", str(tmp_path / "missing.json"))
    assert load_history() == []
