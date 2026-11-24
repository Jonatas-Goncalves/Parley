"""Small exercise helpers: pronunciation scoring and cloze texts."""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass

from .config import SETTINGS, language_name
from .llm import LLMError, complete_chat
from .scenarios import Scenario
from .text import (
    clean_cjk_punctuation,
    ensure_terminal,
    expand_hyphen_runs,
    limit_sentences,
    shorten_to_words,
)

WORD_RE = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*", re.UNICODE)

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be",
    "been", "am", "do", "does", "did", "have", "has", "had", "to", "of", "in",
    "on", "at", "for", "with", "from", "by", "as", "that", "this", "these",
    "those", "it", "its", "i", "you", "he", "she", "we", "they", "my", "your",
    "our", "their", "me", "him", "her", "us", "them", "not", "no", "yes",
    "o", "os", "um", "uma", "uns", "umas", "e", "ou", "mas", "é",
    "são", "foi", "ser", "estar", "está", "estou", "tem", "tenho", "de", "da", "dos", "das", "em", "na", "nos", "nas", "para", "por", "com",
    "que", "isso", "este", "esta", "eu", "você", "ele", "ela", "nós", "eles",
    "elas", "meu", "minha", "seu", "sua", "não", "sim", "el", "la", "los",
    "las", "un", "una", "unos", "unas", "y", "pero", "es", "son", "fue",
    "tiene", "tengo", "del", "al", "en", "con", "esto", "yo", "tú", "él", "ella",
    "le", "les", "des", "du", "une", "et", "mais", "est", "sont",
    "être", "avoir", "ai", "avons", "avez", "ont", "dans", "sur", "avec",
    "pour", "par", "pas", "oui", "je", "tu", "il", "elle", "nous", "vous",
    "ils", "elles", "mon", "ma", "mes", "ton", "ta", "tes", "sa",
    "ses", "ce", "cette", "ces", "qui",
    "lo", "gli", "uno", "ed",
    "è", "sono", "era", "essere", "avere", "ho", "hai", "ha", "abbiamo",
    "avete", "hanno", "di", "della", "dei", "delle", "nel",
    "nella", "su", "per", "che", "questo", "questa", "io", "lui", "lei", "noi", "voi", "loro", "mio", "mia", "tuo", "tua", "suo",
    "non", "sì",
}


def normalize_word(value: str) -> str:
    text = unicodedata.normalize("NFD", value.casefold())
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"[^\w]", "", text)


def words(text: str) -> list[str]:
    return WORD_RE.findall(text or "")


@dataclass
class WordResult:
    word: str
    heard: str
    ok: bool


def compare_reading(expected: str, heard: str) -> tuple[list[WordResult], float]:
    expected_words = words(expected)
    heard_words = words(heard)
    expected_keys = [normalize_word(word) for word in expected_words]
    heard_keys = [normalize_word(word) for word in heard_words]

    matcher = difflib.SequenceMatcher(a=expected_keys, b=heard_keys, autojunk=False)
    matched: dict[int, str] = {}
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            matched[block.a + offset] = heard_words[block.b + offset]

    results = [
        WordResult(
            word=expected_words[index],
            heard=matched.get(index, ""),
            ok=index in matched,
        )
        for index in range(len(expected_words))
    ]
    accuracy = (100.0 * len(matched) / len(expected_words)) if expected_words else 0.0
    return results, accuracy


# -- text generation -----------------------------------------------------
def generate_text(
    scenario: Scenario,
    target: str,
    level: str,
    sentence_count: int,
    backend: str,
    base_url: str,
    model: str,
    max_words: int | None = None,
) -> str:
    language = language_name(target)
    if sentence_count == 1:
        length_rule = (
            "Write exactly ONE short sentence with 8 to 16 words. "
            "Do not write a paragraph, a second sentence or a list."
        )
    else:
        length_rule = (
            f"Write exactly {sentence_count} short sentences. "
            "Keep each sentence under 18 words."
        )
    prompt = (
        f"{length_rule} Write it in {language} for a {level} learner "
        f"practicing this situation: {scenario.label}. Use natural, spoken "
        "language and everyday vocabulary. Punctuation is essential: use "
        "commas, periods, question marks and exclamation marks so the text "
        "can be read aloud with natural pauses. Every sentence must start "
        "with a capital letter and end with punctuation. Never join words "
        "with hyphens; use spaces between words. Separate the sentences with "
        "a single space. "
        "Return only the sentences, no title, no list, no translation and no "
        "quotation marks."
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You write short language-learning material. "
                "Always use correct punctuation and capitalization. "
                "Never connect words with hyphens. "
                "Never add explanations, headings or notes."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    try:
        text = complete_chat(
            SETTINGS,
            backend,
            base_url,
            model,
            messages,
        )
    except LLMError as exc:
        raise RuntimeError(str(exc)) from exc
    text = _normalize_generated_text(text)
    text = limit_sentences(text, sentence_count)
    return shorten_to_words(text, max_words)


def _normalize_generated_text(text: str) -> str:
    """Clean model output and make sure every line ends with punctuation."""

    value = expand_hyphen_runs(text or "")
    value = re.sub(
        r"^\s*(?:#{1,6}|[-*•]|\d+[.)])\s+", "", value, flags=re.MULTILINE
    )
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ""

    fixed = [ensure_terminal(line) for line in lines]
    return clean_cjk_punctuation(" ".join(fixed))


def make_cloze(text: str, count: int = 6) -> tuple[str, list[str]]:
    matches = list(WORD_RE.finditer(text or ""))
    candidates = []
    for index, match in enumerate(matches):
        word = match.group(0)
        if len(word) < 4 or normalize_word(word) in STOPWORDS:
            continue
        candidates.append(index)
    if not candidates:
        return text, []

    step = max(1, len(candidates) // count)
    chosen = candidates[::step][:count]
    chosen_set = set(chosen)
    output = []
    last = 0
    answers: list[str] = []
    for index, match in enumerate(matches):
        if index not in chosen_set:
            continue
        output.append(text[last : match.start()])
        output.append("____")
        answers.append(match.group(0))
        last = match.end()
    output.append(text[last:])
    return "".join(output), answers


def check_cloze(answers: list[str], values: list[str]) -> list[bool]:
    results = []
    for expected, given in zip(answers, values, strict=False):
        results.append(normalize_word(expected) == normalize_word(given) and bool(given.strip()))
    return results
