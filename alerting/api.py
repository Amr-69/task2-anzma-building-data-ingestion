"""FastAPI routes for IDSS and both streaming modes."""
import json
import os
import sqlite3
import time
import urllib.request
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from db import DB_PATH as DEFAULT_DB_PATH

DB_PATH = Path(os.getenv('ANZMA_DB_PATH', str(DEFAULT_DB_PATH))).resolve()
from .engine import detect
from .idss import list_findings, assess_finding
from .llm_early_warning import analyze_llm_early_warnings
from .context import collect_telemetry_context
from .diagnosis import _build_prompt, _validate_diagnosis, DEFAULT_MODEL, DEFAULT_BASE_URL, DEFAULT_TIMEOUT

router = APIRouter(prefix="/api/v1/idss", tags=["IDSS"])

@router.get("/demo", include_in_schema=False)
def idss_demo_page():
    page = Path(__file__).resolve().parent.parent / "dashboard" / "static" / "idss.html"
    return FileResponse(page)



def _finding_by_id(finding_id):
    for finding in detect(DB_PATH):
        if finding["finding_id"] == finding_id:
            return finding
    raise HTTPException(status_code=404, detail="Finding not found")


@router.get("/findings")
def get_findings():
    """List threshold and anomaly findings with deterministic triage."""
    try:
        return {"findings": list_findings(DB_PATH)}
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=503, detail="Unable to read telemetry database.") from exc


@router.get("/early-warnings")
def get_early_warnings():
    """LLM evaluates raw telemetry windows for developing risks."""
    try:
        return analyze_llm_early_warnings(DB_PATH)
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=503, detail="Unable to read telemetry database.") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="LLM early-warning service unavailable.") from exc


@router.get("/assess/{finding_id}")
def get_assessment(finding_id: str):
    """Run the IDSS assessment for a detected finding."""
    finding = _finding_by_id(finding_id)
    return assess_finding(DB_PATH, finding)


@router.get("/stream/telemetry")
def stream_telemetry(
    after_id: int = Query(default=-1, ge=-1),
    duration_seconds: int = Query(default=60, ge=1, le=300),
    poll_seconds: float = Query(default=1.0, ge=0.25, le=10),
):
    """Poll SQLite for newly inserted telemetry and emit SSE events."""
    def events():
        cursor = after_id
        if cursor < 0:
            conn = sqlite3.connect(f"{Path(DB_PATH).resolve().as_uri()}?mode=ro", uri=True)
            try:
                cursor = conn.execute(
                    "SELECT COALESCE(MAX(telemetry_id), 0) FROM telemetry_records"
                ).fetchone()[0]
            finally:
                conn.close()
        deadline = time.monotonic() + duration_seconds
        while time.monotonic() < deadline:
            conn = sqlite3.connect(f"{Path(DB_PATH).resolve().as_uri()}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute("""
                    SELECT t.telemetry_id, a.asset_code, m.name AS metric,
                           m.unit, t.ts, t.value
                    FROM telemetry_records t
                    JOIN assets a ON a.asset_id=t.asset_id
                    JOIN metric_types m ON m.metric_id=t.metric_id
                    WHERE t.telemetry_id > ?
                    ORDER BY t.telemetry_id LIMIT 500
                """, (cursor,)).fetchall()
            finally:
                conn.close()
            for row in rows:
                item = dict(row)
                cursor = item["telemetry_id"]
                yield "event: telemetry\ndata: " + json.dumps(item) + "\n\n"
            if rows:
                yield "event: analysis\ndata: " + json.dumps({
                    "findings": list_findings(DB_PATH)
                }) + "\n\n"
            if not rows:
                yield ": keep-alive\n\n"
            time.sleep(poll_seconds)
        yield "event: complete\ndata: " + json.dumps({"last_id": cursor}) + "\n\n"
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/stream/diagnosis/{finding_id}")
def stream_diagnosis(finding_id: str):
    """Stream Ollama's generated diagnosis tokens, then validate final JSON."""
    finding = _finding_by_id(finding_id)
    context = collect_telemetry_context(DB_PATH, finding)
    prompt = _build_prompt(finding, context)
    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": "You are a careful engineering diagnostic assistant. Return only schema-compliant JSON."},
            {"role": "user", "content": prompt},
        ],
        "format": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "hypotheses": {"type": "array", "items": {
                    "type": "object",
                    "properties": {
                        "hypothesis": {"type": "string"},
                        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                        "reasoning": {"type": "string"},
                        "evidence_ids": {"type": "array", "items": {"type": "integer"}},
                    },
                    "required": ["hypothesis", "confidence", "reasoning", "evidence_ids"],
                }},
                "missing_evidence": {"type": "array", "items": {"type": "string"}},
                "recommended_actions": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary", "hypotheses", "missing_evidence", "recommended_actions"],
        },
        "stream": True,
        "options": {"temperature": 0.1, "num_ctx": 2048},
    }

    def events():
        chunks = []
        request = urllib.request.Request(
            f"{DEFAULT_BASE_URL}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
                for raw in response:
                    if not raw.strip():
                        continue
                    packet = json.loads(raw.decode("utf-8"))
                    token = packet.get("message", {}).get("content", "")
                    if token:
                        chunks.append(token)
                        yield "event: token\ndata: " + json.dumps({"text": token}) + "\n\n"
            diagnosis = _validate_diagnosis("".join(chunks), context, finding)
            yield "event: result\ndata: " + json.dumps({
                "finding": finding, "diagnosis_status": "available",
                "model": DEFAULT_MODEL, "diagnosis": diagnosis,
            }) + "\n\n"
        except Exception as exc:
            # Do not leak local paths, request bodies, or connection details.
            yield "event: error\ndata: " + json.dumps({"error": "Diagnosis streaming or validation failed.", "type": type(exc).__name__}) + "\n\n"
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
