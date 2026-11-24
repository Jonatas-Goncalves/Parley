"""Conversation-only scoring for Voice Practice and the level test.

The numbers are a personal progress estimate inspired by speaking tasks such
as IELTS and TOEFL. They are intentionally simple, fully local and have no
official value. Only speaking and listening behaviour is scored: writing and
reading exercises never feed this history.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .config import DATA_DIR

SCORES_NAME = "scores.json"
LOCK = threading.RLock()

# Score range -> interface translation key. The bands are deliberately generic
# so they are never confused with an official CEFR or exam result.
BAND_KEYS = (
    (85, "score_band_6"),
    (70, "score_band_5"),
    (55, "score_band_4"),
    (40, "score_band_3"),
    (25, "score_band_2"),
    (0, "score_band_1"),
)


@dataclass(frozen=True)
class TurnMetrics:
    """One spoken turn, measured by the speech recogniser."""

    text: str = ""
    words: int = 0
    speech_seconds: float = 0.0
    pause_ratio: float = 0.0
    words_per_minute: float = 0.0
    confidence: float = 1.0


@dataclass
class SessionScore:
    score: int
    band_key: str
    turns: int
    words: int
    unique_ratio: float
    speaking_seconds: float
    words_per_minute: float
    pause_ratio: float
    confidence: float
    notes: list[str] = field(default_factory=list)


def scores_path() -> Path:
    configured = os.environ.get("PARLEY_SCORES", "").strip()
    if configured:
        return Path(configured).expanduser()
    return DATA_DIR / SCORES_NAME


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def band_key_for_score(score: int) -> str:
    for threshold, key in BAND_KEYS:
        if score >= threshold:
            return key
    return "score_band_1"


def _token_words(text: str) -> list[str]:
    cleaned = []
    for raw in (text or "").split():
        word = raw.strip(".,!?;:\"'()[]{}…¿¡。！？、").casefold()
        if word:
            cleaned.append(word)
    return cleaned


def score_turns(turns: list[TurnMetrics]) -> SessionScore:
    """Turn spoken turns into a 0-100 conversation score.

    The formula rewards continuous speech, vocabulary variety, reasonably
    complete turns and recogniser confidence. It is stable for short sessions
    (a few turns) and avoids punishing beginners for speaking slowly.
    """

    spoken = [turn for turn in turns if turn.words > 0 or turn.text.strip()]
    if not spoken:
        return SessionScore(
            score=0,
            band_key="score_band_1",
            turns=0,
            words=0,
            unique_ratio=0.0,
            speaking_seconds=0.0,
            words_per_minute=0.0,
            pause_ratio=0.0,
            confidence=0.0,
        )

    total_words = sum(max(turn.words, len(turn.text.split())) for turn in spoken)
    tokens: list[str] = []
    for turn in spoken:
        tokens.extend(_token_words(turn.text))
    unique_ratio = (len(set(tokens)) / len(tokens)) if tokens else 0.0

    speaking_seconds = sum(max(0.0, turn.speech_seconds) for turn in spoken)
    measured = [turn for turn in spoken if turn.words_per_minute > 0]
    words_per_minute = (
        sum(turn.words_per_minute for turn in measured) / len(measured)
        if measured
        else 0.0
    )
    pause_ratio = sum(max(0.0, min(1.0, turn.pause_ratio)) for turn in spoken) / len(spoken)
    confidence = sum(max(0.0, min(1.0, turn.confidence)) for turn in spoken) / len(spoken)

    average_words = total_words / len(spoken)

    # Fluency: natural conversational speed, tolerant of slower beginners.
    if words_per_minute <= 0:
        fluency = 55.0
    elif 90 <= words_per_minute <= 175:
        fluency = 100.0
    else:
        distance = 90 - words_per_minute if words_per_minute < 90 else words_per_minute - 175
        fluency = _clamp(100.0 - distance * 0.55)

    # Continuity: fewer long pauses, more connected speech.
    continuity = _clamp(105.0 - pause_ratio * 130.0)

    # Vocabulary variety. A natural conversation reuses common words, so a
    # ratio around 0.65 already deserves a high value.
    variety = _clamp(unique_ratio * 145.0)

    # Turn length: short greetings are fine, but longer answers show command.
    length = _clamp(average_words / 14.0 * 100.0)

    # Recogniser confidence is a rough proxy for clear pronunciation.
    clarity = _clamp(confidence * 115.0)

    score = round(
        fluency * 0.24
        + continuity * 0.20
        + variety * 0.22
        + length * 0.20
        + clarity * 0.14
    )
    score = int(_clamp(score))
    return SessionScore(
        score=score,
        band_key=band_key_for_score(score),
        turns=len(spoken),
        words=total_words,
        unique_ratio=round(unique_ratio, 3),
        speaking_seconds=round(speaking_seconds, 1),
        words_per_minute=round(words_per_minute, 1),
        pause_ratio=round(pause_ratio, 3),
        confidence=round(confidence, 3),
    )


def score_transcript(texts: list[str]) -> SessionScore:
    """Convenience wrapper used by tests and the guided level test."""

    turns = []
    for text in texts:
        words = len((text or "").split())
        turns.append(
            TurnMetrics(
                text=text or "",
                words=words,
                speech_seconds=max(1.0, words / 2.2),
                words_per_minute=(words / (max(1.0, words / 2.2) / 60.0)) if words else 0.0,
                confidence=0.8,
            )
        )
    return score_turns(turns)


def load_history() -> list[dict]:
    path = scores_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(raw, dict):
        items = raw.get("sessions", [])
    else:
        items = raw
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _write_history(history: list[dict]) -> None:
    path = scores_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(
        prefix=".scores-", suffix=".json", dir=str(path.parent)
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump({"version": 1, "sessions": history}, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            pass


def save_session(
    language: str,
    scenario_id: str,
    scenario_label: str,
    result: SessionScore,
    mode: str = "practice",
) -> dict:
    record = {
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "language": language,
        "scenario": scenario_id,
        "scenario_label": scenario_label,
        "mode": mode,
        **asdict(result),
    }
    with LOCK:
        history = load_history()
        history.append(record)
        # Keep the file small on long-lived installations.
        _write_history(history[-500:])
    return record


def history_for_language(history: list[dict] | None = None, language: str = "") -> list[dict]:
    items = load_history() if history is None else history
    if not language:
        return list(items)
    return [item for item in items if str(item.get("language") or "") == language]


def summarize(history: list[dict]) -> dict:
    scores = [int(item.get("score") or 0) for item in history]
    if not scores:
        return {
            "count": 0,
            "average": 0,
            "best": 0,
            "latest": 0,
            "band_key": band_key_for_score(0),
        }
    average = round(sum(scores) / len(scores))
    return {
        "count": len(scores),
        "average": average,
        "best": max(scores),
        "latest": scores[-1],
        "band_key": band_key_for_score(average),
    }


def languages_with_history(history: list[dict] | None = None) -> dict[str, dict]:
    items = load_history() if history is None else history
    grouped: dict[str, list[dict]] = {}
    for item in items:
        language = str(item.get("language") or "")
        if language:
            grouped.setdefault(language, []).append(item)
    return {language: summarize(records) for language, records in grouped.items()}


def level_score_from_average(average: int) -> int:
    """Map the historical average to a 1-6 personal level for the test page."""

    if average >= 85:
        return 6
    if average >= 70:
        return 5
    if average >= 55:
        return 4
    if average >= 40:
        return 3
    if average >= 25:
        return 2
    return 1


def weighted_average(history: list[dict]) -> int:
    """Recent sessions weigh a little more than old ones."""

    scores = [int(item.get("score") or 0) for item in history]
    if not scores:
        return 0
    total = 0.0
    weight_total = 0.0
    for index, score in enumerate(scores):
        weight = 1.0 + index / max(1, len(scores))
        total += score * weight
        weight_total += weight
    return round(total / weight_total) if weight_total else 0


def trend(history: list[dict]) -> float:
    """Return the score change between the first and the last session."""

    if len(history) < 2:
        return 0.0
    first = int(history[0].get("score") or 0)
    last = int(history[-1].get("score") or 0)
    return float(last - first)
