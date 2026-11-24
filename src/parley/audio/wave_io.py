"""Small helpers to read and write audio without external binaries."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000


def write_wav(path: str | Path, samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> Path:
    """Write mono float32 samples in [-1, 1] as a 16-bit PCM wav file."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(samples, dtype=np.float32).reshape(-1)
    data = np.clip(data, -1.0, 1.0)
    pcm = (data * 32767.0).astype("<i2")
    with wave.open(str(target), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return target


def read_audio(path: str | Path) -> tuple[np.ndarray, int]:
    """Return mono float32 samples and the sample rate."""

    try:
        import soundfile as sf

        data, rate = sf.read(str(path), dtype="float32", always_2d=False)
        if getattr(data, "ndim", 1) > 1:
            data = data.mean(axis=1)
        return np.asarray(data, dtype=np.float32), int(rate)
    except Exception:
        pass

    try:
        import miniaudio

        decoded = miniaudio.decode_file(str(path))
        data = np.frombuffer(decoded.samples, dtype=np.int16).astype(np.float32)
        data /= 32768.0
        if decoded.nchannels > 1:
            data = data.reshape(-1, decoded.nchannels).mean(axis=1)
        return data, int(decoded.sample_rate)
    except Exception as exc:  # pragma: no cover - depends on optional packages
        raise RuntimeError(f"Could not decode audio file: {exc}") from exc


def resample(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate or samples.size == 0:
        return samples
    ratio = target_rate / float(source_rate)
    count = max(1, int(round(samples.size * ratio)))
    positions = np.linspace(0, samples.size - 1, count, dtype=np.float64)
    return np.interp(positions, np.arange(samples.size), samples).astype(np.float32)


def duration_seconds(path: str | Path) -> float:
    try:
        import soundfile as sf

        info = sf.info(str(path))
        if info.samplerate:
            return float(info.frames) / float(info.samplerate)
    except Exception:
        pass
    try:
        samples, rate = read_audio(path)
        return len(samples) / float(rate or SAMPLE_RATE)
    except Exception:
        return 0.0
