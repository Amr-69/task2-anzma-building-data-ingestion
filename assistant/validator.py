import re
from typing import Any

from assistant.llm import ALLOWED_TOOLS


ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
LATIN_RE = re.compile(r"[A-Za-z]")

EVIDENCE_TOKEN_KEYS = {
    "asset_code",
    "asset",
    "metric",
    "event_type",
    "camera_id",
    "system_type",
}


def validate_tool_selection(tool_name: str) -> list[str]:
    errors = []

    if tool_name not in ALLOWED_TOOLS:
        errors.append(f"Unsupported tool: {tool_name}")

    return errors


def _collect_tokens(value: Any, tokens: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in EVIDENCE_TOKEN_KEYS and isinstance(item, str):
                tokens.add(item.lower())
            _collect_tokens(item, tokens)
    elif isinstance(value, list):
        for item in value:
            _collect_tokens(item, tokens)


def _action_ids(value: Any, ids: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"id", "action_id"} and isinstance(item, str):
                ids.add(item)
            _action_ids(item, ids)
    elif isinstance(value, list):
        for item in value:
            _action_ids(item, ids)


def validate_answer(
    answer: str,
    language: str,
    evidence: dict[str, Any],
) -> list[str]:
    errors = []
    cleaned = answer.strip()

    if not cleaned:
        errors.append("Empty LLM answer")
        return errors

    # The LLM must explain the evidence in prose, not return raw JSON.
    if cleaned.startswith("{") or cleaned.startswith("["):
        errors.append("LLM returned JSON instead of a natural-language answer")

    if language == "ar":
        if not ARABIC_RE.search(cleaned):
            errors.append("Arabic answer contains no Arabic text")
    elif language == "en":
        if not LATIN_RE.search(cleaned):
            errors.append("English answer contains no English text")

    evidence_tokens: set[str] = set()
    _collect_tokens(evidence, evidence_tokens)

    answer_lower = cleaned.lower()
    grounded = any(token in answer_lower for token in evidence_tokens)

    if not grounded:
        errors.append(
            "LLM answer does not reference any asset, metric, event, camera, "
            "or system from the evidence packet"
        )

    allowed_actions: set[str] = set()
    _action_ids(evidence, allowed_actions)

    mentioned_actions = set(re.findall(r"\b(?:SAT|PL)-\d\b", cleaned))
    invalid_actions = mentioned_actions - allowed_actions
    if invalid_actions:
        errors.append(
            "Answer mentions action IDs not present in evidence: "
            + ", ".join(sorted(invalid_actions))
        )

    return errors