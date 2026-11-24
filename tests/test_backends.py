from __future__ import annotations

from parley.core.backends import BackendRuntime, Snapshot, _find_free_port


def test_snapshot_ready_only_when_running() -> None:
    assert Snapshot().ready is False
    assert Snapshot(state="starting").ready is False
    assert Snapshot(state="running").ready is True


def test_server_root_accepts_openai_style_urls() -> None:
    assert BackendRuntime._server_root("http://127.0.0.1:8080/v1") == "http://127.0.0.1:8080"
    assert BackendRuntime._server_root("http://127.0.0.1:8080/v1/") == "http://127.0.0.1:8080"
    assert BackendRuntime._server_root("http://127.0.0.1:8080") == "http://127.0.0.1:8080"
    assert BackendRuntime._server_root("") == ""


def test_find_free_port_returns_a_port() -> None:
    assert 8080 <= _find_free_port(8080) < 8112


def test_stop_without_start_is_safe() -> None:
    runtime = BackendRuntime()
    runtime.stop()
    assert runtime.snapshot().state in ("idle", "running", "error")
