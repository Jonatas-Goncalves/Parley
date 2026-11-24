from __future__ import annotations

import json

import pytest

from parley.core import model_manager


class FakeResponse:
    def __init__(self, lines: list[dict]) -> None:
        self._lines = [json.dumps(line).encode("utf-8") for line in lines]

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_exc) -> None:
        return None

    def __iter__(self):
        return iter(self._lines)


def test_pull_progress_accepts_total_without_completed() -> None:
    status, completed, total = model_manager._pull_progress(
        {"status": "pulling manifest", "total": 4096}
    )
    assert status == "pulling manifest"
    assert completed is None
    assert total == 4096.0


def test_pull_progress_reads_completed_bytes() -> None:
    status, completed, total = model_manager._pull_progress(
        {"status": "pulling layer", "completed": 1024, "total": 4096}
    )
    assert status == "pulling layer"
    assert completed == 1024.0
    assert total == 4096.0


def test_pull_survives_lines_without_completed(monkeypatch) -> None:
    lines = [
        {"status": "pulling manifest"},
        {"status": "pulling layer", "total": 2048},
        {"status": "pulling layer", "completed": 1024, "total": 2048},
        {"status": "success"},
    ]
    monkeypatch.setattr(
        model_manager, "_request", lambda *_args, **_kwargs: FakeResponse(lines)
    )
    events: list[tuple[int, str]] = []
    model_manager.pull_ollama_model("qwen2.5:test", progress=lambda p, m: events.append((p, m)))
    assert events[0][0] == 0
    assert any(percent == 50 for percent, _message in events)
    assert events[-1][0] == 100


def test_pull_stops_when_superseded(monkeypatch) -> None:
    monkeypatch.setattr(
        model_manager,
        "_request",
        lambda *_args, **_kwargs: FakeResponse([{"status": "pulling"}]),
    )
    with pytest.raises(model_manager.PullCancelled):
        model_manager.pull_ollama_model(
            "qwen2.5:test", should_stop=lambda: True
        )
