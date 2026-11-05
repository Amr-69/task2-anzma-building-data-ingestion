import json
import urllib.request
from typing import Any

OLLAMA_URL = "http://localhost:11434/api/chat"
REQUEST_TIMEOUT = 90

MODEL_MAP = {
    "qwen": "qwen2.5:3b",
    "llama": "llama3.2:3b",
}

ALLOWED_TOOLS = {
    "get_building_status",
    "get_recent_faults",
    "get_cctv_availability",
    "get_network_issues",
    "get_corrective_priorities",
    "get_energy_consumption_change",
}

TOOL_SELECTION_PROMPT = """You are a tool-selection assistant for a building operations system.

Choose exactly one tool for the user question.

Allowed tools:
- get_building_status: building condition, KPIs, asset status, overall health.
- get_recent_faults: recent equipment faults, telemetry incidents, HVAC or equipment problems.
- get_cctv_availability: CCTV cameras, camera online/offline status, heartbeat compliance.
- get_network_issues: network device problems, packet loss, latency, link down events.
- get_corrective_priorities: which incident to fix first and recommended corrective actions.
- get_energy_consumption_change: energy use, electricity, kWh, power consumption.

Respond with JSON only:
{"tool": "tool_name"}

User question:
{question}
"""

ANSWER_PROMPT = """You are a building operations assistant.

Use ONLY the facts in the EVIDENCE JSON. Do not invent assets, metrics, numbers, events, incidents, or corrective actions.

Write a clear answer in {language}.

Rules:
- English answer: write English.
- Arabic answer: write Arabic. Latin letters are allowed only for protected technical tokens such as asset codes, metric names, event types, telemetry IDs, timestamps, and units.
- Mention uncertainty or missing data when the evidence shows it.
- Do not claim that the system controls equipment.
- Keep the answer under 180 words.

Question:
{question}

Selected tool:
{tool}

EVIDENCE JSON:
{evidence}
"""


def _call_ollama(model: str, prompt: str) -> str:
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        result = json.loads(response.read().decode("utf-8"))

    return result["message"]["content"]


def _parse_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("LLM did not return valid JSON")
        return json.loads(text[start : end + 1])


def select_tool(question: str, model_key: str) -> str:
    model = MODEL_MAP[model_key]
    prompt = TOOL_SELECTION_PROMPT.format(question=question)
    content = _call_ollama(model, prompt)
    selected = _parse_json(content).get("tool")

    if selected not in ALLOWED_TOOLS:
        raise ValueError(f"Invalid tool selected: {selected}")

    return selected


def generate_answer(
    question: str,
    language: str,
    tool_name: str,
    evidence: dict[str, Any],
    model_key: str,
) -> str:
    model = MODEL_MAP[model_key]
    prompt = ANSWER_PROMPT.format(
        language="English" if language == "en" else "Arabic",
        question=question,
        tool=tool_name,
        evidence=json.dumps(evidence, ensure_ascii=False),
    )

    answer = _call_ollama(model, prompt)
    return answer.strip()