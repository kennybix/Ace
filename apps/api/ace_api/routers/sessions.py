import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ace_api import db
from ace_api.engine import assessor, gamify, session_prep
from ace_api.engine.graders import grade
from ace_api.security import current_user, owned_exam

router = APIRouter(tags=["sessions"])


class AttemptIn(BaseModel):
    exam_id: int
    question_id: int
    session_id: int | None = None
    mock_id: int | None = None
    answer: dict
    confidence: str | None = None  # sure|think|guess
    ms_taken: int | None = None


@router.post("/plan-items/{plan_item_id}/session/start")
async def start_session(plan_item_id: int, user=Depends(current_user)):
    item = await db.fetch_one(
        """SELECT pi.id, p.exam_id FROM plan_items pi JOIN plans p ON p.id=pi.plan_id WHERE pi.id=%s""",
        (plan_item_id,))
    if not item:
        raise HTTPException(404, "plan item not found")
    await owned_exam(item["exam_id"], user)
    sess = await db.fetch_one(
        "SELECT * FROM sessions WHERE plan_item_id=%s ORDER BY id DESC LIMIT 1", (plan_item_id,))
    if not sess:
        out = await session_prep.prepare_session(plan_item_id)
        sess = await db.fetch_one("SELECT * FROM sessions WHERE id=%s", (out["session_id"],))
    return await _serve_session(sess)


@router.post("/sessions/{session_id}/open")
async def open_session(session_id: int, user=Depends(current_user)):
    """Open any session by id (topic drills, resumed sessions)."""
    sess = await db.fetch_one("SELECT * FROM sessions WHERE id=%s", (session_id,))
    if not sess:
        raise HTTPException(404, "session not found")
    await owned_exam(sess["exam_id"], user)
    return await _serve_session(sess)


async def _serve_session(sess: dict) -> dict:
    await db.execute("UPDATE sessions SET started_at=COALESCE(started_at, now()) WHERE id=%s",
                     (sess["id"],))
    payload = sess["prepared_payload"]
    lesson = None
    if payload.get("lesson_id"):
        lesson = await db.fetch_one("SELECT id, kind, body, citations FROM lessons WHERE id=%s",
                                    (payload["lesson_id"],))
    qids = (payload.get("question_ids") or []) + (payload.get("review_ids") or [])
    # resume-safe: never re-serve what's already answered in this session
    answered = {r["question_id"] for r in await db.fetch_all(
        "SELECT question_id FROM attempts WHERE session_id=%s", (sess["id"],))}
    qids = [q for q in qids if q not in answered]
    # 400 only when the session NEVER had anything — if the user answered everything and
    # bailed before the finish screen, an empty list lets the app complete it gracefully
    if not qids and lesson is None and not answered:
        raise HTTPException(
            400, "This session has no content to serve. Add materials in the Library "
                 "(or restore the official practice questions), then try again.")
    video = None
    if payload.get("video_id"):
        video = await db.fetch_one(
            "SELECT id, youtube_id, title FROM videos WHERE id=%s AND status='active'",
            (payload["video_id"],))
    questions = await _questions_for_client(qids)
    return {"session_id": sess["id"], "exam_id": sess["exam_id"], "lesson": lesson,
            "video": video, "questions": questions, "already_answered": len(answered)}


async def _questions_for_client(qids: list[int]) -> list[dict]:
    if not qids:
        return []
    rows = await db.fetch_all(
        "SELECT id, format, cognitive_level, payload, citations FROM questions WHERE id = ANY(%s)",
        (qids,))
    out = []
    for r in sorted(rows, key=lambda r: qids.index(r["id"])):
        p = dict(r["payload"])
        answer_keys = {"correct_index", "answer", "answers", "pairs", "explanation",
                       "option_notes"}
        client_payload = {k: v for k, v in p.items() if k not in answer_keys}
        if r["format"] == "match":
            client_payload["left"], client_payload["right"] = p.get("left", []), p.get("right", [])
        out.append({"id": r["id"], "format": r["format"], "cognitive_level": r["cognitive_level"],
                    "payload": client_payload})
    return out


@router.post("/attempts")
async def submit_attempt(body: AttemptIn, user=Depends(current_user)):
    await owned_exam(body.exam_id, user)
    q = await db.fetch_one("SELECT * FROM questions WHERE id=%s", (body.question_id,))
    if not q:
        raise HTTPException(404, "question not found")
    if q["exam_id"] != body.exam_id:
        raise HTTPException(400, "question does not belong to this exam")
    if body.session_id:
        s = await db.fetch_one("SELECT exam_id FROM sessions WHERE id=%s", (body.session_id,))
        if not s or s["exam_id"] != body.exam_id:
            raise HTTPException(400, "session does not belong to this exam")
    if body.mock_id:
        m = await db.fetch_one("SELECT exam_id FROM mocks WHERE id=%s", (body.mock_id,))
        if not m or m["exam_id"] != body.exam_id:
            raise HTTPException(400, "mock does not belong to this exam")
    correct = grade(q["format"], q["payload"], body.answer)
    await db.execute(
        """INSERT INTO attempts (session_id, mock_id, question_id, exam_id, answer, correct,
                                 confidence, ms_taken)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (body.session_id, body.mock_id, body.question_id, body.exam_id,
         json.dumps(body.answer), correct, body.confidence, body.ms_taken))
    await assessor.on_attempt(body.exam_id, body.question_id, correct, body.confidence)
    if correct:
        await gamify.award(user["id"], "question_correct")
    p = q["payload"]
    reveal = {"correct": correct, "explanation": p.get("explanation", ""),
              "citations": q["citations"]}
    if q["format"] == "mcq":
        reveal["correct_index"] = p["correct_index"]
        if p.get("option_notes"):
            reveal["option_notes"] = p["option_notes"]
    elif q["format"] == "tf":
        reveal["answer"] = p["answer"]
    elif q["format"] == "gap":
        reveal["answers"] = p["answers"]
    elif q["format"] == "match":
        reveal["pairs"] = p["pairs"]
    elif q["format"] == "numeric":
        reveal["answer"] = p["answer"]
    return reveal


@router.post("/sessions/{session_id}/complete")
async def complete_session(session_id: int, user=Depends(current_user)):
    sess = await db.fetch_one("SELECT * FROM sessions WHERE id=%s", (session_id,))
    if not sess:
        raise HTTPException(404, "session not found")
    await owned_exam(sess["exam_id"], user)
    first_completion = sess["completed_at"] is None
    await db.execute(
        "UPDATE sessions SET completed_at=COALESCE(completed_at, now()) WHERE id=%s",
        (session_id,))
    if sess["plan_item_id"]:
        await db.execute("UPDATE plan_items SET status='done' WHERE id=%s", (sess["plan_item_id"],))
    if first_completion:  # re-entering a finished session must never double-award
        await gamify.award(user["id"], "session_complete")
        done = await db.fetch_one(
            "SELECT count(*) AS n FROM sessions WHERE exam_id=%s AND completed_at IS NOT NULL "
            "AND kind='daily'", (sess["exam_id"],))
        if done["n"] == 1:
            await gamify.grant(user["id"], "first_session")
    streak = await gamify.touch_streak(user["id"])
    stats = await db.fetch_one(
        """SELECT count(*) AS answered, count(*) FILTER (WHERE correct) AS correct
           FROM attempts WHERE session_id=%s""", (session_id,))
    return {"completed": True, "streak": streak, **stats}
