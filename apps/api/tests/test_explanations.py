"""Why-right/why-wrong explanations + element-hinted volume ingestion."""

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from ace_api.main import app

from tests.conftest import RESOURCES

E1_PDF = str(RESOURCES / "CIRE_Element_1_Canadian_Securities_Regulatory_Framework.pdf")

pytestmark = pytest.mark.skipif(not __import__("pathlib").Path(E1_PDF).exists(),
                                reason="CIRE corpus not present (bring your own)")


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _auth(client):
    email = f"ex-{uuid.uuid4().hex[:8]}@example.com"
    code = client.post("/auth/otp", json={"email": email}).json()["dev_code"]
    token = client.post("/auth/verify", json={"email": email, "code": code}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _cire_with_e1(client, h) -> int:
    exam_id = client.post("/exams", json={"name": "CIRE", "exam_date": "2026-10-20",
                                          "weekly_hours": 5}, headers=h).json()["exam_id"]
    with open(E1_PDF, "rb") as f:
        client.post(f"/exams/{exam_id}/documents",
                    files={"file": ("CIRE_Element_1_Framework.pdf", f, "application/pdf")},
                    headers=h)
    for _ in range(60):
        st = client.get(f"/exams/{exam_id}/ingestion-status", headers=h).json()
        if all(d["parse_status"] == "parsed" for d in st["documents"]):
            break
        time.sleep(0.2)
    return exam_id


def test_element_hint_maps_volume_into_element_subtree(client):
    import psycopg
    from psycopg.rows import dict_row

    from ace_api.config import settings

    h = _auth(client)
    exam_id = _cire_with_e1(client, h)
    with psycopg.connect(settings().database_url, row_factory=dict_row) as db:
        rows = db.execute(
            """SELECT t.code FROM chunks c JOIN topics t ON t.id=c.topic_id
               WHERE c.exam_id=%s AND c.topic_id IS NOT NULL""", (exam_id,)).fetchall()
    assert rows, "volume chunks were not mapped"
    in_e1 = sum(1 for r in rows if r["code"].startswith("1"))
    assert in_e1 / len(rows) == 1.0  # every chunk of an Element-1 volume lands in element 1


def test_enrichment_adds_why_right_and_why_wrong(client):
    import psycopg
    from psycopg.rows import dict_row

    from ace_api.config import settings

    h = _auth(client)
    exam_id = _cire_with_e1(client, h)
    r = client.post(f"/exams/{exam_id}/enrich-explanations?limit=3", headers=h).json()
    assert r["enriched"] == 3
    with psycopg.connect(settings().database_url, row_factory=dict_row) as db:
        q = db.execute(
            """SELECT payload FROM questions WHERE exam_id=%s AND source='extracted'
               AND payload->'option_notes' IS NOT NULL LIMIT 1""", (exam_id,)).fetchone()
    assert q is not None
    notes = q["payload"]["option_notes"]
    assert set(notes) == {"A", "B", "C", "D"}
    correct_letter = "ABCD"[q["payload"]["correct_index"]]
    assert notes[correct_letter].startswith("Correct")
    assert q["payload"]["explanation"] != "Official CIRO practice exam item."


def test_reveal_returns_notes_but_serving_never_leaks_them(client):
    h = _auth(client)
    exam_id = _cire_with_e1(client, h)
    for _ in range(5):
        r = client.post(f"/exams/{exam_id}/enrich-explanations?limit=40", headers=h).json()
        if r["remaining"] == 0:
            break
    assert r["remaining"] == 0
    d = client.post(f"/exams/{exam_id}/diagnostic/start", headers=h).json()
    qs = client.post("/questions/batch", json={"ids": d["question_ids"][:5]},
                     headers=h).json()["questions"]
    for q in qs:
        assert "option_notes" not in q["payload"]  # never before answering
    r = client.post("/attempts", json={"exam_id": exam_id, "question_id": qs[0]["id"],
                                       "session_id": d["session_id"],
                                       "answer": {"index": 1}}, headers=h).json()
    assert "option_notes" in r and set(r["option_notes"]) == {"A", "B", "C", "D"}
