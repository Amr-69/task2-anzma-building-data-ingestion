from fastapi import APIRouter, HTTPException

from assistant import answer_builder, tools
from assistant.language import detect_language
from assistant.schemas import ChatRequest, ChatResponse, Validation
from assistant.services import AssistantError

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

# question_type -> (tool name, tool function, answer builder)
HANDLERS = {
    "building_status": (
        "get_building_status", tools.get_building_status, answer_builder.build_status_answer,
    ),
    "cctv_availability": (
        "get_cctv_availability", tools.get_cctv_availability, answer_builder.build_cctv_answer,
    ),
}


def _response(req, lang, qtype, tool_name, window, answer, evidence, limits):
    return ChatResponse(
        answer=answer,
        question_type=qtype,
        tool_used=tool_name,
        model_used=MODEL_MAP[req.model],
        language=lang,
        scenario=req.scenario,
        data_window=window,
        evidence=evidence,
        limitations=limits,
        ai_source="fallback",  # becomes "llm" when the LLM step is wired (step 4)
        validation=Validation(passed=True, errors=[]),
    )


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    lang = detect_language(req.question)
    qtype = tools.classify_question(req.question)

    try:
        if qtype == "energy_consumption":
            result = tools.get_energy_consumption_change(
                req.building_id, req.scenario, req.hours
            )
            names = ", ".join(m["name"] for m in result["available_metrics"])
            return _response(
                req, lang, qtype, "get_energy_consumption_change",
                result["data_window"],
                ENERGY_TEXT[lang].format(m=names),
                [{"type": "available_metrics", "items": result["available_metrics"]}],
                [ENERGY_LIMIT[lang]],
            )

        if qtype in HANDLERS:
            tool_name, tool_fn, builder = HANDLERS[qtype]
            result = tool_fn(req.building_id, req.scenario, req.hours)
            answer, limits, evidence = builder(result, lang)
            return _response(
                req, lang, qtype, tool_name, result["data_window"],
                answer, evidence, limits,
            )
    except AssistantError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    raise HTTPException(
        status_code=501,
        detail="This question type is not implemented yet.",
    )