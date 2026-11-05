from fastapi import APIRouter, HTTPException

from assistant import fallback, llm, tools, validator
from assistant.language import detect_language
from assistant.schemas import ChatRequest, ChatResponse, Validation
from assistant.services import AssistantError

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])

MODEL_MAP = llm.MODEL_MAP

TOOL_FUNCTIONS = {
    "get_building_status": tools.get_building_status,
    "get_recent_faults": None,  # set after import below
    "get_cctv_availability": tools.get_cctv_availability,
    "get_network_issues": None,
    "get_corrective_priorities": None,
    "get_energy_consumption_change": tools.get_energy_consumption_change,
}

# Incident tools use the same (building_id, scenario, hours) interface.
from assistant.incident_tools import (
    get_corrective_priorities,
    get_network_issues,
    get_recent_faults,
)

TOOL_FUNCTIONS["get_recent_faults"] = get_recent_faults
TOOL_FUNCTIONS["get_network_issues"] = get_network_issues
TOOL_FUNCTIONS["get_corrective_priorities"] = get_corrective_priorities

KEYWORD_TOOLS = {
    "building_status": "get_building_status",
    "recent_faults": "get_recent_faults",
    "cctv_availability": "get_cctv_availability",
    "network_issues": "get_network_issues",
    "corrective_priorities": "get_corrective_priorities",
    "energy_consumption": "get_energy_consumption_change",
}


def _response(
    req: ChatRequest,
    language: str,
    question_type: str,
    tool_name: str,
    data_window: dict,
    answer: str,
    evidence: list[dict],
    limitations: list[str],
    ai_source: str,
    validation_errors: list[str],
) -> ChatResponse:
    return ChatResponse(
        answer=answer,
        question_type=question_type,
        tool_used=tool_name,
        model_used=MODEL_MAP[req.model],
        language=language,
        scenario=req.scenario,
        data_window=data_window,
        evidence=evidence,
        limitations=limitations,
        ai_source=ai_source,
        validation=Validation(
            passed=not validation_errors,
            errors=validation_errors,
        ),
    )


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    language = detect_language(req.question)

    try:
        # Energy is deterministic and must never depend on the LLM.
        if tools.is_energy_question(req.question):
            tool_name = "get_energy_consumption_change"
            packet = TOOL_FUNCTIONS[tool_name](
                req.building_id, req.scenario, req.hours
            )
            answer, limitations, evidence = fallback.build_fallback_answer(
                tool_name, packet, language
            )
            return _response(
                req,
                language,
                "energy_consumption",
                tool_name,
                packet["data_window"],
                answer,
                evidence,
                limitations,
                "fallback",
                [],
            )

        # LLM chooses the tool. Keyword classification is the deterministic backup.
        try:
            tool_name = llm.select_tool(req.question, req.model)
            tool_errors = validator.validate_tool_selection(tool_name)
        except (ValueError, KeyError, OSError, TimeoutError):
            tool_name = KEYWORD_TOOLS.get(
                tools.classify_question(req.question), ""
            )
            tool_errors = validator.validate_tool_selection(tool_name)

        if not tool_name:
            raise HTTPException(
                status_code=501,
                detail="This question type is not implemented yet.",
            )

        packet = TOOL_FUNCTIONS[tool_name](
            req.building_id, req.scenario, req.hours
        )

        fallback_answer, limitations, evidence = fallback.build_fallback_answer(
            tool_name, packet, language
        )

        try:
            llm_answer = llm.generate_answer(
                req.question,
                language,
                tool_name,
                packet,
                req.model,
            )
            answer_errors = validator.validate_answer(
                llm_answer, language, packet
            )
        except (ValueError, KeyError, OSError, TimeoutError):
            llm_answer = fallback_answer
            answer_errors = ["LLM unavailable; safe fallback used."]

        if answer_errors:
            final_answer = fallback_answer
            ai_source = "fallback"
        else:
            final_answer = llm_answer
            ai_source = "llm"

        return _response(
            req,
            language,
            tool_name.removeprefix("get_"),
            tool_name,
            packet["data_window"],
            final_answer,
            evidence,
            limitations,
            ai_source,
            answer_errors,
        )

    except AssistantError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)