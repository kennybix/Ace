"""Blueprint-faithful timed mocks: per-element counts mirror the exam's real weighting."""

from __future__ import annotations

import json

from ace_api import db


async def start(exam_id: int, scale: float = 1.0) -> dict:
    parents = await db.fetch_all(
        "SELECT id, code, title, weight FROM topics WHERE exam_id=%s AND parent_id IS NULL ORDER BY code",
        (exam_id,))
    blueprint, picked = {}, []
    for p in parents:
        n = max(1, round(p["weight"] * scale))
        rows = await db.fetch_all(
            """SELECT q.id FROM questions q JOIN topics t ON t.id=q.topic_id
               WHERE q.exam_id=%s AND (t.id=%s OR t.parent_id=%s) AND q.status='active'
                 AND q.payload->>'correct_index' IS NOT NULL
               ORDER BY random() LIMIT %s""", (exam_id, p["id"], p["id"], n))
        ids = [r["id"] for r in rows]
        blueprint[p["code"]] = {"target": n, "got": len(ids), "title": p["title"]}
        picked += ids
    if not picked:
        return {"error": "no questions available for a mock"}
    row = await db.fetch_one(
        """INSERT INTO mocks (exam_id, blueprint, question_ids, started_at)
           VALUES (%s,%s,%s, now()) RETURNING id""",
        (exam_id, json.dumps(blueprint), picked))
    return {"mock_id": row["id"], "question_ids": picked, "count": len(picked),
            "duration_min": max(30, int(len(picked) * 65 / 60))}


async def submit(mock_id: int) -> dict:
    mock = await db.fetch_one("SELECT * FROM mocks WHERE id=%s", (mock_id,))
    rows = await db.fetch_all(
        """SELECT a.correct, t.parent_id, pt.code AS element_code
           FROM attempts a JOIN questions q ON q.id=a.question_id
           LEFT JOIN topics t ON t.id=q.topic_id LEFT JOIN topics pt ON pt.id=t.parent_id
           WHERE a.mock_id=%s""", (mock_id,))
    if not rows:
        return {"error": "no attempts recorded for this mock"}
    per: dict[str, list[bool]] = {}
    for r in rows:
        per.setdefault(r["element_code"] or "?", []).append(r["correct"])
    per_scores = {k: round(sum(v) / len(v), 3) for k, v in per.items()}
    score = sum(1 for r in rows if r["correct"]) / len(rows)
    await db.execute(
        "UPDATE mocks SET submitted_at=now(), score=%s, per_element_scores=%s WHERE id=%s",
        (score, json.dumps(per_scores), mock_id))
    return {"score": round(score, 4), "answered": len(rows), "per_element": per_scores,
            "blueprint": mock["blueprint"]}
