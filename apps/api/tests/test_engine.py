"""Engine integration tests: accelerator adoption, ingestion, topic mapping, gated generation,
lessons. Live Postgres (:5445), fake LLM, hash embeddings."""

import uuid

import pytest

from ace_api import db
from ace_api.engine import exam_setup, generator, ingestion, lessons
from tests.conftest import GUIDANCE_PDF


@pytest.fixture(autouse=True)
async def _pool_per_test():
    yield
    await db.close_pool()


async def _mkuser() -> int:
    row = await db.fetch_one(
        "INSERT INTO users (email) VALUES (%s) RETURNING id", (f"t-{uuid.uuid4().hex[:10]}@example.com",))
    return row["id"]


async def _mkexam(name="CIRE") -> tuple[int, int]:
    uid = await _mkuser()
    out = await exam_setup.create_exam(uid, name, "2026-10-01", 6)
    return uid, out["exam_id"]


async def _ingest_guidance(exam_id: int) -> dict:
    doc = await db.fetch_one(
        """INSERT INTO documents (exam_id, filename, sha256, stored_path)
           VALUES (%s,'guidance.pdf','x',%s) RETURNING id""", (exam_id, GUIDANCE_PDF))
    out = await ingestion.ingest_document(doc["id"])
    await ingestion.finalize_exam(exam_id)
    return out


async def test_accelerator_match_and_adoption():
    _, exam_id = await _mkexam("CIRE exam (CIRO)")
    topics = await db.fetch_all("SELECT * FROM topics WHERE exam_id=%s", (exam_id,))
    assert len(topics) == 9 + 93
    qs = await db.fetch_all("SELECT * FROM questions WHERE exam_id=%s AND source='extracted'", (exam_id,))
    assert len(qs) == 110
    assert all(q["topic_id"] is not None for q in qs)  # every real question topic-mapped
    assert all(q["payload"]["correct_index"] in (0, 1, 2, 3) for q in qs)


async def test_unknown_exam_no_accelerator():
    _, exam_id = await _mkexam("Totally Unknown Cert 9000")
    exam = await db.fetch_one("SELECT accelerator_id FROM exams WHERE id=%s", (exam_id,))
    assert exam["accelerator_id"] is None


async def test_ingestion_and_topic_mapping():
    _, exam_id = await _mkexam()
    out = await _ingest_guidance(exam_id)
    assert out["kind"] == "guidance"
    assert out["chunks"] > 5
    mapped = await db.fetch_one(
        "SELECT count(*) AS n FROM chunks WHERE exam_id=%s AND topic_id IS NOT NULL", (exam_id,))
    assert mapped["n"] > 0


async def test_generation_gating_and_dedupe():
    _, exam_id = await _mkexam()
    await _ingest_guidance(exam_id)
    out = await generator.generate_for_topic(exam_id, "3", "mcq", 4)
    assert len(out["accepted"]) == 4, out
    rows = await db.fetch_all(
        "SELECT * FROM questions WHERE exam_id=%s AND source='generated'", (exam_id,))
    assert all(len(r["citations"]) >= 1 for r in rows)
    assert all(r["prompt_version"] == "v1" for r in rows)
    # identical fake output again → all near-dupes rejected
    out2 = await generator.generate_for_topic(exam_id, "3", "mcq", 4)
    assert len(out2["accepted"]) == 0
    assert out2["rejected"]["duplicate"] == 4


async def test_generation_rejects_ungrounded(monkeypatch):
    _, exam_id = await _mkexam()
    await _ingest_guidance(exam_id)

    async def bad_llm(task, system, user, **kw):
        return {"questions": [{"format": "mcq", "cognitive_level": "understand",
                               "citation_chunk_ids": [999999999], "difficulty": 0.5,
                               "stem": "Ungrounded question about nothing in particular?",
                               "options": ["a", "b", "c", "d"], "correct_index": 0,
                               "explanation": "x"}]}

    monkeypatch.setattr(generator, "chat_json", bad_llm)
    out = await generator.generate_for_topic(exam_id, "3", "mcq", 1)
    assert out["accepted"] == []
    assert out["rejected"]["ungrounded"] == 1


async def test_all_five_formats_generate_and_validate():
    _, exam_id = await _mkexam()
    await _ingest_guidance(exam_id)
    for fmt in ("mcq", "tf", "gap", "match", "numeric"):
        out = await generator.generate_for_topic(exam_id, "1", fmt, 2)
        assert len(out["accepted"]) >= 1, (fmt, out)


async def test_lesson_builder_grounded():
    _, exam_id = await _mkexam()
    await _ingest_guidance(exam_id)
    topic = await db.fetch_one(
        "SELECT id FROM topics WHERE exam_id=%s AND parent_id IS NOT NULL LIMIT 1", (exam_id,))
    out = await lessons.build_lesson(exam_id, topic["id"])
    assert "lesson_id" in out, out
    row = await db.fetch_one("SELECT * FROM lessons WHERE id=%s", (out["lesson_id"],))
    assert len(row["citations"]) >= 1
