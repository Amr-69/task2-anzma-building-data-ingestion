from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def _patch_llm(monkeypatch, tool="get_building_status", answer="Valid LLM explanation."):
    def fake_select_tool(question, model_key):
        return tool

    def fake_generate_answer(question, language, tool_name, evidence, model_key):
        return answer

    monkeypatch.setattr("assistant.router.llm.select_tool", fake_select_tool)
    monkeypatch.setattr(
        "assistant.router.llm.generate_answer", fake_generate_answer
    )


def test_llm_answer_is_used_when_valid(monkeypatch):
    _patch_llm(
        monkeypatch,
        tool="get_building_status",
        answer="HVAC-AHU-02 is critical based on recorded telemetry evidence.",
    )

    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "question": "What is the building status?",
            "building_id": 1,
            "scenario": "S1",
            "hours": 24,
            "model": "qwen",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ai_source"] == "llm"
    assert body["tool_used"] == "get_building_status"
    assert body["answer"] == (
        "HVAC-AHU-02 is critical based on recorded telemetry evidence."
    )
    assert body["validation"]["passed"] is True


def test_invalid_llm_answer_uses_fallback(monkeypatch):
    _patch_llm(
        monkeypatch,
        tool="get_building_status",
        answer='{"not": "a natural language answer"}',
    )

    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "question": "What is the building status?",
            "building_id": 1,
            "scenario": "S1",
            "hours": 24,
            "model": "qwen",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ai_source"] == "fallback"
    assert body["validation"]["passed"] is False
    assert body["answer"] != '{"not": "a natural language answer"}'


def test_ollama_unavailable_uses_fallback(monkeypatch):
    def unavailable_select_tool(question, model_key):
        raise OSError("Ollama unavailable")

    def unavailable_generate_answer(*args, **kwargs):
        raise OSError("Ollama unavailable")

    monkeypatch.setattr(
        "assistant.router.llm.select_tool", unavailable_select_tool
    )
    monkeypatch.setattr(
        "assistant.router.llm.generate_answer",
        unavailable_generate_answer,
    )

    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "question": "What is the building status?",
            "building_id": 1,
            "scenario": "S1",
            "hours": 24,
            "model": "qwen",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ai_source"] == "fallback"
    assert body["tool_used"] == "get_building_status"
    assert body["answer"]


def test_energy_question_does_not_call_llm(monkeypatch):
    def fail_select_tool(question, model_key):
        raise AssertionError("Energy questions must not use the LLM")

    def fail_generate_answer(*args, **kwargs):
        raise AssertionError("Energy questions must not use the LLM")

    monkeypatch.setattr(
        "assistant.router.llm.select_tool", fail_select_tool
    )
    monkeypatch.setattr(
        "assistant.router.llm.generate_answer",
        fail_generate_answer,
    )

    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "question": "How did energy consumption change?",
            "building_id": 1,
            "scenario": "baseline",
            "hours": 24,
            "model": "qwen",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["question_type"] == "energy_consumption"
    assert body["tool_used"] == "get_energy_consumption_change"
    assert body["ai_source"] == "fallback"
    assert "cannot be determined" in body["answer"]


def test_qwen_model_is_used(monkeypatch):
    captured = {}

    def fake_select_tool(question, model_key):
        captured["model"] = model_key
        return "get_building_status"

    def fake_generate_answer(
        question, language, tool_name, evidence, model_key
    ):
        captured["answer_model"] = model_key
        return "Valid answer."

    monkeypatch.setattr(
        "assistant.router.llm.select_tool", fake_select_tool
    )
    monkeypatch.setattr(
        "assistant.router.llm.generate_answer",
        fake_generate_answer,
    )

    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "question": "What is the building status?",
            "building_id": 1,
            "scenario": "S1",
            "hours": 24,
            "model": "qwen",
        },
    )

    assert response.status_code == 200
    assert captured["model"] == "qwen"
    assert captured["answer_model"] == "qwen"
    assert response.json()["model_used"] == "qwen2.5:3b"


def test_llama_model_is_used(monkeypatch):
    captured = {}

    def fake_select_tool(question, model_key):
        captured["model"] = model_key
        return "get_building_status"

    def fake_generate_answer(
        question, language, tool_name, evidence, model_key
    ):
        captured["answer_model"] = model_key
        return "Valid answer."

    monkeypatch.setattr(
        "assistant.router.llm.select_tool", fake_select_tool
    )
    monkeypatch.setattr(
        "assistant.router.llm.generate_answer",
        fake_generate_answer,
    )

    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "question": "What is the building status?",
            "building_id": 1,
            "scenario": "S1",
            "hours": 24,
            "model": "llama",
        },
    )

    assert response.status_code == 200
    assert captured["model"] == "llama"
    assert captured["answer_model"] == "llama"
    assert response.json()["model_used"] == "llama3.2:3b"


def test_unsupported_model_is_rejected():
    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "question": "What is the building status?",
            "building_id": 1,
            "scenario": "S1",
            "hours": 24,
            "model": "gpt",
        },
    )

    assert response.status_code == 422


def test_invalid_time_range_is_rejected():
    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "question": "What is the building status?",
            "building_id": 1,
            "scenario": "S1",
            "hours": 48,
            "model": "qwen",
        },
    )

    assert response.status_code == 422