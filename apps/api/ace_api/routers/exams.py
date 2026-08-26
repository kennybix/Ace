import hashlib
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from ace_api import db
from ace_api.config import settings
from ace_api.engine import diagnostic, exam_setup, ingestion
from ace_api.security import current_user, owned_exam

router = APIRouter(prefix="/exams", tags=["exams"])


class ExamCreate(BaseModel):
    name: str
    exam_date: str | None = None
    weekly_hours: int = 5


class ExamPatch(BaseModel):
    exam_date: str | None = None
    weekly_hours: int | None = None


@router.post("")
async def create_exam(body: ExamCreate, user=Depends(current_user)):
    return await exam_setup.create_exam(user["id"], body.name, body.exam_date, body.weekly_hours)


@router.get("")
async def list_my_exams(user=Depends(current_user)):
    rows = await db.fetch_all(
        """SELECT id, name_raw, status, exam_date, weekly_hours FROM exams
           WHERE user_id=%s ORDER BY id DESC""", (user["id"],))
    return {"exams": [{**r, "exam_date": str(r["exam_date"]) if r["exam_date"] else None}
                      for r in rows]}


@router.patch("/{exam_id}")
async def patch_exam(exam_id: int, body: ExamPatch, user=Depends(current_user)):
    await owned_exam(exam_id, user)
    if body.exam_date:
        await db.execute("UPDATE exams SET exam_date=%s WHERE id=%s", (body.exam_date, exam_id))
    if body.weekly_hours:
        await db.execute("UPDATE exams SET weekly_hours=%s WHERE id=%s",
                         (body.weekly_hours, exam_id))
    rebuilt = False
    plan = await db.fetch_one(
        "SELECT id FROM plans WHERE exam_id=%s AND status='active'", (exam_id,))
    if plan and (body.exam_date or body.weekly_hours):
        from ace_api.engine import planner
        out = await planner.build_plan(exam_id)
        rebuilt = "plan_id" in out
    return {"updated": True, "plan_rebuilt": rebuilt}


@router.get("/{exam_id}")
async def get_exam(exam_id: int, user=Depends(current_user)):
    exam = await owned_exam(exam_id, user)
    docs = await db.fetch_all(
        "SELECT id, filename, kind, parse_status, page_count FROM documents WHERE exam_id=%s", (exam_id,))
    counts = await db.fetch_one(
        """SELECT (SELECT count(*) FROM topics WHERE exam_id=%s) AS topics,
                  (SELECT count(*) FROM chunks WHERE exam_id=%s) AS chunks,
                  (SELECT count(*) FROM questions WHERE exam_id=%s AND status='active') AS questions""",
        (exam_id, exam_id, exam_id))
    return {"id": exam["id"], "name_raw": exam["name_raw"], "status": exam["status"],
            "weekly_hours": exam["weekly_hours"], "accelerator_id": exam["accelerator_id"],
            "exam_date": str(exam["exam_date"]) if exam["exam_date"] else None,
            "documents": docs, "counts": counts}


@router.post("/{exam_id}/documents")
async def upload_document(exam_id: int, file: UploadFile, bg: BackgroundTasks,
                          user=Depends(current_user)):
    await owned_exam(exam_id, user)
    if not file.filename.lower().endswith((".pdf", ".epub")):
        raise HTTPException(400, "PDF or EPUB only")
    data = await file.read()
    updir = Path(settings().upload_dir) / str(exam_id)
    updir.mkdir(parents=True, exist_ok=True)
    dest = updir / file.filename
    dest.write_bytes(data)
    doc = await db.fetch_one(
        """INSERT INTO documents (exam_id, filename, sha256, stored_path)
           VALUES (%s,%s,%s,%s) RETURNING id""",
        (exam_id, file.filename, hashlib.sha256(data).hexdigest(), str(dest)))
    await db.execute("UPDATE exams SET status='ingesting' WHERE id=%s", (exam_id,))
    bg.add_task(_ingest_and_finalize, doc["id"], exam_id)
    return {"document_id": doc["id"], "status": "ingesting"}


async def _ingest_and_finalize(document_id: int, exam_id: int) -> None:
    try:
        await ingestion.ingest_document(document_id)
        pending = await db.fetch_one(
            "SELECT count(*) AS n FROM documents WHERE exam_id=%s AND parse_status='pending'", (exam_id,))
        if pending["n"] == 0:
            await ingestion.finalize_exam(exam_id)
    except Exception:
        await db.execute("UPDATE documents SET parse_status='failed' WHERE id=%s", (document_id,))


@router.get("/{exam_id}/ingestion-status")
async def ingestion_status(exam_id: int, user=Depends(current_user)):
    exam = await owned_exam(exam_id, user)
    docs = await db.fetch_all(
        "SELECT id, filename, kind, parse_status FROM documents WHERE exam_id=%s", (exam_id,))
    return {"exam_status": exam["status"], "documents": docs}


@router.get("/{exam_id}/topic-tree")
async def get_topic_tree(exam_id: int, user=Depends(current_user)):
    await owned_exam(exam_id, user)
    rows = await db.fetch_all(
        """SELECT t.id, t.parent_id, t.code, t.title, t.weight, t.cognitive_levels, t.source,
                  m.rating AS mastery, COALESCE(m.n_attempts, 0) AS attempts,
                  (SELECT count(*) FROM questions q
                   WHERE q.topic_id = t.id AND q.status = 'active') AS question_count
           FROM topics t
           LEFT JOIN mastery m ON m.exam_id = t.exam_id AND m.topic_id = t.id
           WHERE t.exam_id=%s ORDER BY t.code""", (exam_id,))
    return {"topics": rows}


@router.get("/{exam_id}/sources")
async def content_sources(exam_id: int, user=Depends(current_user)):
    """Everything feeding this exam's environment: preloaded packs + uploads, with counts."""
    exam = await owned_exam(exam_id, user)
    out: dict = {"preloaded": None, "documents": []}
    if exam["accelerator_id"]:
        acc = await db.fetch_one("SELECT display_name, provenance FROM accelerators WHERE id=%s",
                                 (exam["accelerator_id"],))
        counts = await db.fetch_one(
            """SELECT
                 (SELECT count(*) FROM topics WHERE exam_id=%s AND source='syllabus_parsed')
                   AS topics,
                 (SELECT count(*) FROM questions WHERE exam_id=%s AND source='extracted'
                    AND external_item_id IS NOT NULL AND status='active') AS active_questions,
                 (SELECT count(*) FROM questions WHERE exam_id=%s AND source='extracted'
                    AND external_item_id IS NOT NULL AND status='removed') AS removed_questions""",
            (exam_id, exam_id, exam_id))
        out["preloaded"] = {"name": acc["display_name"], "provenance": acc["provenance"],
                            **counts}
    out["documents"] = await db.fetch_all(
        """SELECT d.id, d.filename, d.kind, d.parse_status, d.page_count,
                  (SELECT count(*) FROM chunks c WHERE c.document_id = d.id) AS chunks
           FROM documents d WHERE d.exam_id=%s ORDER BY d.id""", (exam_id,))
    return out


@router.delete("/{exam_id}/preloaded-questions")
async def remove_preloaded_questions(exam_id: int, user=Depends(current_user)):
    """Take the official practice-question pack out of rotation (restorable)."""
    await owned_exam(exam_id, user)
    rows = await db.fetch_all(
        """UPDATE questions SET status='removed' WHERE exam_id=%s AND source='extracted'
           AND external_item_id IS NOT NULL AND status='active' RETURNING id""", (exam_id,))
    ids = [r["id"] for r in rows]
    if ids:
        await db.execute("DELETE FROM review_queue WHERE exam_id=%s AND question_id=ANY(%s)",
                         (exam_id, ids))
    return {"removed": len(ids)}


@router.post("/{exam_id}/preloaded-questions/restore")
async def restore_preloaded_questions(exam_id: int, user=Depends(current_user)):
    await owned_exam(exam_id, user)
    rows = await db.fetch_all(
        """UPDATE questions SET status='active' WHERE exam_id=%s AND source='extracted'
           AND external_item_id IS NOT NULL AND status='removed' RETURNING id""", (exam_id,))
    return {"restored": len(rows)}


@router.delete("/{exam_id}/documents/{document_id}")
async def delete_document(exam_id: int, document_id: int, user=Depends(current_user)):
    """Remove an upload and everything grounded in it: its chunks, lessons citing them,
    and generated questions citing them (killed, not served again)."""
    await owned_exam(exam_id, user)
    doc = await db.fetch_one("SELECT * FROM documents WHERE id=%s AND exam_id=%s",
                             (document_id, exam_id))
    if not doc:
        raise HTTPException(404, "document not found")
    chunk_rows = await db.fetch_all("SELECT id FROM chunks WHERE document_id=%s", (document_id,))
    chunk_ids = [r["id"] for r in chunk_rows]
    killed_questions = 0
    if chunk_ids:
        qrows = await db.fetch_all(
            """UPDATE questions SET status='removed' WHERE exam_id=%s AND source='generated'
               AND status='active'
               AND EXISTS (SELECT 1 FROM jsonb_array_elements(citations) c
                           WHERE (c->>'chunk_id')::bigint = ANY(%s))
               RETURNING id""", (exam_id, chunk_ids))
        killed_questions = len(qrows)
        if qrows:
            await db.execute("DELETE FROM review_queue WHERE exam_id=%s AND question_id=ANY(%s)",
                             (exam_id, [r["id"] for r in qrows]))
        await db.execute(
            """DELETE FROM lessons WHERE exam_id=%s
               AND EXISTS (SELECT 1 FROM jsonb_array_elements(citations) c
                           WHERE (c->>'chunk_id')::bigint = ANY(%s))""", (exam_id, chunk_ids))
        await db.execute("DELETE FROM chunks WHERE document_id=%s", (document_id,))
    await db.execute("DELETE FROM documents WHERE id=%s", (document_id,))
    try:
        Path(doc["stored_path"]).unlink(missing_ok=True)
    except OSError:
        pass
    return {"deleted": True, "chunks_removed": len(chunk_ids),
            "generated_questions_removed": killed_questions}


@router.get("/{exam_id}/question-profile")
async def get_profile(exam_id: int, user=Depends(current_user)):
    exam = await owned_exam(exam_id, user)
    if exam["accelerator_id"]:
        acc = await db.fetch_one("SELECT default_profile FROM accelerators WHERE id=%s",
                                 (exam["accelerator_id"],))
        return {"profile": acc["default_profile"], "source": "accelerator"}
    fmts = await db.fetch_all(
        """SELECT format, count(*) AS n FROM questions
           WHERE exam_id=%s AND source='extracted' GROUP BY format""", (exam_id,))
    total = sum(f["n"] for f in fmts) or 1
    return {"profile": {"format_mix": {f["format"]: round(f["n"] / total, 3) for f in fmts}},
            "source": "derived_from_uploads" if fmts else "default"}


@router.post("/{exam_id}/confirm")
async def confirm_setup(exam_id: int, user=Depends(current_user)):
    """User confirms the derived topic tree + profile."""
    await owned_exam(exam_id, user)
    await db.execute("UPDATE exams SET status='active' WHERE id=%s", (exam_id,))
    return {"status": "active"}


@router.post("/{exam_id}/diagnostic/start")
async def diagnostic_start(exam_id: int, user=Depends(current_user)):
    await owned_exam(exam_id, user)
    out = await diagnostic.start(exam_id)
    if "error" in out:
        raise HTTPException(400, out["error"])
    return out


@router.post("/{exam_id}/diagnostic/{session_id}/complete")
async def diagnostic_complete(exam_id: int, session_id: int, user=Depends(current_user)):
    await owned_exam(exam_id, user)
    from ace_api.engine import gamify, planner
    result = await diagnostic.complete(exam_id, session_id)
    plan = await planner.build_plan(exam_id)
    await gamify.award(user["id"], "diagnostic_complete")
    await gamify.touch_streak(user["id"])
    return {"result": result, "plan": plan}


@router.post("/{exam_id}/flashcards")
async def flashcard_deck(exam_id: int, rebuild: bool = False, user=Depends(current_user)):
    """Active-recall deck from the exam's weakest topics."""
    await owned_exam(exam_id, user)
    from ace_api.engine.flashcards import get_or_build_deck
    out = await get_or_build_deck(exam_id, rebuild, user["selected_model"])
    if "error" in out:
        raise HTTPException(400, out["error"])
    return out


@router.post("/{exam_id}/starter-pack")
async def build_starter_pack(exam_id: int, bg: BackgroundTasks, user=Depends(current_user)):
    """AI-generated starter environment for exams with no accelerator and no materials —
    topic tree + study notes as a labeled, removable document; runs in the background."""
    exam = await owned_exam(exam_id, user)
    if exam["accelerator_id"]:
        raise HTTPException(400, "This exam already has an official content pack.")
    existing = await db.fetch_one(
        "SELECT id, parse_status FROM documents WHERE exam_id=%s AND kind='starter'",
        (exam_id,))
    if existing and existing["parse_status"] in ("parsing", "parsed"):
        return {"building": existing["parse_status"] == "parsing", "already": True}
    from ace_api.engine.starter import build_starter_pack as run
    bg.add_task(run, exam_id, user["selected_model"])
    return {"building": True, "already": False}


@router.post("/{exam_id}/enrich-explanations")
async def enrich_explanations(exam_id: int, limit: int = 15, user=Depends(current_user)):
    """Write why-right/why-wrong notes for questions that lack them (also runs nightly)."""
    await owned_exam(exam_id, user)
    from ace_api.engine import explain
    n = await explain.enrich_batch(exam_id, min(limit, 40), user["selected_model"])
    remaining = await db.fetch_one(
        """SELECT count(*) AS n FROM questions WHERE exam_id=%s AND status='active'
           AND format='mcq' AND payload->'option_notes' IS NULL""", (exam_id,))
    return {"enriched": n, "remaining": remaining["n"]}


@router.get("/{exam_id}/readiness")
async def readiness(exam_id: int, user=Depends(current_user)):
    await owned_exam(exam_id, user)
    from ace_api.engine import readiness as rd
    return await rd.compute(exam_id)
