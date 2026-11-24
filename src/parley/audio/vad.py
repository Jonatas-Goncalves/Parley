"""Energy based voice activity detection.

The detector adapts to the room noise and groups frames into utterances. It is
deliberately lightweight: no extra model download and no native dependency
beyond numpy.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np


@dataclass
class SegmenterConfig:
    frame_ms: int = 30
    start_frames: int = 3
    end_silence_ms: int = 2500
    min_utterance_ms: int = 350
    max_utterance_ms: int = 30000
    pre_roll_ms: int = 240
    start_ratio: float = 2.8
    floor_ratio: float = 1.35


@dataclass
class Segmenter:
    """Turn a stream of frames into finished utterances."""

    sample_rate: int = 16000
    config: SegmenterConfig = field(default_factory=SegmenterConfig)
    _noise_floor: float = 0.004
    _speaking: bool = False
    _speech_frames: int = 0
    _silence_frames: int = 0
    _frames: list[np.ndarray] = field(default_factory=list)
    _pre_roll: deque = field(default_factory=lambda: deque(maxlen=8))
    _total_frames: int = 0

    def __post_init__(self) -> None:
        frame_samples = max(1, int(self.sample_rate * self.config.frame_ms / 1000))
        self._max_frames = int(self.config.max_utterance_ms / self.config.frame_ms)
        self._min_frames = int(self.config.min_utterance_ms / self.config.frame_ms)
        self._end_frames = int(self.config.end_silence_ms / self.config.frame_ms)
        self._pre_roll = deque(maxlen=max(1, int(self.config.pre_roll_ms / self.config.frame_ms)))
        self._frame_samples = frame_samples

    @property
    def speaking(self) -> bool:
        return self._speaking

    @property
    def level(self) -> float:
        if not self._frames:
            return 0.0
        block = np.concatenate(self._frames[-3:])
        return float(np.sqrt(np.mean(np.square(block)))) if block.size else 0.0

    def reset(self) -> None:
        self._speaking = False
        self._speech_frames = 0
        self._silence_frames = 0
        self._frames.clear()
        self._pre_roll.clear()

    def feed(self, frame: np.ndarray) -> np.ndarray | None:
        frame = np.asarray(frame, dtype=np.float32).reshape(-1)
        if frame.size == 0:
            return None
        rms = float(np.sqrt(np.mean(np.square(frame))))
        self._total_frames += 1

        if not self._speaking:
            # Rise slowly, fall quickly: keeps the floor at the quiet level.
            if rms < self._noise_floor:
                self._noise_floor = 0.9 * self._noise_floor + 0.1 * rms
            else:
                self._noise_floor += (rms - self._noise_floor) * 0.002
            self._noise_floor = max(0.0015, min(self._noise_floor, 0.05))

        threshold = max(0.006, self._noise_floor * self.config.start_ratio)
        loud = rms >= threshold

        if not self._speaking:
            self._pre_roll.append(frame)
            if loud:
                self._speech_frames += 1
                if self._speech_frames >= self.config.start_frames:
                    self._speaking = True
                    self._silence_frames = 0
                    self._frames = list(self._pre_roll)
                    self._pre_roll.clear()
            else:
                self._speech_frames = 0
            return None

        self._frames.append(frame)
        if loud:
            self._silence_frames = 0
        else:
            self._silence_frames += 1

        long_enough = len(self._frames) >= self._min_frames
        if long_enough and self._silence_frames >= self._end_frames:
            return self._finish()
        if len(self._frames) >= self._max_frames:
            return self._finish()
        return None

    def flush(self) -> np.ndarray | None:
        if self._speaking and len(self._frames) >= self._min_frames:
            return self._finish()
        self.reset()
        return None

    def _finish(self) -> np.ndarray:
        audio = np.concatenate(self._frames) if self._frames else np.zeros(0, dtype=np.float32)
        # Drop the trailing silence so the clip ends where the speech ends.
        keep = max(0, len(audio) - self._silence_frames * self._frame_samples)
        audio = audio[:keep] if keep else audio
        self.reset()
        return audio
