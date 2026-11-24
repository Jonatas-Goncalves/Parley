"""Microphone capture with optional voice activity detection.

Two capture modes are supported:

``continuous``
    The stream stays open, a VAD groups frames into utterances and calls
    ``on_utterance`` for each finished utterance.

``push-to-talk``
    ``capture_start()`` records, ``capture_stop()`` returns the samples.
"""

from __future__ import annotations

import queue
import threading
import time

import numpy as np

from .vad import Segmenter, SegmenterConfig
from .wave_io import SAMPLE_RATE

FRAME_MS = 30


class MicrophoneError(RuntimeError):
    pass


class Recorder:
    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        on_utterance=None,
        on_level=None,
    ) -> None:
        self.sample_rate = sample_rate
        self.on_utterance = on_utterance
        self.on_level = on_level
        self._segments = max(1, int(sample_rate * FRAME_MS / 1000))
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=240)
        self._stream = None
        self._thread: threading.Thread | None = None
        self._running = threading.Event()
        self._lock = threading.Lock()
        self._segmenter = Segmenter(sample_rate=sample_rate, config=SegmenterConfig())
        self._suppressed = False
        self._ptt = False
        self._ptt_frames: list[np.ndarray] = []
        self._level = 0.0

    # -- lifecycle -------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._running.is_set()

    @property
    def level(self) -> float:
        return self._level

    def start(self) -> None:
        if self._running.is_set():
            return
        try:
            import sounddevice as sd
        except Exception as exc:  # pragma: no cover - depends on the host
            raise MicrophoneError(
                "Audio input requires the sounddevice package and a working "
                "microphone."
            ) from exc

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=self._segments,
                callback=self._callback,
            )
            self._stream.start()
        except Exception as exc:  # pragma: no cover - depends on the host
            self._stream = None
            raise MicrophoneError(str(exc)) from exc

        self._running.set()
        self._thread = threading.Thread(target=self._consume, name="parley-mic", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running.clear()
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        with self._lock:
            self._ptt = False
            self._ptt_frames.clear()
        self._segmenter.reset()
        self._level = 0.0

    # -- modes -----------------------------------------------------------
    def set_suppressed(self, value: bool) -> None:
        """Ignore incoming audio while the tutor is speaking."""

        with self._lock:
            self._suppressed = value
        if value:
            self._segmenter.reset()

    def capture_start(self) -> None:
        with self._lock:
            self._ptt = True
            self._ptt_frames = []
        self._segmenter.reset()

    def capture_stop(self) -> np.ndarray:
        with self._lock:
            self._ptt = False
            frames = self._ptt_frames
            self._ptt_frames = []
        if not frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(frames)

    # -- internals -------------------------------------------------------
    def _callback(self, indata, frames, time_info, status) -> None:
        block = np.array(indata[:, 0], dtype=np.float32, copy=True)
        try:
            self._queue.put_nowait(block)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(block)
            except queue.Full:
                pass

    def _consume(self) -> None:
        while self._running.is_set():
            try:
                frame = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            rms = float(np.sqrt(np.mean(np.square(frame)))) if frame.size else 0.0
            self._level = rms
            if self.on_level:
                try:
                    self.on_level(rms)
                except Exception:
                    pass

            with self._lock:
                ptt = self._ptt
                suppressed = self._suppressed
                if ptt:
                    self._ptt_frames.append(frame)

            if ptt or suppressed:
                continue

            utterance = self._segmenter.feed(frame)
            if utterance is not None and utterance.size and self.on_utterance:
                try:
                    self.on_utterance(utterance)
                except Exception:
                    pass

    def wait_for_speech(self, timeout: float = 0.5) -> float:
        """Convenience helper used by the level meter."""

        time.sleep(timeout)
        return self._level
