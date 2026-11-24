"""Local training history stored as JSON Lines.

Each completed conversation becomes one JSON object. The file is append-only,
which keeps writes cheap and makes it easy to export or inspect the data.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, datetime

from .config import DATA_DIR
from .i18n import t

HISTORY_DIR = DATA_DIR / "history"
SESSIONS_FILE = HISTORY_DIR / "sessions.jsonl"
LOCK = threading.RLock()

CEFR_ORDER = ("A1", "A2", "B1", "B2", "C1", "C2")
DEFAULT_LEVEL = "A2"


def _ensure() -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def _normalize_cefr(value: str | None, fallback: str = DEFAULT_LEVEL) -> str:
    candidate = (value or "").strip().upper()
    return candidate if candidate in CEFR_ORDER else fallback


def _normalize_target(target: str | None) -> str:
    return (target or "").strip().lower()


def save_session(record: dict) -> dict:
    """Append a session record and return the stored object."""

    stored = dict(record)
    stored.setdefault("id", uuid.uuid4().hex)
    stored.setdefault("timestamp", datetime.now(UTC).isoformat())
    stored["cefr"] = _normalize_cefr(str(stored.get("cefr") or ""))
    try:
        stored["score"] = max(0, min(100, int(float(stored.get("score") or 0))))
    except (TypeError, ValueError):
        stored["score"] = 0
    stored["target"] = _normalize_target(str(stored.get("target") or ""))
    stored["level"] = _normalize_cefr(str(stored.get("level") or ""), "B1")

    _ensure()
    line = json.dumps(stored, ensure_ascii=False)
    with LOCK, SESSIONS_FILE.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return stored


def load_sessions(
    target: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    wanted = _normalize_target(target)
    sessions: list[dict] = []
    if not SESSIONS_FILE.exists():
        return sessions
    with LOCK:
        try:
            lines = SESSIONS_FILE.read_text(encoding="utf-8").splitlines()
        except OSError:
            return sessions
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        if wanted and _normalize_target(str(record.get("target") or "")) != wanted:
            continue
        sessions.append(record)
    sessions.sort(key=lambda item: str(item.get("timestamp") or ""))
    if limit is not None and limit > 0:
        sessions = sessions[-limit:]
    return sessions


def stats(target: str | None = None) -> dict[str, object]:
    sessions = load_sessions(target)
    scores = [int(item.get("score") or 0) for item in sessions]
    average = round(sum(scores) / len(scores), 1) if scores else 0.0
    return {
        "count": len(sessions),
        "average": average,
        "best": max(scores) if scores else 0,
        "worst": min(scores) if scores else 0,
        "last_cefr": _normalize_cefr(
            str(sessions[-1].get("cefr") or "") if sessions else ""
        ),
    }


def suggest_level(target: str | None, current: str | None = None) -> str:
    """Pick the next training level from the learner's recent scores.

    - fewer than two sessions: keep the current level, or start at A2
    - average >= 85 and no recent score below 70: move one CEFR step up
    - average < 50: move one CEFR step down
    - otherwise: keep the most recent level
    """

    sessions = load_sessions(target, limit=10)
    fallback = _normalize_cefr(current, DEFAULT_LEVEL)
    if len(sessions) < 2:
        return fallback

    scores = [int(item.get("score") or 0) for item in sessions]
    average = sum(scores) / len(scores)
    recent = scores[-5:]
    base = _normalize_cefr(str(sessions[-1].get("cefr") or ""), fallback)
    index = CEFR_ORDER.index(base)

    if average >= 85 and min(recent) >= 70:
        index = min(len(CEFR_ORDER) - 1, index + 1)
    elif average < 50:
        index = max(0, index - 1)
    return CEFR_ORDER[index]


def summary_markdown(target: str | None = None, lang: str = "en") -> str:
    sessions = load_sessions(target)
    info = stats(target)
    if not sessions:
        return f"### {t('history_title', lang)}\n\n{t('no_sessions', lang)}"

    lines = [
        f"### {t('history_title', lang)}",
        "",
        (
            f"**{t('sessions', lang)}:** {info['count']} · "
            f"**{t('average_score', lang)}:** {info['average']:.0f}/100"
        ),
        "",
        "| Date | Language | Level | CEFR | Score |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for item in reversed(sessions[-15:]):
        stamp = str(item.get("timestamp") or "")[:10]
        language = str(item.get("target") or "").upper()
        level = str(item.get("level") or "")
        cefr = _normalize_cefr(str(item.get("cefr") or ""))
        score = int(item.get("score") or 0)
        lines.append(f"| {stamp} | {language} | {level} | {cefr} | {score} |")
    return "\n".join(lines)


def table_rows(target: str | None = None) -> list[list[str]]:
    rows: list[list[str]] = []
    for item in reversed(load_sessions(target)):
        rows.append(
            [
                str(item.get("timestamp") or "")[:10],
                str(item.get("target") or "").upper(),
                str(item.get("level") or ""),
                _normalize_cefr(str(item.get("cefr") or "")),
                str(int(item.get("score") or 0)),
            ]
        )
    return rows
