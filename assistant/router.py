from fastapi import APIRouter, HTTPException

from assistant.language import detect_language
from assistant.schemas import ChatRequest, ChatResponse, Validation
from assistant.services import AssistantError
from assistant import tools

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])

MODEL_MAP = {"qwen": "qwen2.5:3b", "llama": "llama3.2:3b"}

ENERGY_TEXT = {
    "en": (
        "Energy-consumption change cannot be determined because the dataset "
        "does not include energy-consumption telemetry. Available metrics: {m}. "
        "No energy values were calculated or estimated."
    ),
    "ar": (
        "لا يمكن تحديد تغيّر استهلاك الطاقة لأن مجموعة البيانات لا تتضمن "
        "قياسات استهلاك الطاقة. المقاييس المتاحة: {m}. "
        "لم يتم حساب أو تقدير أي قيم للطاقة."
    ),
}
ENERGY_LIMIT = {
    "en": "The dataset has no energy-consumption telemetry.",
    "ar": "لا تتضمن مجموعة البيانات قياسات استهلاك الطاقة.",
}


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    lang = detect_language(req.question)
    model_used = MODEL_MAP[req.model]

    try:
        if tools.is_energy_question(req.question):
            result = tools.get_energy_consumption_change(
                req.building_id, req.scenario, req.hours
            )
            names = ", ".join(m["name"] for m in result["available_metrics"])
            return ChatResponse(
                answer=ENERGY_TEXT[lang].format(m=names),
                question_type="energy_consumption",
                tool_used="get_energy_consumption_change",
                model_used=model_used,
                language=lang,
                scenario=req.scenario,
                data_window=result["data_window"],
                evidence=[{"type": "available_metrics",
                           "items": result["available_metrics"]}],
                limitations=[ENERGY_LIMIT[lang]],
                ai_source="fallback",
                validation=Validation(passed=True, errors=[]),
            )
    except AssistantError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    raise HTTPException(
        status_code=501,
        detail="This question type is not implemented yet.",
    )