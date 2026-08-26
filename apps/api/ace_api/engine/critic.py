"""Deliberate-generation critic: every generated artifact is judged (and possibly revised)
against its source chunks before it can be served. Runs in the nightly batch where latency
is free — quality over speed, by design."""

from __future__ import annotations

import json

from ace_api.llm.client import chat_json

CRITIC_SYSTEM = """You are a strict exam-content reviewer. Output ONLY a JSON object.
Judge the question against the source chunks on:
1. ANSWERABLE: the correct answer is fully supported by the chunks (no outside knowledge);
2. SINGLE-BEST: exactly one option is defensibly correct;
3. DISTRACTORS: wrong options are plausible but clearly wrong to someone who knows the material;
4. CLARITY: stem is unambiguous, no trick wording, no grammar cues leaking the answer.
Reply {"verdict": "pass" | "revise" | "fail", "issues": [str, ...], "revised": {…} | null}.
"revise" = fixable: include the FULL corrected question in "revised" using the same schema
(stem/options/correct_index/explanation or the format's fields), keeping it grounded in the
chunks. "fail" = unsalvageable (off-source, no single answer). Be tough — a bad question
that reaches a candidate is worse than no question."""

LESSON_SYSTEM = """You improve exam micro-lessons. Output ONLY a JSON object.
Given the current lesson and source chunks, produce a sharper version: tighter structure,
concrete examples from the chunks, a 'common trap' note if the material supports one.
Stay strictly within the chunks. Reply {"title": str, "body": markdown str}."""


async def critique_question(payload: dict, fmt: str, chunks: list[dict],
                            model_id: str | None = None) -> dict:
    """Returns {"verdict": ..., "issues": [...], "revised": dict|None}. Fails safe to 'pass'
    shape on malformed critic output (the hard gates before this still applied)."""
    user = json.dumps({
        "format": fmt,
        "question": payload,
        "chunks": [{"id": c["id"], "text": c["text"][:1200]} for c in chunks[:6]],
    })
    out = await chat_json("critique_question", CRITIC_SYSTEM, user, model_id=model_id,
                          temperature=0.2)
    if not isinstance(out, dict) or out.get("verdict") not in ("pass", "revise", "fail"):
        return {"verdict": "pass", "issues": ["critic reply malformed — kept original"],
                "revised": None}
    return {"verdict": out["verdict"], "issues": out.get("issues", []),
            "revised": out.get("revised") if isinstance(out.get("revised"), dict) else None}


async def improve_lesson(body: str, topic_title: str, chunks: list[dict],
                         model_id: str | None = None) -> dict | None:
    user = json.dumps({
        "topic": topic_title,
        "current_lesson": body[:4000],
        "chunks": [{"id": c["id"], "text": c["text"][:1200]} for c in chunks[:6]],
    })
    out = await chat_json("improve_lesson", LESSON_SYSTEM, user, model_id=model_id,
                          temperature=0.4)
    if isinstance(out, dict) and isinstance(out.get("body"), str) and len(out["body"]) > 100:
        return out
    return None
