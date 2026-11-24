from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from .config import (
    LANGUAGE_CONFIG,
    PIPER_DIR,
    PIPER_VOICE_REGISTRY,
    VOICE_DOWNLOADS,
    default_voice_for_language,
    normalize_language_code,
    voice_config_path,
    voice_model_path,
)
from .config import (
    voices_for_language as config_voices_for_language,
)

PIPER_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
logger = logging.getLogger(__name__)


class VoiceManager:
    def list_downloaded(self) -> list[str]:
        downloaded = []
        for voice in VOICE_DOWNLOADS:
            if voice_model_path(voice).exists() and voice_config_path(voice).exists():
                downloaded.append(voice)
        return downloaded

    def _download_file(self, url: str, destination: Path) -> bool:
        if destination.exists() and destination.stat().st_size > 0:
            return True
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp = destination.with_suffix(destination.suffix + ".part")
        try:
            if shutil.which("curl"):
                for flags in (
                    [
                        "-fL",
                        "--retry",
                        "3",
                        "--connect-timeout",
                        "15",
                        "-o",
                        str(tmp),
                        url,
                    ],
                    [
                        "-fkL",
                        "--retry",
                        "3",
                        "--connect-timeout",
                        "15",
                        "-o",
                        str(tmp),
                        url,
                    ],
                ):
                    result = subprocess.run(
                        ["curl", *flags], capture_output=True, check=False
                    )
                    if (
                        result.returncode == 0
                        and tmp.exists()
                        and tmp.stat().st_size > 0
                    ):
                        tmp.replace(destination)
                        return True
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
            if shutil.which("wget"):
                for flags in (
                    ["-O", str(tmp), url],
                    ["-O", str(tmp), "--no-check-certificate", url],
                ):
                    result = subprocess.run(
                        ["wget", *flags], capture_output=True, check=False
                    )
                    if (
                        result.returncode == 0
                        and tmp.exists()
                        and tmp.stat().st_size > 0
                    ):
                        tmp.replace(destination)
                        return True
            # Try requests as fallback
            try:
                import requests

                for verify in (True, False):
                    try:
                        resp = requests.get(url, stream=True, timeout=30, verify=verify)
                        resp.raise_for_status()
                        with open(tmp, "wb") as handle:
                            for chunk in resp.iter_content(chunk_size=8192):
                                if chunk:
                                    handle.write(chunk)
                        if tmp.exists() and tmp.stat().st_size > 0:
                            tmp.replace(destination)
                            return True
                    except Exception as exc:
                        logger.debug("Failed to download %s: %s", url, exc)
                        continue
            except Exception as exc:
                logger.debug("Download failed for %s: %s", destination, exc)
        except Exception as exc:
            logger.debug("Unexpected download failure for %s: %s", destination, exc)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
        return False

    def download_voice(self, voice: str) -> tuple[bool, str]:
        if voice not in VOICE_DOWNLOADS:
            return False, f"Unsupported voice: {voice}"
        if voice_model_path(voice).exists() and voice_config_path(voice).exists():
            return True, f"Voice already installed: {voice}"
        relative_dir, filename = VOICE_DOWNLOADS[voice]
        model_url = f"{PIPER_BASE_URL}/{relative_dir}/{filename}.onnx"
        config_url = f"{PIPER_BASE_URL}/{relative_dir}/{filename}.onnx.json"
        PIPER_DIR.mkdir(parents=True, exist_ok=True)
        model_path = voice_model_path(voice)
        config_path = voice_config_path(voice)

        ok_model = self._download_file(model_url, model_path)
        ok_config = self._download_file(config_url, config_path)
        if ok_model and ok_config and model_path.exists() and config_path.exists():
            return True, f"Voice installed successfully: {voice}"
        if model_path.exists() and config_path.exists():
            return True, f"Voice installed successfully: {voice}"
        return False, f"Failed to download voice {voice}. Check the network connection."

    def ensure_language_voice(self, lang_code: str) -> tuple[str | None, bool, str]:
        normalized = normalize_language_code(lang_code) or "en"
        existing = config_voices_for_language(normalized, downloaded_only=True)
        if existing:
            voice = default_voice_for_language(normalized)
            if voice in existing:
                return (
                    voice,
                    True,
                    f"Voice already installed for {LANGUAGE_CONFIG.get(normalized, {}).get('label', normalized)}.",
                )
            return (
                next(iter(existing.keys())),
                True,
                f"Voice already installed for {LANGUAGE_CONFIG.get(normalized, {}).get('label', normalized)}.",
            )
        voice = default_voice_for_language(normalized)
        ok, msg = self.download_voice(voice)
        if ok:
            return voice, True, msg
        return None, False, msg

    def delete_voice(self, voice: str) -> tuple[bool, str]:
        """Remove an installed Piper voice from the data folder."""

        removed = False
        for path in (voice_model_path(voice), voice_config_path(voice)):
            try:
                path.unlink()
                removed = True
            except FileNotFoundError:
                continue
            except OSError as exc:
                return False, f"Could not delete {path.name}: {exc}"
        if removed:
            return True, f"Voice deleted: {voice}"
        return False, f"Voice is not installed: {voice}"

    def voices_for_language(self, lang_code: str) -> dict[str, str]:
        normalized = normalize_language_code(lang_code) or "en"
        voices: dict[str, str] = {}
        for voice, info in PIPER_VOICE_REGISTRY.items():
            if info.get("lang") != normalized:
                continue
            if voice_model_path(voice).exists() and voice_config_path(voice).exists():
                voices[voice] = info.get("name", voice)
        return voices


VOICE_MANAGER = VoiceManager()
