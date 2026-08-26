from fastapi import APIRouter, Depends, HTTPException

from ace_api import db
from ace_api.engine import gamify, mock_exam
from ace_api.security import current_user, owned_exam

router = APIRouter(prefix="/exams/{exam_id}/mocks", tags=["mocks"])


@router.post("/start")
async def start_mock(exam_id: int, user=Depends(current_user)):
    await owned_exam(exam_id, user)
    out = await mock_exam.start(exam_id)
    if "error" in out:
        raise HTTPException(400, out["error"])
    from ace_api.routers.sessions import _questions_for_client
    out["questions"] = await _questions_for_client(out.pop("question_ids"))
    return out


@router.post("/{mock_id}/submit")
async def submit_mock(exam_id: int, mock_id: int, user=Depends(current_user)):
    await owned_exam(exam_id, user)
    mock = await db.fetch_one("SELECT exam_id, submitted_at FROM mocks WHERE id=%s", (mock_id,))
    if not mock or mock["exam_id"] != exam_id:
        raise HTTPException(404, "mock not found")
    first_submission = mock["submitted_at"] is None
    out = await mock_exam.submit(mock_id)
    if "error" in out:
        raise HTTPException(400, out["error"])
    if first_submission:  # resubmits recompute the score but never re-award
        await gamify.award(user["id"], "mock_complete")
        await gamify.grant(user["id"], "first_mock")
        if out["score"] >= 0.6:
            await gamify.grant(user["id"], "mock_pass")
    # a due plan-milestone mock is satisfied by taking any mock — don't leave Today stuck on it
    await db.execute(
        """UPDATE plan_items SET status='done' WHERE id IN (
             SELECT pi.id FROM plan_items pi JOIN plans p ON p.id=pi.plan_id
             WHERE p.exam_id=%s AND p.status='active' AND pi.kind='mock'
               AND pi.status IN ('pending','prepared') AND pi.day <= CURRENT_DATE
             ORDER BY pi.day LIMIT 1)""", (exam_id,))
    return out


@router.get("/{mock_id}/report")
async def mock_report(exam_id: int, mock_id: int, user=Depends(current_user)):
    await owned_exam(exam_id, user)
    mock = await db.fetch_one("SELECT * FROM mocks WHERE id=%s AND exam_id=%s", (mock_id, exam_id))
    if not mock:
        raise HTTPException(404, "mock not found")
    return {"mock_id": mock["id"], "score": mock["score"],
            "per_element": mock["per_element_scores"], "blueprint": mock["blueprint"],
            "started_at": str(mock["started_at"]), "submitted_at": str(mock["submitted_at"])}
