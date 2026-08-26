"""CIRE (CIRO) seed-corpus parsers → the first exam accelerator.

Deterministic parsing of the three official PDFs; golden-tested against known facts:
9 elements, weights {11,11,17,6,9,13,21,6,16}, 110 practice questions with A–D keys.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ace_api.engine.pdf import extract_pages

EXAM_KEY = "cire-ciro-2025"
DISPLAY_NAME = "Canadian Investment Regulatory Exam (CIRE) — CIRO, Jan 2025"

COGNITIVE_VERBS = {"remember": "remember", "understand": "understand",
                   "apply": "apply", "analyze": "analyze", "analyse": "analyze"}


@dataclass
class Outcome:
    code: str
    title: str
    body: str
    cognitive: str


@dataclass
class Element:
    number: int
    title: str
    summary: str
    weight: int = 0
    outcomes: list[Outcome] = field(default_factory=list)


@dataclass
class Syllabus:
    elements: list[Element]
    total_questions: int
    duration_min: int
    attempts_allowed: int


@dataclass
class ExtractedQuestion:
    number: int
    item_id: str
    stem: str
    options: list[str]
    key: str  # A-D
    cognitive: str


# ------------------------------------------------------------------ syllabus

def parse_syllabus(path: str) -> Syllabus:
    pages = extract_pages(path)
    overview = next(p.text for p in pages if "Question weighting" in p.text)
    weights = _parse_weights(overview)

    m = re.search(r"Questions per exam\s*\n?\s*(\d+)", overview)
    total = int(m.group(1)) if m else 0
    m = re.search(r"Exam duration\s*\n?\s*(\d+)\s*hours?", overview)
    duration = int(m.group(1)) * 60 if m else 0
    m = re.search(r"Attempts allowed per exam\s*\n?\s*(\d+)", overview)
    attempts = int(m.group(1)) if m else 0

    elements: list[Element] = []
    for p in pages:
        if "A candidate should:" not in p.text:
            continue
        head = re.search(r"Element\s+(\d+):\s*([^\n]+)", p.text)
        if not head:
            continue
        num = int(head.group(1))
        el = Element(number=num, title=head.group(2).strip(), summary=_summary(p.text),
                     weight=weights.get(num, 0))
        el.outcomes = _parse_outcomes(p.text, num)
        elements.append(el)
    elements.sort(key=lambda e: e.number)
    return Syllabus(elements=elements, total_questions=total, duration_min=duration,
                    attempts_allowed=attempts)


def _parse_weights(overview: str) -> dict[int, int]:
    block = overview.split("Question weighting", 1)[1]
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    weights: dict[int, int] = {}
    current: int | None = None
    for ln in lines:
        m = re.match(r"^(\d)\s+\S", ln)
        if m and int(m.group(1)) == len(weights) + 1:
            current = int(m.group(1))
            continue
        if current is not None and re.fullmatch(r"\d{1,3}", ln):
            weights[current] = int(ln)
            current = None
    return weights


def _summary(text: str) -> str:
    m = re.search(r"Summary:\s*(.*?)\s*A candidate should:", text, re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _parse_outcomes(text: str, element_num: int) -> list[Outcome]:
    body = text.split("A candidate should:", 1)[1]
    marker = re.compile(rf"(?:^|\n)\s*{element_num}\.(\d{{1,2}})\s+")
    hits = list(marker.finditer(body))
    outcomes = []
    for i, h in enumerate(hits):
        seg = body[h.end(): hits[i + 1].start() if i + 1 < len(hits) else len(body)]
        seg = re.sub(r"\s+", " ", seg).strip()
        first_word = seg.split(" ", 1)[0].rstrip(".,:").lower() if seg else ""
        cognitive = COGNITIVE_VERBS.get(first_word, "understand")
        title = seg.split(". ", 1)[0][:220].rstrip(".")
        outcomes.append(Outcome(code=f"{element_num}.{h.group(1)}", title=title, body=seg,
                                cognitive=cognitive))
    return outcomes


# ------------------------------------------------------------- practice exam

_HEADER_RE = re.compile(r"CIRE Practice Exam[^\n]*\|\s*\d+\s*")
_ITEM_RE = re.compile(r"ITEM ID:\s*(CIRO_E_\d+)")
_OPTION_SPLIT = re.compile(r"\n([A-D])\.\s")


def parse_practice_exam(path: str) -> list[ExtractedQuestion]:
    text = "\n".join(p.text for p in extract_pages(path))
    text = _HEADER_RE.sub("", text)

    answers: dict[str, str] = dict(re.findall(r"ITEM ID:\s*(CIRO_E_\d+)\s*\n\s*KEY:\s*([A-D])", text))

    questions: list[ExtractedQuestion] = []
    hits = list(_ITEM_RE.finditer(text))
    for i, h in enumerate(hits):
        block = text[h.end(): hits[i + 1].start() if i + 1 < len(hits) else len(text)]
        if "KEY:" in block:
            continue  # answer-section entry
        item_id = h.group(1)
        m = re.match(r"\s*(\d{1,3})\.\s*", block)
        if not m:
            continue
        number = int(m.group(1))
        rest = block[m.end():]
        parts = _OPTION_SPLIT.split("\n" + rest)
        stem = re.sub(r"\s+", " ", parts[0]).strip()
        options = []
        for j in range(1, len(parts) - 1, 2):
            opt = re.sub(r"\s+", " ", parts[j + 1]).strip()
            # the answers-section title can bleed into the final option of the last page
            opt = re.split(r"Canadian Investment Regulatory Exam|Practice Exam\s*[–-]",
                           opt)[0].strip()
            options.append(opt)
        key = answers.get(item_id, "")
        questions.append(ExtractedQuestion(number=number, item_id=item_id, stem=stem,
                                           options=options[:4], key=key,
                                           cognitive=_classify_cognitive(stem)))
    questions.sort(key=lambda q: q.number)
    return questions


def _classify_cognitive(stem: str) -> str:
    s = stem.lower()
    words = len(stem.split())
    if re.search(r"\bcalculate|compute|what is the (impact|return|fee)\b", s):
        return "apply"
    if words > 45 or re.search(r"\b(best (illustrates|meets|indicates)|compared to|impact will)\b", s):
        return "analyze"
    if words > 22 or re.search(r"\b(must|should) (the |a |an )?\w+ (do|take)\b|to remain compliant|required course of action", s):
        return "apply"
    if re.search(r"^(what is|which of the following is|who is|what are)\b", s):
        return "remember"
    return "understand"


# ---------------------------------------------------------------- guidance

def parse_guidance(path: str) -> dict:
    pages = extract_pages(path)
    text = "\n".join(p.text for p in pages)
    return {"source": "CIRO Guidance for Studying (EN)", "pages": len(pages),
            "text": re.sub(r"[ \t]+", " ", text).strip()}


# ------------------------------------------------------------- profile build

def build_profile(syl: Syllabus, questions: list[ExtractedQuestion]) -> dict:
    total_w = sum(e.weight for e in syl.elements) or 1
    cog: dict[str, float] = {}
    for e in syl.elements:
        if not e.outcomes:
            continue
        share = e.weight / total_w
        per = share / len(e.outcomes)
        for o in e.outcomes:
            cog[o.cognitive] = cog.get(o.cognitive, 0.0) + per
    norm = sum(cog.values()) or 1
    cog = {k: round(v / norm, 4) for k, v in cog.items()}
    return {
        "format_mix": {"mcq": 1.0},
        "cognitive_mix": cog,
        "element_weights": {str(e.number): e.weight for e in syl.elements},
        "total_questions": syl.total_questions,
        "duration_min": syl.duration_min,
        "attempts_allowed": syl.attempts_allowed,
        "option_count": 4,
        "extracted_question_count": len(questions),
        "style_notes": "Single-best-answer MCQ, 4 options, no negative marking indicated.",
    }


def topic_tree_json(syl: Syllabus) -> list[dict]:
    tree = []
    for e in syl.elements:
        tree.append({
            "code": str(e.number), "title": e.title, "weight": e.weight, "summary": e.summary,
            "children": [{"code": o.code, "title": o.title, "body": o.body,
                          "cognitive_levels": [o.cognitive],
                          "weight": round(e.weight / max(len(e.outcomes), 1), 3)}
                         for o in e.outcomes],
        })
    return tree
