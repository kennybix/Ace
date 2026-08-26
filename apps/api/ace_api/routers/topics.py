"""Topic as a destination: detail, on-demand lesson, on-demand curated video, ad-hoc drill."""

from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from ace_api import db
from ace_api.engine import lessons as lessons_engine
from ace_api.jobs.videos import curate_for_topic
from ace_api.security import current_user, owned_exam

router = APIRouter(prefix="/topics", tags=["topics"])


async def _topic_for_user(topic_id: int, user: dict) -> dict:
    t = await db.fetch_one("SELECT * FROM topics WHERE id=%s", (topic_id,))
    if not t or not t["exam_id"]:
        raise HTTPException(404, "topic not found")
    await owned_exam(t["exam_id"], user)
    return t


@router.get("/{topic_id}")
async def topic_detail(topic_id: int, user=Depends(current_user)):
    t = await _topic_for_user(topic_id, user)
    mastery = await db.fetch_one(
        "SELECT rating, n_attempts FROM mastery WHERE exam_id=%s AND topic_id=%s",
        (t["exam_id"], topic_id))
    lesson = await db.fetch_one(
        """SELECT id, body, created_at FROM lessons WHERE exam_id=%s AND topic_id=%s
           AND kind='micro_lesson' ORDER BY id DESC LIMIT 1""", (t["exam_id"], topic_id))
    video = await db.fetch_one(
        """SELECT id, youtube_id, title, curation_score FROM videos
           WHERE exam_id=%s AND topic_id=%s AND status='active'
           ORDER BY curation_score DESC LIMIT 1""", (t["exam_id"], topic_id))
    qn = await db.fetch_one(
        """SELECT count(*) AS n FROM questions q
           WHERE q.exam_id=%s AND q.status='active'
             AND q.topic_id IN (SELECT id FROM topics WHERE exam_id=%s AND (id=%s OR parent_id=%s))""",
        (t["exam_id"], t["exam_id"], topic_id, topic_id))
    return {
        "id": t["id"], "code": t["code"], "title": t["title"],
        "cognitive_levels": t["cognitive_levels"], "weight": t["weight"],
        "mastery": mastery["rating"] if mastery else None,
        "attempts": mastery["n_attempts"] if mastery else 0,
        "question_count": qn["n"],
        "lesson": lesson,
        "video": video,
    }


@router.post("/{topic_id}/lesson")
async def get_or_write_lesson(topic_id: int, rewrite: bool = False,
                              user=Depends(current_user)):
    """Return the topic's micro-lesson, writing one on demand. rewrite=true forces a fresh,
    deeper take (the old version stays in history)."""
    t = await _topic_for_user(topic_id, user)
    if not rewrite:
        existing = await db.fetch_one(
            """SELECT id, body FROM lessons WHERE exam_id=%s AND topic_id=%s
               AND kind='micro_lesson' ORDER BY id DESC LIMIT 1""", (t["exam_id"], topic_id))
        if existing:
            return {"lesson_id": existing["id"], "body": existing["body"], "created": False}
    out = await lessons_engine.build_lesson(t["exam_id"], topic_id, "micro_lesson",
                                            user["selected_model"])
    if "error" in out:
        raise HTTPException(
            400, "No source material covers this topic yet — upload a textbook or notes for "
                 "it in the Library and Ace will write the lesson from them.")
    return {"lesson_id": out["lesson_id"], "body": out["body"], "created": True}


@router.post("/{topic_id}/video")
async def get_or_curate_video(topic_id: int, user=Depends(current_user)):
    """Return the topic's best video, curating one on demand if none exists."""
    t = await _topic_for_user(topic_id, user)
    existing = await db.fetch_one(
        """SELECT id, youtube_id, title FROM videos WHERE exam_id=%s AND topic_id=%s
           AND status='active' ORDER BY curation_score DESC LIMIT 1""",
        (t["exam_id"], topic_id))
    if existing:
        return {"video": existing, "created": False}
    stored = await curate_for_topic(t["exam_id"], topic_id)
    if not stored:
        return {"video": None, "created": False,
                "note": "No suitable video verified for this topic yet — Ace retries nightly."}
    video = await db.fetch_one(
        """SELECT id, youtube_id, title FROM videos WHERE exam_id=%s AND topic_id=%s
           AND status='active' ORDER BY curation_score DESC LIMIT 1""",
        (t["exam_id"], topic_id))
    return {"video": video, "created": True}


@router.post("/{topic_id}/drill")
async def start_topic_drill(topic_id: int, bg: BackgroundTasks, user=Depends(current_user)):
    """Ad-hoc practice for one topic. Pool priority: this topic → its whole element →
    repeats. A thin topic also triggers background generation so it stocks up over time."""
    t = await _topic_for_user(topic_id, user)
    exam_id = t["exam_id"]

    async def pool(scope_sql: str, params: tuple, unattempted: bool) -> list[int]:
        cond = ("AND NOT EXISTS (SELECT 1 FROM attempts a WHERE a.question_id=q.id "
                "AND a.exam_id=%s)") if unattempted else ""
        rows = await db.fetch_all(
            f"""SELECT q.id FROM questions q
                WHERE q.exam_id=%s AND q.status='active'
                  AND q.payload->>'correct_index' IS NOT NULL
                  AND q.topic_id IN ({scope_sql}) {cond}
                ORDER BY (q.source='extracted') DESC, random() LIMIT 8""",
            (exam_id, *params, *((exam_id,) if unattempted else ())))
        return [r["id"] for r in rows]

    own_scope = "SELECT id FROM topics WHERE exam_id=%s AND (id=%s OR parent_id=%s)"
    element_scope = ("SELECT t2.id FROM topics t1 JOIN topics t2 "
                     "ON t2.parent_id = COALESCE(t1.parent_id, t1.id) OR t2.id = t1.id "
                     "WHERE t1.id=%s")

    qids = await pool(own_scope, (exam_id, topic_id, topic_id), True)
    own_count = len(qids)
    scope = "topic"
    if len(qids) < 5:  # borrow siblings from the same element so drills always work
        extra = await pool(element_scope, (topic_id,), True)
        qids += [q for q in extra if q not in set(qids)]
        qids = qids[:8]
        scope = "element" if qids and own_count < len(qids) else scope
    if not qids:
        qids = await pool(element_scope, (topic_id,), False)  # repeats beat a dead end
        scope = "element"
    if not qids:
        raise HTTPException(400, "No practice questions exist for this topic yet — add "
                                 "materials in the Library.")

    # thin topic: stock it up in the background for next time (grounded in its own chunks)
    if own_count < 4:
        from ace_api.engine.generator import generate_for_topic, pick_format
        fmt = await pick_format(exam_id)
        bg.add_task(generate_for_topic, exam_id, t["code"], fmt, 4 - own_count,
                    user["selected_model"])

    sess = await db.fetch_one(
        """INSERT INTO sessions (exam_id, kind, prepared_payload)
           VALUES (%s,'daily',%s) RETURNING id""",
        (exam_id, json.dumps({"question_ids": qids, "review_ids": [], "lesson_id": None,
                              "video_id": None, "topic_drill": t["code"]})))
    return {"session_id": sess["id"], "count": len(qids), "scope": scope,
            "restocking": own_count < 4}
