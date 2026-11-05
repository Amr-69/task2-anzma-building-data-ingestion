from fastapi.testclient import TestClient

from main import app

client = TestClient(app)
URL = "/api/v1/assistant/chat"


def ask(question, **extra):
    return client.post(URL, json={"question": question, **extra})


# ---- Q6 energy ----

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


# ---- Q1 building status ----

def test_status_english():
    r = ask("What is the current status of the building?")
    assert r.status_code == 200
    body = r.json()
    assert body["tool_used"] == "get_building_status"
    assert body["language"] == "en"
    assert "of 29 assets" in body["answer"]
    assert body["data_window"]["hours"] == 24
    assert any(e["type"] == "kpis" for e in body["evidence"])


def test_status_arabic():
    r = ask("ما هي الحالة الحالية للمبنى؟")
    body = r.json()
    assert r.status_code == 200
    assert body["language"] == "ar"
    assert body["tool_used"] == "get_building_status"
    assert "أصل" in body["answer"]


def test_status_with_scenario():
    r = ask("What is the current status of the building?", scenario="S1")
    assert r.status_code == 200
    assert r.json()["scenario"] == "S1"


# ---- Q3 CCTV ----

def test_cctv_english(monkeypatch):
    monkeypatch.setattr(
        "assistant.router.llm.select_tool",
        lambda question, model_key: "get_cctv_availability",
    )
    monkeypatch.setattr(
        "assistant.router.llm.generate_answer",
        lambda question, language, tool_name, evidence, model_key: (
            "CCTV availability is inferred from heartbeat evidence."
            if language == "en"
            else "تتوفر كاميرات المراقبة بناءً على heartbeat."
        ),
    )

    r = ask("Is CCTV available?")

def test_cctv_arabic(monkeypatch):
    monkeypatch.setattr(
        "assistant.router.llm.select_tool",
        lambda question, model_key: "get_cctv_availability",
    )
    monkeypatch.setattr(
        "assistant.router.llm.generate_answer",
        lambda question, language, tool_name, evidence, model_key: (
            "CCTV availability is inferred from heartbeat evidence."
            if language == "en"
            else "تتوفر كاميرات المراقبة بناءً على heartbeat."
        ),
    )

    r = ask("هل كاميرات المراقبة متاحة؟")

# ---- request validation ----

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