"""Hardware detection and local model recommendations."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class HardwareProfile:
    ram_gb: float
    cpu_count: int
    cpu_name: str = ""
    gpu_name: str = ""
    gpu_vendor: str = ""
    vram_gb: float = 0.0
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def usable_gpu(self) -> bool:
        return self.vram_gb >= 6.0

    @property
    def summary(self) -> str:
        gpu = f"{self.gpu_name} ({self.vram_gb:.1f} GB VRAM)" if self.gpu_name else "no GPU detected"
        return f"{self.ram_gb:.1f} GB RAM, {self.cpu_count} CPUs, {gpu}"


def _read_meminfo() -> float:
    try:
        text = Path("/proc/meminfo").read_text(encoding="utf-8")
    except OSError:
        return 0.0
    match = re.search(r"^MemTotal:\s+(\d+)\s+kB", text, re.MULTILINE)
    if not match:
        return 0.0
    return round(int(match.group(1)) / 1024 / 1024, 1)


def _cpu_name() -> str:
    try:
        text = Path("/proc/cpuinfo").read_text(encoding="utf-8")
    except OSError:
        return ""
    match = re.search(r"^model name\s*:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _run(command: list[str], timeout: int = 4) -> str:
    if not shutil.which(command[0]):
        return ""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _nvidia_gpu() -> tuple[str, float, str]:
    output = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total",
            "--format=csv,noheader,nounits",
        ]
    )
    if not output:
        return "", 0.0, ""
    line = output.splitlines()[0]
    parts = [part.strip() for part in line.split(",")]
    if len(parts) < 2:
        return "", 0.0, ""
    name = parts[0]
    try:
        vram = round(float(parts[1]) / 1024, 1)
    except ValueError:
        vram = 0.0
    return name, vram, "nvidia"


def _amd_gpu() -> tuple[str, float, str]:
    for path in sorted(Path("/sys/class/drm").glob("card*/device/mem_info_vram_total")):
        try:
            value = int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        if value <= 0:
            continue
        vram = round(value / 1024 / 1024 / 1024, 1)
        name = "AMD GPU"
        lspci = _run(["lspci"])
        for line in lspci.splitlines():
            if "VGA" in line or "Display" in line:
                match = re.search(r":\s*(.+)$", line)
                if match:
                    name = match.group(1).strip()
                    break
        return name, vram, "amd"
    return "", 0.0, ""


def _intel_gpu() -> tuple[str, float, str]:
    lspci = _run(["lspci"])
    for line in lspci.splitlines():
        if ("VGA" in line or "Display" in line) and "Intel" in line:
            match = re.search(r":\s*(.+)$", line)
            return (match.group(1).strip() if match else "Intel GPU"), 0.0, "intel"
    return "", 0.0, ""


def detect() -> HardwareProfile:
    ram_gb = _read_meminfo()
    cpu_count = os.cpu_count() or 1
    cpu_name = _cpu_name()
    notes: list[str] = []

    gpu_name, vram_gb, vendor = _nvidia_gpu()
    if not gpu_name:
        gpu_name, vram_gb, vendor = _amd_gpu()
    if not gpu_name:
        gpu_name, vram_gb, vendor = _intel_gpu()

    if ram_gb and ram_gb < 8:
        notes.append("Less than 8 GB of RAM: choose a light model and expect slower replies.")
    if gpu_name and vram_gb < 6:
        notes.append("GPU with less than 6 GB of VRAM: the model will run on the CPU.")
    if not gpu_name:
        notes.append("No compatible GPU detected: running on the CPU.")

    return HardwareProfile(
        ram_gb=ram_gb,
        cpu_count=cpu_count,
        cpu_name=cpu_name,
        gpu_name=gpu_name,
        gpu_vendor=vendor,
        vram_gb=vram_gb,
        notes=tuple(notes),
    )


def recommend_gpu_layers(model_size_gb: float, profile: HardwareProfile) -> int:
    """Return the llama.cpp ``-ngl`` value.

    0 means CPU only and 99 means every layer on the GPU. When the model does
    not fit entirely we let llama.cpp choose a safe partial offload.
    """

    if not profile.usable_gpu:
        return 0
    if model_size_gb <= max(0.0, profile.vram_gb - 1.5):
        return 99
    if model_size_gb <= profile.vram_gb:
        return 24
    return 0


def profile_dict(profile: HardwareProfile) -> dict[str, object]:
    return {
        "ram_gb": profile.ram_gb,
        "cpu_count": profile.cpu_count,
        "cpu_name": profile.cpu_name,
        "gpu_name": profile.gpu_name,
        "gpu_vendor": profile.gpu_vendor,
        "vram_gb": profile.vram_gb,
        "usable_gpu": profile.usable_gpu,
        "summary": profile.summary,
        "notes": list(profile.notes),
    }
