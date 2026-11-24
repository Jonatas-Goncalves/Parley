"""Detection and automatic startup of the local LLM backend.

The runtime has no interface code, so the desktop UI and the command line tools
reuse the same logic.

Startup priority:
1. an explicit user choice
2. an Ollama server that is already running
3. a llama.cpp server that is already running
4. start the preferred/default backend (Ollama)
"""

from __future__ import annotations

import logging
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import model_manager, startup_state
from .config import SETTINGS, Settings
from .hardware import detect, profile_dict

logger = logging.getLogger(__name__)


@dataclass
class Snapshot:
    state: str = "idle"
    message: str = ""
    percent: int = 0
    backend: str = ""
    base_url: str = ""
    model: str = ""
    error: str = ""
    note: str = ""
    hardware: dict[str, object] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.state == "running"


class BackendRuntime:
    def __init__(self, settings: Settings = SETTINGS) -> None:
        self.settings = settings
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._thread: threading.Thread | None = None
        self._snapshot = Snapshot()
        self._processes: list[subprocess.Popen] = []
        self._stop_requested = False
        self._managed_llamacpp = False

    # -- state -----------------------------------------------------------
    def snapshot(self) -> Snapshot:
        with self._lock:
            data = Snapshot(**self._snapshot.__dict__)
        return data

    def _set(
        self,
        state: str | None = None,
        message: str | None = None,
        percent: int | None = None,
        **changes: object,
    ) -> None:
        with self._condition:
            if self._stop_requested and state in ("starting", "downloading", "running"):
                return
            if state is not None:
                self._snapshot.state = state
            if message is not None:
                self._snapshot.message = message
            if percent is not None:
                self._snapshot.percent = max(0, min(100, int(percent)))
            for key, value in changes.items():
                if hasattr(self._snapshot, key):
                    setattr(self._snapshot, key, value)
            self._condition.notify_all()

    def _progress(self, start: int, end: int):
        span = max(1, end - start)

        def report(percent: int, message: str) -> None:
            self._set(
                "downloading",
                message,
                start + int(max(0, min(100, percent)) * span / 100),
            )

        return report

    # -- public API ------------------------------------------------------
    def set_preference(
        self,
        backend: str,
        explicit: bool = True,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        backend = "llamacpp" if backend == "llamacpp" else "ollama"
        changes: dict[str, object] = {
            "backend": backend,
            "backend_explicit": explicit,
        }
        if base_url is not None:
            changes["base_url"] = base_url.strip()
        if model is not None:
            changes["model"] = model.strip()
        startup_state.save(changes)
        with self._lock:
            changed = self._snapshot.backend and self._snapshot.backend != backend
        if changed:
            self.stop()
            with self._lock:
                self._snapshot = Snapshot()

    def start_async(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_requested = False
            self._thread = threading.Thread(
                target=self._run,
                name="parley-backend",
                daemon=True,
            )
            self._thread.start()

    def busy(self) -> bool:
        """Return True while a previous backend worker is still running."""

        with self._lock:
            return bool(self._thread and self._thread.is_alive())

    def ensure(self, wait: bool = True, timeout: float = 240.0) -> Snapshot:
        self.start_async()
        if not wait:
            return self.snapshot()
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._snapshot.state not in ("running", "error"):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(min(0.5, remaining))
            return Snapshot(**self._snapshot.__dict__)

    def stop(self) -> None:
        with self._lock:
            self._stop_requested = True
            processes = list(self._processes)
            self._processes.clear()
            self._managed_llamacpp = False
        for process in processes:
            logger.info("Stopping managed backend process pid=%s", getattr(process, "pid", "?"))
            _terminate(process)
        with self._condition:
            self._snapshot = Snapshot(state="idle")
            self._condition.notify_all()

    # -- worker ----------------------------------------------------------
    def _run(self) -> None:
        try:
            config = startup_state.load()
            preferred = str(config.get("backend") or "ollama").lower()
            explicit = bool(config.get("backend_explicit"))
            hardware = profile_dict(detect())

            ollama_up = model_manager.ollama_online(self.settings.ollama_url)
            llama_up = self._llamacpp_online(self.settings.llama_cpp_url)

            if explicit:
                chosen = preferred
            elif ollama_up:
                chosen = "ollama"
            elif llama_up:
                chosen = "llamacpp"
            else:
                chosen = preferred

            self._set(hardware=hardware, backend=chosen)
            if chosen == "llamacpp":
                self._run_llamacpp(config)
            else:
                self._run_ollama(config)
        except model_manager.PullCancelled:
            return
        except Exception as exc:  # pragma: no cover - defensive
            message = str(exc) or exc.__class__.__name__
            self._set("error", message, 100, error=message)

    def _run_ollama(self, config: dict[str, object]) -> None:
        base_url = str(config.get("base_url") or "").strip()
        if not base_url or "11434" not in base_url:
            base_url = self.settings.ollama_url
        self._set(
            "starting",
            "Checking Ollama…",
            2,
            backend="ollama",
            base_url=base_url,
            model="",
            error="",
        )

        if not model_manager.ollama_online(base_url):
            binary = shutil.which("ollama")
            if not binary:
                raise RuntimeError(
                    "Ollama is not installed. Run ./setup.sh, or install Ollama "
                    "from https://ollama.com and try again."
                )
            self._set("starting", "Starting Ollama…", 5)
            process = subprocess.Popen(
                [binary, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            with self._lock:
                self._processes.append(process)
            started = time.monotonic()
            deadline = started + 45
            while time.monotonic() < deadline:
                if model_manager.ollama_online(base_url):
                    break
                if process.poll() is not None and not model_manager.ollama_online(
                    base_url
                ):
                    raise RuntimeError(
                        "Ollama stopped while starting. Run `ollama serve` in a "
                        "terminal to see the error."
                    )
                elapsed = time.monotonic() - started
                self._set(
                    "starting",
                    "Starting Ollama…",
                    min(18, 5 + int(elapsed / 2)),
                )
                time.sleep(0.5)
            if not model_manager.ollama_online(base_url):
                raise RuntimeError(
                    "Ollama did not become ready in time. Run `ollama serve` "
                    "in a terminal and try again."
                )

        self._set("downloading", "Ollama is online. Checking the model…", 20)
        profile = detect()
        tier = str(config.get("model_tier") or "").strip()
        spec = model_manager.for_tier(tier) if tier else model_manager.recommend(profile)
        installed = model_manager.list_ollama_models(base_url)
        configured = str(config.get("model") or "").strip()
        if configured and model_manager._model_present(configured, installed):
            model = configured
            self._set(
                "running",
                f"Ollama ready with {model}.",
                100,
                backend="ollama",
                base_url=base_url,
                model=model,
            )
            return

        model = model_manager.ensure_ollama_model(
            spec,
            base_url,
            self._progress(20, 96),
            should_stop=lambda: self._stop_requested,
        )
        self._set(
            "running",
            f"Ollama ready with {model}.",
            100,
            backend="ollama",
            base_url=base_url,
            model=model,
        )

    def _run_llamacpp(self, config: dict[str, object]) -> None:
        base_url = str(config.get("base_url") or "").strip()
        if not base_url:
            base_url = self.settings.llama_cpp_url
        profile = detect()
        tier = str(config.get("model_tier") or "").strip()
        spec = model_manager.for_tier(tier) if tier else model_manager.recommend(profile)
        custom_gguf = str(config.get("custom_gguf_path") or "").strip()
        custom_path = Path(custom_gguf).expanduser() if custom_gguf else None
        use_custom = bool(custom_path and custom_path.is_file())

        logger.info(
            "llamacpp start: tier=%s model=%s custom=%s base_url=%s",
            tier, spec.gguf_file, custom_path if use_custom else "", base_url,
        )
        self._set(
            "starting",
            "Checking llama.cpp…",
            2,
            backend="llamacpp",
            base_url=base_url,
            model="",
            error="",
        )

        external = self._llamacpp_online(base_url)
        if external and not use_custom:
            models = self._llamacpp_models(base_url)
            if models:
                model = models[0]
                wanted = spec.gguf_file.lower()
                model_lower = model.lower()
                matches_tier = wanted in model_lower or Path(model_lower).name == wanted
                if matches_tier:
                    note = ""
                    if not spec.gguf_path.exists():
                        note = (
                            "llama.cpp is already running. The recommended GGUF is "
                            "being downloaded for the next managed start."
                        )
                        self._background_download(spec)
                    logger.info("Attaching to existing llama.cpp server: %s", model)
                    self._set(
                        "running",
                        f"llama.cpp ready with {model}.",
                        100,
                        backend="llamacpp",
                        base_url=base_url,
                        model=model,
                        note=note,
                    )
                    return
                logger.info(
                    "llama.cpp at %s is serving %s but tier %s wants %s; starting managed server",
                    base_url, model, tier, spec.gguf_file,
                )
                self._set(
                    "starting",
                    f"Running llama.cpp serves a different model ({model}); starting {spec.gguf_file}…",
                    3,
                    backend="llamacpp",
                    base_url=base_url,
                )

        binary = self._find_llama_server()
        if not binary:
            raise RuntimeError(
                "llama-server was not found. Run ./setup.sh --backend llamacpp, "
                "or install llama.cpp from your distribution."
            )

        if use_custom:
            self._set("starting", f"Using custom GGUF: {custom_path.name}…", 10)
            model_path = custom_path
        else:
            self._set("downloading", "Preparing the llama.cpp model…", 5)
            model_manager.ensure_gguf(
                spec,
                self._progress(5, 78),
                should_stop=lambda: self._stop_requested,
            )
            if self._stop_requested:
                return
            model_path = spec.gguf_path

        port = 8080
        if external:
            port = _find_free_port(8081)
        command = model_manager.llama_server_command(
            spec, profile, port=port, context=4096, model_path=model_path
        )
        command[0] = binary
        model_label = custom_path.name if use_custom and custom_path else spec.gguf_file
        self._set(
            "starting",
            f"Starting llama.cpp with {model_label}…",
            82,
            base_url=f"http://127.0.0.1:{port}/v1",
        )
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with self._lock:
            self._processes.append(process)
            self._managed_llamacpp = True

        target_url = f"http://127.0.0.1:{port}/v1"
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            if self._llamacpp_online(target_url):
                models = self._llamacpp_models(target_url)
                model = models[0] if models else spec.gguf_file
                self._set(
                    "running",
                    f"llama.cpp ready with {model}.",
                    100,
                    backend="llamacpp",
                    base_url=target_url,
                    model=model,
                )
                return
            if process.poll() is not None:
                raise RuntimeError(
                    "llama-server stopped while loading the model. Run "
                    f"`{binary} -m {spec.gguf_path}` in a terminal to see why."
                )
            with self._lock:
                if self._stop_requested:
                    return
            self._set(
                "starting",
                "Loading the model into llama.cpp…",
                min(99, 82 + int((240 - (deadline - time.monotonic())) / 20)),
            )
            time.sleep(1)

        raise RuntimeError(
            "llama.cpp did not become ready in time. Try a smaller model or "
            "check the application log."
        )

    # -- helpers ---------------------------------------------------------
    def _find_llama_server(self) -> str:
        binary = shutil.which("llama-server")
        if binary:
            return binary
        local = Path.home() / ".local" / "share" / "parley" / "bin" / "llama-server"
        if local.exists() and local.is_file():
            return str(local)
        return ""

    def _background_download(self, spec: model_manager.ModelSpec) -> None:
        if spec.gguf_path.exists():
            return

        def worker() -> None:
            try:
                model_manager.ensure_gguf(spec)
            except Exception:
                pass

        threading.Thread(
            target=worker, name="parley-llamacpp-download", daemon=True
        ).start()

    @staticmethod
    def _server_root(base_url: str) -> str:
        value = (base_url or "").strip().rstrip("/")
        value = value.removesuffix("/v1")
        return value

    def _llamacpp_online(self, base_url: str) -> bool:
        root = self._server_root(base_url)
        if not root:
            return False
        try:
            import urllib.request

            with urllib.request.urlopen(f"{root}/v1/models", timeout=1.5) as response:
                return response.status == 200
        except Exception:
            return False

    def _llamacpp_models(self, base_url: str) -> list[str]:
        root = self._server_root(base_url)
        if not root:
            return []
        try:
            import json
            import urllib.request

            with urllib.request.urlopen(f"{root}/v1/models", timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return []
        items = payload.get("data", []) if isinstance(payload, dict) else []
        return [
            str(item.get("id"))
            for item in items
            if isinstance(item, dict) and item.get("id")
        ]


def _terminate(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
    except OSError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            pass


def _find_free_port(start: int) -> int:
    for port in range(start, start + 32):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    return start


RUNTIME = BackendRuntime()
