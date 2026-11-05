from fastapi import APIRouter, HTTPException

from assistant import llm
from assistant.language import detect_language
from assistant.schemas import ChatRequest, ChatResponse, Validation
from assistant.services import AssistantError

from assistant.incident_tools import (
    get_corrective_priorities,
    get_network_issues,
    get_recent_faults,
)
from assistant.tools import (
    get_building_status,
    get_cctv_availability,
    get_energy_consumption_change,
)

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])

MODEL_MAP = llm.MODEL_MAP

TOOL_FUNCTIONS = {
    "get_building_status": get_building_status,
    "get_recent_faults": get_recent_faults,
    "get_cctv_availability": get_cctv_availability,
    "get_network_issues": get_network_issues,
    "get_corrective_priorities": get_corrective_priorities,
    "get_energy_consumption_change": get_energy_consumption_change,
}


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    language = detect_language(req.question)

    try:
        answer, tool_used, evidence = llm.run_agent(
            question=req.question,
            language=language,
            model_key=req.model,
            building_id=req.building_id,
            scenario=req.scenario,
            hours=req.hours,
            tool_functions=TOOL_FUNCTIONS,
            history=req.history,
        )
    except AssistantError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        )
    except (ValueError, KeyError, OSError, TimeoutError) as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "The AI assistant is unavailable or could not complete the "
                "request. Please try again."
            ),
        ) from exc

    return ChatResponse(
        answer=answer,
        question_type=tool_used or "conversational",
        tool_used=tool_used,
        model_used=MODEL_MAP[req.model],
        language=language,
        scenario=req.scenario,
        data_window={
            "hours": req.hours,
            "scenario": req.scenario,
        },
        evidence=evidence,
        limitations=[],
        ai_source="llm",
        validation=Validation(passed=True, errors=[]),
    )