"""Exam creation: free-text exam name → optional accelerator match → topic/question adoption."""

from __future__ import annotations

import json
import re

from ace_api import db
from ace_api.engine.embedder import cosine, embed


def _norm(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


async def match_accelerator(name_raw: str) -> dict | None:
    """Token-overlap match against known accelerators ('cire', 'ciro', full name all hit)."""
    accs = await db.fetch_all("SELECT id, exam_key, display_name FROM accelerators")
    tokens = _norm(name_raw)
    best, best_score = None, 0.0
    for a in accs:
        cand = _norm(a["exam_key"]) | _norm(a["display_name"])
        overlap = len(tokens & cand)
        score = overlap / max(len(tokens), 1)
        if overlap >= 1 and score > best_score:
            best, best_score = a, score
    return best if best_score >= 0.3 or (best and len(tokens) == 1) else None


async def create_exam(user_id: int, name_raw: str, exam_date, weekly_hours: int) -> dict:
    acc = await match_accelerator(name_raw)
    async with db.conn() as c:
        row = await (await c.execute(
            """INSERT INTO exams (user_id, name_raw, accelerator_id, exam_date, weekly_hours, status)
               VALUES (%s,%s,%s,%s,%s,'onboarding') RETURNING id""",
            (user_id, name_raw, acc["id"] if acc else None, exam_date, weekly_hours),
        )).fetchone()
    exam_id = row["id"]
    if acc:
        await adopt_accelerator(exam_id, acc["id"])
    return {"exam_id": exam_id, "accelerator": acc["display_name"] if acc else None}


async def adopt_accelerator(exam_id: int, accelerator_id: int) -> None:
    """Clone accelerator topics into the exam and copy its extracted questions, topic-mapped."""
    acc = await db.fetch_one("SELECT * FROM accelerators WHERE id=%s", (accelerator_id,))
    tree = acc["topic_tree"]
    child_rows: list[tuple[int, str, str]] = []  # (topic_id, title, body)
    async with db.conn() as c:
        for el in tree:
            parent = await (await c.execute(
                """INSERT INTO topics (exam_id, code, title, weight, cognitive_levels, source)
                   VALUES (%s,%s,%s,%s,'{}','syllabus_parsed') RETURNING id""",
                (exam_id, el["code"], el["title"], el["weight"]),
            )).fetchone()
            for ch in el["children"]:
                r = await (await c.execute(
                    """INSERT INTO topics (exam_id, parent_id, code, title, weight, cognitive_levels, source)
                       VALUES (%s,%s,%s,%s,%s,%s,'syllabus_parsed') RETURNING id""",
                    (exam_id, parent["id"], ch["code"], ch["title"], ch["weight"],
                     ch.get("cognitive_levels", [])),
                )).fetchone()
                child_rows.append((r["id"], ch["title"], ch.get("body", "")))

    topic_vecs = await embed([f"{t[1]} {t[2][:400]}" for t in child_rows])
    qs = await db.fetch_all(
        "SELECT id, payload, cognitive_level, external_item_id, embedding FROM questions "
        "WHERE accelerator_id=%s AND status='active'", (accelerator_id,))
    async with db.conn() as c:
        for q in qs:
            v = q["embedding"]
            v = v if isinstance(v, list) else [float(x) for x in str(v).strip("[]").split(",")]
            best_i = max(range(len(child_rows)), key=lambda i: cosine(v, topic_vecs[i]), default=-1)
            topic_id = child_rows[best_i][0] if best_i >= 0 else None
            await c.execute(
                """INSERT INTO questions (exam_id, topic_id, source, format, cognitive_level, payload,
                                          citations, status, external_item_id, embedding)
                   VALUES (%s,%s,'extracted','mcq',%s,%s,'[]','active',%s,%s)""",
                (exam_id, topic_id, q["cognitive_level"], json.dumps(q["payload"]),
                 q["external_item_id"], "[" + ",".join(f"{x:.6f}" for x in v) + "]"),
            )
