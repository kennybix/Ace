"""Deliberate generation (critic gate) + nightly improvement cycle."""

import json
import uuid

import pytest

from ace_api import db
from ace_api.engine import exam_setup, generator, improvement, ingestion
from tests.conftest import GUIDANCE_PDF


@pytest.fixture(autouse=True)
async def _pool_per_test():
    yield
    await db.close_pool()


async def _exam_with_chunks() -> int:
    row = await db.fetch_one("INSERT INTO users (email) VALUES (%s) RETURNING id",
                             (f"imp-{uuid.uuid4().hex[:10]}@example.com",))
    out = await exam_setup.create_exam(row["id"], "CIRE", "2026-10-01", 6)
    doc = await db.fetch_one(
        "INSERT INTO documents (exam_id, filename, sha256, stored_path) "
        "VALUES (%s,'g.pdf','x',%s) RETURNING id", (out["exam_id"], GUIDANCE_PDF))
    await ingestion.ingest_document(doc["id"])
    await ingestion.finalize_exam(out["exam_id"])
    return out["exam_id"]


async def test_critic_gate_fails_bad_questions(monkeypatch):
    exam_id = await _exam_with_chunks()

    real_chat = generator.chat_json

    async def gen_then_critic(task, system, user, **kw):
        if task == "generate_questions":
            out = await real_chat(task, system, user, **kw)
            for q in out["questions"]:
                q["stem"] = "FAKE-FAIL " + q["stem"]
            return out
        return await real_chat(task, system, user, **kw)

    monkeypatch.setattr(generator, "chat_json", gen_then_critic)
    out = await generator.generate_for_topic(exam_id, "1", "mcq", 2)
    assert out["accepted"] == []
    assert out["rejected"]["failed_critique"] == 2


async def test_critic_revision_applied(monkeypatch):
    exam_id = await _exam_with_chunks()
    real_chat = generator.chat_json

    async def gen_then_critic(task, system, user, **kw):
        if task == "generate_questions":
            out = await real_chat(task, system, user, **kw)
            for q in out["questions"]:
                q["stem"] = "FAKE-REVISE " + q["stem"]
            return out
        return await real_chat(task, system, user, **kw)

    monkeypatch.setattr(generator, "chat_json", gen_then_critic)
    out = await generator.generate_for_topic(exam_id, "1", "mcq", 1)
    assert len(out["accepted"]) == 1
    assert out["rejected"]["revised"] == 1
    q = await db.fetch_one("SELECT payload, last_reviewed_at FROM questions WHERE id=%s",
                           (out["accepted"][0],))
    assert q["payload"]["stem"].startswith("REVISED")
    assert q["last_reviewed_at"] is not None


async def test_reaudit_kills_and_revises(monkeypatch):
    exam_id = await _exam_with_chunks()
    out = await generator.generate_for_topic(exam_id, "1", "mcq", 2)
    assert len(out["accepted"]) == 2
    kill_id, revise_id = out["accepted"]
    chunk = await db.fetch_one("SELECT id FROM chunks WHERE exam_id=%s LIMIT 1", (exam_id,))
    for qid, marker in ((kill_id, "FAKE-FAIL"), (revise_id, "FAKE-REVISE")):
        q = await db.fetch_one("SELECT payload FROM questions WHERE id=%s", (qid,))
        p = dict(q["payload"])
        p["stem"] = f"{marker} {p['stem']}"
        await db.execute(
            "UPDATE questions SET payload=%s, citations=%s, last_reviewed_at=NULL WHERE id=%s",
            (json.dumps(p), json.dumps([{"chunk_id": chunk["id"]}]), qid))

    stats = await improvement._reaudit_sample(exam_id, None)
    assert stats["killed_on_reaudit"] >= 1
    assert stats["revised_on_reaudit"] >= 1
    killed = await db.fetch_one("SELECT status FROM questions WHERE id=%s", (kill_id,))
    assert killed["status"] == "killed"
    revised = await db.fetch_one("SELECT payload, status FROM questions WHERE id=%s",
                                 (revise_id,))
    assert revised["status"] == "active"
    assert "REVISED" in revised["payload"]["stem"]


async def test_replace_killed_generates_fresh(monkeypatch):
    exam_id = await _exam_with_chunks()
    out = await generator.generate_for_topic(exam_id, "2", "mcq", 2)
    # kill the whole topic's generated pool — replacement only fires when nothing newer exists
    await db.execute("UPDATE questions SET status='killed' WHERE id = ANY(%s)",
                     (out["accepted"],))
    n = await improvement._replace_killed(exam_id, None)
    assert n >= 1


async def test_full_cycle_runs(monkeypatch):
    exam_id = await _exam_with_chunks()
    await generator.generate_for_topic(exam_id, "1", "mcq", 2)
    stats = await improvement.run_cycle(exam_id)
    assert stats["reaudited"] >= 1
    assert "topped_up" in stats
