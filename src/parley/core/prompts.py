from __future__ import annotations

from .config import (
    language_label,
    language_name,
    normalize_language_code,
)
from .scenarios import Scenario

LEVELS = {
    "A1": {
        "label": "A1 - Beginner",
        "guidance": (
            "Use very short sentences, common words and present simple. "
            "Avoid idioms and complex grammar."
        ),
    },
    "A2": {
        "label": "A2 - Elementary",
        "guidance": (
            "Use short, clear sentences and everyday vocabulary. "
            "You may use simple past and future."
        ),
    },
    "B1": {
        "label": "B1 - Intermediate",
        "guidance": (
            "Use natural everyday language with some idioms and phrasal verbs. "
            "Keep sentences manageable."
        ),
    },
    "B2": {
        "label": "B2 - Upper intermediate",
        "guidance": (
            "Use natural, varied language with common idioms and nuanced "
            "opinions. Do not simplify too much."
        ),
    },
    "C1": {
        "label": "C1 - Advanced",
        "guidance": (
            "Use fluent, idiomatic and culturally natural language. "
            "Challenge the user with richer vocabulary and collocations."
        ),
    },
    "C2": {
        "label": "C2 - Proficient",
        "guidance": (
            "Use fully natural, precise and nuanced language, including "
            "idioms, register shifts and sophisticated argumentation."
        ),
    },
}

LEVEL_CHOICES = [(data["label"], code) for code, data in LEVELS.items()]
DEFAULT_LEVEL = "B1"

PT_HEADER = "💡 **Explicação & Contexto (PT-BR):**"
EN_NOTE_HEADER = "📝 **English note:**"
GENERIC_NOTE_HEADER = "📝 **Vocabulary note:**"

PT_TEMPLATE = """\
💡 **Explicação & Contexto (PT-BR):**
- **palavra em português** -> **English equivalent**
- **Explicação:** explicação curta, didática e natural em português, incluindo contexto de uso, registro ou variação regional quando relevante.
- **Exemplo:** "An English example sentence." - "Tradução do exemplo."
"""

EN_NOTE_TEMPLATE = """\
📝 **English note:**
- **palavra em português** -> **English equivalent**
- **Explanation:** short, natural explanation in English, including context of use, register or regional variation when relevant.
- **Example:** "An English example sentence." - "Tradução do exemplo."
"""

GENERIC_NOTE_TEMPLATE = """\
📝 **Vocabulary note:**
- **source expression** -> **meaning in the note language**
- **Explanation:** short, natural explanation in the note language, including context of use, register or regional variation when relevant.
- **Example:** "A short example in the target language." - "Translation in the note language."
"""


def _clean_language(code: str | None, fallback: str) -> str:
    normalized = normalize_language_code(code)
    return normalized or fallback


def _note_template(note_lang: str, target_lang: str, native_lang: str) -> str:
    if note_lang == "pt" and target_lang == "en" and native_lang == "pt":
        return PT_TEMPLATE
    if note_lang == "en" and target_lang == "en" and native_lang == "pt":
        return EN_NOTE_TEMPLATE
    native_name = language_name(native_lang)
    target_name = language_name(target_lang)
    note_name = language_name(note_lang)
    return f"""\
📝 **Vocabulary note:**
- **{native_name} expression** -> **{target_name} equivalent**
- **Explanation:** short, natural explanation in {note_name}, including
  context of use, register or regional variation when relevant.
- **Example:** "A short example in {target_name}." - "Translation in {note_name}."
"""


def _note_header(note_lang: str) -> str:
    if note_lang == "pt":
        return PT_HEADER
    if note_lang == "en":
        return EN_NOTE_HEADER
    return f"📝 **Vocabulary note ({language_label(note_lang)}):**"


def _note_instruction(
    note_lang: str,
    target_lang: str,
    native_lang: str,
    correct_errors: bool,
    main_lang: str,
) -> str:
    target_name = language_name(target_lang)
    native_name = language_name(native_lang)
    note_name = language_name(note_lang)
    source_name = native_name
    meaning_name = target_name

    if main_lang == target_lang:
        correction_rule = (
            f"If the user makes an important {target_name} error, add one "
            "short **Correction:** bullet inside the note. Correct only what "
            "really matters and never interrupt the roleplay to teach."
            if correct_errors
            else "Do not correct the user's language in this turn."
        )
    else:
        correction_rule = (
            f"Do not correct the user's {native_name}. Use the note to teach "
            f"useful {target_name} equivalents."
            if correct_errors
            else "Do not correct the user's language in this turn."
        )

    template = _note_template(note_lang, target_lang, native_lang)
    return f"""\
ALWAYS include the note at the end, even when the user writes only in one language.
The note must be written in {note_name} and use exactly this structure:
{template}
The left side must be the {source_name} word or expression and the right side
its {meaning_name} equivalent. If the user used words from the other language,
explain those exact terms first. Otherwise, choose one useful expression from
the conversation and teach it.
{correction_rule}
If a SPEECH INPUT NOTE is present, add one extra short bullet at the end:
- **Speech:** one practical comment about clarity, speed, pauses or sentence
  length, based only on the speech metrics. Do not claim to evaluate
  pronunciation and do not invent audio details.
Keep the note concise: at most 5 short bullets, or 6 when a speech note is present.
"""


def build_system_prompt(
    scenario: Scenario,
    level: str,
    custom_description: str = "",
    always_explain: bool = True,
    correct_errors: bool = True,
    speech_note: str = "",
    reply_language: str = "en",
    target_language: str | None = None,
    native_language: str | None = None,
    asked_questions: list[str] | None = None,
) -> str:
    level_data = LEVELS.get(level, LEVELS[DEFAULT_LEVEL])
    target_lang = _clean_language(target_language or reply_language, "en")
    native_lang = _clean_language(native_language, "pt")
    main_lang = _clean_language(reply_language, target_lang)
    note_lang = (
        target_lang
        if main_lang == native_lang and native_lang != target_lang
        else native_lang
    )
    main_name = language_name(main_lang)
    target_name = language_name(target_lang)
    native_name = language_name(native_lang)
    note_name = language_name(note_lang)

    custom_block = ""
    if scenario.id == "custom":
        description = custom_description.strip()
        if description:
            custom_block = f"\nCUSTOM ROLEPLAY DESCRIBED BY THE USER:\n{description}\n"
        else:
            custom_block = (
                "\nThe user has not described a custom scenario yet. "
                "Ask a short question to discover the scenario and then "
                "roleplay it.\n"
            )

    speech_note = (speech_note or "").strip()
    speech_block = ""
    if speech_note:
        speech_block = f"""
SPEECH INPUT NOTE (from the speech recognizer):
{speech_note}
The transcript may contain recognition errors. If it looks incomplete,
incoherent or unlikely for the scenario, say briefly in {main_name} that you
did not understand and ask the student to repeat. Do not invent what the
student said.
"""

    note_rules = (
        _note_instruction(
            note_lang, target_lang, native_lang, correct_errors, main_lang
        )
        if always_explain
        else "Do not include any note or explanation section in this turn.\n"
    )

    conversation_rules = """\
CONVERSATION RULES:
- Keep the roleplay moving forward. Never restart the introduction.
- Never repeat a question the learner has already answered.
- Ask at most one question per reply, and make it a new question about a
  different detail or a related topic.
- React to the learner's last answer with a short comment before asking
  something new.
- If the learner gives a short answer, offer a detail or a choice so they can
  expand, then ask about a new point.
- Vary your openings and vocabulary; do not reuse the same phrase twice.
"""

    asked_block = ""
    if asked_questions:
        unique: list[str] = []
        for question in asked_questions:
            cleaned = " ".join((question or "").split())
            if cleaned and cleaned not in unique:
                unique.append(cleaned)
        if unique:
            lines = "\n".join(f"- {question}" for question in unique[-8:])
            asked_block = (
                "\nQUESTIONS ALREADY ASKED (never ask them again):\n"
                f"{lines}\n"
            )

    if always_explain:
        response_format = f"""\
<MAIN>
Your in-character reply in {main_name} here. Use 2 to 4 natural sentences. Do not include headings, notes, tags or bullet lists here.
</MAIN>
<NOTE>
Your note in {note_name} here, using the required template.
</NOTE>"""
    else:
        response_format = f"""\
<MAIN>
Your in-character reply in {main_name} here. Use 2 to 4 natural sentences.
</MAIN>"""

    language_rules = f"""\
- MAIN REPLY LANGUAGE: {main_name}. Always reply in this language, in character.
- The learner is practicing {target_name}; the learner's native language is {native_name}.
- If the user explicitly asks for an explanation in {native_name}, put that
  explanation in the note, not in the main reply.
- If MAIN REPLY LANGUAGE is {target_name} and the user mixes in {native_name}
  words, understand them, continue in {target_name}, and explain those words
  in the note.
- If MAIN REPLY LANGUAGE is {native_name}, reply naturally in {native_name}
  and use the note to teach useful {target_name} equivalents.
- Never answer in a language different from {main_name} outside the note.
- Never translate your entire reply. Focus on the vocabulary the user needed
  or on one useful expression.
- Do not mention that you are an AI, a model or a prompt.
- Do not use the tags or the note heading inside the main reply."""

    return f"""\
You are a patient multilingual tutor and conversation partner.
You are roleplaying with a learner of {target_name} whose native language is
{native_name}.

SCENARIO:
{scenario.persona}
{custom_block}{speech_block}
LEARNER LEVEL: {level} - {level_data["guidance"]}

LANGUAGE RULES:
{language_rules}

{conversation_rules}
{asked_block}
{note_rules}

RESPONSE FORMAT (mandatory):
{response_format}

Return only the content inside the requested tags. Do not add anything before
<MAIN> or after </NOTE>.
"""


def build_note_feedback_system(
    note_lang: str,
    target_lang: str,
    native_lang: str,
) -> str:
    note_lang = _clean_language(note_lang, "pt")
    target_lang = _clean_language(target_lang, "en")
    native_lang = _clean_language(native_lang, "pt")
    source_name = language_name(native_lang)
    meaning_name = language_name(target_lang)
    note_name = language_name(note_lang)
    template = _note_template(note_lang, target_lang, native_lang)
    return f"""\
You are a language teacher helping a learner of {language_name(target_lang)}.
Write ONLY the vocabulary note in {note_name}, using exactly this template:
{template}
The left side must be the {source_name} word or expression and the right side
its {meaning_name} equivalent. If the learner used words from the other
language, explain those exact terms first. Otherwise, choose one useful
expression from the conversation.
Be concise, natural and didactic. Do not write a roleplay reply. Do not use
the tags <MAIN>, </MAIN>, <NOTE> or </NOTE>. Return only the note.
"""


def build_note_feedback_user_prompt(
    main_reply: str,
    user_message: str,
    correct_errors: bool,
    main_lang: str = "en",
    target_lang: str = "en",
    native_lang: str = "pt",
) -> str:
    correction = (
        f"If there is a relevant {language_name(target_lang)} error in the "
        "user's message, include one short **Correction:** bullet."
        if correct_errors and main_lang == target_lang
        else "Do not correct the user's language."
    )
    return f"""\
Tutor's reply:
{main_reply}

User's message:
{user_message}

{correction}
Write the vocabulary note now.
"""


# Compatibility wrappers for older callers/tests.
PT_FEEDBACK_SYSTEM = build_note_feedback_system("pt", "en", "pt")
EN_NOTE_SYSTEM = build_note_feedback_system("en", "en", "pt")


def build_pt_feedback_user_prompt(
    english_reply: str, user_message: str, correct_errors: bool
) -> str:
    return build_note_feedback_user_prompt(
        english_reply, user_message, correct_errors, "en", "en", "pt"
    )


def build_en_note_user_prompt(
    main_reply: str, user_message: str, correct_errors: bool
) -> str:
    return build_note_feedback_user_prompt(
        main_reply, user_message, correct_errors, "pt", "en", "pt"
    )


EXPLAIN_MORE_SYSTEM = """\
You are a language teacher. The student wants a deeper explanation of the
tutor's last reply. Write in the student's native language, with clear headings
and short bullets. Include:
1. The main vocabulary and collocations from the reply.
2. Nuance, register, regional variation or cultural context when relevant.
3. Two examples in the target language with translations.
Do not roleplay. Do not use <EN> or <PT> tags. Keep it under 250 words.
"""


def build_explain_more_system(native_lang: str, target_lang: str) -> str:
    native_name = language_name(native_lang)
    target_name = language_name(target_lang)
    return f"""\
You are a teacher of {target_name}. The student wants a deeper explanation of
the tutor's last reply. Write in {native_name}, with clear headings and short
bullets. Include:
1. The main vocabulary and collocations from the reply.
2. Nuance, register, regional variation or cultural context when relevant.
3. Two examples in {target_name} with translations in {native_name}.
Do not roleplay. Do not use <MAIN>, <NOTE>, <EN> or <PT> tags. Keep it under
250 words.
"""


def build_explain_more_user_prompt(
    main_reply: str, note_reply: str, user_message: str
) -> str:
    return f"""\
Tutor's last reply:
{main_reply}

Previous note:
{note_reply or "(none)"}

User's last message:
{user_message or "(none)"}

Explain the tutor's reply in more depth for the learner.
"""


SIMPLER_ENGLISH_SYSTEM = """\
You are a language teacher. Rewrite the tutor's last reply in simple A2-level
English. Keep the same meaning and the same roleplay context. Use 2 or 3 short
sentences. Then add a short PT-BR note explaining the key vocabulary.

Return exactly this format:
<MAIN>
The simplified English reply.
</MAIN>
<NOTE>
💡 **Explicação & Contexto (PT-BR):**
- **key expression** -> **Portuguese meaning**
- **Explicação:** short explanation in Brazilian Portuguese.
- **Exemplo:** "An English example." - "Tradução."
</NOTE>
"""


def build_simpler_system(target_lang: str, native_lang: str) -> str:
    target_name = language_name(target_lang)
    native_name = language_name(native_lang)
    template = _note_template(native_lang, target_lang, native_lang)
    return f"""\
You are a teacher of {target_name}. Rewrite the tutor's last reply in simple
A2-level {target_name}. If the last reply was in {native_name}, translate it
into simple {target_name} first. Keep the same meaning and roleplay context.
Use 2 or 3 short sentences. Then add a short note in {native_name}.

Return exactly this format:
<MAIN>
The simplified reply in {target_name}.
</MAIN>
<NOTE>
{template}
</NOTE>
"""


def build_simpler_user_prompt(
    main_reply: str, user_message: str, target_lang: str = "en"
) -> str:
    return f"""\
Tutor's last reply:
{main_reply}

User's last message:
{user_message or "(none)"}

Rewrite the reply in simpler {language_name(target_lang)} and add the note.
"""
