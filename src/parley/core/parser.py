from __future__ import annotations

import re
from dataclasses import dataclass

from .config import language_label, normalize_language_code
from .language import detect_language
from .prompts import EN_NOTE_HEADER, PT_HEADER

TAG_NOISE = re.compile(r"<\s*/?\s*(?:EN|PT|MAIN|NOTE)\s*>", re.IGNORECASE)
PARTIAL_TAG = re.compile(r"<[^>]*$")
ARROW = re.compile(r"\s*(?:->|=>|→)\s*")
PT_HEADING = re.compile(r"(?i)(?:💡\s*)?\**\s*explica(?:ç|c)[aã]o\s*&\s*contexto")
EN_NOTE_HEADING = re.compile(r"(?i)(?:📝\s*)?\**\s*english\s+note\b")
ANY_NOTE_HEADING = re.compile(
    r"(?i)(?:💡|📝)?\s*\**\s*(?:"
    r"explica(?:ç|c)[aã]o\s*&\s*contexto|english\s+note|"
    r"vocabulary\s+note|nota|note|メモ|提示"
    r")"
)
KNOWN_BULLET_KEYS = (
    "explicação",
    "explicacao",
    "explicación",
    "explicacion",
    "exemplo",
    "ejemplo",
    "correção",
    "correcao",
    "corrección",
    "correccion",
    "dica",
    "contexto",
    "uso",
    "variação",
    "variacao",
    "pronúncia",
    "pronuncia",
    "explanation",
    "example",
    "speech",
    "fala",
    "説明",
    "例",
    "설명",
    "예",
    "解释",
    "例句",
)


@dataclass
class ParsedReply:
    english: str
    portuguese: str
    display: str
    missing_pt: bool = False
    had_tags: bool = False


def _clean_block(text: str) -> str:
    text = TAG_NOISE.sub("", text or "")
    text = text.replace("\r\n", "\n").strip()
    return text


def format_note_block(
    note_text: str, note_lang: str = "pt", note_label: str | None = None
) -> str:
    note_text = _clean_block(note_text)
    if not note_text:
        return ""
    normalized = normalize_language_code(note_lang) or "pt"
    simplified = note_text.lstrip("*# ").casefold()
    if normalized == "en":
        if simplified.startswith(("📝", "english note", "note")):
            return note_text
        return f"{EN_NOTE_HEADER}\n\n{note_text}"
    if normalized == "pt":
        if simplified.startswith(("💡", "📝", "explicação", "explicacao", "nota")):
            return note_text
        return f"{PT_HEADER}\n\n{note_text}"
    if simplified.startswith(("📝", "vocabulary note", "note", "nota")):
        return note_text
    label = note_label or language_label(normalized)
    return f"📝 **Vocabulary note ({label}):**\n\n{note_text}"


def format_pt_block(pt_text: str) -> str:
    return format_note_block(pt_text, "pt")


def parse_response(
    raw: str,
    always_explain: bool = True,
    main_lang: str = "en",
    note_lang: str | None = None,
) -> ParsedReply:
    raw = (raw or "").strip()
    note_lang = normalize_language_code(note_lang) or (
        "en" if normalize_language_code(main_lang) == "pt" else "pt"
    )
    if not raw:
        return ParsedReply("", "", "", missing_pt=always_explain)

    main_match = re.search(
        r"<\s*(?:EN|MAIN)\s*>(.*?)"
        r"(?=<\s*(?:PT|NOTE)\s*>|<\s*/\s*(?:EN|MAIN)\s*>|$)",
        raw,
        re.IGNORECASE | re.DOTALL,
    )
    note_match = re.search(
        r"<\s*(?:PT|NOTE)\s*>(.*?)"
        r"(?=<\s*/\s*(?:PT|NOTE)\s*>|$)",
        raw,
        re.IGNORECASE | re.DOTALL,
    )
    had_tags = bool(main_match or note_match)

    english = _clean_block(main_match.group(1)) if main_match else ""
    note = _clean_block(note_match.group(1)) if note_match else ""

    if not main_match and not note_match:
        heading = ANY_NOTE_HEADING.search(raw)
        if heading and heading.start() > 0:
            english = _clean_block(raw[: heading.start()])
            note = _clean_block(raw[heading.start() :])
        elif heading:
            note = _clean_block(raw[heading.start() :])
        else:
            english = _clean_block(raw)
    else:
        if not note:
            outside_main = re.sub(
                r"<\s*(?:EN|MAIN)\s*>.*?<\s*/\s*(?:EN|MAIN)\s*>",
                "",
                raw,
                flags=re.IGNORECASE | re.DOTALL,
            )
            outside_heading = ANY_NOTE_HEADING.search(outside_main)
            if outside_heading:
                candidate = re.split(
                    r"<\s*(?:EN|MAIN)\s*>",
                    outside_main[outside_heading.start() :],
                    flags=re.IGNORECASE,
                )[0]
                note = _clean_block(candidate)

        if english:
            inline_heading = ANY_NOTE_HEADING.search(english)
            if inline_heading:
                if not note:
                    note = english[inline_heading.start() :].strip()
                if inline_heading.start() > 0:
                    english = english[: inline_heading.start()].strip()
                else:
                    english = ""

    if not english and note:
        english = ""

    if not always_explain:
        note = ""

    display_parts = []
    if english:
        display_parts.append(english)
    if note:
        display_parts.append(format_note_block(note, note_lang))

    missing_pt = bool(always_explain and english and not note)
    return ParsedReply(
        english=english,
        portuguese=note,
        display="\n\n".join(display_parts),
        missing_pt=missing_pt,
        had_tags=had_tags,
    )


def render_stream(raw: str) -> str:
    text = raw or ""
    note_start = re.search(r"<\s*(?:PT|NOTE)\s*>", text, re.IGNORECASE)
    if note_start:
        text = text[: note_start.start()]
    else:
        fallback_heading = re.search(r"(?:💡|📝)", text)
        if fallback_heading:
            text = text[: fallback_heading.start()]
    text = re.sub(r"<\s*/?\s*(?:EN|MAIN)\s*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*/?\s*(?:PT|NOTE)\s*>", "", text, flags=re.IGNORECASE)
    text = PARTIAL_TAG.sub("", text)
    return text.strip()


def _strip_markdown(value: str) -> str:
    value = value.replace("**", "").replace("__", "").replace("`", "")
    value = value.strip(" \t-*•:;,.>\"'“”‘’")
    return re.sub(r"\s+", " ", value).strip()


def _is_template_placeholder(value: str) -> bool:
    lowered = value.casefold()
    return any(
        marker in lowered
        for marker in (
            "palavra em português",
            "palavra em portugues",
            "tradução em en",
            "traducao em en",
            "english equivalent",
            "explicação didática",
            "explicacao didatica",
            "source expression",
            "native meaning",
            "target equivalent",
            "meaning in the note language",
            "translation in the note language",
            "portuguese meaning",
            "english meaning",
        )
    )


def _extract_line_value(pt_text: str, label: str) -> str:
    match = re.search(
        rf"(?im)^\s*(?:[-*•]\s*)?\**{label}\**:\s*(.+?)"
        r"(?=\n\s*(?:[-*•]\s*)?\**\S|\Z)",
        pt_text,
        re.DOTALL,
    )
    if not match:
        return ""
    value = match.group(1)
    if label.casefold().startswith(
        ("exemplo", "example", "ejemplo", "例", "예", "例句")
    ):
        quoted = re.findall(r"[\"“](.+?)[\"”]", value)
        if len(quoted) >= 2:
            return f'"{quoted[0].strip()}" - "{quoted[1].strip()}"'[:500]
    value = re.sub(r"\*\*|__|`", "", value)
    value = value.strip(" \t-*•:;,.>")
    return re.sub(r"\s+", " ", value)[:500]


def _extract_any(pt_text: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        value = _extract_line_value(pt_text, label)
        if value:
            return value
    return ""


def parse_vocabulary(
    pt_text: str,
    source_lang: str = "pt",
    target_lang: str | None = None,
    native_lang: str | None = None,
) -> list[dict]:
    if not pt_text:
        return []

    explanation = _extract_any(
        pt_text,
        (
            "Explicação",
            "Explicacao",
            "Explicación",
            "Explicacion",
            "Explanation",
            "説明",
            "설명",
            "解释",
        ),
    )
    example = _extract_any(
        pt_text, ("Exemplo", "Ejemplo", "Example", "例", "예", "例句")
    )

    entries: list[dict] = []
    for raw_line in pt_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^[-*•]\s*", "", line).strip()
        if not line:
            continue

        plain = re.sub(r"\*\*|__|`", "", line).strip()
        plain = plain.lstrip("*•- ").strip()
        lowered = plain.casefold()
        if lowered.startswith(KNOWN_BULLET_KEYS):
            continue

        left = ""
        right = ""
        if ARROW.search(plain):
            left, right = ARROW.split(plain, maxsplit=1)
        elif ":" in plain:
            candidate_left, candidate_right = plain.split(":", 1)
            if (
                len(candidate_left.strip()) <= 45
                and len(candidate_right.strip()) <= 120
                and not candidate_left.casefold().startswith(KNOWN_BULLET_KEYS)
            ):
                left, right = candidate_left, candidate_right

        left = _strip_markdown(left)
        right = _strip_markdown(right)
        if not left or not right:
            continue
        if (
            source_lang == "en"
            and detect_language(left) == "en"
            and detect_language(right) == "pt"
        ):
            left, right = right, left
        if len(left) > 80 or len(right) > 140:
            continue
        if _is_template_placeholder(left) or _is_template_placeholder(right):
            continue
        if left.casefold() == right.casefold():
            continue

        entries.append(
            {
                "pt": left,
                "en": right,
                "explanation": explanation,
                "example": example,
            }
        )
    return entries


def merge_vocabulary(existing: list[dict], new_entries: list[dict]) -> list[dict]:
    merged = list(existing)
    index = {
        (
            item.get("pt", "").casefold().strip(),
            item.get("en", "").casefold().strip(),
        ): item
        for item in merged
    }
    for entry in new_entries:
        key = (
            entry.get("pt", "").casefold().strip(),
            entry.get("en", "").casefold().strip(),
        )
        if not all(key):
            continue
        if key in index:
            current = index[key]
            if not current.get("explanation") and entry.get("explanation"):
                current["explanation"] = entry["explanation"]
            if not current.get("example") and entry.get("example"):
                current["example"] = entry["example"]
            continue
        merged.append(entry)
        index[key] = entry
    return merged


def vocabulary_rows(entries: list[dict]) -> list[list[str]]:
    return [
        [
            entry.get("pt", ""),
            entry.get("en", ""),
            entry.get("explanation", ""),
            entry.get("example", ""),
        ]
        for entry in entries
    ]
