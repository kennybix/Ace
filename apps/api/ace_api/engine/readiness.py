"""Composite Readiness Score from multiple signals, with per-topic and per-format breakdowns."""

from __future__ import annotations

import json

from ace_api import db

WEIGHTS = {"accuracy": 0.40, "mock": 0.30, "calibration": 0.15, "recall": 0.15}
CONF_EXPECTED = {"sure": 0.90, "think": 0.65, "guess": 0.40}


async def compute(exam_id: int) -> dict:
    signals: dict[str, float] = {}

    # accuracy: mastery weighted by topic weight
    rows = await db.fetch_all(
        """SELECT t.weight, COALESCE(m.rating, 0.3) AS rating, t.code, t.title,
                  COALESCE(m.n_attempts, 0) AS n
           FROM topics t LEFT JOIN mastery m ON m.topic_id=t.id AND m.exam_id=t.exam_id
           WHERE t.exam_id=%s AND t.parent_id IS NOT NULL""", (exam_id,))
    if not rows:
        rows = await db.fetch_all(
            """SELECT t.weight, COALESCE(m.rating,0.3) AS rating, t.code, t.title,
                      COALESCE(m.n_attempts,0) AS n
               FROM topics t LEFT JOIN mastery m ON m.topic_id=t.id AND m.exam_id=t.exam_id
               WHERE t.exam_id=%s""", (exam_id,))
    total_w = sum(r["weight"] for r in rows) or 1
    if rows:
        signals["accuracy"] = sum(r["rating"] * r["weight"] for r in rows) / total_w

    mock = await db.fetch_one(
        "SELECT score FROM mocks WHERE exam_id=%s AND score IS NOT NULL ORDER BY submitted_at DESC LIMIT 1",
        (exam_id,))
    if mock:
        signals["mock"] = float(mock["score"])

    # calibration: |actual accuracy - expected| per confidence bucket
    buckets = await db.fetch_all(
        """SELECT confidence, avg(CASE WHEN correct THEN 1.0 ELSE 0.0 END) AS acc, count(*) AS n
           FROM attempts WHERE exam_id=%s AND confidence IS NOT NULL GROUP BY confidence""", (exam_id,))
    gaps = [abs(float(b["acc"]) - CONF_EXPECTED[b["confidence"]])
            for b in buckets if b["confidence"] in CONF_EXPECTED and b["n"] >= 3]
    if gaps:
        signals["calibration"] = max(0.0, 1.0 - sum(gaps) / len(gaps))

    recall = await db.fetch_one(
        """SELECT avg(CASE WHEN a.correct THEN 1.0 ELSE 0.0 END) AS acc, count(*) AS n
           FROM attempts a JOIN review_queue r ON r.question_id=a.question_id AND r.exam_id=a.exam_id
           WHERE a.exam_id=%s""", (exam_id,))
    if recall and recall["n"] and recall["n"] >= 5:
        signals["recall"] = float(recall["acc"])

    avail = {k: WEIGHTS[k] for k in signals}
    wsum = sum(avail.values()) or 1
    composite = sum(signals[k] * avail[k] for k in signals) / wsum

    await db.execute(
        "INSERT INTO readiness_snapshots (exam_id, composite, signals) VALUES (%s,%s,%s)",
        (exam_id, composite, json.dumps(signals)))

    heat = [{"code": r["code"], "title": r["title"], "mastery": round(r["rating"], 3),
             "weight": r["weight"], "attempts": r["n"]} for r in sorted(rows, key=lambda x: x["code"])]

    # element rollup: weighted mastery per parent (children carry the live ratings)
    child_rows = await db.fetch_all(
        """SELECT t.parent_id, t.weight, COALESCE(m.rating, 0.3) AS rating,
                  COALESCE(m.n_attempts, 0) AS n
           FROM topics t LEFT JOIN mastery m ON m.topic_id=t.id AND m.exam_id=t.exam_id
           WHERE t.exam_id=%s AND t.parent_id IS NOT NULL""", (exam_id,))
    parents = await db.fetch_all(
        "SELECT id, code, title, weight FROM topics WHERE exam_id=%s AND parent_id IS NULL "
        "ORDER BY code", (exam_id,))
    by_parent: dict[int, list] = {}
    for cr in child_rows:
        by_parent.setdefault(cr["parent_id"], []).append(cr)
    elements = []
    for p in parents:
        kids = by_parent.get(p["id"], [])
        wsum2 = sum(k["weight"] for k in kids) or 1
        elements.append({
            "code": p["code"], "title": p["title"], "weight": p["weight"],
            "mastery": round(sum(k["rating"] * k["weight"] for k in kids) / wsum2, 3),
            "attempts": sum(k["n"] for k in kids),
        })
    fmts = await db.fetch_all(
        """SELECT q.format, avg(CASE WHEN a.correct THEN 1.0 ELSE 0.0 END) AS acc, count(*) AS n
           FROM attempts a JOIN questions q ON q.id=a.question_id
           WHERE a.exam_id=%s GROUP BY q.format""", (exam_id,))
    return {"composite": round(composite, 4), "signals": {k: round(v, 4) for k, v in signals.items()},
            "topics": heat, "elements": elements,
            "per_format": {f["format"]: {"accuracy": round(float(f["acc"]), 3), "n": f["n"]} for f in fmts}}
