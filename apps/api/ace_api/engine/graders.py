"""Deterministic auto-graders per question format. Answer shapes (from the app):
mcq: {"index": int} · tf: {"value": bool} · gap: {"text": str} · match: {"pairs": [[i,j],...]}
numeric: {"value": float}
"""

from __future__ import annotations

import re


def grade(fmt: str, payload: dict, answer: dict) -> bool:
    try:
        if fmt == "mcq":
            return int(answer["index"]) == int(payload["correct_index"])
        if fmt == "tf":
            return bool(answer["value"]) == bool(payload["answer"])
        if fmt == "gap":
            given = _norm(str(answer["text"]))
            return any(given == _norm(str(a)) for a in payload["answers"])
        if fmt == "match":
            return {tuple(p) for p in answer["pairs"]} == {tuple(p) for p in payload["pairs"]}
        if fmt == "numeric":
            # tolerance is absolute, always — generation prompt specifies it in answer units
            return abs(float(answer["value"]) - float(payload["answer"])) <= float(
                payload.get("tolerance", 0))
    except (KeyError, TypeError, ValueError):
        return False
    return False


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
