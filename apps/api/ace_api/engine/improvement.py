"""Continuous content improvement — runs in the nightly batch, per active exam.

Four passes, all time-bounded so a night's cycle stays cheap:
  1. replace_killed   — reported/killed questions get fresh replacements for their topics
  2. reaudit_sample   — oldest-reviewed generated questions go back through the critic;
                        fails are killed (and replaced next pass), revisions are applied
  3. refresh_lessons  — topics where mastery is stuck get a rewritten micro-lesson
  4. top_up           — topics in the upcoming plan keep a minimum pool of unseen questions
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from ace_api import db
from ace_api.engine import critic, generator, lessons

REAUDIT_BATCH = 6
TOP_UP_MIN = 4
STUCK_MASTERY = 0.45
STUCK_MIN_ATTEMPTS = 8


async def run_cycle(exam_id: int, model_id: str | None = None) -> dict:
    stats = {"replaced_killed": 0, "reaudited": 0, "killed_on_reaudit": 0,
             "revised_on_reaudit": 0, "lessons_refreshed": 0, "topped_up": 0}

    stats["replaced_killed"] = await _replace_killed(exam_id, model_id)
    ra = await _reaudit_sample(exam_id, model_id)
    stats.update(ra)
    stats["lessons_refreshed"] = await _refresh_stuck_lessons(exam_id, model_id)
    stats["topped_up"] = await _top_up(exam_id, model_id)
    stats["videos_curated"] = await _curate_missing_videos(exam_id)
    from ace_api.engine import explain
    stats["explanations_enriched"] = await explain.enrich_batch(exam_id, 15, model_id)
    stats["thin_lessons_rewritten"] = await _rewrite_thin_lessons(exam_id, model_id)
    return stats


async def _rewrite_thin_lessons(exam_id: int, model_id: str | None, limit: int = 3) -> int:
    """Short lessons (pre-deep-prompt era, or weak generations) get rewritten properly."""
    rows = await db.fetch_all(
        """SELECT DISTINCT ON (topic_id) topic_id, length(body) AS len
           FROM lessons WHERE exam_id=%s AND kind='micro_lesson'
           ORDER BY topic_id, id DESC""", (exam_id,))
    thin = [r for r in rows if r["len"] < 1200][:limit]
    done = 0
    for r in thin:
        try:
            out = await lessons.build_lesson(exam_id, r["topic_id"], "micro_lesson", model_id)
            if "lesson_id" in out:
                done += 1
        except Exception:
            continue
    return done


async def _curate_missing_videos(exam_id: int) -> int:
    """Topics coming up in the next week get a vetted video if they lack one (3/night)."""
    from ace_api.jobs.videos import curate_for_topic
    rows = await db.fetch_all(
        """SELECT DISTINCT unnest(pi.topic_ids) AS topic_id
           FROM plan_items pi JOIN plans p ON p.id=pi.plan_id
           WHERE p.exam_id=%s AND p.status='active' AND pi.status='pending'
             AND pi.day <= %s""", (exam_id, date.today() + timedelta(days=7)))
    curated = 0
    for r in rows:
        if curated >= 3:
            break
        has = await db.fetch_one(
            "SELECT 1 AS x FROM videos WHERE exam_id=%s AND topic_id=%s AND status='active' "
            "LIMIT 1", (exam_id, r["topic_id"]))
        if has:
            continue
        try:
            curated += 1 if await curate_for_topic(exam_id, r["topic_id"]) else 0
        except Exception:
            continue
    return curated


async def _replace_killed(exam_id: int, model_id: str | None) -> int:
    rows = await db.fetch_all(
        """SELECT q.topic_id, t.code, count(*) AS n FROM questions q
           JOIN topics t ON t.id = q.topic_id
           WHERE q.exam_id=%s AND q.status='killed' AND q.source='generated'
             AND q.topic_id IS NOT NULL
             AND NOT EXISTS (SELECT 1 FROM questions r WHERE r.exam_id=q.exam_id
                             AND r.topic_id=q.topic_id AND r.status='active'
                             AND r.source='generated' AND r.created_at > q.created_at)
           GROUP BY q.topic_id, t.code LIMIT 5""", (exam_id,))
    replaced = 0
    for r in rows:
        out = await generator.generate_for_topic(exam_id, r["code"], "mcq",
                                                 min(int(r["n"]), 3), model_id)
        replaced += len(out.get("accepted", []))
    return replaced


async def _reaudit_sample(exam_id: int, model_id: str | None) -> dict:
    rows = await db.fetch_all(
        """SELECT id, format, payload, citations FROM questions
           WHERE exam_id=%s AND source='generated' AND status='active'
           ORDER BY last_reviewed_at ASC NULLS FIRST LIMIT %s""",
        (exam_id, REAUDIT_BATCH))
    out = {"reaudited": 0, "killed_on_reaudit": 0, "revised_on_reaudit": 0}
    for r in rows:
        chunk_ids = [c["chunk_id"] for c in (r["citations"] or []) if "chunk_id" in c]
        chunks = await db.fetch_all(
            "SELECT id, text FROM chunks WHERE id = ANY(%s)", (chunk_ids or [0],))
        if not chunks:
            continue
        verdict = await critic.critique_question(r["payload"], r["format"], chunks, model_id)
        out["reaudited"] += 1
        if verdict["verdict"] == "fail":
            await db.execute(
                "UPDATE questions SET status='killed', critique_notes=%s, "
                "last_reviewed_at=now() WHERE id=%s",
                (json.dumps(verdict["issues"]), r["id"]))
            out["killed_on_reaudit"] += 1
        elif verdict["verdict"] == "revise" and verdict["revised"]:
            revised = generator._normalize({**verdict["revised"], "format": r["format"]})
            if generator._valid(revised):
                payload = {k: v for k, v in revised.items()
                           if k not in {"format", "cognitive_level", "citation_chunk_ids",
                                        "difficulty"}}
                await db.execute(
                    "UPDATE questions SET payload=%s, critique_notes=%s, "
                    "last_reviewed_at=now() WHERE id=%s",
                    (json.dumps(payload), json.dumps(verdict["issues"]), r["id"]))
                out["revised_on_reaudit"] += 1
        else:
            await db.execute("UPDATE questions SET last_reviewed_at=now() WHERE id=%s",
                             (r["id"],))
    return out


async def _refresh_stuck_lessons(exam_id: int, model_id: str | None) -> int:
    rows = await db.fetch_all(
        """SELECT m.topic_id, t.code, t.title FROM mastery m JOIN topics t ON t.id=m.topic_id
           WHERE m.exam_id=%s AND m.rating < %s AND m.n_attempts >= %s LIMIT 3""",
        (exam_id, STUCK_MASTERY, STUCK_MIN_ATTEMPTS))
    refreshed = 0
    for r in rows:
        current = await db.fetch_one(
            """SELECT id, body FROM lessons WHERE exam_id=%s AND topic_id=%s
               AND kind='micro_lesson' ORDER BY id DESC LIMIT 1""",
            (exam_id, r["topic_id"]))
        if not current:
            continue
        chunks = await db.fetch_all(
            """SELECT id, text FROM chunks WHERE exam_id=%s AND topic_id IN
               (SELECT id FROM topics WHERE exam_id=%s AND (id=%s OR parent_id=%s)) LIMIT 6""",
            (exam_id, exam_id, r["topic_id"], r["topic_id"]))
        if not chunks:
            continue
        improved = await critic.improve_lesson(current["body"], f"{r['code']} {r['title']}",
                                               chunks, model_id)
        if improved:
            await db.execute(
                """INSERT INTO lessons (exam_id, topic_id, kind, body, citations, model_id,
                                        prompt_version)
                   VALUES (%s,%s,'micro_lesson',%s,%s,%s,'v1-improved')""",
                (exam_id, r["topic_id"], improved["body"],
                 json.dumps([{"chunk_id": c["id"]} for c in chunks[:3]]),
                 model_id or "default"))
            refreshed += 1
    return refreshed


async def _top_up(exam_id: int, model_id: str | None) -> int:
    """Topics scheduled in the next week keep >= TOP_UP_MIN unseen active questions —
    plus, every night, the exam's least-stocked subtopics get built up so topic drills
    work everywhere, plan or no plan."""
    rows = await db.fetch_all(
        """SELECT DISTINCT unnest(pi.topic_ids) AS topic_id
           FROM plan_items pi JOIN plans p ON p.id=pi.plan_id
           WHERE p.exam_id=%s AND p.status='active' AND pi.status='pending'
             AND pi.day <= %s""", (exam_id, date.today() + timedelta(days=7)))
    thin = await db.fetch_all(
        """SELECT t.id AS topic_id FROM topics t
           WHERE t.exam_id=%s AND t.parent_id IS NOT NULL
             AND (SELECT count(*) FROM questions q WHERE q.topic_id=t.id
                  AND q.status='active'
                  AND q.payload->>'correct_index' IS NOT NULL) < %s
           ORDER BY (SELECT count(*) FROM questions q WHERE q.topic_id=t.id
                     AND q.status='active') ASC, random() LIMIT 8""",
        (exam_id, TOP_UP_MIN))
    seen_ids = {r["topic_id"] for r in rows}
    rows = list(rows) + [r for r in thin if r["topic_id"] not in seen_ids]
    added = 0
    for r in rows[:14]:
        pool = await db.fetch_one(
            """SELECT count(*) AS n FROM questions q
               WHERE q.exam_id=%s AND q.topic_id=%s AND q.status='active'
                 AND q.payload->>'correct_index' IS NOT NULL
                 AND NOT EXISTS (SELECT 1 FROM attempts a WHERE a.question_id=q.id
                                 AND a.exam_id=%s)""",
            (exam_id, r["topic_id"], exam_id))
        if pool["n"] >= TOP_UP_MIN:
            continue
        topic = await db.fetch_one("SELECT code FROM topics WHERE id=%s", (r["topic_id"],))
        fmt = await generator.pick_format(exam_id)
        out = await generator.generate_for_topic(exam_id, topic["code"], fmt,
                                                 TOP_UP_MIN - pool["n"], model_id)
        added += len(out.get("accepted", []))
    return added
