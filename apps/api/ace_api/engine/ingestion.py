"""Ingestion pipeline: classify → chunk → embed → topic-map; exam-agnostic.

Deterministic heuristics first; LLM only where structure is genuinely absent
(topic-tree inference for exams with no syllabus upload and no accelerator).
"""

from __future__ import annotations

import json
import re

from ace_api import db
from ace_api.engine.embedder import cosine, embed, to_pgvector
from ace_api.engine.pdf import extract_pages
from ace_api.llm.client import chat_json

CHUNK_CHARS = 1200
TOPIC_MATCH_MIN = 0.08  # hash-embedding scale; proxy embeddings clear this easily


def classify_text(filename: str, text: str) -> str:
    name = filename.lower()
    body = text[:20000]
    option_qs = len(re.findall(r"\n\s*[A-D]\.\s", body))
    numbered = len(re.findall(r"\n\s*\d{1,3}\.\s", body))
    if "syllabus" in name or ("learning outcome" in body.lower() and "element" in body.lower()):
        return "syllabus"
    if option_qs >= 12 and numbered >= 4:
        return "past_questions"
    if "guidance" in name or "how to study" in body.lower():
        return "guidance"
    return "textbook"


def chunk_pages(pages) -> list[dict]:
    chunks, buf, start_page = [], "", 1
    for p in pages:
        paras = [s for s in re.split(r"\n\s*\n", p.text) if s.strip()]
        for para in paras:
            if not buf:
                start_page = p.number
            buf += ("\n\n" if buf else "") + para.strip()
            if len(buf) >= CHUNK_CHARS:
                chunks.append({"page_from": start_page, "page_to": p.number, "text": buf})
                buf = ""
        # page boundary: flush oversized remainder to keep page ranges tight
        if len(buf) >= CHUNK_CHARS // 2:
            chunks.append({"page_from": start_page, "page_to": p.number, "text": buf})
            buf = ""
    if buf.strip():
        chunks.append({"page_from": start_page, "page_to": pages[-1].number if pages else 1, "text": buf})
    return [c for c in chunks if len(c["text"]) > 80]


GENERIC_Q_RE = re.compile(r"\n\s*(\d{1,3})[\.\)]\s+(.{15,400}?)\n\s*A[\.\)]\s", re.S)


def extract_generic_questions(text: str) -> list[dict]:
    """Numbered stem + A–D options extractor for arbitrary past-question uploads."""
    out = []
    option_split = re.compile(r"\n\s*([A-D])[\.\)]\s")
    blocks = re.split(r"(?=\n\s*\d{1,3}[\.\)]\s)", "\n" + text)
    for b in blocks:
        m = re.match(r"\n\s*(\d{1,3})[\.\)]\s*(.*)", b, re.S)
        if not m:
            continue
        parts = option_split.split(m.group(2))
        if len(parts) < 9:  # stem + 4*(marker,text)
            continue
        stem = re.sub(r"\s+", " ", parts[0]).strip()
        options = [re.sub(r"\s+", " ", parts[i + 1]).strip()[:400] for i in range(1, 9, 2)]
        if len(stem) > 15 and all(options):
            out.append({"number": int(m.group(1)), "stem": stem, "options": options[:4]})
    return out


async def ingest_document(document_id: int) -> dict:
    doc = await db.fetch_one("SELECT * FROM documents WHERE id=%s", (document_id,))
    pages = extract_pages(doc["stored_path"])
    text = "\n".join(p.text for p in pages)
    kind = classify_text(doc["filename"], text)
    chunks = chunk_pages(pages)
    vecs = await embed([c["text"] for c in chunks]) if chunks else []

    async with db.conn() as c:
        await c.execute("UPDATE documents SET kind=%s, page_count=%s, parse_status='parsed' WHERE id=%s",
                        (kind, len(pages), document_id))
        for ch, v in zip(chunks, vecs):
            await c.execute(
                """INSERT INTO chunks (document_id, exam_id, page_from, page_to, text, embedding)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (document_id, doc["exam_id"], ch["page_from"], ch["page_to"], ch["text"], to_pgvector(v)),
            )
        extracted = 0
        if kind == "past_questions":
            qs = extract_generic_questions(text)
            qv = await embed([q["stem"] + " " + " ".join(q["options"]) for q in qs]) if qs else []
            for q, v in zip(qs, qv):
                payload = {"stem": q["stem"], "options": q["options"], "correct_index": None,
                           "explanation": "Extracted from your uploaded past questions."}
                await c.execute(
                    """INSERT INTO questions (exam_id, source, format, cognitive_level, payload,
                                              citations, status, embedding)
                       VALUES (%s,'extracted','mcq','understand',%s,'[]','pending_review',%s)""",
                    (doc["exam_id"], json.dumps(payload), to_pgvector(v)),
                )
                extracted += 1
    return {"kind": kind, "pages": len(pages), "chunks": len(chunks), "extracted_questions": extracted}


async def finalize_exam(exam_id: int) -> dict:
    """After all docs ingested: ensure topic tree exists, map chunks + questions to topics."""
    topics = await db.fetch_all(
        "SELECT id, code, title, weight FROM topics WHERE exam_id=%s AND parent_id IS NOT NULL", (exam_id,))
    if not topics:
        topics_all = await db.fetch_all("SELECT id, code, title FROM topics WHERE exam_id=%s", (exam_id,))
        if not topics_all:
            await _infer_topic_tree(exam_id)
            topics = await db.fetch_all(
                "SELECT id, code, title, weight FROM topics WHERE exam_id=%s AND parent_id IS NOT NULL",
                (exam_id,))
            if not topics:
                topics = await db.fetch_all("SELECT id, code, title, weight FROM topics WHERE exam_id=%s",
                                            (exam_id,))
        else:
            topics = topics_all

    topic_vecs = await embed([f"{t['title']}" for t in topics])

    # element hints: a document named/titled "Element N …" maps only into element N's
    # subtree — far more precise than embedding similarity across the whole tree
    parents = await db.fetch_all(
        "SELECT id, code FROM topics WHERE exam_id=%s AND parent_id IS NULL", (exam_id,))
    parent_by_code = {p["code"]: p["id"] for p in parents}
    child_parent = {t["id"]: None for t in topics}
    for t in await db.fetch_all(
            "SELECT id, parent_id FROM topics WHERE exam_id=%s AND parent_id IS NOT NULL",
            (exam_id,)):
        child_parent[t["id"]] = t["parent_id"]
    doc_hint: dict[int, int] = {}
    for d in await db.fetch_all("SELECT id, filename FROM documents WHERE exam_id=%s", (exam_id,)):
        m = re.search(r"element[\s_-]*(\d)", d["filename"], re.I)
        if m and m.group(1) in parent_by_code:
            doc_hint[d["id"]] = parent_by_code[m.group(1)]

    mapped = 0
    rows = await db.fetch_all(
        "SELECT id, document_id, text, embedding FROM chunks WHERE exam_id=%s AND topic_id IS NULL",
        (exam_id,))
    for r in rows:
        v = _parse_vec(r["embedding"])
        hint_parent = doc_hint.get(r["document_id"])
        best_i, best_s = -1, -1.0
        for i, tv in enumerate(topic_vecs):
            if hint_parent is not None and child_parent.get(topics[i]["id"]) != hint_parent \
                    and topics[i]["id"] != hint_parent:
                continue
            s = cosine(v, tv)
            if s > best_s:
                best_i, best_s = i, s
        if best_i >= 0 and (best_s >= TOPIC_MATCH_MIN or hint_parent is not None):
            await db.execute("UPDATE chunks SET topic_id=%s WHERE id=%s", (topics[best_i]["id"], r["id"]))
            mapped += 1
    qrows = await db.fetch_all(
        "SELECT id, embedding FROM questions WHERE exam_id=%s AND topic_id IS NULL", (exam_id,))
    for r in qrows:
        v = _parse_vec(r["embedding"])
        best_i = max(range(len(topic_vecs)), key=lambda i: cosine(v, topic_vecs[i]), default=-1)
        if best_i >= 0:
            await db.execute("UPDATE questions SET topic_id=%s WHERE id=%s", (topics[best_i]["id"], r["id"]))
    await db.execute("UPDATE exams SET status='confirming' WHERE id=%s", (exam_id,))
    return {"topics": len(topics), "chunks_mapped": mapped}


def _parse_vec(raw) -> list[float]:
    if isinstance(raw, list):
        return raw
    return [float(x) for x in str(raw).strip("[]").split(",")]


async def _infer_topic_tree(exam_id: int) -> None:
    """No syllabus, no accelerator: infer a flat tree from content (LLM), fallback to single bucket."""
    sample = await db.fetch_all(
        "SELECT text FROM chunks WHERE exam_id=%s ORDER BY id LIMIT 30", (exam_id,))
    corpus = "\n---\n".join(r["text"][:400] for r in sample)
    try:
        out = await chat_json("infer_topic_tree",
                              "Infer an exam topic tree. Reply JSON {\"topics\":[{code,title,weight,cognitive_levels}]}",
                              json.dumps({"corpus": corpus[:12000]}))
        topics = out.get("topics") or []
    except Exception:
        topics = []
    if not topics:
        topics = [{"code": "1", "title": "General", "weight": 1, "cognitive_levels": ["understand"]}]
    for t in topics:
        await db.execute(
            """INSERT INTO topics (exam_id, code, title, weight, cognitive_levels, source)
               VALUES (%s,%s,%s,%s,%s,'toc_inferred')""",
            (exam_id, str(t["code"]), t["title"][:200], float(t.get("weight", 1)),
             t.get("cognitive_levels", ["understand"])),
        )
