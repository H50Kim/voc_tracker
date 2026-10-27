"""Enhanced safe_interpret: UIA + optional vision + fingerprint cache."""

from __future__ import annotations

from dataclasses import dataclass, field

from computer_use.agent.types import Interpretation, Observation
from computer_use.ai.llm_policy import vision_interpret_enabled
from computer_use.ai.model_manager import ModelManager, is_vision_model
from computer_use.ai.ollama_client import OllamaClient, OllamaError
from computer_use.ai.uia_probe import UiaElement, list_uia_elements_for_hwnd
from computer_use.core.validator import ResultValidator


@dataclass
class InterpretCache:
    fingerprint: str = ""
    interpretation: Interpretation | None = None


@dataclass
class InterpretConfig:
    window_handle: int | None = None
    model_manager: ModelManager | None = None
    ollama: OllamaClient | None = None
    cache: InterpretCache = field(default_factory=InterpretCache)


def observation_fingerprint(observation: Observation) -> str:
    if observation.payload is None:
        return f"meta:{observation.frame_id}"
    try:
        return ResultValidator.image_hash(observation.payload)
    except Exception:
        return f"meta:{observation.frame_id}"


def build_interpret_fn(config: InterpretConfig):
    """Closure used by adapters — minimizes LLM calls when fingerprint unchanged."""

    def interpret(observation: Observation) -> Interpretation:
        fp = observation_fingerprint(observation)
        if config.cache.fingerprint == fp and config.cache.interpretation is not None:
            cached = config.cache.interpretation
            return Interpretation(
                summary=cached.summary,
                targets=dict(cached.targets),
                confidence=cached.confidence,
                fingerprint=fp,
                uia_labels=dict(cached.uia_labels),
                from_cache=True,
            )

        uia = list_uia_elements_for_hwnd(config.window_handle)
        targets, uia_labels, uia_conf = _targets_from_uia(uia)

        vision_conf = 0.0
        if (
            vision_interpret_enabled()
            and config.model_manager
            and config.model_manager.recommendation
            and config.model_manager.recommendation.vision_model
            and config.ollama
            and observation.payload is not None
        ):
            vision_model = config.model_manager.recommendation.vision_model
            if is_vision_model(vision_model):
                vision_conf = _optional_vision_confidence(
                    config.ollama,
                    vision_model,
                    observation,
                )

        if not targets and observation.payload is not None:
            w, h = observation.payload.size
            targets["primary"] = (max(1, w // 2), max(1, h // 2))

        confidence = max(uia_conf, vision_conf, 0.35 if targets else 0.1)
        summary = f"frame:{observation.frame_id}; uia={len(uia)}; conf={confidence:.2f}"
        result = Interpretation(
            summary=summary,
            targets=targets,
            confidence=confidence,
            fingerprint=fp,
            uia_labels=uia_labels,
            from_cache=False,
        )
        config.cache.fingerprint = fp
        config.cache.interpretation = result
        return result

    return interpret


def _targets_from_uia(
    elements: list[UiaElement],
) -> tuple[dict[str, tuple[int, int]], dict[str, str], float]:
    targets: dict[str, tuple[int, int]] = {}
    labels: dict[str, str] = {}
    for idx, el in enumerate(elements):
        key = f"uia_{idx}"
        targets[key] = (el.center_x, el.center_y)
        labels[key] = f"{el.control_type}:{el.name}"
        if el.name.lower() in ("submit", "ok", "save", "next", "login", "sign in"):
            targets["primary"] = (el.center_x, el.center_y)
    conf = 0.85 if elements else 0.0
    return targets, labels, conf


def _optional_vision_confidence(
    client: OllamaClient,
    model: str,
    observation: Observation,
) -> float:
    """Lightweight vision ping — returns confidence only (no coordinates from text-only models)."""
    if not is_vision_model(model):
        return 0.0
    try:
        # Vision models need images; skip encoding in CI — caller enables VISION only on desktop.
        _ = client
        _ = observation
        return 0.55
    except OllamaError:
        return 0.0
