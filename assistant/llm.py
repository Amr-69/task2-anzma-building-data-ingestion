import json
import urllib.request
from typing import Any, Callable


OLLAMA_URL = "http://localhost:11434/api/chat"
REQUEST_TIMEOUT = 120
MAX_TOOL_CALLS = 3


MODEL_MAP = {
    "qwen": "qwen2.5:3b",
    "llama": "llama3.2:3b",
}


TOOLS = {
    "get_building_status": (
        "Use for questions about the overall building condition, KPIs, "
        "asset operational status, equipment health, or current alerts."
    ),
    "get_recent_faults": (
        "Use for questions about recent equipment faults, telemetry incidents, "
        "HVAC problems, abnormal readings, or equipment needing attention."
    ),
    "get_cctv_availability": (
        "Use for questions about CCTV cameras, camera availability, "
        "camera offline status, or heartbeat compliance."
    ),
    "get_network_issues": (
        "Use for questions about network devices, packet loss, latency, "
        "link down events, or network problems."
    ),
    "get_corrective_priorities": (
        "Use for questions about which incident should be fixed first, "
        "recommended corrective actions, or operational priorities."
    ),
    "get_energy_consumption_change": (
        "Use for questions about energy consumption, electricity, power use, "
        "or kWh. The current dataset may not contain energy telemetry."
    ),
}


AGENT_SYSTEM_PROMPT = """You are the intelligent AI assistant for the AnzmaTech building-operations dashboard.


You can answer general conversation directly. For questions that require building data, you may call one read-only tool at a time.


Available tools:
{tools}


Rules:
1. Reply with JSON only.
2. To call a tool, reply:
{{"action": "tool", "tool": "tool_name"}}
3. After receiving TOOL_RESULT, provide the final answer:
{{"action": "answer", "answer": "your answer"}}
4. Use the TOOL_RESULT and earlier conversation as context. For building facts, use only the TOOL_RESULT. Never invent assets, metrics, readings, incidents, events, KPIs, or corrective actions.
5. Understand follow-up questions such as "explain them", "the most critical", or "what about the network?" using the earlier conversation. Call a tool again only if you need new data.
6. If the data does not contain the requested information, say that clearly.
7. Answer in the same language as the user: English or Arabic.
8. Do not claim that the system controls equipment. Recommendations are advisory only.
9. You may call a tool at most {max_tool_calls} times.
"""


def _call_ollama(
    model: str,
    messages: list[dict[str, str]],
    use_json_format: bool = True,
) -> str:
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "stream": False,
            "format": "json" if use_json_format else "text",
            "options": {
                "temperature": 0.2,
                "num_ctx": 4096,
            },
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
            raise ValueError("The AI model did not return valid JSON.")
        return json.loads(text[start : end + 1])



def _tool_prompt() -> str:
    lines = []
    for name, description in TOOLS.items():
        lines.append(f"- {name}: {description}")
    return "\n".join(lines)



def run_agent(
    question: str,
    language: str,
    model_key: str,
    building_id: int,
    scenario: str,
    hours: int,
    tool_functions: dict[str, Callable],
    history: list[dict[str, str]] | None = None,
) -> tuple[str, str | None, list[dict[str, Any]]]:
    model = MODEL_MAP[model_key]

    messages = [
        {
            "role": "system",
            "content": AGENT_SYSTEM_PROMPT.format(
                tools=_tool_prompt(),
                max_tool_calls=MAX_TOOL_CALLS,
            ),
        }
    ]


    for item in (history or [])[-8:]:
        role = item.get("role")
        content = item.get("content")

        if role in {"user", "assistant"} and content:
            messages.append(
                {
                    "role": role,
                    "content": content,
                }
            )


    messages.append(
        {
            "role": "user",
            "content": question,
        }
    )


    tool_used: str | None = None
    evidence: list[dict[str, Any]] = []


    for _ in range(MAX_TOOL_CALLS + 1):
        content = _call_ollama(model, messages, use_json_format=True)
        decision = _parse_json(content)
        action = decision.get("action")


        if action == "answer":
            answer = str(decision.get("answer", "")).strip()

            if not answer:
                raise ValueError("The AI model returned an empty answer.")

            return answer, tool_used, evidence


        if action == "tool":
            tool_name = decision.get("tool")

            if tool_name not in tool_functions:
                raise ValueError(f"Unknown tool requested: {tool_name}")

            tool_used = tool_name

            try:
                result = tool_functions[tool_name](
                    building_id,
                    scenario,
                    hours,
                )
            except Exception as exc:
                result = {
                    "error": f"Tool execution failed: {exc}",
                }

            evidence.append(
                {
                    "tool": tool_name,
                    "result": result,
                }
            )

            messages.append(
                {
                    "role": "assistant",
                    "content": json.dumps(decision, ensure_ascii=False),
                }
            )

            messages.append(
                {
                    "role": "user",
                    "content": "TOOL_RESULT:\n"
                    + json.dumps(result, ensure_ascii=False),
                }
            )

            continue


        raise ValueError(f"Unknown AI action: {action}")


    raise ValueError(
        "The AI model did not provide a final answer after tool calls."
    )