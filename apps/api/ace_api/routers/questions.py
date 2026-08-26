from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ace_api import db
from ace_api.security import current_user

router = APIRouter(prefix="/questions", tags=["questions"])

KILL_THRESHOLD = 2  # reports before a question is pulled


class ReportIn(BaseModel):
    reason: str = ""


class BatchIn(BaseModel):
    ids: list[int]


@router.post("/batch")
async def batch_get(body: BatchIn, user=Depends(current_user)):
    """Client-safe payloads (answers stripped) — only for questions in the user's own exams."""
    from ace_api.routers.sessions import _questions_for_client
    owned = await db.fetch_all(
        """SELECT q.id FROM questions q JOIN exams e ON e.id=q.exam_id
           WHERE q.id = ANY(%s) AND e.user_id=%s""", (body.ids[:200], user["id"]))
    owned_ids = [r["id"] for r in owned]
    ordered = [i for i in body.ids[:200] if i in set(owned_ids)]
    return {"questions": await _questions_for_client(ordered)}


@router.post("/{question_id}/report")
async def report_question(question_id: int, body: ReportIn, user=Depends(current_user)):
    q = await db.fetch_one(
        """SELECT q.id FROM questions q JOIN exams e ON e.id=q.exam_id
           WHERE q.id=%s AND e.user_id=%s""", (question_id, user["id"]))
    if not q:
        raise HTTPException(404, "question not found")
    await db.execute(
        "INSERT INTO question_reports (question_id, user_id, reason) VALUES (%s,%s,%s)",
        (question_id, user["id"], body.reason))
    n = await db.fetch_one("SELECT count(*) AS n FROM question_reports WHERE question_id=%s",
                           (question_id,))
    if n["n"] >= KILL_THRESHOLD:
        await db.execute("UPDATE questions SET status='killed' WHERE id=%s", (question_id,))
    return {"reported": True, "question_status": "killed" if n["n"] >= KILL_THRESHOLD else "active"}
