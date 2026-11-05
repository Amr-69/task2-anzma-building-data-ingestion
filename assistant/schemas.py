from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    building_id: int = 1
    scenario: str = "baseline"
    hours: Literal[1, 6, 12, 24] = 24
    model: Literal["qwen", "llama"] = "qwen"
    history: list[dict[str, str]] = Field(default_factory=list)


class Validation(BaseModel):
    passed: bool
    errors: list[str] = []


class ChatResponse(BaseModel):
    answer: str
    question_type: str
    tool_used: Optional[str]
    model_used: str
    language: Literal["en", "ar"]
    scenario: str
    data_window: dict[str, Any]
    evidence: list[dict[str, Any]]
    limitations: list[str]
    ai_source: Literal["llm", "fallback"]
    validation: Validation