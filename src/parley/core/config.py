from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent.parent


def _user_data_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Parley"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "parley"


def _frozen_base() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))


def _root_dir() -> Path:
    """Return the folder that contains ``assets`` and the local data folders.

    In a source checkout this is the repository root, and in the Linux packages
    it is the staged application folder. A frozen build keeps everything next to
    the executable. A plain wheel install has neither, so the user data folder
    is used instead.
    """

    frozen = _frozen_base()
    if frozen is not None:
        return frozen
    candidate = PACKAGE_DIR.parent.parent
    if (candidate / "assets").is_dir() or (candidate / "pyproject.toml").is_file():
        return candidate
    return _user_data_dir()


ROOT_DIR = _root_dir()


def _data_dir() -> Path:
    """Return the writable folder that holds models, cache and preferences.

    By default it follows ROOT_DIR: a source checkout keeps everything inside
    the project, while installed builds fall back to the user profile. Packages
    (AppImage, Flatpak, deb, rpm) set PARLEY_DATA_DIR explicitly. The legacy
    PARLE_DATA_DIR and TUTOR_DATA_DIR names are still honoured.
    """

    configured = (
        os.environ.get("PARLEY_DATA_DIR")
        or os.environ.get("PARLE_DATA_DIR")
        or os.environ.get("TUTOR_DATA_DIR")
    )
    if configured and configured.strip():
        return Path(configured).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return _user_data_dir()
    return ROOT_DIR


DATA_DIR = _data_dir()
MODELS_DIR = DATA_DIR / "models"
PIPER_DIR = MODELS_DIR / "piper"
WHISPER_DIR = MODELS_DIR / "whisper"
CACHE_DIR = DATA_DIR / "cache"
TTS_CACHE_DIR = CACHE_DIR / "tts"
AUDIO_DIR = CACHE_DIR / "audio"
EXPORT_DIR = CACHE_DIR / "exports"

MODEL_TIERS = {
    "weak": "qwen2.5:1.5b-instruct-q4_K_M",
    "medium": "qwen2.5:3b-instruct-q4_K_M",
    "strong": "qwen2.5:7b-instruct-q4_K_M",
}

DEFAULT_MODELS = tuple(MODEL_TIERS.values())

PIPER_VOICES = {
    "en_US-lessac-medium": "English (US) - Lessac",
    "en_US-ryan-medium": "English (US) - Ryan",
    "pt_BR-faber-medium": "Portugues (BR) - Faber",
}

LANGUAGE_CONFIG = {
    "pt": {
        "label": "Portuguese (Brazil)",
        "choice_label": "Portuguese (Brazil)",
        "name": "Brazilian Portuguese",
        "whisper_lang": "pt",
        "piper_prefix": "pt_BR",
        "tts_voice_key": "pt",
        "tts_default": "pt_BR-faber-medium",
        "scenarios_lang": "pt",
        "arrow_word": "means",
    },
    "en": {
        "label": "English (US)",
        "choice_label": "English (US)",
        "name": "English",
        "whisper_lang": "en",
        "piper_prefix": "en_US",
        "tts_voice_key": "en",
        "tts_default": "en_US-lessac-medium",
        "scenarios_lang": "en",
        "arrow_word": "means",
    },
    "es": {
        "label": "Spanish (Spain)",
        "choice_label": "Spanish (Spain)",
        "name": "Spanish",
        "whisper_lang": "es",
        "piper_prefix": "es_ES",
        "tts_voice_key": "es",
        "tts_default": "es_ES-davefx-medium",
        "scenarios_lang": "es",
        "arrow_word": "significa",
    },
    "fr": {
        "label": "French (France)",
        "choice_label": "French (France)",
        "name": "French",
        "whisper_lang": "fr",
        "piper_prefix": "fr_FR",
        "tts_voice_key": "fr",
        "tts_default": "fr_FR-siwis-medium",
        "scenarios_lang": "fr",
        "arrow_word": "signifie",
    },
    "it": {
        "label": "Italian",
        "choice_label": "Italian",
        "name": "Italian",
        "whisper_lang": "it",
        "piper_prefix": "it_IT",
        "tts_voice_key": "it",
        "tts_default": "it_IT-paola-medium",
        "scenarios_lang": "it",
        "arrow_word": "significa",
    },
    "ja": {
        "label": "Japanese",
        "choice_label": "Japanese",
        "name": "Japanese",
        "whisper_lang": "ja",
        "piper_prefix": "ja_JP",
        "tts_voice_key": "ja",
        "tts_default": "ja_JP-hi_fi_captain-medium",
        "scenarios_lang": "ja",
        "arrow_word": "という意味です",
    },
    "ko": {
        "label": "Korean",
        "choice_label": "Korean",
        "name": "Korean",
        "whisper_lang": "ko",
        "piper_prefix": "ko_KR",
        "tts_voice_key": "ko",
        "tts_default": "ko_KR-kss-medium",
        "scenarios_lang": "ko",
        "arrow_word": "라는 뜻입니다",
    },
    "zh": {
        "label": "Mandarin Chinese",
        "choice_label": "Mandarin Chinese",
        "name": "Mandarin Chinese",
        "whisper_lang": "zh",
        "piper_prefix": "zh_CN",
        "tts_voice_key": "zh",
        "tts_default": "zh_CN-huayan-medium",
        "scenarios_lang": "zh",
        "arrow_word": "意思是",
    },
}

SUPPORTED_LANGUAGES = list(LANGUAGE_CONFIG.keys())

PIPER_VOICE_REGISTRY = {
    "en_US-lessac-medium": {"lang": "en", "name": "English (US) - Lessac"},
    "en_US-ryan-medium": {"lang": "en", "name": "English (US) - Ryan"},
    "pt_BR-faber-medium": {"lang": "pt", "name": "Portuguese (BR) - Faber"},
    "es_ES-davefx-medium": {"lang": "es", "name": "Spanish (ES) - DaveFX"},
    "es_MX-ald-medium": {"lang": "es", "name": "Spanish (MX) - Ald"},
    "fr_FR-siwis-medium": {"lang": "fr", "name": "French - Siwis"},
    "it_IT-paola-medium": {"lang": "it", "name": "Italian - Paola"},
    "it_IT-riccardo-x_low": {"lang": "it", "name": "Italian - Riccardo"},
    "ja_JP-hi_fi_captain-medium": {
        "lang": "ja",
        "name": "Japanese - Hi-Fi Captain",
    },
    "ko_KR-kss-medium": {"lang": "ko", "name": "Korean - KSS"},
    "zh_CN-huayan-medium": {"lang": "zh", "name": "Mandarin - Huayan"},
}

VOICE_DOWNLOADS = {
    "en_US-lessac-medium": ("en/en_US/lessac/medium", "en_US-lessac-medium"),
    "en_US-ryan-medium": ("en/en_US/ryan/medium", "en_US-ryan-medium"),
    "pt_BR-faber-medium": ("pt/pt_BR/faber/medium", "pt_BR-faber-medium"),
    "es_ES-davefx-medium": ("es/es_ES/davefx/medium", "es_ES-davefx-medium"),
    "es_MX-ald-medium": ("es/es_MX/ald/medium", "es_MX-ald-medium"),
    "fr_FR-siwis-medium": ("fr/fr_FR/siwis/medium", "fr_FR-siwis-medium"),
    "it_IT-paola-medium": ("it/it_IT/paola/medium", "it_IT-paola-medium"),
    "it_IT-riccardo-x_low": ("it/it_IT/riccardo/x_low", "it_IT-riccardo-x_low"),
    "ja_JP-hi_fi_captain-medium": (
        "ja/ja_JP/hi_fi_captain/medium",
        "ja_JP-hi_fi_captain-medium",
    ),
    "ko_KR-kss-medium": ("ko/ko_KR/kss/medium", "ko_KR-kss-medium"),
    "zh_CN-huayan-medium": ("zh/zh_CN/huayan/medium", "zh_CN-huayan-medium"),
}

DEFAULT_LANGUAGES = {
    "native": "pt",
    "target": "en",
}
DEFAULT_EN_VOICE = "en_US-lessac-medium"
DEFAULT_PT_VOICE = "pt_BR-faber-medium"

WHISPER_MODELS = ("tiny", "base", "small")

SYSTEM_PACKAGE_HINT = (
    "sudo zypper install python313 python313-gobject gtk4 "
    "typelib-1_0-Gtk-4_0 libportaudio2 libsndfile1 ffmpeg"
)
PYTHON_PACKAGE_HINT = "python3 -m pip install -r requirements.txt"


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    ollama_url: str = _env_str("PARLEY_OLLAMA_URL", "http://127.0.0.1:11434")
    llama_cpp_url: str = _env_str("PARLEY_LLAMA_CPP_URL", "http://127.0.0.1:8080/v1")
    default_backend: str = _env_str("PARLEY_BACKEND", "ollama")
    default_model: str = _env_str("PARLEY_MODEL", "qwen2.5:3b-instruct-q4_K_M")
    num_ctx: int = _env_int("PARLEY_NUM_CTX", 2048)
    num_predict: int = _env_int("PARLEY_NUM_PREDICT", 400)
    temperature: float = _env_float("PARLEY_TEMPERATURE", 0.6)
    top_p: float = _env_float("PARLEY_TOP_P", 0.9)
    keep_alive: str = _env_str("PARLEY_KEEP_ALIVE", "10m")
    history_turns: int = _env_int("PARLEY_HISTORY_TURNS", 10)
    max_user_chars: int = _env_int("PARLEY_MAX_USER_CHARS", 2000)
    whisper_model: str = _env_str("PARLEY_WHISPER_MODEL", "base")
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_threads: int = _env_int(
        "PARLEY_WHISPER_THREADS", max(1, min(4, os.cpu_count() or 4))
    )
    tts_chunk_chars: int = _env_int("PARLEY_TTS_CHUNK_CHARS", 350)
    connect_timeout: int = _env_int("PARLEY_CONNECT_TIMEOUT", 5)
    read_timeout: int = _env_int("PARLEY_READ_TIMEOUT", 300)
    tts_timeout: int = _env_int("PARLEY_TTS_TIMEOUT", 120)
    cache_max_age_hours: int = _env_int("PARLEY_CACHE_MAX_AGE_HOURS", 24)


SETTINGS = Settings()


def ensure_directories() -> None:
    for directory in (
        MODELS_DIR,
        PIPER_DIR,
        WHISPER_DIR,
        CACHE_DIR,
        TTS_CACHE_DIR,
        AUDIO_DIR,
        EXPORT_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def cleanup_cache(max_age_hours: int | None = None) -> None:
    ensure_directories()
    max_age = (max_age_hours or SETTINGS.cache_max_age_hours) * 3600
    now = time.time()
    for directory in (TTS_CACHE_DIR, AUDIO_DIR, EXPORT_DIR):
        for path in directory.glob("*"):
            if not path.is_file():
                continue
            try:
                if now - path.stat().st_mtime > max_age:
                    path.unlink()
            except OSError:
                continue


def voice_model_path(voice: str) -> Path:
    return PIPER_DIR / f"{voice}.onnx"


def voice_config_path(voice: str) -> Path:
    return PIPER_DIR / f"{voice}.onnx.json"


def normalize_language_code(code: str | None) -> str | None:
    value = (code or "").strip().casefold().replace("_", "-")
    if not value:
        return None
    aliases = {
        "pt": "pt",
        "pt-br": "pt",
        "portuguese": "pt",
        "portugues": "pt",
        "en": "en",
        "en-us": "en",
        "english": "en",
        "ingles": "en",
        "es": "es",
        "es-es": "es",
        "es-mx": "es",
        "spanish": "es",
        "espanol": "es",
        "español": "es",
        "fr": "fr",
        "it": "it",
        "fr-fr": "fr",
        "french": "fr",
        "francais": "fr",
        "français": "fr",
        "italian": "it",
        "italiano": "it",
        "it-it": "it",
        "ja": "ja",
        "ja-jp": "ja",
        "japanese": "ja",
        "ko": "ko",
        "ko-kr": "ko",
        "korean": "ko",
        "zh": "zh",
        "zh-cn": "zh",
        "zh-tw": "zh",
        "chinese": "zh",
        "mandarin": "zh",
    }
    if value in aliases:
        return aliases[value]
    for prefix, language in (
        ("port", "pt"),
        ("ingl", "en"),
        ("espan", "es"),
        ("españ", "es"),
        ("franc", "fr"),
        ("franç", "fr"),
        ("ital", "it"),
        ("jap", "ja"),
        ("kore", "ko"),
        ("chin", "zh"),
    ):
        if value.startswith(prefix):
            return language
    return None


def language_label(code: str) -> str:
    normalized = normalize_language_code(code) or "en"
    return LANGUAGE_CONFIG.get(normalized, {}).get("label", normalized)


def language_choice_label(code: str) -> str:
    normalized = normalize_language_code(code) or "en"
    config = LANGUAGE_CONFIG.get(normalized, {})
    return config.get("choice_label") or config.get("label") or normalized


def language_name(code: str) -> str:
    normalized = normalize_language_code(code) or "en"
    return LANGUAGE_CONFIG.get(normalized, {}).get("name", normalized)


def default_voice_for_language(code: str) -> str:
    normalized = normalize_language_code(code) or "en"
    return LANGUAGE_CONFIG.get(normalized, {}).get("tts_default", DEFAULT_EN_VOICE)


def voices_for_language(code: str, downloaded_only: bool = True) -> dict[str, str]:
    normalized = normalize_language_code(code) or "en"
    voices: dict[str, str] = {}
    for voice, info in PIPER_VOICE_REGISTRY.items():
        if info.get("lang") != normalized:
            continue
        present = voice_model_path(voice).exists() and voice_config_path(voice).exists()
        if downloaded_only and not present:
            continue
        voices[voice] = info.get("name", voice)
    return voices


def language_voice_ready(code: str) -> bool:
    return bool(voices_for_language(code, downloaded_only=True))


def available_voices() -> dict[str, str]:
    voices = {}
    for voice, label in PIPER_VOICE_REGISTRY.items():
        if voice_model_path(voice).exists() and voice_config_path(voice).exists():
            voices[voice] = label.get("name", voice)
    if voices:
        return voices
    return dict(PIPER_VOICES)
