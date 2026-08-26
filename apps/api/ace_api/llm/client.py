"""OpenAI-compatible chat client for the CLI proxy gateway, plus a deterministic fake for tests.

Every call site passes `task` (stable string) — the fake dispatches on it, and telemetry keys on it.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from ace_api.config import settings

PROMPT_VERSION = "v1"


class LLMError(RuntimeError):
    pass


def resolve_model(model_id: str | None) -> dict:
    s = settings()
    mid = model_id or s.llm_default_model
    for m in s.llm_models:
        if m["id"] == mid or m["gateway"] == mid:
            return m
    raise LLMError(f"unknown model '{mid}'")


async def chat_json(task: str, system: str, user: str, model_id: str | None = None,
                    temperature: float = 0.3, max_tokens: int = 4000) -> dict[str, Any]:
    """One structured-output call. Returns parsed JSON dict. Honors fake mode."""
    s = settings()
    if s.llm_fake or not s.llm_api_key:
        return _fake(task, user)
    model = resolve_model(model_id)
    body = {
        "model": model["gateway"],
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    # Claude 4.8/5-era models deprecate the temperature param — omit it for them
    if not model["gateway"].startswith("claude"):
        body["temperature"] = temperature
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            f"{s.llm_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {s.llm_api_key}"},
            json=body,
        )
    if resp.status_code != 200:
        raise LLMError(f"gateway {resp.status_code}: {resp.text[:300]}")
    content = resp.json()["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        # salvage 1: strip code fences; salvage 2: first JSON object/array embedded in prose
        stripped = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        for candidate in (stripped, _embedded_json(content)):
            if candidate:
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue
        raise LLMError(f"non-JSON reply for task={task}: {content[:200]}") from e


def _embedded_json(text: str) -> str | None:
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = text.find(open_c)
        end = text.rfind(close_c)
        if 0 <= start < end:
            return text[start:end + 1]
    return None


# ---------------------------------------------------------------- fake mode

def _fake(task: str, user: str) -> dict[str, Any]:
    """Deterministic canned outputs so the whole pipeline is testable without a gateway key."""
    if task == "generate_questions":
        payload = json.loads(user)
        n = payload["n"]
        fmt = payload["format"]
        out = []
        for i in range(n):
            src = payload["chunks"][i % len(payload["chunks"])]
            off = (i * 97) % max(len(src["text"]) - 80, 1)
            snippet = src["text"][off:off + 70]
            base = {
                "format": fmt,
                "cognitive_level": payload.get("cognitive_level", "understand"),
                "citation_chunk_ids": [src["id"]],
                "difficulty": 0.5,
            }
            if fmt == "mcq":
                base.update(stem=f"[fake q{i}] Per the material: {snippet}…?",
                            options=["Correct per source", "Distractor A", "Distractor B", "Distractor C"],
                            correct_index=0,
                            explanation=f"Grounded in chunk {src['id']}.",
                            option_notes={"A": "Correct — per source.",
                                          "B": "Wrong — contradicts source.",
                                          "C": "Wrong — out of scope.",
                                          "D": "Wrong — misreads the rule."})
            elif fmt == "tf":
                base.update(statement=f"[fake q{i}] {src['text'][:60]} is accurate.", answer=True,
                            explanation="Per source.")
            elif fmt == "gap":
                base.update(text_with_gap=f"[fake q{i}] The key term here is ____.", answers=["term"],
                            explanation="Per source.")
            elif fmt == "match":
                base.update(left=["A1", "B1"], right=["A2", "B2"], pairs=[[0, 0], [1, 1]],
                            explanation="Per source.")
            elif fmt == "numeric":
                base.update(stem=f"[fake q{i}] Compute the value.", answer=42.0, tolerance=0.01,
                            unit="", explanation="Per source.")
            out.append(base)
        return {"questions": out}
    if task == "build_lesson":
        payload = json.loads(user)
        cites = [c["id"] for c in payload["chunks"][:3]]
        return {"title": f"Lesson: {payload['topic_title']}",
                "body": f"# {payload['topic_title']}\n\nKey points from your materials…",
                "citation_chunk_ids": cites}
    if task == "classify_document":
        return {"kind": "textbook"}
    if task == "infer_topic_tree":
        return {"topics": [{"code": "1", "title": "Inferred Topic 1", "weight": 1,
                            "cognitive_levels": ["understand"]}]}
    if task == "plan_rationale":
        return {"rationale": "Plan weights topics by exam weighting and your baseline weaknesses."}
    if task == "critique_question":
        payload = json.loads(user)
        stem = str(payload.get("question", {}).get("stem", ""))
        if "FAKE-FAIL" in stem:
            return {"verdict": "fail", "issues": ["fake: unsalvageable"], "revised": None}
        if "FAKE-REVISE" in stem:
            q = dict(payload["question"])
            q["stem"] = q["stem"].replace("FAKE-REVISE", "REVISED")
            return {"verdict": "revise", "issues": ["fake: reworded"], "revised": q}
        return {"verdict": "pass", "issues": [], "revised": None}
    if task == "build_flashcards":
        payload = json.loads(user)
        cards = []
        for i, ex in enumerate(payload.get("excerpts", [])[:6]):
            cards.append({"front": f"Fake cue {i}: what does the source say?",
                          "back": ex["text"][:80], "topic_code": ex["topic_code"]})
        return {"cards": cards}
    if task == "starter_topic_tree":
        payload = json.loads(user)
        if "Unknown" in payload.get("exam", ""):
            return {"elements": []}
        return {"elements": [
            {"code": "1", "title": "Foundations", "weight": 10, "children": [
                {"code": "1.1", "title": "Core concepts", "cognitive": "understand"},
                {"code": "1.2", "title": "Key processes", "cognitive": "apply"}]},
            {"code": "2", "title": "Practice", "weight": 8, "children": [
                {"code": "2.1", "title": "Applied scenarios", "cognitive": "analyze"}]},
        ]}
    if task == "starter_notes":
        payload = json.loads(user)
        return {"sections": [
            {"topic_code": t["code"],
             "notes": f"Starter notes for {t['title']}: key rules, definitions and "
                      f"distinctions a candidate must know about {t['title']}. " + "x" * 120}
            for t in payload.get("topics", [])]}
    if task == "explain_question":
        payload = json.loads(user)
        correct = payload.get("correct", "A")
        notes = {}
        for L in payload.get("options", {}):
            notes[L] = (f"Correct — matches the source material." if L == correct
                        else f"Wrong — option {L} misstates the rule per the source.")
        return {"explanation": "The correct answer follows directly from the cited source "
                               "passage on this topic (fake-mode explanation).",
                "option_notes": notes}
    if task == "rank_videos":
        payload = json.loads(user)
        return {"relevant_ids": [c["id"] for c in payload.get("candidates", [])][:2]}
    if task == "suggest_videos":
        return {"videos": [{"id": "fakevid00001"[:11], "title": "Fake topic video",
                            "channel": "FakeChan"}]}
    if task == "improve_lesson":
        payload = json.loads(user)
        return {"title": f"Improved: {payload['topic']}",
                "body": f"# {payload['topic']} (improved)\n\nSharper take with a common trap…"
                        + " " * 80}
    if task == "watch_check":
        return {"questions": [{"stem": "What did the video cover?", "options": ["The topic", "x", "y", "z"],
                               "correct_index": 0}]}
    raise LLMError(f"fake mode has no handler for task={task}")
