"""Golden tests for the CIRE accelerator parsers (implementation plan tasks 0.4–0.6)."""

from ace_api.engine import cire
from tests.conftest import GUIDANCE_PDF, PRACTICE_PDF, SYLLABUS_PDF

EXPECTED_WEIGHTS = {1: 11, 2: 11, 3: 17, 4: 6, 5: 9, 6: 13, 7: 21, 8: 6, 9: 16}


def test_syllabus_elements_and_weights():
    syl = cire.parse_syllabus(SYLLABUS_PDF)
    assert len(syl.elements) == 9
    assert {e.number: e.weight for e in syl.elements} == EXPECTED_WEIGHTS
    assert sum(e.weight for e in syl.elements) == 110
    assert syl.total_questions == 110
    assert syl.duration_min == 120
    assert syl.attempts_allowed == 3


def test_syllabus_outcomes():
    syl = cire.parse_syllabus(SYLLABUS_PDF)
    by_num = {e.number: e for e in syl.elements}
    assert len(by_num[1].outcomes) == 11  # 1.1–1.11 seen in the source
    assert len(by_num[3].outcomes) == 17  # 3.1–3.17 seen in the source
    for e in syl.elements:
        assert len(e.outcomes) >= 3, f"element {e.number} has too few outcomes"
        assert e.summary
        for o in e.outcomes:
            assert o.code.startswith(f"{e.number}.")
            assert o.cognitive in {"remember", "understand", "apply", "analyze"}
            assert len(o.title) > 10


def test_practice_exam_extraction_complete():
    qs = cire.parse_practice_exam(PRACTICE_PDF)
    assert len(qs) == 110
    assert [q.number for q in qs] == list(range(1, 111))
    assert len({q.item_id for q in qs}) == 110
    for q in qs:
        assert len(q.options) == 4, f"Q{q.number} has {len(q.options)} options"
        assert q.key in "ABCD", f"Q{q.number} missing answer key"
        assert len(q.stem) > 15
        assert all(len(o) > 1 for o in q.options)
        assert q.cognitive in {"remember", "understand", "apply", "analyze"}
        for o in q.options:  # section headers must never bleed into option text
            assert "Practice Exam" not in o and "Regulatory Exam" not in o, \
                f"Q{q.number} contaminated option: {o[:80]}"


def test_known_practice_items_verbatim():
    qs = {q.item_id: q for q in cire.parse_practice_exam(PRACTICE_PDF)}
    q1 = qs["CIRO_E_000017"]
    assert q1.number == 1
    assert q1.stem == "Which of the following statements is true?"
    assert q1.options[2].startswith("When an Investment Dealer arranges the execution")
    q2 = qs["CIRO_E_000025"]
    assert "Canadian Investor Protection Fund" in q2.stem
    # keys from the answer section
    assert qs["CIRO_E_000696"].key == "C"
    assert qs["CIRO_E_000698"].key == "A"


def test_profile_and_tree():
    syl = cire.parse_syllabus(SYLLABUS_PDF)
    qs = cire.parse_practice_exam(PRACTICE_PDF)
    profile = cire.build_profile(syl, qs)
    assert profile["format_mix"] == {"mcq": 1.0}
    assert abs(sum(profile["cognitive_mix"].values()) - 1.0) < 0.01
    assert profile["element_weights"]["7"] == 21
    tree = cire.topic_tree_json(syl)
    assert len(tree) == 9
    assert sum(len(t["children"]) for t in tree) >= 80


def test_guidance_parses():
    g = cire.parse_guidance(GUIDANCE_PDF)
    assert g["pages"] == 11
    assert len(g["text"]) > 1000
