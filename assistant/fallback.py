from typing import Any

from assistant import answer_builder


def _incident_line(incident: dict[str, Any], language: str) -> str:
    asset = incident.get("asset_code", "unknown")
    metric = incident.get("metric", "unknown")
    severity = incident.get("severity", "unknown")
    started = incident.get("start_ts", "unknown")

    if language == "ar":
        return (
            f"{asset} - {metric}: حالة {severity}، بدأت في {started}."
        )
    return (
        f"{asset} - {metric}: {severity} incident, started at {started}."
    )


def build_fallback_answer(
    tool_name: str,
    packet: dict[str, Any],
    language: str,
) -> tuple[str, list[str], list[dict[str, Any]]]:
    if tool_name == "get_building_status":
        return answer_builder.build_status_answer(packet, language)

    if tool_name == "get_cctv_availability":
        return answer_builder.build_cctv_answer(packet, language)

    if tool_name == "get_energy_consumption_change":
        metrics = ", ".join(
            metric["name"] for metric in packet.get("available_metrics", [])
        )
        if language == "ar":
            answer = (
                "لا يمكن تحديد تغير استهلاك الطاقة لأن مجموعة البيانات لا تتضمن "
                f"قياسات استهلاك الطاقة. المقاييس المتاحة: {metrics}. "
                "لم يتم حساب أو تقدير أي قيم للطاقة."
            )
            limitation = "لا تتضمن مجموعة البيانات قياسات استهلاك الطاقة."
        else:
            answer = (
                "Energy-consumption change cannot be determined because the dataset "
                f"does not include energy-consumption telemetry. Available metrics: {metrics}. "
                "No energy values were calculated or estimated."
            )
            limitation = "The dataset has no energy-consumption telemetry."

        return (
            answer,
            [limitation],
            [{"type": "available_metrics", "items": packet.get("available_metrics", [])}],
        )

    if tool_name == "get_recent_faults":
        incidents = packet.get("incidents", [])
        if language == "ar":
            if not incidents:
                answer = "لا توجد حوادث قياس نشطة في الفترة المحددة."
            else:
                lines = [_incident_line(item, language) for item in incidents[:3]]
                answer = "تم العثور على حوادث القياس التالية: " + " ".join(lines)
            limitation = "النتيجة مبنية على بيانات القياس المسجلة في قاعدة البيانات."
        else:
            if not incidents:
                answer = "No telemetry incidents were found in the selected period."
            else:
                lines = [_incident_line(item, language) for item in incidents[:3]]
                answer = "The following telemetry incidents were found: " + " ".join(lines)
            limitation = "The result is based on telemetry incidents recorded in the database."

        return answer, [limitation], [{"type": "incidents", "items": incidents}]

    if tool_name == "get_network_issues":
        incidents = packet.get("incidents", [])
        events = packet.get("events", [])
        if language == "ar":
            answer = (
                f"تم العثور على {len(incidents)} حادث قياس شبكي و{len(events)} حدث شبكي مسجل."
            )
            limitation = "الأحداث المسجلة قد لا تكون نشطة حاليًا."
        else:
            answer = (
                f"Found {len(incidents)} network telemetry incidents and "
                f"{len(events)} recorded network events."
            )
            limitation = "Recorded events are historical and may not still be active."

        return (
            answer,
            [limitation],
            [
                {"type": "incidents", "items": incidents},
                {"type": "recorded_events", "items": events},
            ],
        )

    if tool_name == "get_corrective_priorities":
        ranked = packet.get("ranked", [])
        if language == "ar":
            if not ranked:
                answer = "لا توجد حوادث قياس ذات إجراءات تصحيحية ذات أولوية."
            else:
                first = ranked[0]
                actions = ", ".join(
                    action["id"] for action in first.get("actions", [])
                )
                answer = (
                    f"الأولوية الأولى هي {first.get('asset_code')} - "
                    f"{first.get('metric')}، والإجراءات المقترحة: {actions}."
                )
            limitation = "الإجراءات مقترحة فقط ولا يقوم النظام بتنفيذها."
        else:
            if not ranked:
                answer = "No telemetry incidents have corrective actions to prioritize."
            else:
                first = ranked[0]
                actions = ", ".join(
                    action["id"] for action in first.get("actions", [])
                )
                answer = (
                    f"The highest-priority incident is {first.get('asset_code')} - "
                    f"{first.get('metric')}. Recommended actions: {actions}."
                )
            limitation = "Actions are recommendations only; the system does not control equipment."

        return answer, [limitation], [{"type": "ranked_incidents", "items": ranked}]

    raise ValueError(f"Unsupported fallback tool: {tool_name}")