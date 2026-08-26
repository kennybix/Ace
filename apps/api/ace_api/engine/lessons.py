"""Grounded micro-lessons / revision sheets / flashcards. Same citation gate as questions.

Lessons are the product here — the spec demands substance: exam-focused, structured,
with worked scenarios and trap warnings, not a thin summary."""

from __future__ import annotations

import json

from ace_api import db
from ace_api.engine.embedder import embed, to_pgvector
from ace_api.llm.client import PROMPT_VERSION, chat_json

SYSTEM = """Output ONLY a JSON object — no prose outside it, no markdown fences.
You write exam-prep study lessons. Reply {"title": str, "body": markdown str,
"citation_chunk_ids": [int, ...]}.

For kind=micro_lesson, the body MUST be a substantial, teach-first lesson (600–900 words)
with this structure, in markdown:
# <punchy title>
Opening 2–3 sentences: what this topic is and why the exam cares about it.
## The core ideas
Explain each key concept properly — define terms, give the numbers/thresholds/rules
exactly as the source states them. Use **bold** for terms worth memorising.
## In practice
One concrete worked scenario applying the rules (name a person/firm, walk the decision).
## How the exam tests this
2–4 bullet traps: the confusions and near-miss wrong answers examiners love, based on
the source's distinctions.
## Remember
4–6 tight recall bullets.

kind=revision_sheet: dense bullet recap of everything testable. kind=flashcard: body is
'FRONT: ...\\nBACK: ...'. Stay strictly within the provided chunks — every rule, number
and term must come from them. Cite every chunk you actually used."""


async def build_lesson(exam_id: int, topic_id: int, kind: str = "micro_lesson",
                       model_id: str | None = None) -> dict:
    topic = await db.fetch_one("SELECT id, code, title FROM topics WHERE id=%s", (topic_id,))
    # retrieval: the topic's own chunks first, then nearest element-sibling chunks — a
    # lesson deserves the full relevant slice of the volumes, not a thin sample
    own = await db.fetch_all(
        """SELECT id, text FROM chunks WHERE exam_id=%s AND topic_id IN
           (SELECT id FROM topics WHERE exam_id=%s AND (id=%s OR parent_id=%s)) LIMIT 6""",
        (exam_id, exam_id, topic_id, topic_id))
    chunks = list(own)
    if len(chunks) < 10:
        vec = (await embed([topic["title"]]))[0]
        sibling = await db.fetch_all(
            """SELECT c.id, c.text FROM chunks c
               WHERE c.exam_id=%s AND c.embedding IS NOT NULL AND c.id != ALL(%s)
                 AND c.topic_id IN (
                   SELECT t2.id FROM topics t1 JOIN topics t2 ON t2.parent_id = t1.parent_id
                   WHERE t1.id=%s)
               ORDER BY c.embedding <=> %s LIMIT %s""",
            (exam_id, [c["id"] for c in chunks] or [0], topic_id, to_pgvector(vec),
             10 - len(chunks)))
        chunks += list(sibling)
    if not chunks:
        chunks = await db.fetch_all("SELECT id, text FROM chunks WHERE exam_id=%s LIMIT 8",
                                    (exam_id,))
    if not chunks:
        return {"error": "no chunks to ground a lesson in"}
    user = json.dumps({"kind": kind, "topic_title": f"{topic['code']} {topic['title']}",
                       "chunks": [{"id": c["id"], "text": c["text"][:2000]} for c in chunks]})
    out = await chat_json("build_lesson", SYSTEM, user, model_id=model_id, temperature=0.4,
                          max_tokens=7000)
    if not isinstance(out, dict) or "body" not in out:
        return {"error": "lesson reply malformed"}
    cites = out.get("citation_chunk_ids") or []
    if not cites or not set(int(c) for c in cites if str(c).lstrip("-").isdigit()) \
            <= {c["id"] for c in chunks}:
        return {"error": "lesson failed citation gate"}
    row = await db.fetch_one(
        """INSERT INTO lessons (exam_id, topic_id, kind, body, citations, model_id, prompt_version)
           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (exam_id, topic_id, kind, out["body"], json.dumps([{"chunk_id": int(c)} for c in cites]),
         model_id or "default", PROMPT_VERSION + "-deep"))
    return {"lesson_id": row["id"], "title": out.get("title", ""), "body": out["body"]}
