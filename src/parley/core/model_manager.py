"""Hardware-aware model catalogue and download helpers.

This module is intentionally limited to the Python standard library so it can
also run from ``setup.sh`` before the application virtual environment exists.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import startup_state
from .config import MODELS_DIR, SETTINGS
from .hardware import HardwareProfile, detect, profile_dict, recommend_gpu_layers

Progress = Callable[[int, str], None]
ShouldStop = Callable[[], bool]


class PullCancelled(RuntimeError):
    """Raised when a running pull is superseded by another model choice."""


@dataclass(frozen=True)
class ModelSpec:
    name: str
    label: str
    size_gb: float
    min_ram_gb: float
    ollama_tag: str
    gguf_file: str
    gguf_url: str
    description: str = ""
    tier: str = ""
    gguf_files: tuple[str, ...] = ()
    gguf_urls: tuple[str, ...] = ()

    @property
    def gguf_path(self) -> Path:
        return MODELS_DIR / "gguf" / self.gguf_file

    @property
    def gguf_parts(self) -> tuple[tuple[str, str], ...]:
        if self.gguf_files and self.gguf_urls and len(self.gguf_files) == len(self.gguf_urls):
            return tuple(zip(self.gguf_files, self.gguf_urls, strict=True))
        return ((self.gguf_file, self.gguf_url),)

    @property
    def all_gguf_paths(self) -> tuple[Path, ...]:
        return tuple(MODELS_DIR / "gguf" / name for name, _url in self.gguf_parts)


OLLAMA_BASE_URL = "http://127.0.0.1:11434"
LLAMACPP_BASE_URL = "http://127.0.0.1:8080/v1"

CATALOG: tuple[ModelSpec, ...] = (
    ModelSpec(
        name="qwen2.5-1.5b",
        label="Qwen2.5 1.5B",
        size_gb=1.1,
        min_ram_gb=4.0,
        ollama_tag="qwen2.5:1.5b-instruct-q4_K_M",
        gguf_file="qwen2.5-1.5b-instruct-q4_k_m.gguf",
        gguf_url=(
            "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/"
            "resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
        ),
        description=(
            "Runs on very light computers. Short, simple replies and more "
            "mistakes in grammar and vocabulary."
        ),
        tier="weak",
    ),
    ModelSpec(
        name="qwen2.5-3b",
        label="Qwen2.5 3B",
        size_gb=2.0,
        min_ram_gb=8.0,
        ollama_tag="qwen2.5:3b-instruct-q4_K_M",
        gguf_file="qwen2.5-3b-instruct-q4_k_m.gguf",
        gguf_url=(
            "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/"
            "resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
        ),
        description=(
            "Best balance for 8 GB of RAM. Natural conversations with "
            "occasional slips."
        ),
        tier="medium",
    ),
    ModelSpec(
        name="qwen2.5-7b",
        label="Qwen2.5 7B",
        size_gb=4.7,
        min_ram_gb=16.0,
        ollama_tag="qwen2.5:7b-instruct-q4_K_M",
        gguf_file="qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf",
        gguf_url=(
            "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/"
            "resolve/main/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf"
        ),
        gguf_files=(
            "qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf",
            "qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf",
        ),
        gguf_urls=(
            "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/"
            "resolve/main/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf",
            "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/"
            "resolve/main/qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf",
        ),
        description=(
            "Richest vocabulary and most reliable corrections. Needs 16 GB "
            "of RAM and a faster CPU or a GPU."
        ),
        tier="strong",
    ),
)


def catalog() -> tuple[ModelSpec, ...]:
    return CATALOG


def tier(name: str) -> str:
    for spec in CATALOG:
        if spec.tier == name or spec.name == name:
            return spec.tier
    return ""


def for_tier(name: str) -> ModelSpec:
    for spec in CATALOG:
        if spec.tier == name:
            return spec
    for spec in CATALOG:
        if spec.tier == "medium":
            return spec
    return CATALOG[0]


def recommend(profile: HardwareProfile | None = None) -> ModelSpec:
    profile = profile or detect()
    usable = [spec for spec in CATALOG if spec.min_ram_gb <= max(profile.ram_gb, 0)]
    if not usable:
        return CATALOG[0]
    return usable[-1]


def describe(spec: ModelSpec, profile: HardwareProfile | None = None) -> str:
    profile = profile or detect()
    gpu = (
        f"{profile.gpu_name} ({profile.vram_gb:.1f} GB VRAM)"
        if profile.gpu_name
        else "CPU only"
    )
    return (
        f"{spec.label} · {spec.size_gb:.1f} GB · "
        f"RAM {profile.ram_gb:.1f} GB · {gpu}"
    )


def _dream(progress: Progress | None, percent: int, message: str) -> None:
    if progress:
        progress(max(0, min(100, percent)), message)


def _request(url: str, payload: dict | None = None, timeout: int = 30):
    data = None
    headers = {"User-Agent": "Parley/1.0"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    return urllib.request.urlopen(request, timeout=timeout)


def ollama_online(base_url: str = OLLAMA_BASE_URL, timeout: float = 1.5) -> bool:
    try:
        with _request(f"{base_url.rstrip('/')}/api/tags", timeout=timeout) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError, ValueError):
        return False


def list_ollama_models(base_url: str = OLLAMA_BASE_URL) -> list[str]:
    try:
        with _request(f"{base_url.rstrip('/')}/api/tags", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, ValueError):
        return []
    models = payload.get("models", []) if isinstance(payload, dict) else []
    result: list[str] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("model") or "").strip()
        if name:
            result.append(name)
    return sorted(result)


def _model_present(tag: str, installed: list[str]) -> bool:
    tag = tag.strip()
    if tag in installed:
        return True
    # Ollama may store an implicit ":latest" suffix.
    return f"{tag}:latest" in installed


def is_model_installed(
    spec: ModelSpec,
    backend: str = "ollama",
    base_url: str = OLLAMA_BASE_URL,
) -> bool:
    """Return True when the tier model is already available locally."""

    if backend == "llamacpp":
        return all(p.exists() and p.stat().st_size > 0 for p in spec.all_gguf_paths)
    return _model_present(spec.ollama_tag, list_ollama_models(base_url))


def installed_tiers(
    backend: str = "ollama",
    base_url: str = OLLAMA_BASE_URL,
) -> dict[str, bool]:
    """Check all catalogue tiers in one call (one Ollama request)."""

    if backend == "llamacpp":
        return {
            spec.tier: all(p.exists() and p.stat().st_size > 0 for p in spec.all_gguf_paths)
            for spec in CATALOG
        }
    installed = list_ollama_models(base_url)
    return {
        spec.tier: _model_present(spec.ollama_tag, installed) for spec in CATALOG
    }


def pull_ollama_model(
    tag: str,
    base_url: str = OLLAMA_BASE_URL,
    progress: Progress | None = None,
    should_stop: ShouldStop | None = None,
) -> None:
    """Pull an Ollama model, reporting byte progress when available."""

    _dream(progress, 0, f"Pulling {tag} with Ollama")
    payload = {"model": tag, "stream": True}
    percent = 0
    try:
        with _request(f"{base_url.rstrip('/')}/api/pull", payload, timeout=30) as response:
            for raw_line in response:
                if should_stop is not None and should_stop():
                    raise PullCancelled(tag)
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(data, dict):
                    continue
                if data.get("error"):
                    raise RuntimeError(str(data["error"]))
                status, completed, total = _pull_progress(data)
                message = f"{status} · {tag}"
                if completed is not None and total:
                    percent = int(completed * 100 / total)
                    message = (
                        f"{status} · {tag} "
                        f"({completed / 1024 / 1024:.0f}/{total / 1024 / 1024:.0f} MB)"
                    )
                _dream(progress, percent, message)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Ollama pull failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama is not reachable: {exc.reason}") from exc
    _dream(progress, 100, f"Model {tag} is ready")


def _pull_progress(data: dict[str, object]) -> tuple[str, float | None, float | None]:
    """Read one Ollama pull event without assuming every field is present.

    Ollama sends ``total`` on manifest and layer lines even when ``completed``
    is missing, so both values must be checked before any arithmetic.
    """

    status = str(data.get("status") or "pulling")
    completed = data.get("completed")
    total = data.get("total")
    completed_number = float(completed) if isinstance(completed, (int, float)) else None
    total_number = float(total) if isinstance(total, (int, float)) and total > 0 else None
    if completed_number is not None and total_number is None:
        completed_number = None
    return status, completed_number, total_number


def ensure_ollama_model(
    spec: ModelSpec,
    base_url: str = OLLAMA_BASE_URL,
    progress: Progress | None = None,
    should_stop: ShouldStop | None = None,
) -> str:
    installed = list_ollama_models(base_url)
    if _model_present(spec.ollama_tag, installed):
        _dream(progress, 100, f"Model {spec.ollama_tag} already installed")
        return spec.ollama_tag
    pull_ollama_model(spec.ollama_tag, base_url, progress, should_stop)
    return spec.ollama_tag


def start_ollama_server(wait_seconds: int = 45) -> bool:
    """Start ``ollama serve`` when the binary exists but no server is online."""

    if ollama_online():
        return True
    binary = shutil.which("ollama")
    if not binary:
        return False
    try:
        subprocess.Popen(
            [binary, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return False
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if ollama_online():
            return True
        time.sleep(0.5)
    return False


def _download_file(
    filename: str,
    url: str,
    destination: Path,
    progress: Progress | None = None,
    force: bool = False,
    should_stop: ShouldStop | None = None,
    part_index: int = 0,
    part_count: int = 1,
) -> Path:
    if destination.exists() and destination.stat().st_size > 0 and not force:
        pct = int(((part_index + 1) / max(1, part_count)) * 100)
        _dream(progress, pct, f"Model file already present: {filename}")
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "Parley/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            total = int(response.headers.get("Content-Length") or 0)
            downloaded = 0
            started = time.monotonic()
            with partial.open("wb") as handle:
                while True:
                    if should_stop is not None and should_stop():
                        raise PullCancelled("cancelled")
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        part_fraction = downloaded / total
                    else:
                        part_fraction = min(0.95, downloaded / (5 * 1024 * 1024))
                    overall = ((part_index + part_fraction) / max(1, part_count)) * 100
                    if time.monotonic() - started > 0.15:
                        started = time.monotonic()
                        part_label = (
                            f" (part {part_index + 1}/{part_count})" if part_count > 1 else ""
                        )
                        _dream(
                            progress,
                            int(overall),
                            (
                                f"Downloading {filename}{part_label} · "
                                f"{downloaded / 1024 / 1024:.0f} MB"
                                + (f" / {total / 1024 / 1024:.0f} MB" if total else "")
                            ),
                        )
    except PullCancelled:
        partial.unlink(missing_ok=True)
        raise
    except urllib.error.HTTPError as exc:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"Download failed ({exc.code}) for {url}") from exc
    except urllib.error.URLError as exc:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"Download failed: {exc.reason}") from exc

    partial.replace(destination)
    return destination


def download_gguf(
    spec: ModelSpec,
    progress: Progress | None = None,
    force: bool = False,
    should_stop: ShouldStop | None = None,
) -> Path:
    parts = spec.gguf_parts
    for idx, (filename, url) in enumerate(parts):
        if should_stop is not None and should_stop():
            raise PullCancelled("cancelled")
        _download_file(
            filename,
            url,
            MODELS_DIR / "gguf" / filename,
            progress=progress,
            force=force,
            should_stop=should_stop,
            part_index=idx,
            part_count=len(parts),
        )
    destination = spec.gguf_path
    _dream(progress, 100, f"Model file ready: {destination.name}")
    return destination


def ensure_gguf(
    spec: ModelSpec,
    progress: Progress | None = None,
    should_stop: ShouldStop | None = None,
) -> Path:
    return download_gguf(spec, progress, should_stop=should_stop)


def remove_gguf(spec: ModelSpec) -> bool:
    """Delete downloaded GGUF file(s). Returns True if any file was removed."""
    removed = False
    for path in spec.all_gguf_paths:
        for target in (path, path.with_suffix(path.suffix + ".part")):
            if target.exists():
                target.unlink()
                removed = True
    return removed


def remove_ollama_model(tag: str, base_url: str = OLLAMA_BASE_URL) -> bool:
    """Remove an Ollama model by tag. Returns True on success."""
    payload = {"model": tag}
    try:
        with _request(f"{base_url.rstrip('/')}/api/delete", payload, timeout=30) as response:
            _ = response.read()
            return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise RuntimeError(f"Failed to remove {tag}: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to remove {tag}: {exc.reason}") from exc


def llama_server_command(
    spec: ModelSpec,
    profile: HardwareProfile | None = None,
    port: int = 8080,
    context: int = 4096,
    model_path: Path | None = None,
) -> list[str]:
    profile = profile or detect()
    binary = shutil.which("llama-server")
    if not binary:
        local = Path.home() / ".local" / "share" / "parley" / "bin" / "llama-server"
        binary = str(local) if local.exists() else "llama-server"
    layers = recommend_gpu_layers(spec.size_gb, profile)
    target = model_path or spec.gguf_path
    return [
        binary,
        "-m",
        str(target),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--ctx-size",
        str(context),
        "-ngl",
        str(layers),
        "--parallel",
        "1",
    ]


def _cli_progress(as_json: bool) -> Progress:
    def report(percent: int, message: str) -> None:
        if as_json:
            print(
                json.dumps(
                    {"event": "progress", "percent": percent, "message": message},
                    ensure_ascii=False,
                ),
                flush=True,
            )
        else:
            print(f"[{percent:3d}%] {message}", flush=True)

    return report


def _download_recommended(
    backend: str | None, as_json: bool, force: bool
) -> int:
    profile = detect()
    spec = recommend(profile)
    progress = _cli_progress(as_json)
    if as_json:
        print(
            json.dumps(
                {
                    "event": "plan",
                    "hardware": profile_dict(profile),
                    "model": spec.name,
                    "label": spec.label,
                    "backend": backend or startup_state.get("backend", "ollama"),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    else:
        print(f"Hardware: {profile.summary}", flush=True)
        print(f"Recommended model: {spec.label}", flush=True)

    chosen = (backend or str(startup_state.get("backend", "ollama"))).lower()
    base_url = str(SETTINGS.ollama_url)

    if chosen == "ollama":
        if not ollama_online(base_url):
            print("Ollama is not running; trying to start it…", flush=True)
            if not start_ollama_server():
                print(
                    "Ollama is not available. Downloading the GGUF model instead "
                    "so llama.cpp can use it on first launch.",
                    flush=True,
                )
                ensure_gguf(spec, progress)
                return 0
        try:
            ensure_ollama_model(spec, base_url, progress)
            return 0
        except RuntimeError as exc:
            print(f"Ollama model download failed: {exc}", file=sys.stderr)
            print("Falling back to a direct GGUF download.", file=sys.stderr)
            ensure_gguf(spec, progress)
            return 0

    ensure_gguf(spec, progress)
    return 0


def _print_info(as_json: bool) -> int:
    profile = detect()
    spec = recommend(profile)
    data = {
        "hardware": profile_dict(profile),
        "model": {
            "name": spec.name,
            "label": spec.label,
            "size_gb": spec.size_gb,
            "min_ram_gb": spec.min_ram_gb,
            "ollama_tag": spec.ollama_tag,
            "gguf_path": str(spec.gguf_path),
            "gguf_url": spec.gguf_url,
        },
    }
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"Hardware: {profile.summary}")
        print(f"Recommended model: {spec.label}")
        print(f"Ollama tag: {spec.ollama_tag}")
        print(f"GGUF: {spec.gguf_path}")
        for note in profile.notes:
            print(f"- {note}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parley model manager")
    parser.add_argument(
        "--download-recommended",
        action="store_true",
        help="download the model recommended for this computer",
    )
    parser.add_argument(
        "--backend",
        choices=["ollama", "llamacpp"],
        default=None,
        help="preferred backend for the download",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON lines")
    parser.add_argument("--info", action="store_true", help="show hardware and model")
    parser.add_argument("--force", action="store_true", help="download again")
    args = parser.parse_args(argv)

    if args.info:
        return _print_info(args.json or not sys.stdout.isatty())
    if args.download_recommended:
        return _download_recommended(
            args.backend, args.json or not sys.stdout.isatty(), args.force
        )
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
