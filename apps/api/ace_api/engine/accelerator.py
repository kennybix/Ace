"""Build + persist exam accelerators (pooled, derived from official/public docs only)."""

from __future__ import annotations

import json
from pathlib import Path

from ace_api import db
from ace_api.engine import cire
from ace_api.engine.embedder import embed, to_pgvector


async def build_cire(resources_dir: str) -> dict:
    base = Path(resources_dir)
    syl = cire.parse_syllabus(str(base / "Appendix-1-Canadian-Investment-Regulatory-Exam-CIRE-Syllabus-EN.pdf"))
    questions = cire.parse_practice_exam(str(base / "Appendix-2-CIRE-Practice-Exam-EN.pdf"))
    guidance = cire.parse_guidance(str(base / "Appendix-3-CIRE-Guidance-for-Studying-EN.pdf"))
    tree = cire.topic_tree_json(syl)
    profile = cire.build_profile(syl, questions)

    async with db.conn() as c:
        # idempotent rebuild
        old = await (await c.execute("SELECT id FROM accelerators WHERE exam_key=%s", (cire.EXAM_KEY,))).fetchone()
        if old:
            await c.execute("DELETE FROM questions WHERE accelerator_id=%s", (old["id"],))
            await c.execute("DELETE FROM topics WHERE accelerator_id=%s", (old["id"],))
            await c.execute("DELETE FROM accelerators WHERE id=%s", (old["id"],))
        row = await (await c.execute(
            """INSERT INTO accelerators (exam_key, display_name, topic_tree, default_profile, planner_defaults, provenance)
               VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
            (cire.EXAM_KEY, cire.DISPLAY_NAME, json.dumps(tree), json.dumps(profile),
             json.dumps(guidance), "CIRO official PDFs (Jan 2025), parsed deterministically"),
        )).fetchone()
        acc_id = row["id"]

        for el in tree:
            parent = await (await c.execute(
                """INSERT INTO topics (accelerator_id, code, title, weight, cognitive_levels, source)
                   VALUES (%s,%s,%s,%s,%s,'syllabus_parsed') RETURNING id""",
                (acc_id, el["code"], el["title"], el["weight"], []),
            )).fetchone()
            for ch in el["children"]:
                await c.execute(
                    """INSERT INTO topics (accelerator_id, parent_id, code, title, weight, cognitive_levels, source)
                       VALUES (%s,%s,%s,%s,%s,%s,'syllabus_parsed')""",
                    (acc_id, parent["id"], ch["code"], ch["title"], ch["weight"], ch["cognitive_levels"]),
                )

        vecs = await embed([q.stem + " " + " ".join(q.options) for q in questions])
        for q, v in zip(questions, vecs):
            payload = {"stem": q.stem, "options": q.options, "correct_index": "ABCD".index(q.key),
                       "explanation": "Official CIRO practice exam item."}
            await c.execute(
                """INSERT INTO questions (accelerator_id, source, format, cognitive_level, payload,
                                          citations, status, external_item_id, embedding)
                   VALUES (%s,'extracted','mcq',%s,%s,'[]','active',%s,%s)""",
                (acc_id, q.cognitive, json.dumps(payload), q.item_id, to_pgvector(v)),
            )
    return {"accelerator_id": acc_id, "elements": len(tree),
            "outcomes": sum(len(t["children"]) for t in tree), "questions": len(questions),
            "profile": profile}
