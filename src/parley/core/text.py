"""Text cleanup helpers shared by exercise generation and speech synthesis.

Language models sometimes return word runs joined by hyphens, duplicated CJK
punctuation or a whole paragraph when a single phrase was requested. These
helpers keep the visible text and the spoken text identical and readable.
"""

from __future__ import annotations

import re

CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")
TERMINAL = (".", "!", "?", "…", "。", "！", "？", ")", "]", '"', "'", "”", "’")
HYPHEN_RUN = re.compile(r"(?<!\S)([^\s\-]+(?:-[^\s\-]+){2,})(?!\S)")
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…])\s+|(?<=[。！？])\s*")
MIXED_CJK_TAIL = re.compile(r"(?<=[。！？])[、，,.;:!?]+")
TERMINAL_RUN = re.compile(r"([。！？!?])[。！？、，,.;:!?]+")
SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([,.!?;:。！？、，])")
SPACE_AFTER_CJK_TERMINAL = re.compile(r"(?<=[。！？])\s+")


def has_cjk(text: str) -> bool:
    return bool(CJK_RE.search(text or ""))


def expand_hyphen_runs(text: str) -> str:
    """Turn ``word-word-word`` into ``word word word``.

    A real compound such as ``well-known`` is left alone. Runs of three or more
    joined words are almost always a model formatting artefact and read aloud as
    an unnatural pause, so they are expanded.
    """

    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        parts = token.split("-")
        if len(parts) < 3 or any(not part for part in parts):
            return token
        return " ".join(parts)

    return HYPHEN_RUN.sub(replace, text or "")


def clean_cjk_punctuation(text: str) -> str:
    """Remove duplicated or mixed punctuation produced by some models."""

    value = text or ""
    if not has_cjk(value):
        return SPACE_BEFORE_PUNCTUATION.sub(r"\1", value)
    value = MIXED_CJK_TAIL.sub("", value)
    value = TERMINAL_RUN.sub(r"\1", value)
    value = re.sub(r"([、，,])(?:[、，,]+)", r"\1", value)
    value = SPACE_AFTER_CJK_TERMINAL.sub("", value)
    return SPACE_BEFORE_PUNCTUATION.sub(r"\1", value)


def terminal_for(text: str) -> str:
    return "。" if has_cjk(text) else "."


def ensure_terminal(text: str) -> str:
    value = (text or "").strip().rstrip(",;:、，")
    if not value:
        return ""
    if value.endswith(TERMINAL):
        return value
    return value + terminal_for(value)


def split_sentences(text: str) -> list[str]:
    return [
        part.strip()
        for part in SENTENCE_BOUNDARY.split(text or "")
        if part and part.strip()
    ]


def join_sentences(sentences: list[str], sample: str = "") -> str:
    joiner = "" if has_cjk(sample or (sentences[0] if sentences else "")) else " "
    return joiner.join(sentences)


def limit_sentences(text: str, count: int) -> str:
    """Keep at most ``count`` sentences from model output."""

    if count <= 0:
        return ""
    sentences = split_sentences(text)
    if len(sentences) <= count:
        return text
    kept = [ensure_terminal(sentence) for sentence in sentences[:count]]
    return join_sentences(kept, text)


def shorten_to_words(text: str, max_words: int | None) -> str:
    """Shorten a single phrase for pronunciation practice.

    The limit counts whitespace-separated words for alphabetic languages and
    characters for CJK, where words are not separated by spaces.
    """

    if not max_words or not text:
        return text

    if has_cjk(text):
        limit = max_words * 2
        chars = re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)
        if len(chars) <= limit:
            return text
        sentences = split_sentences(text)
        chosen = ""
        for sentence in sentences:
            candidate = join_sentences([chosen, sentence], text) if chosen else sentence
            if len(re.sub(r"[\s\W_]+", "", candidate, flags=re.UNICODE)) > limit:
                break
            chosen = candidate
        return ensure_terminal(chosen) if chosen else text

    parts = text.split()
    if len(parts) <= max_words:
        return text

    clauses = re.split(r"(?<=[,;:])\s+", text)
    chosen_parts: list[str] = []
    for clause in clauses:
        trial = " ".join([*chosen_parts, clause])
        if len(trial.split()) > max_words and chosen_parts:
            break
        chosen_parts.append(clause)
    result = " ".join(chosen_parts).strip()
    if len(result.split()) > max_words:
        result = " ".join(result.split()[:max_words])
    return ensure_terminal(result)


def extract_questions(text: str) -> list[str]:
    return [
        sentence
        for sentence in split_sentences(text)
        if sentence.endswith(("?", "？"))
    ]
