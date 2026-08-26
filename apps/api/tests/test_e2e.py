"""End-to-end journey through the HTTP API (fake LLM, hash embeddings, live Postgres).
Mirrors implementation-plan §6 'E2E smoke'."""

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from ace_api import db
from ace_api.main import app
from tests.conftest import GUIDANCE_PDF


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _auth(client) -> dict:
    email = f"e2e-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/auth/otp", json={"email": email})
    assert r.status_code == 200, r.text
    code = r.json()["dev_code"]
    r = client.post("/auth/verify", json={"email": email, "code": code})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_full_journey(client):
    h = _auth(client)

    # wrong OTP is rejected
    assert client.post("/auth/verify", json={"email": "x@example.com", "code": "000000"}).status_code == 401

    # create exam — free-text name matches the CIRE accelerator
    r = client.post("/exams", json={"name": "CIRE (Canadian Investment Regulatory Exam)",
                                    "exam_date": "2026-10-01", "weekly_hours": 6}, headers=h)
    assert r.status_code == 200, r.text
    exam_id = r.json()["exam_id"]
    assert r.json()["accelerator"] is not None

    # re-login finds the exam again (session restore path)
    r = client.get("/exams", headers=h)
    assert any(e["id"] == exam_id for e in r.json()["exams"])

    # exam is editable (date/hours); plan doesn't exist yet so no rebuild
    r = client.patch(f"/exams/{exam_id}", json={"exam_date": "2026-10-15", "weekly_hours": 7},
                     headers=h)
    assert r.status_code == 200 and r.json()["plan_rebuilt"] is False
    r = client.get(f"/exams/{exam_id}", headers=h)
    assert r.json()["exam_date"] == "2026-10-15" and r.json()["weekly_hours"] == 7

    # a second exam can coexist (multi-exam support)
    r = client.post("/exams", json={"name": "PMP", "exam_date": "2026-12-01",
                                    "weekly_hours": 4}, headers=h)
    assert r.status_code == 200
    r = client.get("/exams", headers=h)
    assert len(r.json()["exams"]) >= 2

    # upload a real PDF → background ingestion
    with open(GUIDANCE_PDF, "rb") as f:
        r = client.post(f"/exams/{exam_id}/documents",
                        files={"file": ("guidance.pdf", f, "application/pdf")}, headers=h)
    assert r.status_code == 200, r.text
    for _ in range(60):  # TestClient runs background tasks after response; poll for parsed
        r = client.get(f"/exams/{exam_id}/ingestion-status", headers=h)
        if all(d["parse_status"] == "parsed" for d in r.json()["documents"]):
            break
        time.sleep(0.2)
    assert all(d["parse_status"] == "parsed" for d in r.json()["documents"])

    # topic tree + profile present (accelerator: 9 elements + 93 outcomes)
    r = client.get(f"/exams/{exam_id}/topic-tree", headers=h)
    assert len(r.json()["topics"]) == 102
    r = client.get(f"/exams/{exam_id}/question-profile", headers=h)
    assert r.json()["profile"]["format_mix"] == {"mcq": 1.0}
    assert client.post(f"/exams/{exam_id}/confirm", headers=h).status_code == 200

    # diagnostic
    r = client.post(f"/exams/{exam_id}/diagnostic/start", headers=h)
    assert r.status_code == 200, r.text
    diag = r.json()
    assert diag["count"] >= 9
    qrows = [db_q for db_q in _fetch_questions(diag["question_ids"])]
    for q in qrows:  # answer ~60% correctly
        correct_idx = q["payload"]["correct_index"]
        idx = correct_idx if q["id"] % 5 < 3 else (correct_idx + 1) % 4
        r = client.post("/attempts", json={"exam_id": exam_id, "question_id": q["id"],
                                           "session_id": diag["session_id"],
                                           "answer": {"index": idx}, "confidence": "think"},
                        headers=h)
        assert r.status_code == 200
        assert r.json()["correct"] == (idx == correct_idx)
    r = client.post(f"/exams/{exam_id}/diagnostic/{diag['session_id']}/complete", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["plan"]["plan_id"]

    # plan exists, has items incl. mocks
    r = client.get(f"/exams/{exam_id}/plan", headers=h)
    plan = r.json()
    assert len(plan["items"]) > 10
    kinds = {i["kind"] for i in plan["items"]}
    assert {"learn", "mock"} <= kinds

    # start today's session (prepares on demand), answer everything, complete
    first_learn = next(i for i in plan["items"] if i["kind"] == "learn")
    r = client.post(f"/plan-items/{first_learn['id']}/session/start", headers=h)
    assert r.status_code == 200, r.text
    sess = r.json()
    assert sess["lesson"] is not None
    assert len(sess["questions"]) >= 3
    assert all("correct_index" not in q["payload"] for q in sess["questions"])  # answers never leak
    for q in sess["questions"]:
        r = client.post("/attempts", json={"exam_id": exam_id, "question_id": q["id"],
                                           "session_id": sess["session_id"],
                                           "answer": _some_answer(q), "confidence": "sure"}, headers=h)
        assert r.status_code == 200
    r = client.post(f"/sessions/{sess['session_id']}/complete", headers=h)
    assert r.status_code == 200
    assert r.json()["streak"]["current"] >= 1

    # readiness composite with signals
    r = client.get(f"/exams/{exam_id}/readiness", headers=h)
    ready = r.json()
    assert 0 < ready["composite"] < 1
    assert "accuracy" in ready["signals"]
    assert len(ready["topics"]) >= 9

    # mock exam: blueprint-faithful, submit scores per element
    r = client.post(f"/exams/{exam_id}/mocks/start", headers=h)
    assert r.status_code == 200, r.text
    mock = r.json()
    assert mock["count"] >= 50  # 110-weighted blueprint against available bank
    for q in mock["questions"][:30]:
        client.post("/attempts", json={"exam_id": exam_id, "question_id": q["id"],
                                       "mock_id": mock["mock_id"],
                                       "answer": {"index": 0}}, headers=h)
    r = client.post(f"/exams/{exam_id}/mocks/{mock['mock_id']}/submit", headers=h)
    assert r.status_code == 200
    assert 0 <= r.json()["score"] <= 1
    assert r.json()["per_element"]

    # gamification accumulated
    r = client.get("/me/gamify", headers=h)
    g = r.json()
    assert g["xp"] > 0
    assert any(b["key"] == "first_session" for b in g["badges"])
    assert any(b["key"] == "first_mock" for b in g["badges"])

    # model picker
    r = client.get("/models", headers=h)
    assert {m["id"] for m in r.json()["models"]} == {"opus-4.8", "fable-5", "gpt-5.5", "gpt-5.6"}
    r = client.put("/me/model", json={"model_id": "fable-5"}, headers=h)
    assert r.json()["selected"] == "fable-5"
    assert client.put("/me/model", json={"model_id": "bogus"}, headers=h).status_code == 400

    # question report → kill after threshold
    qid = sess["questions"][0]["id"]
    client.post(f"/questions/{qid}/report", json={"reason": "test"}, headers=h)
    r = client.post(f"/questions/{qid}/report", json={"reason": "test2"}, headers=h)
    assert r.json()["question_status"] == "killed"


def _fetch_questions(qids):
    import psycopg
    from psycopg.rows import dict_row

    from ace_api.config import settings

    with psycopg.connect(settings().database_url, row_factory=dict_row) as c:
        return c.execute("SELECT id, payload FROM questions WHERE id = ANY(%s)", (qids,)).fetchall()


def _some_answer(q):
    fmt = q["format"]
    if fmt == "mcq":
        return {"index": 0}
    if fmt == "tf":
        return {"value": True}
    if fmt == "gap":
        return {"text": "term"}
    if fmt == "match":
        return {"pairs": [[0, 0], [1, 1]]}
    return {"value": 42.0}


def test_auth_required(client):
    assert client.get("/models").status_code in (401, 403)
    assert client.post("/exams", json={"name": "X"}).status_code in (401, 403)
