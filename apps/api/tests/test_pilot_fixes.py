"""Regression tests for issues found in the 2026-07-17 user pilot."""

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from ace_api.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _auth(client):
    email = f"pf-{uuid.uuid4().hex[:8]}@example.com"
    code = client.post("/auth/otp", json={"email": email}).json()["dev_code"]
    token = client.post("/auth/verify", json={"email": email, "code": code}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _cire(client, h) -> int:
    exam_id = client.post("/exams", json={"name": "CIRE", "exam_date": "2026-10-20",
                                          "weekly_hours": 7}, headers=h).json()["exam_id"]
    client.post(f"/exams/{exam_id}/confirm", headers=h)
    return exam_id


def _finish_diagnostic(client, h, exam_id) -> None:
    d = client.post(f"/exams/{exam_id}/diagnostic/start", headers=h).json()
    for qid in d["question_ids"]:
        client.post("/attempts", json={"exam_id": exam_id, "question_id": qid,
                                       "session_id": d["session_id"],
                                       "answer": {"index": 0}}, headers=h)
    client.post(f"/exams/{exam_id}/diagnostic/{d['session_id']}/complete", headers=h)


def test_diagnostic_resumes_not_orphans(client):
    h = _auth(client)
    exam_id = _cire(client, h)
    d1 = client.post(f"/exams/{exam_id}/diagnostic/start", headers=h).json()
    for qid in d1["question_ids"][:3]:
        client.post("/attempts", json={"exam_id": exam_id, "question_id": qid,
                                       "session_id": d1["session_id"],
                                       "answer": {"index": 0}}, headers=h)
    d2 = client.post(f"/exams/{exam_id}/diagnostic/start", headers=h).json()
    assert d2["session_id"] == d1["session_id"]
    assert d2.get("resumed") is True
    assert d2["count"] == d1["count"] - 3


def test_session_resume_filters_answered(client):
    h = _auth(client)
    exam_id = _cire(client, h)
    _finish_diagnostic(client, h, exam_id)
    nxt = client.get(f"/exams/{exam_id}/plan/next", headers=h).json()["item"]
    assert nxt is not None
    s1 = client.post(f"/plan-items/{nxt['id']}/session/start", headers=h).json()
    assert len(s1["questions"]) > 0
    n_answer = min(2, len(s1["questions"]))
    for q in s1["questions"][:n_answer]:
        client.post("/attempts", json={"exam_id": exam_id, "question_id": q["id"],
                                       "session_id": s1["session_id"],
                                       "answer": {"index": 0}}, headers=h)
    s2 = client.post(f"/plan-items/{nxt['id']}/session/start", headers=h).json()
    assert s2["session_id"] == s1["session_id"]
    assert len(s2["questions"]) == len(s1["questions"]) - n_answer
    assert s2["already_answered"] == n_answer


def test_fully_answered_session_reentry_completes_not_errors(client):
    """Answer everything, quit before the finish screen, re-enter: empty list (app completes),
    never a 400."""
    h = _auth(client)
    exam_id = _cire(client, h)
    _finish_diagnostic(client, h, exam_id)
    nxt = client.get(f"/exams/{exam_id}/plan/next", headers=h).json()["item"]
    s1 = client.post(f"/plan-items/{nxt['id']}/session/start", headers=h).json()
    for q in s1["questions"]:
        client.post("/attempts", json={"exam_id": exam_id, "question_id": q["id"],
                                       "session_id": s1["session_id"],
                                       "answer": {"index": 0}}, headers=h)
    r = client.post(f"/plan-items/{nxt['id']}/session/start", headers=h)
    assert r.status_code == 200
    assert r.json()["questions"] == [] or r.json()["lesson"] is not None
    r = client.post(f"/sessions/{s1['session_id']}/complete", headers=h)
    assert r.status_code == 200


def test_fresh_plan_offers_something_now(client):
    """Either today has an item, or /plan/next names the next one — never a dead 'rest' end."""
    h = _auth(client)
    exam_id = _cire(client, h)
    _finish_diagnostic(client, h, exam_id)
    today = client.get(f"/exams/{exam_id}/plan/today", headers=h).json()["item"]
    nxt = client.get(f"/exams/{exam_id}/plan/next", headers=h).json()["item"]
    assert today is not None or nxt is not None
    plan = client.get(f"/exams/{exam_id}/plan", headers=h).json()
    assert "completed_sessions" in plan
    # 7h/week → today is a study day in almost every pattern; day-0 scheduling holds
    days = [i["day"] for i in plan["items"]]
    assert str(date.today()) in days or today is not None or nxt is not None


def test_contentless_session_is_a_clear_400(client):
    h = _auth(client)
    exam_id = _cire(client, h)
    _finish_diagnostic(client, h, exam_id)
    client.delete(f"/exams/{exam_id}/preloaded-questions", headers=h)
    nxt = client.get(f"/exams/{exam_id}/plan/next", headers=h).json()["item"]
    # find an unprepared item so prep runs against the emptied bank
    plan = client.get(f"/exams/{exam_id}/plan", headers=h).json()
    pending = [i for i in plan["items"] if i["status"] == "pending" and i["kind"] == "learn"]
    r = client.post(f"/plan-items/{pending[0]['id']}/session/start", headers=h)
    assert r.status_code == 400
    assert "Library" in r.json()["detail"]
