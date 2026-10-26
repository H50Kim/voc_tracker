"""Discover Ollama / optional llama.cpp servers; probe hardware; recommend models."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from computer_use.ai.llm_policy import default_ollama_base_url
from computer_use.ai.ollama_client import OllamaClient, OllamaError, OllamaModelInfo

ModelRole = Literal["planner_text", "vision", "unsupported"]

# Heuristic: never treat these patterns as vision-capable.
_TEXT_ONLY_HINTS = ("embed", "embedding", "bge-", "nomic-embed")
_VISION_HINTS = (
    "llava",
    "bakllava",
    "moondream",
    "minicpm-v",
    "llama3.2-vision",
    "qwen2-vl",
    "qwen-vl",
    "gemma3",
    "vision",
    "vl-",
    "-vl",
)


@dataclass(frozen=True)
class HardwareProfile:
    cpu_count: int
    ram_gb: float
    gpu_name: str
    vram_gb: float | None
    disk_free_gb: float
    platform: str


@dataclass(frozen=True)
class ModelRecommendation:
    text_model: str
    vision_model: str | None
    num_ctx: int
    num_gpu_layers: int
    notes: str


@dataclass
class ModelManager:
    """Startup probe + model catalog for local LLM pipeline."""

    ollama: OllamaClient | None = None
    llama_cpp_url: str | None = None
    hardware: HardwareProfile | None = None
    ollama_models: list[OllamaModelInfo] = field(default_factory=list)
    recommendation: ModelRecommendation | None = None
    last_error: str = ""

    def startup(self) -> None:
        self.hardware = probe_hardware()
        self.llama_cpp_url = discover_llama_cpp_server()
        try:
            client = self.ollama or OllamaClient()
            self.ollama = client
            self.ollama_models = client.list_models()
            self.last_error = ""
        except OllamaError as exc:
            self.ollama_models = []
            self.last_error = str(exc)
        self.recommendation = recommend_models(self.hardware, self.ollama_models)

    def status_summary(self) -> str:
        hw = self.hardware
        rec = self.recommendation
        parts: list[str] = []
        if hw:
            parts.append(
                f"CPU×{hw.cpu_count}, RAM≈{hw.ram_gb:.1f}GB, disk≈{hw.disk_free_gb:.0f}GB free"
            )
            if hw.gpu_name:
                vram = f", VRAM≈{hw.vram_gb:.1f}GB" if hw.vram_gb else ""
                parts.append(f"GPU: {hw.gpu_name}{vram}")
        if self.ollama_models:
            parts.append(f"Ollama: {len(self.ollama_models)} model(s)")
        elif self.last_error:
            parts.append("Ollama: unavailable")
        if self.llama_cpp_url:
            parts.append(f"llama.cpp: {self.llama_cpp_url}")
        if rec:
            parts.append(f"text={rec.text_model}")
            if rec.vision_model:
                parts.append(f"vision={rec.vision_model}")
        return " | ".join(parts) if parts else "AI: not probed"


def classify_model_role(name: str) -> ModelRole:
    lower = name.lower()
    for hint in _TEXT_ONLY_HINTS:
        if hint in lower:
            return "unsupported"
    for hint in _VISION_HINTS:
        if hint in lower:
            return "vision"
    return "planner_text"


def is_vision_model(name: str) -> bool:
    return classify_model_role(name) == "vision"


def is_text_planner_model(name: str) -> bool:
    return classify_model_role(name) == "planner_text"


def probe_hardware() -> HardwareProfile:
    cpu = os.cpu_count() or 1
    ram_gb = _read_ram_gb()
    gpu_name, vram_gb = _probe_gpu()
    disk_free = _disk_free_gb(Path.cwd())
    return HardwareProfile(
        cpu_count=cpu,
        ram_gb=ram_gb,
        gpu_name=gpu_name,
        vram_gb=vram_gb,
        disk_free_gb=disk_free,
        platform=f"{platform.system()} {platform.release()}",
    )


def _read_ram_gb() -> float:
    if sys.platform == "linux":
        try:
            meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
            for line in meminfo.splitlines():
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return kb / (1024 * 1024)
        except OSError:
            pass
    if sys.platform == "win32":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return stat.ullTotalPhys / (1024**3)
        except Exception:
            pass
    return 8.0


def _disk_free_gb(path: Path) -> float:
    try:
        usage = shutil.disk_usage(path)
        return usage.free / (1024**3)
    except OSError:
        return 0.0


def _probe_gpu() -> tuple[str, float | None]:
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            line = (out.stdout or "").strip().splitlines()
            if line:
                parts = [p.strip() for p in line[0].split(",")]
                name = parts[0] if parts else ""
                vram: float | None = None
                if len(parts) > 1:
                    try:
                        vram = float(parts[1]) / 1024
                    except ValueError:
                        vram = None
                return name, vram
        except (subprocess.TimeoutExpired, OSError):
            pass
    return "", None


def discover_llama_cpp_server() -> str | None:
    env = os.environ.get("LLAMA_CPP_SERVER_URL", "").strip()
    if env:
        return env.rstrip("/")
    for port in (8080, 8000, 11435):
        url = f"http://127.0.0.1:{port}"
        try:
            req = __import__("urllib.request").request.Request(
                f"{url}/health", method="GET"
            )
            with __import__("urllib.request").request.urlopen(req, timeout=0.5) as resp:
                if resp.status == 200:
                    return url
        except Exception:
            continue
    return None


def recommend_models(
    hw: HardwareProfile | None,
    models: list[OllamaModelInfo],
) -> ModelRecommendation:
    text_candidates = [m.name for m in models if is_text_planner_model(m.name)]
    vision_candidates = [m.name for m in models if is_vision_model(m.name)]

    ram = hw.ram_gb if hw else 8.0
    if ram >= 32:
        preferred_text = _pick_preferred(text_candidates, ("llama3.1", "qwen2.5", "mistral"))
        num_ctx = 8192
        num_gpu = 35
    elif ram >= 16:
        preferred_text = _pick_preferred(text_candidates, ("llama3.2", "phi3", "gemma2"))
        num_ctx = 4096
        num_gpu = 20
    else:
        preferred_text = _pick_preferred(text_candidates, ("phi3", "llama3.2", "gemma2"))
        num_ctx = 2048
        num_gpu = 0

    if not preferred_text:
        preferred_text = os.environ.get("COMPUTER_USE_OLLAMA_TEXT_MODEL", "llama3.2")

    vision = _pick_preferred(vision_candidates, ("llava", "moondream", "minicpm-v"))
    notes = "Local Ollama only unless COMPUTER_USE_ALLOW_EXTERNAL_LLM=1"
    if vision_candidates and not vision:
        notes += "; vision tags found but none matched allowlist"
    return ModelRecommendation(
        text_model=preferred_text,
        vision_model=vision,
        num_ctx=num_ctx,
        num_gpu_layers=num_gpu,
        notes=notes,
    )


def _pick_preferred(names: list[str], substrings: tuple[str, ...]) -> str | None:
    if not names:
        return None
    lower_map = {n: n.lower() for n in names}
    for sub in substrings:
        for name, lower in lower_map.items():
            if sub in lower:
                return name
    return names[0]
