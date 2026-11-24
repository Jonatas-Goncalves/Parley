from __future__ import annotations

from parley.core.i18n import (
    DEFAULT_UI_LANGUAGE,
    STRINGS,
    UI_LANGUAGES,
    normalize_ui_language,
    t,
)


def test_all_ui_languages_are_available() -> None:
    assert list(UI_LANGUAGES) == ["en", "pt", "es", "fr", "it", "ja", "ko", "zh"]


def test_every_key_is_translated_in_every_language() -> None:
    missing = [
        (key, language)
        for key, translations in STRINGS.items()
        for language in UI_LANGUAGES
        if not translations.get(language)
    ]
    assert missing == []


def test_unknown_language_falls_back_to_english() -> None:
    assert normalize_ui_language("xx") == DEFAULT_UI_LANGUAGE
    assert t("settings", "xx") == "Settings"


def test_placeholders_are_filled() -> None:
    text = t("stories_available", "it", count=49, size="248.0")
    assert "49" in text and "248.0" in text


def test_invalid_placeholder_does_not_crash() -> None:
    assert t("stories_available", "en")


def test_cjk_language_labels_follow_the_interface_language() -> None:
    assert t("language_ja", "en") == "Japanese"
    assert t("language_ko", "en") == "Korean"
    assert t("language_zh", "en") == "Chinese"
    assert t("language_ja", "pt") == "Japonês"
    assert t("language_zh", "ja") == "中国語"
