"""Audio playback used by the session, pronunciation and story pages."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from .wave_io import read_audio, resample


class AudioPlayer:
    def __init__(self, sample_rate: int = 48000) -> None:
        self.sample_rate = sample_rate
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._position = 0.0
        self._duration = 0.0
        self._speed = 1.0
        self._path: Path | None = None
        self._paused = False
        self.on_position = None
        self.on_done = None

    # -- public API ------------------------------------------------------
    @property
    def playing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def position(self) -> float:
        return self._position

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def speed(self) -> float:
        return self._speed

    def load(self, path: str | Path) -> float:
        self.stop()
        self._path = Path(path)
        try:
            samples, rate = read_audio(self._path)
            self._duration = len(samples) / float(rate or 1)
        except Exception:
            self._duration = 0.0
        self._position = 0.0
        return self._duration

    def play(
        self,
        path: str | Path | None = None,
        start: float | None = None,
        speed: float | None = None,
    ) -> None:
        if path is not None:
            self.load(path)
        if self._path is None:
            return
        if start is not None:
            self._position = max(0.0, min(start, self._duration))
        elif self._duration > 0 and self._position >= self._duration - 0.05:
            # Pressing play after the clip finished restarts from the beginning.
            self._position = 0.0
        if speed is not None:
            self._speed = max(0.5, min(1.5, float(speed)))
        self.stop(keep_position=True)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="parley-player", daemon=True)
        self._thread.start()

    def pause(self) -> None:
        if self.playing:
            self._stop.set()
            self._paused = True

    def resume(self) -> None:
        if self._paused:
            self._paused = False
            self.play(start=self._position)

    def toggle(self) -> None:
        if self.playing:
            self.pause()
        elif self._paused:
            self.resume()
        else:
            self.play(start=self._position)

    def seek(self, seconds: float) -> None:
        self._position = max(0.0, min(seconds, self._duration))
        if self.playing:
            self.play(start=self._position)

    def set_speed(self, speed: float) -> None:
        self._speed = max(0.5, min(1.5, float(speed)))
        if self.playing:
            self.play(start=self._position)

    def stop(self, keep_position: bool = False) -> None:
        self._stop.set()
        try:
            import sounddevice as sd

            sd.stop()
        except Exception:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None
        if not keep_position:
            self._position = 0.0
            self._paused = False

    # -- worker ----------------------------------------------------------
    def _run(self) -> None:
        try:
            import sounddevice as sd

            samples, rate = read_audio(self._path)
            speed = max(0.5, min(1.5, self._speed))
            if speed != 1.0:
                samples = resample(samples, rate, int(rate / speed))
                rate = int(rate / speed)
            offset = int(self._position * rate)
            samples = samples[offset:]
            if samples.size == 0:
                self._position = self._duration
                return
            clip_seconds = len(samples) / float(rate)
            sd.play(samples, rate, blocking=False)
            started = time.monotonic()
            while not self._stop.is_set():
                elapsed = time.monotonic() - started
                if elapsed >= clip_seconds:
                    break
                if self.on_position:
                    try:
                        self.on_position(
                            min(self._duration, self._position + elapsed),
                            self._duration,
                        )
                    except Exception:
                        pass
                time.sleep(0.1)
            if not self._stop.is_set():
                self._position = self._duration
        except Exception:
            pass
        finally:
            try:
                import sounddevice as sd

                sd.stop()
            except Exception:
                pass
            if self.on_done:
                try:
                    self.on_done()
                except Exception:
                    pass

    def _finish(self) -> None:
        try:
            import sounddevice as sd

            sd.stop()
        except Exception:
            pass
        if not self._stop.is_set():
            self._position = self._duration
        if self.on_done:
            try:
                self.on_done()
            except Exception:
                pass


def play_blocking(path: str | Path) -> None:
    player = AudioPlayer()
    player.play(path)
    while player.playing:
        time.sleep(0.05)
    player.stop(keep_position=True)
