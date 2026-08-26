"""Diagnostic: format-mix-faithful baseline across elements, preferring real extracted questions."""

from __future__ import annotations

import json

from ace_api import db

TARGET_QS = 24


async def start(exam_id: int) -> dict:
    # resume an abandoned diagnostic instead of orphaning it — progress is sacred
    existing = await db.fetch_one(
        """SELECT id, prepared_payload FROM sessions WHERE exam_id=%s AND kind='diagnostic'
           AND completed_at IS NULL ORDER BY id DESC LIMIT 1""", (exam_id,))
    if existing:
        qids = existing["prepared_payload"].get("question_ids", [])
        answered = {r["question_id"] for r in await db.fetch_all(
            "SELECT question_id FROM attempts WHERE session_id=%s", (existing["id"],))}
        remaining = [q for q in qids if q not in answered]
        if remaining:
            return {"session_id": existing["id"], "question_ids": remaining,
                    "count": len(remaining), "resumed": True,
                    "already_answered": len(answered)}

    parents = await db.fetch_all(
        "SELECT id, code, weight FROM topics WHERE exam_id=%s AND parent_id IS NULL ORDER BY code",
        (exam_id,))
    if not parents:
        parents = await db.fetch_all(
            "SELECT id, code, weight FROM topics WHERE exam_id=%s ORDER BY code", (exam_id,))
    total_w = sum(p["weight"] for p in parents) or 1
    picked: list[int] = []
    for p in parents:
        n = max(1, round(TARGET_QS * p["weight"] / total_w))
        rows = await db.fetch_all(
            """SELECT q.id FROM questions q JOIN topics t ON t.id=q.topic_id
               WHERE q.exam_id=%s AND (t.id=%s OR t.parent_id=%s) AND q.status='active'
                 AND q.payload->>'correct_index' IS NOT NULL
               ORDER BY (q.source='extracted') DESC, random() LIMIT %s""",
            (exam_id, p["id"], p["id"], n))
        picked += [r["id"] for r in rows]
    if not picked:
        rows = await db.fetch_all(
            "SELECT id FROM questions WHERE exam_id=%s AND status='active' ORDER BY random() LIMIT %s",
            (exam_id, TARGET_QS))
        picked = [r["id"] for r in rows]
    if not picked:
        return {"error": "no questions available — ingest materials or adopt an accelerator first"}
    sess = await db.fetch_one(
        """INSERT INTO sessions (exam_id, kind, prepared_payload, started_at)
           VALUES (%s,'diagnostic',%s, now()) RETURNING id""",
        (exam_id, json.dumps({"question_ids": picked})))
    return {"session_id": sess["id"], "question_ids": picked, "count": len(picked)}


async def complete(exam_id: int, session_id: int) -> dict:
    rows = await db.fetch_all(
        """SELECT q.topic_id, t.parent_id, a.correct FROM attempts a
           JOIN questions q ON q.id=a.question_id LEFT JOIN topics t ON t.id=q.topic_id
           WHERE a.session_id=%s""", (session_id,))
    by_topic: dict[int, list[bool]] = {}
    for r in rows:
        if r["topic_id"]:
            by_topic.setdefault(r["topic_id"], []).append(r["correct"])
            if r["parent_id"]:
                by_topic.setdefault(r["parent_id"], []).append(r["correct"])
    for topic_id, results in by_topic.items():
        acc = sum(results) / len(results)
        baseline = 0.3 + (acc - 0.3) * min(len(results) / 5.0, 1.0)  # shrink small samples
        await db.execute(
            """INSERT INTO mastery (exam_id, topic_id, rating, n_attempts)
               VALUES (%s,%s,%s,%s)
               ON CONFLICT (exam_id, topic_id)
               DO UPDATE SET rating=EXCLUDED.rating, n_attempts=mastery.n_attempts+EXCLUDED.n_attempts,
                             updated_at=now()""",
            (exam_id, topic_id, baseline, len(results)))
    await db.execute("UPDATE sessions SET completed_at=now() WHERE id=%s", (session_id,))
    correct = sum(1 for r in rows if r["correct"])
    return {"answered": len(rows), "correct": correct,
            "accuracy": round(correct / len(rows), 3) if rows else 0.0}
