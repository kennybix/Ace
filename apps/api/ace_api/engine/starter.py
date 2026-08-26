"""Exam-agnostic cold start: for an exam with no accelerator and no uploads, the agent
builds a STARTER PACK from model knowledge — a topic tree plus per-topic study notes,
stored as a clearly-labeled AI-generated document whose chunks feed the normal gated
pipeline (lessons, questions, critic, enrichment). Provenance is never hidden: the pack
appears in the Library as its own removable document, marked AI-generated."""

from __future__ import annotations

import json

from ace_api import db
from ace_api.engine.embedder import embed, to_pgvector
from ace_api.llm.client import chat_json

STARTER_DOC_NAME = "Ace Starter Pack (AI-generated — verify against official materials)"

TREE_SYSTEM = """Output ONLY a JSON object. You design an exam-prep syllabus outline for a
well-known professional exam from your knowledge of it. Reply
{"elements": [{"code": "1", "title": str, "weight": int (relative exam emphasis 1-20),
  "children": [{"code": "1.1", "title": str,
                "cognitive": "remember"|"understand"|"apply"|"analyze"}]}]}
5–9 elements, 3–8 children each, mirroring the real exam's published domains as closely as
you know them. If the exam is obscure and you genuinely don't know its structure, reply
{"elements": []}."""

NOTES_SYSTEM = """Output ONLY a JSON object. You write concise exam-prep study notes from
your knowledge. For the given element and its topics reply
{"sections": [{"topic_code": str, "notes": str}]} — one section per topic, 150–300 words
each: the key rules, definitions, numbers and distinctions a candidate must know. Be
factual and specific; skip filler. If you don't know a topic well, keep its section short
rather than inventing specifics."""


async def build_starter_pack(exam_id: int, model_id: str | None = None) -> dict:
    exam = await db.fetch_one("SELECT * FROM exams WHERE id=%s", (exam_id,))
    stats = {"topics_created": 0, "sections": 0, "chunks": 0}

    doc = await db.fetch_one(
        """INSERT INTO documents (exam_id, filename, sha256, stored_path, kind, parse_status)
           VALUES (%s,%s,'starter','', 'starter', 'parsing') RETURNING id""",
        (exam_id, STARTER_DOC_NAME))
    try:
        parents = await db.fetch_all(
            "SELECT id, code, title FROM topics WHERE exam_id=%s AND parent_id IS NULL "
            "ORDER BY code", (exam_id,))
        children_by_parent: dict[int, list[dict]] = {}

        if not parents:
            out = await chat_json("starter_topic_tree", TREE_SYSTEM,
                                  json.dumps({"exam": exam["name_raw"]}), model_id=model_id,
                                  temperature=0.3, max_tokens=6000)
            elements = out.get("elements", []) if isinstance(out, dict) else []
            if not elements:
                await db.execute(
                    "UPDATE documents SET parse_status='failed' WHERE id=%s", (doc["id"],))
                return {"error": "Ace doesn't know this exam's structure — upload a syllabus "
                                 "or study materials instead."}
            for el in elements[:9]:
                p = await db.fetch_one(
                    """INSERT INTO topics (exam_id, code, title, weight, cognitive_levels, source)
                       VALUES (%s,%s,%s,%s,'{}','ai_starter') RETURNING id, code, title""",
                    (exam_id, str(el.get("code", "?")), str(el.get("title", ""))[:200],
                     float(el.get("weight", 5))))
                kids = []
                for ch in el.get("children", [])[:8]:
                    c = await db.fetch_one(
                        """INSERT INTO topics (exam_id, parent_id, code, title, weight,
                                               cognitive_levels, source)
                           VALUES (%s,%s,%s,%s,%s,%s,'ai_starter') RETURNING id, code, title""",
                        (exam_id, p["id"], str(ch.get("code", "?")),
                         str(ch.get("title", ""))[:200],
                         float(el.get("weight", 5)) / max(len(el.get("children", [])), 1),
                         [str(ch.get("cognitive", "understand"))]))
                    kids.append(c)
                    stats["topics_created"] += 1
                parents = parents + [p]
                children_by_parent[p["id"]] = kids
                stats["topics_created"] += 1
        else:
            for p in parents:
                children_by_parent[p["id"]] = await db.fetch_all(
                    "SELECT id, code, title FROM topics WHERE exam_id=%s AND parent_id=%s",
                    (exam_id, p["id"]))

        # per-element study notes → chunks mapped directly to their topics
        for p in parents[:9]:
            kids = children_by_parent.get(p["id"], [])
            if not kids:
                continue
            out = await chat_json(
                "starter_notes", NOTES_SYSTEM,
                json.dumps({"exam": exam["name_raw"], "element": f"{p['code']} {p['title']}",
                            "topics": [{"code": k["code"], "title": k["title"]} for k in kids]}),
                model_id=model_id, temperature=0.3, max_tokens=8000)
            sections = out.get("sections", []) if isinstance(out, dict) else []
            by_code = {k["code"]: k["id"] for k in kids}
            texts, tids = [], []
            for s in sections:
                code = str(s.get("topic_code", ""))
                notes = str(s.get("notes", "")).strip()
                if code in by_code and len(notes) > 80:
                    texts.append(f"[AI starter notes — verify] {p['title']} · {code}: {notes}")
                    tids.append(by_code[code])
            if texts:
                vecs = await embed(texts)
                for text, tid, v in zip(texts, tids, vecs):
                    await db.execute(
                        """INSERT INTO chunks (document_id, exam_id, page_from, page_to, text,
                                               embedding, topic_id)
                           VALUES (%s,%s,0,0,%s,%s,%s)""",
                        (doc["id"], exam_id, text, to_pgvector(v), tid))
                    stats["chunks"] += 1
                stats["sections"] += len(texts)

        # seed questions so the diagnostic and drills work immediately — normal gated
        # pipeline (citations to the starter chunks, critic and all)
        stats["seed_questions"] = 0
        if stats["chunks"]:
            from ace_api.engine.generator import generate_for_topic, pick_format
            seed_topics = await db.fetch_all(
                """SELECT DISTINCT ON (t.parent_id) t.code FROM topics t
                   JOIN chunks c ON c.topic_id = t.id
                   WHERE t.exam_id=%s AND t.parent_id IS NOT NULL
                   ORDER BY t.parent_id, t.code LIMIT 8""", (exam_id,))
            for st_topic in seed_topics:
                try:
                    fmt = await pick_format(exam_id)
                    out = await generate_for_topic(exam_id, st_topic["code"], fmt, 2,
                                                   model_id)
                    stats["seed_questions"] += len(out.get("accepted", []))
                except Exception:
                    continue

        await db.execute(
            "UPDATE documents SET parse_status=%s, page_count=%s WHERE id=%s",
            ("parsed" if stats["chunks"] else "failed", stats["sections"], doc["id"]))
        await db.execute("UPDATE exams SET status='active' WHERE id=%s", (exam_id,))
    except Exception:
        await db.execute("UPDATE documents SET parse_status='failed' WHERE id=%s", (doc["id"],))
        raise
    return stats
