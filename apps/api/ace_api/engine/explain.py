"""Answer explanations that teach: why the right answer is right AND why each wrong option
is wrong — grounded in the exam's study materials. Enriches extracted questions (whose
official explanations are stubs) and any question missing per-option notes."""

from __future__ import annotations

import json

from ace_api import db
from ace_api.engine.embedder import embed, to_pgvector
from ace_api.llm.client import chat_json

EXPLAIN_SYSTEM = """Output ONLY a JSON object. You write answer explanations for exam prep.
Given a question, its correct answer, and source excerpts, reply:
{"explanation": 2-4 sentence teach-why-correct (cite the concept, not the excerpt number),
 "option_notes": {"A": one sentence, "B": …, "C": …, "D": …}}
For the correct option the note starts "Correct —"; for wrong options explain the specific
misconception or why it fails. Ground everything in the excerpts; never invent rules."""

STUB_MARKERS = ("Official CIRO practice exam item.", "")


async def enrich_question(question_id: int, model_id: str | None = None) -> bool:
    q = await db.fetch_one("SELECT * FROM questions WHERE id=%s", (question_id,))
    if not q or q["format"] != "mcq":
        return False
    payload = dict(q["payload"])
    if payload.get("option_notes") and payload.get("explanation") not in STUB_MARKERS:
        return False  # already rich

    text = payload.get("stem", "") + " " + " ".join(payload.get("options", []))
    vec = (await embed([text]))[0]
    chunks = await db.fetch_all(
        """SELECT id, text FROM chunks WHERE exam_id=%s AND embedding IS NOT NULL
           ORDER BY embedding <=> %s LIMIT 5""",
        (q["exam_id"], to_pgvector(vec)))
    if not chunks:
        return False

    correct_letter = "ABCD"[payload["correct_index"]]
    out = await chat_json(
        "explain_question", EXPLAIN_SYSTEM,
        json.dumps({
            "stem": payload["stem"],
            "options": {L: o for L, o in zip("ABCD", payload["options"])},
            "correct": correct_letter,
            "excerpts": [c["text"][:900] for c in chunks],
        }), model_id=model_id, temperature=0.3)
    if not isinstance(out, dict) or not isinstance(out.get("option_notes"), dict) \
            or len(out.get("explanation", "")) < 20:
        return False
    payload["explanation"] = out["explanation"]
    payload["option_notes"] = {k: str(v)[:400] for k, v in out["option_notes"].items()
                               if k in "ABCD"}
    await db.execute(
        "UPDATE questions SET payload=%s, last_reviewed_at=now() WHERE id=%s",
        (json.dumps(payload), question_id))
    return True


async def enrich_batch(exam_id: int, limit: int = 15, model_id: str | None = None) -> int:
    rows = await db.fetch_all(
        """SELECT id FROM questions WHERE exam_id=%s AND status='active' AND format='mcq'
           AND (payload->'option_notes' IS NULL)
           ORDER BY (source='extracted') DESC, id LIMIT %s""", (exam_id, limit))
    done = 0
    for r in rows:
        try:
            if await enrich_question(r["id"], model_id):
                done += 1
        except Exception:
            continue
    return done
