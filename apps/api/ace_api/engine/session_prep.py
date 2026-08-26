"""Session preparation (nightly batch + on-demand): lesson → video slot → drills → reviews."""

from __future__ import annotations

import json
from datetime import date, timedelta

from ace_api import db
from ace_api.engine import assessor, generator, lessons

DRILLS_PER_SESSION = 10


async def prepare_session(plan_item_id: int, model_id: str | None = None) -> dict:
    item = await db.fetch_one("SELECT * FROM plan_items WHERE id=%s", (plan_item_id,))
    plan = await db.fetch_one("SELECT exam_id FROM plans WHERE id=%s", (item["plan_id"],))
    exam_id = plan["exam_id"]
    exam = await db.fetch_one("SELECT e.*, u.selected_model FROM exams e JOIN users u ON u.id=e.user_id "
                              "WHERE e.id=%s", (exam_id,))
    model = model_id or exam["selected_model"]

    payload: dict = {"question_ids": [], "review_ids": [], "lesson_id": None, "video_id": None}
    topic_ids = item["topic_ids"] or []

    if item["kind"] in ("learn", "taper") and topic_ids:
        lead_topic = topic_ids[0]
        existing = await db.fetch_one(
            "SELECT id FROM lessons WHERE exam_id=%s AND topic_id=%s AND kind='micro_lesson' LIMIT 1",
            (exam_id, lead_topic))
        if existing:
            payload["lesson_id"] = existing["id"]
        else:
            out = await lessons.build_lesson(exam_id, lead_topic, "micro_lesson", model)
            payload["lesson_id"] = out.get("lesson_id")

        video = await db.fetch_one(
            "SELECT id FROM videos WHERE exam_id=%s AND topic_id=ANY(%s) AND status='active' "
            "ORDER BY curation_score DESC LIMIT 1", (exam_id, topic_ids))
        if video:
            payload["video_id"] = video["id"]

        # drills: unattempted extracted first, then generated top-up in profile formats
        per_topic = max(2, DRILLS_PER_SESSION // max(len(topic_ids), 1))
        for tid in topic_ids:
            rows = await db.fetch_all(
                """SELECT q.id FROM questions q
                   WHERE q.exam_id=%s AND q.topic_id=%s AND q.status='active'
                     AND q.payload->>'correct_index' IS NOT NULL
                     AND NOT EXISTS (SELECT 1 FROM attempts a WHERE a.question_id=q.id AND a.exam_id=%s)
                   ORDER BY (q.source='extracted') DESC, random() LIMIT %s""",
                (exam_id, tid, exam_id, per_topic))
            ids = [r["id"] for r in rows]
            if len(ids) < per_topic:
                topic = await db.fetch_one("SELECT code FROM topics WHERE id=%s", (tid,))
                fmt = await generator.pick_format(exam_id)
                gen = await generator.generate_for_topic(exam_id, topic["code"], fmt,
                                                         per_topic - len(ids), model)
                ids += gen.get("accepted", [])
            payload["question_ids"] += ids

    # fallback: a session must never be empty — if the item's topics have no pool,
    # drill the exam-wide unattempted pool instead
    if item["kind"] in ("learn", "taper") and not payload["question_ids"]:
        rows = await db.fetch_all(
            """SELECT q.id FROM questions q
               WHERE q.exam_id=%s AND q.status='active'
                 AND q.payload->>'correct_index' IS NOT NULL
                 AND NOT EXISTS (SELECT 1 FROM attempts a WHERE a.question_id=q.id
                                 AND a.exam_id=%s)
               ORDER BY (q.source='extracted') DESC, random() LIMIT %s""",
            (exam_id, exam_id, DRILLS_PER_SESSION))
        payload["question_ids"] = [r["id"] for r in rows]

    payload["review_ids"] = await assessor.due_reviews(exam_id, 5)

    sess = await db.fetch_one(
        """INSERT INTO sessions (plan_item_id, exam_id, kind, prepared_payload, model_id)
           VALUES (%s,%s,'daily',%s,%s) RETURNING id""",
        (plan_item_id, exam_id, json.dumps(payload), model))
    await db.execute("UPDATE plan_items SET status='prepared' WHERE id=%s", (plan_item_id,))
    return {"session_id": sess["id"], **payload}


async def nightly(exam_id: int | None = None) -> dict:
    """Nightly batch per active exam: prepare upcoming sessions, then run the content
    improvement cycle (replace killed, re-audit, refresh stuck lessons, top up pools).
    Slow and thorough on purpose — nothing here is latency-sensitive."""
    from ace_api.engine import improvement

    exams = await db.fetch_all(
        "SELECT id FROM exams WHERE status='active'" + (" AND id=%s" if exam_id else ""),
        (exam_id,) if exam_id else ())
    prepared = 0
    improve_totals: dict[str, int] = {}
    horizon = date.today() + timedelta(days=1)
    for e in exams:
        items = await db.fetch_all(
            """SELECT pi.id FROM plan_items pi JOIN plans p ON p.id=pi.plan_id
               WHERE p.exam_id=%s AND p.status='active' AND pi.status='pending' AND pi.day<=%s
                 AND pi.kind IN ('learn','taper')""", (e["id"], horizon))
        for it in items:
            await prepare_session(it["id"])
            prepared += 1
        try:
            stats = await improvement.run_cycle(e["id"])
            for k, v in stats.items():
                improve_totals[k] = improve_totals.get(k, 0) + v
        except Exception as ex:  # a failed improvement pass must never block session prep
            improve_totals["errors"] = improve_totals.get("errors", 0) + 1
            improve_totals["last_error"] = str(ex)[:120]  # type: ignore[assignment]
    return {"exams": len(exams), "sessions_prepared": prepared, "improvement": improve_totals}
