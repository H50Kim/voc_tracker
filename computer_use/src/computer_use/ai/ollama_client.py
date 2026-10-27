"""Minimal Ollama HTTP client (stdlib only — easy to mock in tests)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from computer_use.ai.llm_policy import assert_llm_endpoint_allowed, default_ollama_base_url


@dataclass(frozen=True)
class OllamaModelInfo:
    name: str
    size_bytes: int = 0
    family: str = ""
    parameter_size: str = ""


class OllamaClient:
    def __init__(self, base_url: str | None = None, *, timeout_sec: float = 5.0) -> None:
        self.base_url = (base_url or default_ollama_base_url()).rstrip("/")
        self.timeout_sec = timeout_sec
        assert_llm_endpoint_allowed(self.base_url)

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = None
        headers: dict[str, str] = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                raw = resp.read().decode("utf-8")
                if not raw.strip():
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
            raise OllamaError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise OllamaError(str(exc.reason)) from exc
        except json.JSONDecodeError as exc:
            raise OllamaError("Invalid JSON from Ollama") from exc

    def is_reachable(self) -> bool:
        try:
            self.list_models()
            return True
        except OllamaError:
            return False

    def list_models(self) -> list[OllamaModelInfo]:
        payload = self._request("GET", "/api/tags")
        models: list[OllamaModelInfo] = []
        for entry in payload.get("models") or []:
            name = str(entry.get("name") or "")
            if not name:
                continue
            details = entry.get("details") or {}
            models.append(
                OllamaModelInfo(
                    name=name,
                    size_bytes=int(entry.get("size") or 0),
                    family=str(details.get("family") or ""),
                    parameter_size=str(details.get("parameter_size") or ""),
                )
            )
        return models

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        format_json: bool = False,
    ) -> str:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if format_json:
            body["format"] = "json"
        payload = self._request("POST", "/api/chat", body)
        message = payload.get("message") or {}
        content = message.get("content")
        return str(content or "")


class OllamaError(Exception):
    """Ollama HTTP or parse failure (no secrets in message)."""
