from __future__ import annotations

import importlib.metadata
import importlib.util
import shutil
import sys

from .config import (
    DEFAULT_EN_VOICE,
    DEFAULT_PT_VOICE,
    PIPER_DIR,
    PIPER_VOICES,
    SETTINGS,
    WHISPER_DIR,
    ensure_directories,
    voice_config_path,
    voice_model_path,
)
from .llm import probe_backend


def _status(ok: bool, label: str, detail: str = "") -> str:
    marker = "OK" if ok else "WARNING"
    suffix = f" - {detail}" if detail else ""
    return f"- **[{marker}]** {label}{suffix}"


def environment_report() -> str:
    ensure_directories()
    lines = ["### Environment check", ""]

    version_ok = sys.version_info[:2] >= (3, 11)
    lines.append(
        _status(
            version_ok,
            f"Python {sys.version.split()[0]}",
            "Python 3.11 or newer is required" if not version_ok else "supported version",
        )
    )

    for module, label in (
        ("faster_whisper", "faster-whisper"),
        ("av", "PyAV"),
        ("piper", "Piper"),
        ("sounddevice", "Audio devices"),
        ("gi", "GTK bindings"),
    ):
        present = importlib.util.find_spec(module) is not None
        lines.append(_status(present, label))

    try:
        av_version = importlib.metadata.version("av")
    except importlib.metadata.PackageNotFoundError:
        av_version = ""
    if av_version:
        try:
            av_major = int(av_version.split(".", 1)[0])
        except ValueError:
            av_major = 0
        lines.append(
            _status(
                av_major < 19,
                f"PyAV {av_version} compatibility",
                (
                    "faster-whisper 1.2.1 requires av<19; run "
                    "pip install -r requirements.txt"
                    if av_major >= 19
                    else "compatible with faster-whisper"
                ),
            )
        )

    piper_command = shutil.which("piper")
    piper_module = importlib.util.find_spec("piper") is not None
    lines.append(
        _status(
            bool(piper_command or piper_module),
            "Piper TTS",
            piper_command or ("Python module" if piper_module else "not found"),
        )
    )

    for voice, label in PIPER_VOICES.items():
        model = voice_model_path(voice)
        config = voice_config_path(voice)
        present = model.exists() and config.exists()
        detail = "" if present else f"download with ./setup.sh ({PIPER_DIR})"
        lines.append(_status(present, f"Voice {label}", detail))

    default_voices_ok = (
        voice_model_path(DEFAULT_EN_VOICE).exists()
        and voice_model_path(DEFAULT_PT_VOICE).exists()
    )
    lines.append(
        _status(
            default_voices_ok,
            "Default EN/PT voices",
            f"{DEFAULT_EN_VOICE}, {DEFAULT_PT_VOICE}",
        )
    )

    whisper_files = list(WHISPER_DIR.rglob("*")) if WHISPER_DIR.exists() else []
    whisper_ok = any(path.is_file() for path in whisper_files)
    lines.append(
        _status(
            whisper_ok,
            f"Whisper model in {WHISPER_DIR}",
            "" if whisper_ok else "downloaded on first use or via setup.sh",
        )
    )

    ffmpeg = shutil.which("ffmpeg")
    lines.append(
        _status(
            bool(ffmpeg),
            "FFmpeg",
            ffmpeg or "optional; used only when voices have different rates",
        )
    )

    lines.extend(["", "#### Local backends", ""])
    for backend, url in (
        ("ollama", SETTINGS.ollama_url),
        ("llamacpp", SETTINGS.llama_cpp_url),
    ):
        probe = probe_backend(SETTINGS, backend, url)
        lines.append(
            f"- **[{'OK' if probe.online else 'ERROR'}]** {backend}: {probe.message}"
        )

    lines.extend(
        [
            "",
            "#### Useful commands",
            "",
            "```bash",
            "./setup.sh",
            "python3.13 -m pip install --user --break-system-packages -r requirements.txt",
            "ollama pull qwen2.5:3b-instruct-q4_K_M",
            "```",
        ]
    )
    return "\n".join(lines)
