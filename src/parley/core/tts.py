from __future__ import annotations

import hashlib
import html
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unicodedata
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path

from .config import (
    AUDIO_DIR,
    LANGUAGE_CONFIG,
    PIPER_DIR,
    SETTINGS,
    TTS_CACHE_DIR,
    ensure_directories,
    normalize_language_code,
    voice_config_path,
    voice_model_path,
)
from .text import clean_cjk_punctuation, expand_hyphen_runs


class TTSError(RuntimeError):
    pass


@dataclass(frozen=True)
class Segment:
    text: str
    lang: str
    group: str


@dataclass
class TTSBundle:
    combined: Path | None
    english: Path | None
    portuguese: Path | None

    @property
    def main(self) -> Path | None:
        return self.english

    @property
    def note(self) -> Path | None:
        return self.portuguese


EMOJI_RE = re.compile(
    "[\U0001f300-\U0001faff\U00002600-\U000027bf"
    "\U0001f1e6-\U0001f1ff\U0000fe0f\U0000200d]+",
    re.UNICODE,
)
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
HTML_RE = re.compile(r"<[^>]+>")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
SPACE_RE = re.compile(r"\s+")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_PIPER_API_LOCK = threading.Lock()
_PIPER_API: tuple[object, object] | None | bool = None


def _load_piper_api() -> tuple[object, object] | None:
    global _PIPER_API
    if _PIPER_API is None:
        with _PIPER_API_LOCK:
            if _PIPER_API is None:
                try:
                    from piper import PiperVoice, SynthesisConfig
                except Exception:
                    _PIPER_API = False
                else:
                    _PIPER_API = (PiperVoice, SynthesisConfig)
    return _PIPER_API if _PIPER_API not in (None, False) else None


QUOTED_RE = re.compile(r"[\"“](.+?)[\"”]", re.DOTALL)
ARROW_RE = re.compile(r"\s*(?:->|=>|→)\s*")
HEADER_RE = re.compile(
    r"(?i)^\s*(?:#{1,6}\s*)?(?:💡\s*)?\**\s*"
    r"explica(?:ç|c)[aã]o\s*&\s*contexto.*$"
)
HEADER_EN_RE = re.compile(r"(?i)^\s*(?:#{1,6}\s*)?(?:📝\s*)?\**\s*english\s+note.*$")
HEADER_ANY_RE = re.compile(
    r"(?i)^\s*(?:#{1,6}\s*)?(?:💡|📝)\s*.*(?:note|nota|explica(?:ç|c)[aã]o|contexto|vocabulary|メモ|提示|notas).*$"
)


def _arrow_word(lang: str) -> str:
    code = normalize_language_code(lang) or "en"
    return LANGUAGE_CONFIG.get(code, {}).get("arrow_word", "means")


def _clean_inline(value: str) -> str:
    value = re.sub(r"\*\*|__|`", "", value or "")
    value = value.strip(" \t-*•:;>\"'“”‘’")
    return SPACE_RE.sub(" ", value).strip()


def _hash_key(*parts: str) -> str:
    digest = hashlib.sha1()
    for part in parts:
        digest.update(part.encode("utf-8", errors="ignore"))
        digest.update(b"\0")
    return digest.hexdigest()[:20]


class PiperTTS:
    def __init__(self) -> None:
        self._command: list[str] | None = None
        self._output_flag = "--output_file"
        self._length_flag: str | None = "--length_scale"
        self._lock = threading.Lock()
        self._voice_lock = threading.Lock()
        self._synth_lock = threading.Lock()
        self._api_voices: dict[str, object] = {}
        self._api_failed: set[str] = set()

    def _find_command(self) -> list[str]:
        if self._command:
            return self._command
        with self._lock:
            if self._command:
                return self._command
            candidates: list[list[str]] = []
            executable = shutil.which("piper")
            if executable:
                candidates.append([executable])
            if importlib.util.find_spec("piper") is not None:
                candidates.append([sys.executable, "-m", "piper"])
            if not candidates:
                raise TTSError(
                    "Piper not found. Install it with 'sudo zypper install "
                    "piper-tts' or 'python3.13 -m pip install --user "
                    "--break-system-packages piper-tts'."
                )

            for candidate in candidates:
                try:
                    result = subprocess.run(
                        [*candidate, "--help"],
                        capture_output=True,
                        text=True,
                        timeout=15,
                        encoding="utf-8",
                        check=False,
                    )
                except (OSError, subprocess.SubprocessError):
                    continue
                help_text = f"{result.stdout}\n{result.stderr}"
                if result.returncode != 0 and "usage" not in help_text.casefold():
                    continue
                if "--output-file" in help_text and "--output_file" not in help_text:
                    self._output_flag = "--output-file"
                if "--length-scale" in help_text and "--length_scale" not in help_text:
                    self._length_flag = "--length-scale"
                elif (
                    "--length_scale" not in help_text
                    and "--length-scale" not in help_text
                ):
                    self._length_flag = None
                self._command = candidate
                return candidate
            raise TTSError(
                "The 'piper' command was found but did not answer --help. "
                "Check the Piper installation."
            )

    def _voice_files(self, voice: str) -> tuple[Path, Path]:
        model = voice_model_path(voice)
        config = voice_config_path(voice)
        if not model.exists() or not config.exists():
            raise TTSError(
                f"Piper voice '{voice}' not found in {PIPER_DIR}. "
                "Run ./setup.sh to download the voices."
            )
        return model, config

    def clean_for_tts(self, text: str, lang: str) -> str:
        text = html.unescape(text or "")
        text = unicodedata.normalize("NFC", text)
        text = text.replace("\ufffd", " ")
        text = CONTROL_RE.sub(" ", text)
        text = INVISIBLE_RE.sub("", text)
        text = HTML_RE.sub(" ", text)
        text = URL_RE.sub(" ", text)
        text = EMOJI_RE.sub(" ", text)
        text = HEADER_RE.sub(" ", text)
        text = HEADER_EN_RE.sub(" ", text)
        text = HEADER_ANY_RE.sub(" ", text)
        text = re.sub(r"\(\s*PT-BR\s*\)", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\bPT-BR\b", " ", text, flags=re.IGNORECASE)
        arrow = _arrow_word(lang)
        text = ARROW_RE.sub(f" {arrow} ", text)
        text = re.sub(r"^\s*[-*•]\s*", " ", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*#{1,6}\s*", " ", text, flags=re.MULTILINE)
        text = re.sub(r"[*_`#>]+", " ", text)
        text = expand_hyphen_runs(text)
        text = re.sub(r"\s+", " ", text)
        text = clean_cjk_punctuation(text)
        text = re.sub(r"\s+([,.!?;:])", r"\1", text)
        return text.strip(" \t\n-–—")

    def _split_chunks(self, text: str) -> list[str]:
        max_chars = max(80, SETTINGS.tts_chunk_chars)
        if len(text) <= max_chars:
            return [text]
        sentences = [
            part.strip() for part in SENTENCE_SPLIT.split(text) if part.strip()
        ]
        chunks: list[str] = []
        current = ""
        for sentence in sentences:
            if len(sentence) > max_chars:
                words = sentence.split()
                for word in words:
                    candidate = f"{current} {word}".strip()
                    if len(candidate) > max_chars and current:
                        chunks.append(current)
                        current = word
                    else:
                        current = candidate
                continue
            candidate = f"{current} {sentence}".strip()
            if len(candidate) > max_chars and current:
                chunks.append(current)
                current = sentence
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks or [text]

    def _api_voice(self, voice: str) -> object | None:
        api = _load_piper_api()
        if api is None:
            return None
        with self._voice_lock:
            if voice in self._api_failed:
                return None
            cached = self._api_voices.get(voice)
            if cached is not None:
                return cached
            model, config = self._voice_files(voice)
            voice_class = api[0]
            try:
                loaded = voice_class.load(  # type: ignore[attr-defined]
                    str(model), str(config), use_cuda=False
                )
            except Exception:
                self._api_failed.add(voice)
                return None
            self._api_voices[voice] = loaded
            return loaded

    def _run_piper_api(
        self, text: str, voice: str, output: Path, length_scale: float
    ) -> bool:
        api = _load_piper_api()
        if api is None:
            return False
        voice_obj = self._api_voice(voice)
        if voice_obj is None:
            return False
        synthesis_config = api[1](length_scale=length_scale)
        temporary = output.with_name(f"{output.stem}-api-{uuid.uuid4().hex[:8]}.wav")
        try:
            with self._synth_lock, wave.open(str(temporary), "wb") as handle:
                voice_obj.synthesize_wav(  # type: ignore[attr-defined]
                    text, handle, syn_config=synthesis_config
                )
            if not temporary.exists() or temporary.stat().st_size <= 44:
                return False
            temporary.replace(output)
            return True
        except Exception:
            return False
        finally:
            if temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass

    def _run_piper(
        self, text: str, voice: str, output: Path, length_scale: float
    ) -> None:
        if self._run_piper_api(text, voice, output, length_scale):
            return
        model, _ = self._voice_files(voice)
        command = [*self._find_command(), "--model", str(model)]
        command.extend([self._output_flag, str(output)])
        if self._length_flag:
            command.extend([self._length_flag, f"{length_scale:.3f}"])
        try:
            result = subprocess.run(
                command,
                input=text,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=SETTINGS.tts_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TTSError("Piper took too long to generate the audio.") from exc
        except OSError as exc:
            raise TTSError(f"Could not run Piper: {exc}") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()[-600:]
            raise TTSError(f"Piper failed to synthesize: {detail}")
        if not output.exists() or output.stat().st_size == 0:
            raise TTSError("Piper did not produce a valid audio file.")

    @staticmethod
    def _read_wav(path: Path) -> tuple[wave._wave_params, bytes]:
        with wave.open(str(path), "rb") as handle:
            params = handle.getparams()
            frames = handle.readframes(handle.getnframes())
        return params, frames

    def _concat_with_ffmpeg(
        self, paths: list[Path], output: Path, frame_rate: int
    ) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise TTSError(
                "The voices use different sample rates and FFmpeg is not "
                "installed. Install ffmpeg or use compatible voices."
            )
        command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
        for path in paths:
            command.extend(["-i", str(path)])
        filters = []
        for index in range(len(paths)):
            filters.append(
                f"[{index}:a]aresample={frame_rate},aformat=sample_fmts=s16[a{index}]"
            )
        labels = "".join(f"[a{index}]" for index in range(len(paths)))
        filters.append(f"{labels}concat=n={len(paths)}:v=0:a=1[out]")
        command.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[out]",
                "-ar",
                str(frame_rate),
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(output),
            ]
        )
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            check=False,
        )
        if result.returncode != 0 or not output.exists():
            detail = (result.stderr or "").strip()[-600:]
            raise TTSError(f"FFmpeg failed to concatenate the audio files: {detail}")

    def _concat_wavs(
        self, paths: list[Path], output: Path, gap_ms: int = 120
    ) -> Path | None:
        paths = [path for path in paths if path.exists() and path.stat().st_size > 0]
        if not paths:
            return None
        output.parent.mkdir(parents=True, exist_ok=True)
        if len(paths) == 1:
            shutil.copy2(paths[0], output)
            return output

        params, _first_frames = self._read_wav(paths[0])
        compatible = True
        all_frames: list[bytes] = []
        for index, path in enumerate(paths):
            current_params, frames = self._read_wav(path)
            if (
                current_params.nchannels != params.nchannels
                or current_params.sampwidth != params.sampwidth
                or current_params.framerate != params.framerate
            ):
                compatible = False
                break
            if index:
                silence_size = (
                    int(params.framerate * gap_ms / 1000)
                    * params.nchannels
                    * params.sampwidth
                )
                all_frames.append(b"\x00" * silence_size)
            all_frames.append(frames)
        if not compatible:
            self._concat_with_ffmpeg(paths, output, params.framerate)
            return output

        with wave.open(str(output), "wb") as handle:
            handle.setparams(params)
            for frames in all_frames:
                handle.writeframes(frames)
        return output

    def _synthesize_chunked(
        self,
        text: str,
        voice: str,
        lang: str,
        output: Path,
        length_scale: float = 1.0,
    ) -> Path | None:
        cleaned = self.clean_for_tts(text, lang)
        if not cleaned:
            return None
        chunks = self._split_chunks(cleaned)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TTS_CACHE_DIR) as temp_dir:
            chunk_paths: list[Path] = []
            for index, chunk in enumerate(chunks):
                chunk_path = Path(temp_dir) / f"chunk-{index:03d}.wav"
                self._run_piper(chunk, voice, chunk_path, length_scale)
                chunk_paths.append(chunk_path)
            return self._concat_wavs(chunk_paths, output, gap_ms=80)

    def synthesize_plain(
        self,
        text: str,
        voice: str,
        lang: str = "en",
        slow: bool = False,
    ) -> Path | None:
        cleaned = self.clean_for_tts(text, lang)
        if not cleaned:
            return None
        ensure_directories()
        length_scale = 1.3 if slow else 1.0
        key = _hash_key(cleaned, voice, lang, f"{length_scale:.2f}")
        output = TTS_CACHE_DIR / f"plain-{voice}-{key}.wav"
        if output.exists() and output.stat().st_size > 0:
            return output
        return self._synthesize_chunked(
            cleaned, voice, lang, output, length_scale=length_scale
        )

    def _pt_segments(self, pt_text: str) -> list[Segment]:
        segments: list[Segment] = []
        for raw_line in (pt_text or "").splitlines():
            line = raw_line.strip()
            if (
                not line
                or HEADER_RE.match(line)
                or HEADER_EN_RE.match(line)
                or HEADER_ANY_RE.match(line)
            ):
                continue
            line = re.sub(r"^\s*[-*•]\s*", "", line).strip()
            plain = _clean_inline(line)
            if not plain:
                continue
            lowered = plain.casefold()
            if lowered.startswith(
                ("palavra em português", "palavra em portugues", "native expression")
            ):
                continue

            if lowered.startswith(("exemplo", "example", "ejemplo")):
                quoted = QUOTED_RE.search(plain)
                if quoted:
                    segments.append(Segment("Por exemplo,", "pt", "note"))
                    segments.append(Segment(quoted.group(1), "en", "note"))
                    rest = plain[quoted.end() :].strip(" -–—:;")
                    if rest:
                        segments.append(Segment(rest, "pt", "note"))
                    continue

            if ARROW_RE.search(plain) and not lowered.startswith(
                ("explicação", "explicacao", "correção", "correcao", "explanation")
            ):
                left, right = ARROW_RE.split(plain, maxsplit=1)
                left = _clean_inline(left)
                right = _clean_inline(right)
                if left and right and len(left) <= 80 and len(right) <= 140:
                    segments.append(Segment(f"{left}. Em inglês,", "pt", "note"))
                    segments.append(Segment(right, "en", "note"))
                    continue

            segments.append(Segment(plain, "pt", "note"))

        if segments:
            segments.insert(0, Segment("Agora, a explicação.", "pt", "note"))
        return segments

    def _en_note_segments(self, note_text: str) -> list[Segment]:
        segments: list[Segment] = []
        for raw_line in (note_text or "").splitlines():
            line = raw_line.strip()
            if (
                not line
                or HEADER_RE.match(line)
                or HEADER_EN_RE.match(line)
                or HEADER_ANY_RE.match(line)
            ):
                continue
            line = re.sub(r"^\s*[-*•]\s*", "", line).strip()
            plain = _clean_inline(line)
            if not plain:
                continue
            lowered = plain.casefold()

            if lowered.startswith(("example", "exemplo", "ejemplo")):
                quoted = QUOTED_RE.search(plain)
                if quoted:
                    segments.append(Segment("For example,", "en", "note"))
                    segments.append(Segment(quoted.group(1), "en", "note"))
                    rest = plain[quoted.end() :].strip(" -–—:;")
                    if rest:
                        segments.append(Segment(rest, "pt", "note"))
                    continue

            if lowered.startswith(("explanation", "explicação", "explicacion")):
                rest = re.sub(
                    r"(?i)^(explanation|explicação|explicacao|explicación|explicacion)\s*:?\s*",
                    "",
                    plain,
                ).strip()
                if rest:
                    segments.append(Segment(f"Explanation. {rest}", "en", "note"))
                continue

            if ARROW_RE.search(plain):
                left, right = ARROW_RE.split(plain, maxsplit=1)
                left = _clean_inline(left)
                right = _clean_inline(right)
                if left and right and len(left) <= 90 and len(right) <= 160:
                    segments.append(Segment(f"In Portuguese, {left}.", "pt", "note"))
                    segments.append(Segment(f"In English, {right}.", "en", "note"))
                    continue

            segments.append(Segment(plain, "en", "note"))

        if segments:
            segments.insert(0, Segment("Here is a quick note.", "en", "note"))
        return segments

    def _note_segments(
        self,
        note_text: str,
        note_lang: str,
        target_lang: str,
        main_lang: str = "en",
    ) -> list[Segment]:
        note_lang = normalize_language_code(note_lang) or "pt"
        target_lang = normalize_language_code(target_lang) or "en"
        main_lang = normalize_language_code(main_lang) or "en"
        if note_lang == "pt" and target_lang == "en":
            segments = self._pt_segments(note_text)
            return segments
        if note_lang == "en" and target_lang == "pt":
            segments = self._en_note_segments(note_text)
            return segments
        # For notes teaching target when main is native, PT target, EN native
        if note_lang == "en" and target_lang == "pt":
            segments = self._en_note_segments(note_text)
            return segments
        cleaned = self.clean_for_tts(note_text, note_lang)
        if not cleaned:
            return []
        return [Segment(cleaned, note_lang, "note")]

    def build_segments(
        self,
        main_text: str,
        note_text: str,
        main_lang: str = "en",
        note_lang: str | None = None,
        target_lang: str | None = None,
        native_lang: str | None = None,
    ) -> list[Segment]:
        main_lang = normalize_language_code(main_lang) or "en"
        target_lang = normalize_language_code(target_lang) or main_lang
        native_lang = normalize_language_code(native_lang) or (
            "pt" if main_lang == "en" else "en"
        )
        note_lang = normalize_language_code(note_lang) or (
            target_lang
            if main_lang == native_lang and native_lang != target_lang
            else native_lang
        )
        segments: list[Segment] = []
        main_clean = self.clean_for_tts(main_text, main_lang)
        if main_clean:
            segments.append(Segment(main_clean, main_lang, "main"))
        if note_text:
            segments.extend(
                self._note_segments(note_text, note_lang, target_lang, main_lang)
            )
        return segments

    def synthesize_hybrid(
        self,
        en_text: str,
        pt_text: str,
        en_voice: str,
        pt_voice: str,
        main_lang: str = "en",
        note_lang: str | None = None,
        target_lang: str | None = None,
        native_lang: str | None = None,
        main_voice: str | None = None,
        note_voice: str | None = None,
    ) -> TTSBundle:
        ensure_directories()
        main_lang_n = normalize_language_code(main_lang) or "en"
        target_lang_n = normalize_language_code(target_lang) or main_lang_n
        native_lang_n = normalize_language_code(native_lang) or (
            "pt" if main_lang_n == "en" else "en"
        )
        note_lang_n = normalize_language_code(note_lang) or (
            target_lang_n
            if main_lang_n == native_lang_n and native_lang_n != target_lang_n
            else native_lang_n
        )
        main_voice_n = main_voice or en_voice
        note_voice_n = note_voice or pt_voice
        segments = self.build_segments(
            en_text,
            pt_text,
            main_lang_n,
            note_lang_n,
            target_lang_n,
            native_lang_n,
        )
        if not segments:
            return TTSBundle(None, None, None)

        key = _hash_key(
            en_text or "",
            pt_text or "",
            main_voice_n,
            note_voice_n,
            main_lang_n,
            note_lang_n,
            target_lang_n,
            "hybrid-v3",
        )
        combined_path = AUDIO_DIR / f"combined-{key}.wav"
        english_path = AUDIO_DIR / f"english-{key}.wav"
        portuguese_path = AUDIO_DIR / f"portuguese-{key}.wav"

        main_segments = [item for item in segments if item.group == "main"]
        note_segments = [item for item in segments if item.group == "note"]
        if (
            combined_path.exists()
            and (not main_segments or english_path.exists())
            and (not note_segments or portuguese_path.exists())
        ):
            return TTSBundle(
                combined_path,
                english_path if main_segments else None,
                portuguese_path if note_segments else None,
            )

        with tempfile.TemporaryDirectory(dir=TTS_CACHE_DIR) as temp_dir:
            temp = Path(temp_dir)
            rendered: list[tuple[Segment, Path]] = []
            for index, segment in enumerate(segments):
                if segment.group == "main":
                    voice = main_voice_n
                else:
                    # Special PT note case expects target en for quotes
                    if (
                        note_lang_n == "pt"
                        and target_lang_n == "en"
                        or note_lang_n == "en"
                        and target_lang_n == "pt"
                    ):
                        voice = en_voice if segment.lang == "en" else pt_voice
                    else:
                        voice = (
                            note_voice_n
                            if segment.lang == note_lang_n
                            else main_voice_n
                        )
                output = temp / f"segment-{index:03d}.wav"
                path = self._synthesize_chunked(
                    segment.text, voice, segment.lang, output, length_scale=1.0
                )
                if path:
                    rendered.append((segment, path))

            if not rendered:
                return TTSBundle(None, None, None)

            main_paths = [path for segment, path in rendered if segment.group == "main"]
            note_paths = [path for segment, path in rendered if segment.group == "note"]

            english = self._concat_wavs(main_paths, english_path, gap_ms=120)
            portuguese = self._concat_wavs(note_paths, portuguese_path, gap_ms=120)
            combined_paths = []
            if english:
                combined_paths.append(english)
            if portuguese:
                combined_paths.append(portuguese)
            combined = self._concat_wavs(combined_paths, combined_path, gap_ms=350)
            return TTSBundle(combined, english, portuguese)

    def synthesize_note(
        self,
        note_text: str,
        note_lang: str,
        en_voice: str,
        pt_voice: str,
        target_lang: str | None = None,
        target_voice: str | None = None,
        native_voice: str | None = None,
        native_lang: str | None = None,
        main_voice: str | None = None,
    ) -> Path | None:
        note_lang_n = normalize_language_code(note_lang) or "pt"
        target_lang_n = normalize_language_code(target_lang) or (
            "en" if note_lang_n != "en" else "pt"
        )
        native_lang_n = normalize_language_code(native_lang) or note_lang_n
        main_voice_n = main_voice or (target_voice or en_voice)
        note_voice_n = native_voice or pt_voice
        if note_lang_n == "pt" and target_lang_n == "en":
            note_voice_n = pt_voice
            main_voice_n = en_voice
        elif note_lang_n == "en" and target_lang_n == "pt":
            note_voice_n = en_voice
            main_voice_n = pt_voice
        bundle = self.synthesize_hybrid(
            "",
            note_text,
            main_voice_n,
            note_voice_n,
            main_lang=target_lang_n,
            note_lang=note_lang_n,
            target_lang=target_lang_n,
            native_lang=native_lang_n,
            main_voice=main_voice_n,
            note_voice=note_voice_n,
        )
        return bundle.combined

    def synthesize_portuguese_block(
        self, pt_text: str, en_voice: str, pt_voice: str
    ) -> Path | None:
        return self.synthesize_note(pt_text, "pt", en_voice, pt_voice)
