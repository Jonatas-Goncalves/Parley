"""Audio capture, voice activity detection and playback.

The module never imports GTK. Everything here runs on worker threads and is
driven by the GTK layer through callbacks.
"""

from __future__ import annotations

from .pipeline import ConversationEngine, EngineEvent
from .player import AudioPlayer, play_blocking
from .recorder import MicrophoneError, Recorder

__all__ = [
    "AudioPlayer",
    "ConversationEngine",
    "EngineEvent",
    "MicrophoneError",
    "Recorder",
    "play_blocking",
]
