from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ace_api import db
from ace_api.security import current_user

router = APIRouter(prefix="/videos", tags=["videos"])


class ReportIn(BaseModel):
    reason: str = ""


@router.get("/{video_id}")
async def get_video(video_id: int, user=Depends(current_user)):
    from ace_api.security import owned_exam
    v = await db.fetch_one(
        "SELECT id, exam_id, youtube_id, title, duration_s, status FROM videos WHERE id=%s",
        (video_id,))
    if v and v["exam_id"]:
        await owned_exam(v["exam_id"], user)
    return {"video": v}


@router.post("/{video_id}/report")
async def report_video(video_id: int, body: ReportIn, user=Depends(current_user)):
    # one report pulls a video from rotation — but only the exam's owner may report it
    v = await db.fetch_one(
        """SELECT v.id FROM videos v JOIN exams e ON e.id=v.exam_id
           WHERE v.id=%s AND e.user_id=%s""", (video_id, user["id"]))
    if not v:
        from fastapi import HTTPException
        raise HTTPException(404, "video not found")
    await db.execute("UPDATE videos SET status='reported' WHERE id=%s", (video_id,))
    return {"reported": True}
