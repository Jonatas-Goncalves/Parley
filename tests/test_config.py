from __future__ import annotations

from parley.core.config import (
    LANGUAGE_CONFIG,
    MODEL_TIERS,
    ROOT_DIR,
    SUPPORTED_LANGUAGES,
    VOICE_DOWNLOADS,
    normalize_language_code,
    voices_for_language,
)


def test_supported_languages_include_italian() -> None:
    assert SUPPORTED_LANGUAGES == ["pt", "en", "es", "fr", "it", "ja", "ko", "zh"]
    assert LANGUAGE_CONFIG["it"]["name"] == "Italian"
    assert LANGUAGE_CONFIG["it"]["tts_default"] == "it_IT-paola-medium"


def test_exactly_three_model_tiers() -> None:
    assert list(MODEL_TIERS) == ["weak", "medium", "strong"]
    assert len(set(MODEL_TIERS.values())) == 3


def test_italian_voice_can_be_downloaded() -> None:
    voices = voices_for_language("it", downloaded_only=False)
    assert "it_IT-paola-medium" in voices
    assert "it_IT-paola-medium" in VOICE_DOWNLOADS


def test_italian_aliases_are_normalised() -> None:
    for value in ("it", "IT", "italian", "italiano", "it-IT"):
        assert normalize_language_code(value) == "it"


def test_every_language_has_a_voice() -> None:
    for code in SUPPORTED_LANGUAGES:
        assert voices_for_language(code, downloaded_only=False), code


def test_root_dir_points_at_the_project_assets() -> None:
    assert (ROOT_DIR / "assets" / "cacert.pem").is_file()
