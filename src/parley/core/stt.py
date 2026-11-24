from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass
from pathlib import Path

from .config import SETTINGS, WHISPER_DIR, ensure_directories
from .language import detect_language, language_scores, normalize_language

logger = logging.getLogger(__name__)


class STTError(RuntimeError):
    pass


@dataclass
class Transcription:
    text: str
    language: str
    probability: float
    model: str = ""
    duration: float = 0.0
    speech_duration: float = 0.0
    pause_ratio: float = 0.0
    words: int = 0
    words_per_minute: float = 0.0
    confidence: float = 0.0
    uncertain: bool = False


class SpeechToText:
    def __init__(self) -> None:
        self._models: dict[str, object] = {}
        self._unavailable: set[str] = set()
        self._lock = threading.Lock()

    def _load_model(self, model_name: str):
        with self._lock:
            if model_name in self._models:
                return self._models[model_name]
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise STTError(
                    "faster-whisper is not installed. Run: "
                    "python3.13 -m pip install --user --break-system-packages "
                    "faster-whisper"
                ) from exc

            ensure_directories()
            try:
                model = WhisperModel(
                    model_name,
                    device=SETTINGS.whisper_device,
                    compute_type=SETTINGS.whisper_compute_type,
                    cpu_threads=SETTINGS.whisper_threads,
                    num_workers=1,
                    download_root=str(WHISPER_DIR),
                )
            except Exception as exc:
                raise STTError(
                    f"Could not load Whisper '{model_name}': {exc}. "
                    "Check the installation and, on first use, the connection "
                    "needed to download the model."
                ) from exc
            self._models[model_name] = model
            return model

    def _load_model_with_fallback(self, model_name: str):
        requested = (model_name or "base").strip() or "base"
        if requested not in self._unavailable:
            try:
                return requested, self._load_model(requested)
            except STTError as exc:
                logger.warning("Whisper '%s' unavailable: %s", requested, exc)
                self._unavailable.add(requested)

        fallbacks = [name for name in ("base", "tiny") if name != requested]
        for fallback in fallbacks:
            if fallback in self._unavailable:
                continue
            try:
                model = self._load_model(fallback)
            except STTError as exc:
                logger.warning("Whisper '%s' unavailable: %s", fallback, exc)
                self._unavailable.add(fallback)
                continue
            logger.warning("Using Whisper '%s' instead of '%s'.", fallback, requested)
            return fallback, model
        raise STTError(
            f"No Whisper model available (requested: {requested}). "
            "Run ./setup.sh to download the base model."
        )

    def warm_up(self, model_name: str) -> None:
        """Load the Whisper model before the first recording is sent."""
        self._load_model_with_fallback(model_name)

    def _transcribe_once(
        self, path: Path, model, model_name: str, language: str | None
    ) -> Transcription:
        initial_prompt = None
        if language == "en":
            initial_prompt = (
                "English conversation. Preserve any Portuguese words spoken "
                "exactly as pronounced, e.g. bola de gude, tenis de mesa, "
                "tomada, obrigado, por favor, não, você."
            )
        elif language == "pt":
            initial_prompt = (
                "Portuguese conversation. Preserve any English words spoken "
                "exactly as pronounced, e.g. tennis, badminton, coffee, please."
            )
        elif language is None:
            initial_prompt = (
                "Code-switched conversation mixing English and Portuguese. "
                "Transcribe Portuguese words verbatim when used inside English sentences."
            )
        try:
            transcribe_kwargs = dict(  # noqa: C408
                language=language,
                task="transcribe",
                beam_size=5,
                best_of=5,
                patience=1.0,
                temperature=0.0,
                vad_filter=True,
                vad_parameters={
                    "min_silence_duration_ms": 250,
                    "speech_pad_ms": 400,
                    "max_speech_duration_s": 30,
                },
                condition_on_previous_text=False,
                without_timestamps=True,
            )
            if initial_prompt:
                transcribe_kwargs["initial_prompt"] = initial_prompt
            segments, info = model.transcribe(
                str(path),
                **transcribe_kwargs,
            )
            collected = [
                segment for segment in segments if segment.text and segment.text.strip()
            ]
            text = " ".join(segment.text.strip() for segment in collected).strip()
        except Exception as exc:
            if "metadata_errors" in str(exc):
                raise STTError(
                    "PyAV 19 is incompatible with faster-whisper 1.2.1. "
                    "Run: python3.13 -m pip install --user "
                    "--break-system-packages 'av>=14,<19' and restart the app."
                ) from exc
            raise STTError(f"Failed to transcribe the audio: {exc}") from exc

        if not text:
            raise STTError(
                "No speech was detected. Try recording again closer to the "
                "microphone."
            )

        duration = float(getattr(info, "duration", 0.0) or 0.0)
        if duration <= 0 and collected:
            duration = float(getattr(collected[-1], "end", 0.0) or 0.0)
        speech_duration = float(getattr(info, "duration_after_vad", 0.0) or 0.0)
        if speech_duration <= 0:
            speech_duration = sum(
                max(
                    0.0,
                    float(getattr(segment, "end", 0.0) or 0.0)
                    - float(getattr(segment, "start", 0.0) or 0.0),
                )
                for segment in collected
            )
        if speech_duration <= 0:
            speech_duration = duration
        pause_ratio = 0.0
        if duration > 0 and speech_duration > 0:
            pause_ratio = max(0.0, min(1.0, 1.0 - speech_duration / duration))
        words = len(text.split())
        words_per_minute = (
            words / (speech_duration / 60.0) if speech_duration > 0 else 0.0
        )

        logprobs = [
            float(getattr(segment, "avg_logprob", -1.0) or -1.0)
            for segment in collected
        ]
        average_logprob = sum(logprobs) / len(logprobs) if logprobs else -1.0
        average_logprob = min(0.0, average_logprob)
        confidence = max(0.0, min(1.0, math.exp(average_logprob)))
        no_speech = max(
            (
                float(getattr(segment, "no_speech_prob", 0.0) or 0.0)
                for segment in collected
            ),
            default=0.0,
        )
        uncertain = bool(collected) and (confidence < 0.55 or no_speech > 0.6)

        detected = normalize_language(language or getattr(info, "language", None))
        if detected is None:
            detected = detect_language(text)

        return Transcription(
            text=text,
            language=detected,
            probability=float(getattr(info, "language_probability", 0.0) or 0.0),
            duration=duration,
            speech_duration=speech_duration,
            pause_ratio=pause_ratio,
            words=words,
            words_per_minute=words_per_minute,
            confidence=confidence,
            uncertain=uncertain,
            model=model_name,
        )

    @staticmethod
    def _candidate_score(result: Transcription) -> float:
        text_language = detect_language(result.text)
        bonus = 0.12 if text_language == result.language else -0.08
        pt_score, en_score = language_scores(result.text)
        if result.language == "en" and pt_score >= 1:
            bonus += 0.05
        if result.language == "pt" and en_score >= 1 and pt_score >= en_score:
            bonus += 0.02
        return result.confidence + bonus

    def transcribe(
        self, audio_path: str | Path, model_name: str, language: str = "auto"
    ) -> Transcription:
        path = Path(audio_path)
        if not path.exists() or path.stat().st_size == 0:
            raise STTError("No valid audio was received from the microphone.")

        active_model, model = self._load_model_with_fallback(model_name)
        selected_language = normalize_language(language)
        if selected_language:
            return self._transcribe_once(path, model, active_model, selected_language)

        first = self._transcribe_once(path, model, active_model, None)
        pt_score, en_score = language_scores(first.text)
        text_language = detect_language(first.text)
        retry_language: str | None = None

        if first.language not in ("en", "pt"):
            retry_language = text_language
        elif text_language == "pt" and pt_score >= en_score + 1:
            retry_language = "pt" if first.language != "pt" else None
        elif text_language == "en" and en_score >= pt_score + 1:
            retry_language = "en" if first.language != "en" else None
        elif pt_score >= 1 and first.language == "en" and en_score <= pt_score:
            retry_language = "en"
        elif first.uncertain:
            retry_language = "pt" if first.language == "en" else "en"

        if not retry_language or retry_language == first.language:
            if first.language == "en" and pt_score >= 1 and en_score <= pt_score:
                try:
                    second = self._transcribe_once(path, model, active_model, "en")
                    return (
                        second
                        if self._candidate_score(second) > self._candidate_score(first)
                        else first
                    )
                except STTError:
                    return first
            return first

        try:
            second = self._transcribe_once(path, model, active_model, retry_language)
        except STTError:
            return first
        return (
            second
            if self._candidate_score(second) > self._candidate_score(first)
            else first
        )
