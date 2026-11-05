from fastapi.testclient import TestClient

from main import app

client = TestClient(app)
URL = "/api/v1/assistant/chat"


def ask(question, **extra):
    return client.post(URL, json={"question": question, **extra})


def test_energy_english():
    r = ask("How has energy consumption changed?")
    assert r.status_code == 200
    body = r.json()
    assert body["tool_used"] == "get_energy_consumption_change"
    assert body["language"] == "en"
    assert "cannot be determined" in body["answer"]
    assert "packet_loss_pct" in body["answer"]
    assert body["data_window"]["end_exclusive"].endswith("Z")
    assert body["validation"]["passed"] is True


def test_energy_arabic():
    r = ask("كيف تغير استهلاك الطاقة؟")
    body = r.json()
    assert body["language"] == "ar"
    assert "لا يمكن" in body["answer"]
    assert "packet_loss_pct" in body["answer"]


def test_model_selection():
    assert ask("energy?", model="llama").json()["model_used"] == "llama3.2:3b"
    assert ask("energy?", model="qwen").json()["model_used"] == "qwen2.5:3b"


def test_unsupported_model_rejected():
    assert ask("energy?", model="gpt").status_code == 422


def test_invalid_hours_rejected():
    assert ask("energy?", hours=5).status_code == 422


def test_invalid_scenario_rejected():
    assert ask("energy?", scenario="S9").status_code == 400


def test_unknown_building_rejected():
    assert ask("energy?", building_id=999).status_code == 404