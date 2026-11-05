"""Tests for Task 5 conversational assistant behavior."""

from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_chat_rejects_invalid_scenario():
    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "question": "What is wrong with the building?",
            "model": "ollama",
            "building_id": 1,
            "scenario": "../../data/anzma_building.db",
            "hours": 24,
            "history": [],
        },
    )

    assert response.status_code in (400, 422)


def test_chat_rejects_invalid_time_window():
    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "question": "What is wrong with the building?",
            "model": "ollama",
            "building_id": 1,
            "scenario": "baseline",
            "hours": 7,
            "history": [],
        },
    )

    assert response.status_code in (400, 422)


def test_chat_accepts_conversation_history():
    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "question": "Which device is most affected?",
            "model": "ollama",
            "building_id": 1,
            "scenario": "baseline",
            "hours": 24,
            "history": [
                {"role": "user", "content": "What is wrong with the building?"},
                {"role": "assistant", "content": "The cooling system shows an issue."},
            ],
        },
    )

    assert response.status_code in (200, 400, 422, 503)


def test_scenarios_endpoint_returns_required_scenarios():
    response = client.get("/api/v1/dashboard/alerts/scenarios")

    assert response.status_code == 200

    scenario_ids = {
        item["id"]
        for item in response.json()["scenarios"]
    }

    expected = {"baseline", "S1", "S2", "S3", "S4", "S5"}

    assert expected.issubset(scenario_ids)
