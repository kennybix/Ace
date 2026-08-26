from fastapi import APIRouter, Depends, HTTPException

from ace_api import db
from ace_api.security import current_user, owned_exam

router = APIRouter(prefix="/exams/{exam_id}/plan", tags=["plan"])


@router.get("")
async def get_plan(exam_id: int, user=Depends(current_user)):
    await owned_exam(exam_id, user)
    plan = await db.fetch_one(
        "SELECT * FROM plans WHERE exam_id=%s AND status='active'", (exam_id,))
    if not plan:
        raise HTTPException(404, "no active plan — complete the diagnostic first")
    items = await db.fetch_all(
        """SELECT pi.id, pi.day, pi.kind, pi.est_minutes, pi.status, pi.topic_ids,
                  (SELECT array_agg(code ORDER BY code) FROM topics WHERE id = ANY(pi.topic_ids))
                  AS topic_codes
           FROM plan_items pi WHERE pi.plan_id=%s ORDER BY pi.day""", (plan["id"],))
    # lifetime progress survives plan rebuilds — it comes from sessions, not plan items
    done = await db.fetch_one(
        "SELECT count(*) AS n FROM sessions WHERE exam_id=%s AND kind='daily' "
        "AND completed_at IS NOT NULL", (exam_id,))
    return {"plan_id": plan["id"], "version": plan["version"], "rationale": plan["rationale"],
            "completed_sessions": done["n"],
            "items": [{**i, "day": str(i["day"])} for i in items]}


@router.get("/today")
async def today_item(exam_id: int, user=Depends(current_user)):
    await owned_exam(exam_id, user)
    row = await db.fetch_one(
        """SELECT pi.* FROM plan_items pi JOIN plans p ON p.id=pi.plan_id
           WHERE p.exam_id=%s AND p.status='active' AND pi.day <= CURRENT_DATE
             AND pi.status IN ('pending','prepared')
           ORDER BY pi.day LIMIT 1""", (exam_id,))
    if not row:
        return {"item": None}
    sess = await db.fetch_one(
        "SELECT id, prepared_payload, started_at, completed_at FROM sessions WHERE plan_item_id=%s "
        "ORDER BY id DESC LIMIT 1", (row["id"],))
    return {"item": {**{k: row[k] for k in ("id", "kind", "est_minutes", "status", "topic_ids")},
                     "day": str(row["day"])},
            "session": sess}


@router.get("/next")
async def next_item(exam_id: int, user=Depends(current_user)):
    """Next pending session regardless of date — powers 'start early'."""
    await owned_exam(exam_id, user)
    row = await db.fetch_one(
        """SELECT pi.* FROM plan_items pi JOIN plans p ON p.id=pi.plan_id
           WHERE p.exam_id=%s AND p.status='active' AND pi.status IN ('pending','prepared')
           ORDER BY pi.day LIMIT 1""", (exam_id,))
    if not row:
        return {"item": None}
    return {"item": {**{k: row[k] for k in ("id", "kind", "est_minutes", "status",
                                            "topic_ids")},
                     "day": str(row["day"])}}


@router.post("/rebuild")
async def rebuild(exam_id: int, user=Depends(current_user)):
    await owned_exam(exam_id, user)
    from ace_api.engine import planner
    out = await planner.build_plan(exam_id)
    if "error" in out:
        raise HTTPException(400, out["error"])
    return out
