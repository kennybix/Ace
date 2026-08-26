"""Mastery updates (EWMA, confidence-weighted) + SM-2-lite spaced repetition."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from ace_api import db

ALPHA = {"sure": 0.20, "think": 0.15, "guess": 0.10, None: 0.15}


async def on_attempt(exam_id: int, question_id: int, correct: bool, confidence: str | None) -> None:
    q = await db.fetch_one(
        "SELECT topic_id, format, cognitive_level FROM questions WHERE id=%s", (question_id,))
    if q and q["topic_id"]:
        await _update_mastery(exam_id, q["topic_id"], q["format"], q["cognitive_level"],
                              correct, confidence)
    await _schedule_review(exam_id, question_id, correct)


async def _update_mastery(exam_id, topic_id, fmt, cog, correct, confidence):
    a = ALPHA.get(confidence, 0.15)
    x = 1.0 if correct else 0.0
    row = await db.fetch_one("SELECT * FROM mastery WHERE exam_id=%s AND topic_id=%s",
                             (exam_id, topic_id))
    if not row:
        rating = 0.3 * (1 - a) + x * a
        pf, pc = {fmt: rating}, {cog: rating}
        await db.execute(
            """INSERT INTO mastery (exam_id, topic_id, rating, per_format, per_cognitive, n_attempts)
               VALUES (%s,%s,%s,%s,%s,1) ON CONFLICT (exam_id, topic_id) DO NOTHING""",
            (exam_id, topic_id, rating, json.dumps(pf), json.dumps(pc)))
        return
    rating = row["rating"] * (1 - a) + x * a
    pf = row["per_format"] or {}
    pc = row["per_cognitive"] or {}
    pf[fmt] = pf.get(fmt, 0.3) * (1 - a) + x * a
    pc[cog] = pc.get(cog, 0.3) * (1 - a) + x * a
    await db.execute(
        """UPDATE mastery SET rating=%s, per_format=%s, per_cognitive=%s,
           n_attempts=n_attempts+1, updated_at=now() WHERE exam_id=%s AND topic_id=%s""",
        (rating, json.dumps(pf), json.dumps(pc), exam_id, topic_id))


async def _schedule_review(exam_id: int, question_id: int, correct: bool) -> None:
    now = datetime.now(timezone.utc)
    row = await db.fetch_one("SELECT * FROM review_queue WHERE exam_id=%s AND question_id=%s",
                             (exam_id, question_id))
    if not row:
        interval = 2.0 if correct else 1.0
        await db.execute(
            """INSERT INTO review_queue (exam_id, question_id, due_at, interval_d, ease)
               VALUES (%s,%s,%s,%s,2.5) ON CONFLICT DO NOTHING""",
            (exam_id, question_id, now + timedelta(days=interval), interval))
        return
    if correct:
        ease = min(row["ease"] + 0.05, 2.8)
        interval = max(row["interval_d"] * ease, 1.0)
    else:
        ease = max(row["ease"] - 0.2, 1.3)
        interval = 1.0
    await db.execute(
        "UPDATE review_queue SET due_at=%s, interval_d=%s, ease=%s WHERE exam_id=%s AND question_id=%s",
        (now + timedelta(days=interval), interval, ease, exam_id, question_id))


async def due_reviews(exam_id: int, limit: int = 5) -> list[int]:
    rows = await db.fetch_all(
        """SELECT question_id FROM review_queue WHERE exam_id=%s AND due_at <= now()
           ORDER BY due_at LIMIT %s""", (exam_id, limit))
    return [r["question_id"] for r in rows]
