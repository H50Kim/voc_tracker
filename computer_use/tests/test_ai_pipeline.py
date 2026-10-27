"""Phase 4 AI pipeline — mocked Ollama HTTP (no GPU)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from PIL import Image

from computer_use.agent.adapters import safe_interpret
from computer_use.agent.types import Observation
from computer_use.ai.glean_helper import extract_search_query_from_goal, suggest_glean_search_in_edge
from computer_use.ai.llm_policy import assert_llm_endpoint_allowed, external_llm_allowed
from computer_use.ai.model_manager import (
    ModelManager,
    classify_model_role,
    is_vision_model,
    recommend_models,
    probe_hardware,
)
from computer_use.ai.ollama_client import OllamaClient, OllamaError
from computer_use.ai.result_validator import ExtendedResultValidator
from computer_use.ai.task_planner import TaskPlanner, heuristic_plan
from computer_use.policy.policy_guard import PolicyViolation


def test_classify_vision_vs_text_only():
    assert classify_model_role("llava:7b") == "vision"
    assert classify_model_role("nomic-embed-text") == "unsupported"
    assert classify_model_role("llama3.2") == "planner_text"
    assert is_vision_model("llama3.2") is False


def test_external_llm_blocked_without_opt_in():
    with pytest.raises(PolicyViolation):
        assert_llm_endpoint_allowed("https://api.example.com/v1")


def test_external_llm_allowed_with_env(monkeypatch):
    monkeypatch.setenv("COMPUTER_USE_ALLOW_EXTERNAL_LLM", "1")
    assert external_llm_allowed()
    assert_llm_endpoint_allowed("https://api.example.com/v1")


def test_ollama_list_models_mocked():
    payload = {
        "models": [
            {"name": "llama3.2:latest", "size": 1000, "details": {"family": "llama"}},
            {"name": "llava:7b", "size": 2000, "details": {}},
        ]
    }

    client = OllamaClient(base_url="http://127.0.0.1:11434")
    with patch.object(client, "_request", return_value=payload):
        models = client.list_models()
    assert len(models) == 2
    assert models[0].name == "llama3.2:latest"


def test_ollama_chat_mocked():
    client = OllamaClient(base_url="http://127.0.0.1:11434")
    with patch.object(
        client,
        "_request",
        return_value={"message": {"content": '{"steps":[]}' }},
    ):
        text = client.chat(model="llama3.2", messages=[{"role": "user", "content": "hi"}])
    assert "steps" in text


def test_task_planner_ollama_json():
    client = OllamaClient(base_url="http://127.0.0.1:11434")
    plan_json = json.dumps(
        {
            "steps": [
                {
                    "id": "s1",
                    "kind": "click",
                    "description": "Click OK",
                    "semantic_key": "op:ok",
                    "target_id": "primary",
                }
            ]
        }
    )
    with patch.object(client, "chat", return_value=plan_json):
        planner = TaskPlanner(client=client, text_model="llama3.2")
        plan = planner.plan("Click OK button")
    assert plan.source == "ollama"
    assert len(plan.steps) == 1
    assert plan.steps[0].semantic_operation_key == "op:ok"


def test_heuristic_plan_fallback():
    plan = heuristic_plan('Type "hello" in the field')
    kinds = {s.kind.value for s in plan.steps}
    assert "type" in kinds


def test_model_manager_startup_mocked():
    mgr = ModelManager()
    mgr.ollama = OllamaClient(base_url="http://127.0.0.1:11434")
    with patch.object(mgr.ollama, "list_models", return_value=[]):
        mgr.startup()
    assert mgr.hardware is not None
    assert mgr.recommendation is not None


def test_extended_validator_file_and_text():
    ext = ExtendedResultValidator()
    text = ext.validate_text_present(haystack="Hello Glean world", needle="glean")
    assert text.passed
    missing = ext.validate_file_exists("/nonexistent/path/file.txt")
    assert not missing.passed


def test_interpret_cache_same_fingerprint():
    img = Image.new("RGB", (4, 4), color=(1, 2, 3))
    obs1 = Observation(frame_id="a", payload=img)
    obs2 = Observation(frame_id="b", payload=img.copy())
    i1 = safe_interpret(obs1)
    i2 = safe_interpret(obs2)
    assert i1.fingerprint == i2.fingerprint


def test_glean_suggestion_reference_only():
    from computer_use.controllers.browser_controller import BrowserController, StubEdgeWindowEnumerator

    browser = BrowserController(enumerator=StubEdgeWindowEnumerator())
    goal = 'Glean search for "quarterly revenue policy"'
    assert extract_search_query_from_goal(goal) == "quarterly revenue policy"
    suggestion = suggest_glean_search_in_edge(goal, browser=browser, preferred_handle=9001)
    assert suggestion is not None
    assert suggestion.reference_only is True
    assert "Reference" in suggestion.message


def test_adapters_ai_disabled_use_stubs(monkeypatch):
    monkeypatch.setenv("COMPUTER_USE_AI_ENABLED", "0")
    from computer_use.agent.adapters import default_generate_candidates

    obs = Observation(frame_id="x")
    interp = safe_interpret(obs)
    assert interp.targets == {}
    actions = default_generate_candidates(interp, goal="click save")
    assert len(actions) >= 1


def test_probe_hardware_runs():
    hw = probe_hardware()
    assert hw.cpu_count >= 1
    assert hw.ram_gb > 0


def test_recommend_models_prefers_text_not_embed():
    hw = probe_hardware()
    from computer_use.ai.ollama_client import OllamaModelInfo

    rec = recommend_models(
        hw,
        [
            OllamaModelInfo(name="nomic-embed-text"),
            OllamaModelInfo(name="llama3.2:latest"),
            OllamaModelInfo(name="llava:7b"),
        ],
    )
    assert "llama3.2" in rec.text_model
    assert rec.vision_model == "llava:7b"
