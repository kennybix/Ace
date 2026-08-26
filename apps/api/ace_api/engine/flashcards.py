"""Flashcard decks for active recall — built from the exam's weakest topics, grounded in
the same chunks as everything else. Stored as a lessons row (kind='flashcard_deck')."""

from __future__ import annotations

import json

from ace_api import db
from ace_api.llm.client import chat_json

DECK_SYSTEM = """Output ONLY a JSON object. You write active-recall flashcards from source
excerpts. Reply {"cards": [{"front": str, "back": str, "topic_code": str}]} — 10 to 14 cards.
front: a precise cue or question (a definition to give, a threshold to state, a distinction
to make). back: the tight, complete answer with the exact rule/number from the source.
No fluff, no "see source". Every fact must come from the excerpts."""


async def build_deck(exam_id: int, model_id: str | None = None) -> dict:
    # weakest attempted topics first, else heaviest topics — 4 topics, 3 chunks each
    topics = await db.fetch_all(
        """SELECT t.id, t.code, t.title, COALESCE(m.rating, 1.0) AS rating
           FROM topics t LEFT JOIN mastery m ON m.topic_id=t.id AND m.exam_id=t.exam_id
           WHERE t.exam_id=%s AND t.parent_id IS NOT NULL
           ORDER BY (m.rating IS NULL), m.rating ASC, t.weight DESC LIMIT 4""", (exam_id,))
    excerpts = []
    for t in topics:
        rows = await db.fetch_all(
            "SELECT text FROM chunks WHERE exam_id=%s AND topic_id=%s LIMIT 3",
            (exam_id, t["id"]))
        for r in rows:
            excerpts.append({"topic_code": t["code"], "text": r["text"][:1500]})
    if not excerpts:
        rows = await db.fetch_all("SELECT text FROM chunks WHERE exam_id=%s LIMIT 10",
                                  (exam_id,))
        excerpts = [{"topic_code": topics[0]["code"] if topics else "?",
                     "text": r["text"][:1500]} for r in rows]
    if not excerpts:
        return {"error": "no source material for flashcards — add materials in the Library"}

    out = await chat_json("build_flashcards", DECK_SYSTEM,
                          json.dumps({"topics": [{"code": t["code"], "title": t["title"]}
                                                 for t in topics],
                                      "excerpts": excerpts}),
                          model_id=model_id, temperature=0.4, max_tokens=6000)
    cards = out.get("cards", []) if isinstance(out, dict) else []
    cards = [{"front": str(c.get("front", ""))[:300], "back": str(c.get("back", ""))[:500],
              "topic_code": str(c.get("topic_code", ""))[:10]}
             for c in cards if c.get("front") and c.get("back")][:14]
    if len(cards) < 4:
        return {"error": "couldn't build a solid deck — try again"}
    row = await db.fetch_one(
        """INSERT INTO lessons (exam_id, kind, body, citations, model_id, prompt_version)
           VALUES (%s,'flashcard_deck',%s,'[]',%s,'v1') RETURNING id""",
        (exam_id, json.dumps(cards), model_id or "default"))
    return {"deck_id": row["id"], "cards": cards}


async def get_or_build_deck(exam_id: int, rebuild: bool = False,
                            model_id: str | None = None) -> dict:
    if not rebuild:
        row = await db.fetch_one(
            """SELECT id, body FROM lessons WHERE exam_id=%s AND kind='flashcard_deck'
               ORDER BY id DESC LIMIT 1""", (exam_id,))
        if row:
            return {"deck_id": row["id"], "cards": json.loads(row["body"]), "cached": True}
    return await build_deck(exam_id, model_id)
