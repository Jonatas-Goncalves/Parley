from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .config import EXPORT_DIR, ensure_directories


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def export_vocabulary(entries: list[dict]) -> Path | None:
    if not entries:
        return None
    ensure_directories()
    path = EXPORT_DIR / f"vocabulario-{_timestamp()}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["Portugues", "Ingles", "Explicacao", "Exemplo"])
        for entry in entries:
            writer.writerow(
                [
                    entry.get("pt", ""),
                    entry.get("en", ""),
                    entry.get("explanation", ""),
                    entry.get("example", ""),
                ]
            )
    return path


def export_transcript(
    messages: list[dict], scenario_label: str, level: str
) -> Path | None:
    if not messages:
        return None
    ensure_directories()
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Transcript - Language Tutor",
        "",
        f"- Scenario: {scenario_label}",
        f"- Level: {level}",
        f"- Generated on: {generated}",
        "",
        "---",
        "",
    ]
    for message in messages:
        role = message.get("role", "assistant")
        title = "Learner" if role == "user" else "Tutor"
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        lines.extend([f"## {title}", "", content, ""])
    path = EXPORT_DIR / f"transcript-{_timestamp()}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
