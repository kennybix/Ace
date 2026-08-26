"""Deterministic plan builder: backwards from exam date, weighted by syllabus weight × weakness.
LLM used only for the human-readable rationale."""

from __future__ import annotations

import json
from datetime import date, timedelta

from ace_api import db
from ace_api.llm.client import chat_json

SESSION_MIN = 45
DAY_PATTERNS = {1: [0], 2: [0, 3], 3: [0, 2, 4], 4: [0, 1, 3, 5], 5: [0, 1, 2, 4, 5],
                6: [0, 1, 2, 3, 4, 5], 7: [0, 1, 2, 3, 4, 5, 6]}


async def build_plan(exam_id: int) -> dict:
    exam = await db.fetch_one("SELECT * FROM exams WHERE id=%s", (exam_id,))
    topics = await db.fetch_all(
        """SELECT t.id, t.code, t.title, t.weight, COALESCE(m.rating, 0.3) AS mastery
           FROM topics t LEFT JOIN mastery m ON m.topic_id = t.id AND m.exam_id = t.exam_id
           WHERE t.exam_id=%s AND t.parent_id IS NOT NULL ORDER BY t.code""", (exam_id,))
    if not topics:
        topics = await db.fetch_all(
            """SELECT t.id, t.code, t.title, t.weight, COALESCE(m.rating, 0.3) AS mastery
               FROM topics t LEFT JOIN mastery m ON m.topic_id = t.id AND m.exam_id = t.exam_id
               WHERE t.exam_id=%s ORDER BY t.code""", (exam_id,))
    if not topics or not exam["exam_date"]:
        return {"error": "need topics and an exam date to plan"}

    today = date.today()
    exam_day = exam["exam_date"]
    if exam_day <= today:
        return {"error": "exam date is in the past — update it in the Library first"}
    days_left = max((exam_day - today).days, 3)
    per_week = min(7, max(3, round(exam["weekly_hours"] * 60 / SESSION_MIN)))
    pattern = DAY_PATTERNS[per_week]

    # day 0 included: a fresh plan offers a session TODAY, not "come back tomorrow"
    study_days = [today + timedelta(days=d)
                  for d in range(0, days_left)
                  if (today + timedelta(days=d)).weekday() in pattern]
    if not study_days:
        study_days = [today + timedelta(days=d) for d in range(0, days_left)]
    taper_days = [d for d in study_days if (exam_day - d).days <= 3]
    mock_idx = sorted({int(len(study_days) * 0.6), int(len(study_days) * 0.85)}) if len(study_days) >= 6 else []
    work_days = [d for i, d in enumerate(study_days) if d not in taper_days and i not in mock_idx]

    # priority = exam weight × current weakness
    ranked = sorted(topics, key=lambda t: -(t["weight"] * (1.0 - t["mastery"])))
    n_learn = len(work_days)
    groups: list[list] = [[] for _ in range(max(n_learn, 1))]
    for i, t in enumerate(ranked):
        groups[i % max(n_learn, 1)].append(t)

    async with db.conn() as c:
        await c.execute("UPDATE plans SET status='superseded' WHERE exam_id=%s AND status='active'",
                        (exam_id,))
        ver = await (await c.execute(
            "SELECT COALESCE(MAX(version),0)+1 AS v FROM plans WHERE exam_id=%s", (exam_id,))).fetchone()
        plan = await (await c.execute(
            "INSERT INTO plans (exam_id, version, status) VALUES (%s,%s,'active') RETURNING id",
            (exam_id, ver["v"]))).fetchone()
        plan_id = plan["id"]
        for i, d in enumerate(study_days):
            if i in mock_idx:
                kind, tids, minutes = "mock", [], 130
            elif d in taper_days:
                kind, tids, minutes = "taper", [t["id"] for t in ranked[:6]], SESSION_MIN
            else:
                gi = work_days.index(d) if d in work_days else 0
                kind, tids, minutes = "learn", [t["id"] for t in groups[gi % len(groups)]], SESSION_MIN
            await c.execute(
                """INSERT INTO plan_items (plan_id, day, topic_ids, kind, est_minutes)
                   VALUES (%s,%s,%s,%s,%s)""", (plan_id, d, tids, kind, minutes))

    try:
        rat = await chat_json("plan_rationale",
                              "Explain this study plan in 2 sentences. JSON {\"rationale\": str}",
                              json.dumps({"days_left": days_left, "sessions": len(study_days),
                                          "weakest": [t["code"] for t in ranked[:5]]}))
        rationale = rat.get("rationale", "")
    except Exception:
        rationale = ""
    await db.execute("UPDATE plans SET rationale=%s WHERE id=%s", (rationale, plan_id))
    await db.execute("UPDATE exams SET status='active' WHERE id=%s", (exam_id,))
    return {"plan_id": plan_id, "version": ver["v"], "sessions": len(study_days),
            "mocks": len(mock_idx), "rationale": rationale}
