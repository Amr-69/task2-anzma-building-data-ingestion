"""Python-written factual answers in English and Arabic.

Digits stay Western. Asset codes, metric names, event types and timestamps
stay in English in both languages. The LLM (step 4) only adds explanation.
"""

STATUS_EN = {"normal": "Normal", "warning": "Warning", "critical": "Critical", "no_data": "No data"}
STATUS_AR = {"normal": "طبيعي", "warning": "تحذير", "critical": "حرج", "no_data": "بدون بيانات"}


def _attention_text(items, lang, limit=5):
    labels = STATUS_EN if lang == "en" else STATUS_AR
    if not items:
        return "none" if lang == "en" else "لا يوجد"
    shown = ", ".join(f"{a['asset_code']} ({labels[a['status']]})" for a in items[:limit])
    extra = len(items) - limit
    if extra > 0:
        shown += f" and {extra} more" if lang == "en" else f" و{extra} أخرى"
    return shown


def build_status_answer(r, lang):
    w = r["data_window"]
    c = r["status_counts"]
    total = r["total_assets"]
    pct = round(c["normal"] / total * 100, 1) if total else 0.0
    attn = _attention_text(r["attention"], lang)
    name = r["building"]["name"]

    if lang == "en":
        answer = (
            f"Building status for {name}, window {w['start']} to {w['end_exclusive']} UTC "
            f"(last {w['hours']} hours, anchored to the end of the dataset): "
            f"{c['normal']} of {total} assets are Normal ({pct}%), "
            f"{c['warning']} Warning, {c['critical']} Critical, {c['no_data']} No data. "
            f"Recorded events in the window: {r['warning_events']} warning and "
            f"{r['critical_events']} critical. Assets needing attention: {attn}."
        )
        limits = [
            "Status comes from recorded warning/critical events in the window; "
            "a recorded event is not necessarily still active.",
            "Telemetry-based incident detection (Day 4) is not part of this answer.",
        ]
    else:
        answer = (
            f"حالة المبنى {name} للفترة من {w['start']} إلى {w['end_exclusive']} UTC "
            f"(آخر {w['hours']} ساعة، مرتبطة بنهاية البيانات): "
            f"{c['normal']} من أصل {total} أصل بحالة طبيعي ({pct}%)، "
            f"{c['warning']} بحالة تحذير، {c['critical']} بحالة حرج، {c['no_data']} بدون بيانات. "
            f"الأحداث المسجلة في الفترة: {r['warning_events']} تحذير و{r['critical_events']} حرج. "
            f"الأصول التي تحتاج إلى انتباه: {attn}."
        )
        limits = [
            "الحالة مبنية على أحداث التحذير والحرج المسجلة في الفترة، "
            "والحدث المسجل ليس بالضرورة ما زال نشطا.",
            "كشف الحوادث المبني على القياسات (اليوم الرابع) غير مشمول في هذه الإجابة.",
        ]

    evidence = [
        {"type": "kpis", "source": "Day 3 dashboard KPIs", "items": r["kpis"]},
        {"type": "status_counts", "source": "Day 3 asset status", "items": c},
        {"type": "assets_needing_attention", "source": "Day 3 asset status", "items": r["attention"]},
    ]
    return answer, limits, evidence


def build_cctv_answer(r, lang):
    w = r["data_window"]
    pct = r["availability_pct"]
    n = r["cameras_observed"]
    missing = ", ".join(r["without_heartbeat"]) or ("none" if lang == "en" else "لا يوجد")

    if lang == "en":
        pct_text = f"{pct}%" if pct is not None else "not calculable"
        answer = (
            f"CCTV availability is inferred from heartbeat events, not from a direct "
            f"online/offline state. Window {w['start']} to {w['end_exclusive']} UTC "
            f"(last {w['hours']} hours). {r['cameras_reporting']} of {n} cameras sent at least "
            f"one heartbeat. Heartbeats received: {r['total_heartbeats']} of "
            f"{r['total_expected']} expected ({pct_text}). Cameras without heartbeat: {missing}."
        )
        for d in r["disagreements"]:
            answer += (
                f" {d['asset_code']} reported camera_offline at {d['offline_ts']}, "
                f"but its heartbeats continued, so the two signals disagree."
            )
        limits = [
            "Expected heartbeats are derived from each camera's observed reporting interval.",
            "camera_offline and camera_online events are recorded states and may disagree with heartbeats.",
        ]
    else:
        pct_text = f"{pct}%" if pct is not None else "غير قابلة للحساب"
        answer = (
            f"يتم استنتاج توفر الكاميرات من أحداث heartbeat وليس من حالة اتصال مباشرة. "
            f"الفترة من {w['start']} إلى {w['end_exclusive']} UTC (آخر {w['hours']} ساعة). "
            f"أرسلت {r['cameras_reporting']} من أصل {n} كاميرا نبضة واحدة على الأقل. "
            f"عدد النبضات المستلمة: {r['total_heartbeats']} من أصل {r['total_expected']} متوقعة ({pct_text}). "
            f"الكاميرات بدون نبضات: {missing}."
        )
        for d in r["disagreements"]:
            answer += (
                f" سجلت {d['asset_code']} الحدث camera_offline في {d['offline_ts']}، "
                f"لكن نبضاتها استمرت، لذلك الإشارتان غير متطابقتين."
            )
        limits = [
            "النبضات المتوقعة محسوبة من فترة الإبلاغ الملاحظة لكل كاميرا.",
            "أحداث camera_offline وcamera_online حالات مسجلة وقد لا تتفق مع النبضات.",
        ]

    evidence = [
        {"type": "cctv_cameras", "source": "Day 2 heartbeat and camera events", "items": r["cameras"]},
        {"type": "signal_disagreements", "source": "Python comparison", "items": r["disagreements"]},
    ]
    return answer, limits, evidence