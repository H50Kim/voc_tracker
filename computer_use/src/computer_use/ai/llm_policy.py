"""LLM endpoint policy — local Ollama by default; external only with explicit opt-in."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from computer_use.policy.policy_guard import PolicyViolation


def external_llm_allowed() -> bool:
    return os.environ.get("COMPUTER_USE_ALLOW_EXTERNAL_LLM", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def ai_pipeline_enabled() -> bool:
    """When false, adapters use deterministic stubs only."""
    raw = os.environ.get("COMPUTER_USE_AI_ENABLED", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def vision_interpret_enabled() -> bool:
    return os.environ.get("COMPUTER_USE_VISION", "").strip().lower() in ("1", "true", "yes")


def assert_llm_endpoint_allowed(base_url: str) -> None:
    """Block company data to non-local LLM hosts unless env opt-in."""
    if external_llm_allowed():
        return
    parsed = urlparse(base_url.strip())
    host = (parsed.hostname or "").lower()
    if host in ("127.0.0.1", "localhost", "::1"):
        return
    raise PolicyViolation(
        "External LLM endpoint blocked. Use local Ollama (127.0.0.1) or set "
        "COMPUTER_USE_ALLOW_EXTERNAL_LLM=1 to opt in."
    )


def default_ollama_base_url() -> str:
    return os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
