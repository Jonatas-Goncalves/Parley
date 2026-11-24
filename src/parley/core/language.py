from __future__ import annotations

import re

from .config import normalize_language_code

PT_WORDS = {
    "agora",
    "aqui",
    "amanha",
    "amanhã",
    "aquilo",
    "bem",
    "bom",
    "boa",
    "cafe",
    "café",
    "cardapio",
    "cardápio",
    "cerveja",
    "com",
    "como",
    "conta",
    "correcao",
    "correção",
    "desculpa",
    "desculpe",
    "dinheiro",
    "ela",
    "ele",
    "eles",
    "elas",
    "entendi",
    "entendo",
    "estou",
    "esta",
    "está",
    "favor",
    "falar",
    "fala",
    "fome",
    "gostaria",
    "gosto",
    "hoje",
    "isso",
    "isto",
    "jantar",
    "lugar",
    "mais",
    "muito",
    "nao",
    "não",
    "obrigado",
    "obrigada",
    "ola",
    "olá",
    "onde",
    "ontem",
    "para",
    "pedir",
    "pode",
    "porque",
    "preciso",
    "prato",
    "qual",
    "quando",
    "quero",
    "quem",
    "restaurante",
    "sim",
    "tambem",
    "também",
    "tem",
    "tenho",
    "tudo",
    "uma",
    "voce",
    "você",
    "voces",
    "vocês",
}

FR_WORDS = {
    "aller",
    "appartement",
    "au",
    "aux",
    "avec",
    "avoir",
    "bonjour",
    "bonsoir",
    "ça",
    "ca",
    "carte",
    "chez",
    "combien",
    "comment",
    "d'accord",
    "dans",
    "de",
    "des",
    "du",
    "en",
    "est",
    "et",
    "être",
    "excuse",
    "expliquer",
    "faire",
    "faim",
    "garçon",
    "homme",
    "il",
    "je",
    "l",
    "la",
    "le",
    "les",
    "merci",
    "monsieur",
    "moi",
    "non",
    "nous",
    "oui",
    "où",
    "ou",
    "par",
    "pardon",
    "parler",
    "pas",
    "pour",
    "pourquoi",
    "prix",
    "quand",
    "que",
    "qui",
    "quoi",
    "restaurant",
    "s'il",
    "si",
    "sommes",
    "son",
    "sont",
    "table",
    "toi",
    "tout",
    "très",
    "tres",
    "tu",
    "un",
    "une",
    "vous",
    "vouloir",
    "voiture",
    "votre",
}

EN_WORDS = {
    "about",
    "after",
    "again",
    "all",
    "am",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "bills",
    "bring",
    "but",
    "by",
    "can",
    "check",
    "could",
    "did",
    "do",
    "does",
    "drink",
    "excuse",
    "food",
    "for",
    "from",
    "get",
    "give",
    "good",
    "great",
    "had",
    "has",
    "have",
    "hello",
    "help",
    "her",
    "here",
    "hi",
    "his",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "like",
    "me",
    "menu",
    "might",
    "must",
    "my",
    "need",
    "no",
    "not",
    "now",
    "of",
    "on",
    "or",
    "order",
    "our",
    "please",
    "platter",
    "seafood",
    "she",
    "should",
    "so",
    "sorry",
    "sure",
    "thank",
    "thanks",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "to",
    "today",
    "tomorrow",
    "too",
    "want",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
    "would",
    "yes",
    "you",
    "your",
    "yesterday",
}

ES_WORDS = {
    "ahora",
    "algo",
    "allí",
    "alli",
    "amigo",
    "aquí",
    "aqui",
    "bien",
    "bueno",
    "buenos",
    "casa",
    "cerveza",
    "comida",
    "cómo",
    "como",
    "cuando",
    "cuánto",
    "cuanto",
    "dinero",
    "dónde",
    "donde",
    "ella",
    "ellos",
    "entonces",
    "está",
    "esta",
    "estoy",
    "favor",
    "gente",
    "gracias",
    "hablar",
    "hacer",
    "hambre",
    "hola",
    "hotel",
    "más",
    "mas",
    "mesa",
    "mucho",
    "muy",
    "necesito",
    "no",
    "para",
    "pero",
    "por",
    "porque",
    "puedo",
    "qué",
    "que",
    "quiero",
    "restaurante",
    "sí",
    "si",
    "también",
    "tambien",
    "tengo",
    "tiene",
    "todo",
    "tomar",
    "usted",
    "vamos",
    "viaje",
    "y",
    "yo",
}

PT_DIACRITICS = set("ãõçáéíóúâêôà")
ES_DIACRITICS = set("ñ¿¡")
FR_DIACRITICS = set("àâæçèéêëîïôœùûüÿ")
PORTUGUESE_SUFFIXES = (
    "ção",
    "ções",
    "mente",
    "dade",
    "idades",
    "agem",
    "agens",
    "ismo",
    "ismos",
    "ista",
    "istas",
)
SPANISH_SUFFIXES = (
    "ción",
    "ciones",
    "mente",
    "dad",
    "dades",
    "ismo",
    "ismos",
    "ista",
    "istas",
)
FRENCH_SUFFIXES = (
    "tion",
    "ment",
    "ment",
    "eur",
    "euse",
    "tion",
    "ités",
    "ité",
    "age",
)
WORD_RE = re.compile(r"[a-zà-ÿœæçñ¿¡']+", re.IGNORECASE)
JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff]")
KOREAN_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]")
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")


def normalize_language(code: str | None) -> str | None:
    return normalize_language_code(code)


def language_scores(text: str) -> tuple[int, int]:
    """Legacy PT/EN score used by the mixed-language STT retry logic."""
    raw = text or ""
    lowered = raw.casefold()
    pt_score = sum(2 for char in lowered if char in PT_DIACRITICS)
    en_score = 0

    for word in WORD_RE.findall(lowered):
        if word in PT_WORDS:
            pt_score += 2
        if word in EN_WORDS:
            en_score += 1
        if word.endswith(PORTUGUESE_SUFFIXES):
            pt_score += 1

    return pt_score, en_score


def language_scores_all(text: str) -> dict[str, int]:
    raw = text or ""
    lowered = raw.casefold()
    scores = {"pt": 0, "en": 0, "es": 0, "fr": 0, "ja": 0, "ko": 0, "zh": 0}
    scores["pt"] += sum(3 for char in lowered if char in PT_DIACRITICS)
    scores["es"] += sum(3 for char in lowered if char in ES_DIACRITICS)
    scores["fr"] += sum(2 for char in lowered if char in FR_DIACRITICS)
    scores["ja"] += len(JAPANESE_RE.findall(raw)) * 3
    scores["ko"] += len(KOREAN_RE.findall(raw)) * 3
    scores["zh"] += len(CHINESE_RE.findall(raw)) * 2

    for word in WORD_RE.findall(lowered):
        if word in PT_WORDS:
            scores["pt"] += 2
        if word in EN_WORDS:
            scores["en"] += 1
        if word in ES_WORDS:
            scores["es"] += 2
        if word in FR_WORDS:
            scores["fr"] += 2
        if word.endswith(PORTUGUESE_SUFFIXES):
            scores["pt"] += 1
        if word.endswith(SPANISH_SUFFIXES):
            scores["es"] += 1
        if word.endswith(FRENCH_SUFFIXES):
            scores["fr"] += 1
    return scores


def detect_language(text: str) -> str:
    raw = text or ""
    if JAPANESE_RE.search(raw):
        return "ja"
    if KOREAN_RE.search(raw):
        return "ko"
    if CHINESE_RE.search(raw):
        return "zh"

    scores = language_scores_all(raw)
    winner = max(scores, key=lambda code: scores[code])
    if scores[winner] > 0:
        if scores["pt"] == scores["es"] and scores["pt"] > 0:
            return "pt"
        if scores["fr"] > 0 and winner == "en" and scores["fr"] >= scores["en"]:
            return "fr"
        return winner
    lowered = raw.casefold()
    if any(char in PT_DIACRITICS for char in lowered):
        return "pt"
    if any(char in FR_DIACRITICS for char in lowered):
        return "fr"
    if any(char in ES_DIACRITICS for char in lowered):
        return "es"
    return "en"


def resolve_language(text: str, hint: str | None = None) -> str:
    hint = normalize_language(hint)
    detected = detect_language(text)
    if hint in (None, "auto"):
        return detected
    if hint == detected:
        return hint
    # A short mixed sentence can be dominated by one language. Keep the
    # explicit hint unless the other language is clearly present.
    scores = language_scores_all(text)
    if scores.get(hint, 0) > 0:
        return hint
    if scores.get(detected, 0) >= 2:
        return detected
    return hint


def resolve_reply_language(
    text: str,
    hint: str | None,
    target_lang: str,
    native_lang: str,
) -> str:
    """Choose the main reply language for a target/native language pair.

    The default PT/EN behaviour is preserved: a Portuguese message gets a
    Portuguese reply, while a mixed English/Portuguese message stays English.
    With an explicit target language, the target is preferred unless the
    learner wrote clearly in the native language.
    """
    target = normalize_language(target_lang) or "en"
    native = normalize_language(native_lang) or "pt"
    detected = resolve_language(text, hint)

    if target == native:
        return target

    if target == "en" and native == "pt":
        pt_score, en_score = language_scores(text)
        if detected == "pt" and pt_score > en_score and en_score == 0:
            return "pt"
        return "en"

    if detected == native:
        native_score = language_scores_all(text).get(native, 0)
        target_score = language_scores_all(text).get(target, 0)
        if native_score > target_score:
            return native
    return target


def choose_note_language(main_lang: str, target_lang: str, native_lang: str) -> str:
    target = normalize_language(target_lang) or "en"
    native = normalize_language(native_lang) or "pt"
    main = normalize_language(main_lang) or target
    if target == native:
        return native
    return target if main == native else native
