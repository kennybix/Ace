"""Grounded, format-faithful question generation with hard gating.

Gates (enforced in code, never trusted to the model):
  1. citations non-empty and every cited chunk id must be one we supplied
  2. payload schema-valid for its format
  3. near-duplicate check vs existing questions for the exam (embedding cosine)
"""

from __future__ import annotations

import json

from ace_api import db
from ace_api.config import settings
from ace_api.engine.embedder import cosine, embed, to_pgvector
from ace_api.llm.client import PROMPT_VERSION, chat_json

DUPE_COSINE = 0.92

SYSTEM = """Output ONLY a JSON object — no prose, no questions back, no markdown fences.
You write exam practice questions STRICTLY grounded in the provided source chunks.
Every question must be answerable from the chunks alone. Reply JSON:
{"questions": [{"format": "...", "cognitive_level": "...", "citation_chunk_ids": [int, ...],
  "difficulty": 0..1, ...format fields...}]}
Use EXACTLY these keys. "options" is an ARRAY of 4 strings (never an object). "correct_index" is an
integer 0-3. "citation_chunk_ids" contains the integer ids of chunks you used, as provided.
Format fields — mcq: stem, options[4], correct_index, explanation, option_notes {"A": why
right/wrong one-liner, "B": …, "C": …, "D": …}; tf: statement, answer, explanation;
gap: text_with_gap (with ____), answers[], explanation; match: left[], right[], pairs[[i,j]], explanation;
numeric: stem, answer, tolerance, unit, explanation.
Mirror the style of the example questions if given. If the chunks cannot support questions on the
topic, reply {"questions": []} — NEVER prose, never an apology, never a refusal outside JSON."""


LETTERS = "ABCD"


def _normalize(q: dict) -> dict:
    """Map model-dialect keys onto the canonical schema before validation.
    Models drift (stem→question, options as {A:..}, answers as letters) — gates stay strict,
    normalization absorbs the dialects."""
    q = dict(q)
    if "stem" not in q and q.get("format") in (None, "mcq", "numeric"):
        for k in ("question", "prompt", "text"):
            if isinstance(q.get(k), str):
                q["stem"] = q.pop(k)
                break
    opts = q.get("options")
    if isinstance(opts, dict):
        q["options"] = [str(opts[k]) for k in sorted(opts.keys())]
    if q.get("format", "mcq") == "mcq" and "correct_index" not in q:
        ans = (q.get("correct_answer") or q.get("correct_option") or q.get("answer")
               or q.get("key"))
        if isinstance(ans, int) and 0 <= ans < 4:
            q["correct_index"] = ans
        elif isinstance(ans, str):
            a = ans.strip()
            if len(a) == 1 and a.upper() in LETTERS:
                q["correct_index"] = LETTERS.index(a.upper())
            elif isinstance(q.get("options"), list) and a in q["options"]:
                q["correct_index"] = q["options"].index(a)
    if "explanation" not in q and isinstance(q.get("rationale"), str):
        q["explanation"] = q.pop("rationale")
    q.setdefault("explanation", "")
    cites = q.get("citation_chunk_ids") or q.get("citations") or q.get("citation_ids") or []
    norm: list[int] = []
    for c in cites if isinstance(cites, list) else []:
        if isinstance(c, dict):
            c = c.get("chunk_id")
        try:
            norm.append(int(c))
        except (TypeError, ValueError):
            continue
    q["citation_chunk_ids"] = norm
    return q


def _valid(q: dict) -> bool:
    fmt = q.get("format")
    try:
        if fmt == "mcq":
            return (len(q["options"]) == 4 and isinstance(q["correct_index"], int)
                    and 0 <= q["correct_index"] < 4 and len(q["stem"]) > 8)
        if fmt == "tf":
            return isinstance(q["answer"], bool) and len(q["statement"]) > 8
        if fmt == "gap":
            return "____" in q["text_with_gap"] and q["answers"]
        if fmt == "match":
            return (len(q["left"]) == len(q["right"]) >= 2
                    and all(len(p) == 2 for p in q["pairs"]) and len(q["pairs"]) == len(q["left"]))
        if fmt == "numeric":
            return isinstance(q["answer"], (int, float)) and isinstance(q["tolerance"], (int, float))
    except (KeyError, TypeError):
        return False
    return False


async def generate_for_topic(exam_id: int, topic_code: str, fmt: str, n: int,
                             model_id: str | None = None, cognitive_level: str | None = None) -> dict:
    topic = await db.fetch_one(
        "SELECT id, code, title FROM topics WHERE exam_id=%s AND code=%s", (exam_id, topic_code))
    if not topic:
        return {"error": f"topic {topic_code} not found for exam {exam_id}"}
    chunks = await db.fetch_all(
        """SELECT id, text FROM chunks WHERE exam_id=%s AND topic_id IN
           (SELECT id FROM topics WHERE exam_id=%s AND (id=%s OR parent_id=%s))
           ORDER BY id LIMIT 8""", (exam_id, exam_id, topic["id"], topic["id"]))
    if not chunks:  # fall back to any exam chunks nearest the topic title
        chunks = await db.fetch_all(
            "SELECT id, text FROM chunks WHERE exam_id=%s ORDER BY id LIMIT 8", (exam_id,))
    if not chunks:
        return {"error": "no source chunks ingested for this exam — upload materials first"}

    style = await db.fetch_all(
        """SELECT payload FROM questions WHERE exam_id=%s AND source='extracted' AND format=%s
           AND status='active' LIMIT 3""", (exam_id, fmt))
    user = json.dumps({
        "n": n, "format": fmt, "topic": f"{topic['code']} {topic['title']}",
        "cognitive_level": cognitive_level or "understand",
        "chunks": [{"id": c["id"], "text": c["text"][:1500]} for c in chunks],
        "style_examples": [s["payload"] for s in style],
        "CRITICAL": ("Every question MUST include \"citation_chunk_ids\": a non-empty array of the "
                     "integer chunk ids (above) it is grounded in. Questions without it are "
                     "DISCARDED automatically."),
        "output_example": {"questions": [{"citation_chunk_ids": [chunks[0]["id"]], "format": fmt,
                                          "cognitive_level": "understand", "difficulty": 0.5,
                                          "stem": "…", "options": ["…", "…", "…", "…"],
                                          "correct_index": 0, "explanation": "…"}]},
    })
    from ace_api.llm.client import LLMError
    try:
        out = await chat_json("generate_questions", SYSTEM, user, model_id=model_id, temperature=0.6)
    except LLMError as e:
        return {"accepted": [], "rejected": {"llm_error": str(e)[:200]}, "requested": n}
    # models occasionally reply with a bare array despite the schema — normalize
    candidates = out.get("questions", []) if isinstance(out, dict) else (
        out if isinstance(out, list) else [])

    chunk_ids = {c["id"] for c in chunks}
    existing = await db.fetch_all(
        "SELECT embedding FROM questions WHERE exam_id=%s AND status='active'", (exam_id,))
    existing_vecs = [e["embedding"] if isinstance(e["embedding"], list)
                     else [float(x) for x in str(e["embedding"]).strip("[]").split(",")]
                     for e in existing if e["embedding"] is not None]

    accepted, rejected = [], {"ungrounded": 0, "invalid": 0, "duplicate": 0,
                              "failed_critique": 0, "revised": 0}
    for q in candidates:
        if not isinstance(q, dict):
            rejected["invalid"] += 1
            continue
        q = _normalize(q)
        q.setdefault("format", fmt)
        cites = q.get("citation_chunk_ids") or []
        if not cites or not set(cites) <= chunk_ids:
            rejected["ungrounded"] += 1
            continue
        if not _valid(q):
            rejected["invalid"] += 1
            continue

        # deliberate generation: critic judges (and may revise) before anything is served
        critique_notes: list[str] = []
        if settings().deliberate_generation:
            from ace_api.engine.critic import critique_question
            chunk_subset = [c for c in chunks if c["id"] in set(cites)] or chunks[:4]
            payload_for_critic = {k: v for k, v in q.items() if k != "citation_chunk_ids"}
            verdict = await critique_question(payload_for_critic, q["format"], chunk_subset,
                                              model_id)
            if verdict["verdict"] == "fail":
                rejected["failed_critique"] += 1
                continue
            if verdict["verdict"] == "revise" and verdict["revised"]:
                revised = _normalize({**verdict["revised"],
                                      "citation_chunk_ids": cites,
                                      "format": q["format"]})
                revised.setdefault("cognitive_level", q.get("cognitive_level", "understand"))
                revised.setdefault("difficulty", q.get("difficulty", 0.5))
                if _valid(revised):
                    q = revised
                    rejected["revised"] += 1
            critique_notes = verdict.get("issues", [])
        text = _text_of(q)
        vec = (await embed([text]))[0]
        if any(cosine(vec, ev) > DUPE_COSINE for ev in existing_vecs):
            rejected["duplicate"] += 1
            continue
        existing_vecs.append(vec)
        payload = {k: v for k, v in q.items()
                   if k not in {"format", "cognitive_level", "citation_chunk_ids", "difficulty"}}
        citations = [{"chunk_id": cid} for cid in cites]
        row = await db.fetch_one(
            """INSERT INTO questions (exam_id, topic_id, source, format, cognitive_level, payload,
                                      citations, difficulty, status, model_id, prompt_version,
                                      embedding, last_reviewed_at, critique_notes)
               VALUES (%s,%s,'generated',%s,%s,%s,%s,%s,'active',%s,%s,%s, now(), %s)
               RETURNING id""",
            (exam_id, topic["id"], q["format"], q.get("cognitive_level", "understand"),
             json.dumps(payload), json.dumps(citations), float(q.get("difficulty", 0.5)),
             model_id or "default", PROMPT_VERSION, to_pgvector(vec),
             json.dumps(critique_notes)))
        accepted.append(row["id"])
    return {"accepted": accepted, "rejected": rejected, "requested": n}


GRADABLE = {"mcq", "tf", "gap", "match", "numeric"}


async def pick_format(exam_id: int) -> str:
    """Weighted-random format matching the exam's question-type profile — CIRE (100% MCQ)
    always gets mcq; a mixed-format exam gets its real mix."""
    import random
    exam = await db.fetch_one("SELECT accelerator_id FROM exams WHERE id=%s", (exam_id,))
    mix: dict | None = None
    if exam and exam["accelerator_id"]:
        acc = await db.fetch_one("SELECT default_profile FROM accelerators WHERE id=%s",
                                 (exam["accelerator_id"],))
        mix = (acc["default_profile"] or {}).get("format_mix")
    if not mix:
        rows = await db.fetch_all(
            """SELECT format, count(*) AS n FROM questions
               WHERE exam_id=%s AND source='extracted' AND status='active' GROUP BY format""",
            (exam_id,))
        mix = {r["format"]: r["n"] for r in rows}
    mix = {k: v for k, v in (mix or {}).items() if k in GRADABLE and v > 0}
    if not mix:
        return "mcq"
    formats, weights = zip(*mix.items())
    return random.choices(formats, weights=weights)[0]


def _text_of(q: dict) -> str:
    for k in ("stem", "statement", "text_with_gap"):
        if k in q:
            base = q[k]
            break
    else:
        base = json.dumps(q.get("left", "")) + json.dumps(q.get("right", ""))
    return f"{base} {' '.join(q.get('options', []))}"
