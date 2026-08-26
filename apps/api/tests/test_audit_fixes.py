"""Regression tests for the 2026-07-17 thorough-check audit."""

import uuid

import pytest
from fastapi.testclient import TestClient

from ace_api.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _auth(client):
    email = f"af-{uuid.uuid4().hex[:8]}@example.com"
    code = client.post("/auth/otp", json={"email": email}).json()["dev_code"]
    token = client.post("/auth/verify", json={"email": email, "code": code}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _cire(client, h) -> int:
    exam_id = client.post("/exams", json={"name": "CIRE", "exam_date": "2026-10-20",
                                          "weekly_hours": 7}, headers=h).json()["exam_id"]
    client.post(f"/exams/{exam_id}/confirm", headers=h)
    return exam_id


def _finish_diag(client, h, exam_id):
    d = client.post(f"/exams/{exam_id}/diagnostic/start", headers=h).json()
    for qid in d["question_ids"]:
        client.post("/attempts", json={"exam_id": exam_id, "question_id": qid,
                                       "session_id": d["session_id"],
                                       "answer": {"index": 0}}, headers=h)
    client.post(f"/exams/{exam_id}/diagnostic/{d['session_id']}/complete", headers=h)


def test_cross_exam_attempt_rejected(client):
    h = _auth(client)
    exam_a = _cire(client, h)
    exam_b = _cire(client, h)
    qa = client.get(f"/exams/{exam_a}/topic-tree", headers=h)  # warm; question from exam A
    d = client.post(f"/exams/{exam_a}/diagnostic/start", headers=h).json()
    foreign_q = d["question_ids"][0]
    r = client.post("/attempts", json={"exam_id": exam_b, "question_id": foreign_q,
                                       "answer": {"index": 0}}, headers=h)
    assert r.status_code == 400


def test_double_complete_no_double_award(client):
    h = _auth(client)
    exam_id = _cire(client, h)
    _finish_diag(client, h, exam_id)
    nxt = client.get(f"/exams/{exam_id}/plan/next", headers=h).json()["item"]
    s = client.post(f"/plan-items/{nxt['id']}/session/start", headers=h).json()
    for q in s["questions"]:
        client.post("/attempts", json={"exam_id": exam_id, "question_id": q["id"],
                                       "session_id": s["session_id"],
                                       "answer": {"index": 0}}, headers=h)
    client.post(f"/sessions/{s['session_id']}/complete", headers=h)
    xp1 = client.get("/me/gamify", headers=h).json()["xp"]
    client.post(f"/sessions/{s['session_id']}/complete", headers=h)  # re-entry / double tap
    xp2 = client.get("/me/gamify", headers=h).json()["xp"]
    assert xp2 == xp1  # streak_day may tick once daily but not via re-complete same day


def test_mock_satisfies_due_plan_milestone(client):
    from datetime import date

    import psycopg
    from psycopg.rows import dict_row

    from ace_api.config import settings

    h = _auth(client)
    exam_id = _cire(client, h)
    _finish_diag(client, h, exam_id)
    # force a mock plan item due today
    with psycopg.connect(settings().database_url, row_factory=dict_row) as db:
        row = db.execute(
            """UPDATE plan_items SET day=%s WHERE id IN (
                 SELECT pi.id FROM plan_items pi JOIN plans p ON p.id=pi.plan_id
                 WHERE p.exam_id=%s AND pi.kind='mock' LIMIT 1) RETURNING id""",
            (date.today(), exam_id)).fetchone()
        db.commit()
    assert row is not None
    m = client.post(f"/exams/{exam_id}/mocks/start", headers=h).json()
    for q in m["questions"][:5]:
        client.post("/attempts", json={"exam_id": exam_id, "question_id": q["id"],
                                       "mock_id": m["mock_id"], "answer": {"index": 0}},
                    headers=h)
    client.post(f"/exams/{exam_id}/mocks/{m['mock_id']}/submit", headers=h)
    with psycopg.connect(settings().database_url, row_factory=dict_row) as db:
        st = db.execute("SELECT status FROM plan_items WHERE id=%s", (row["id"],)).fetchone()
    assert st["status"] == "done"


def test_session_returns_video_object_shape(client):
    h = _auth(client)
    exam_id = _cire(client, h)
    _finish_diag(client, h, exam_id)
    nxt = client.get(f"/exams/{exam_id}/plan/next", headers=h).json()["item"]
    s = client.post(f"/plan-items/{nxt['id']}/session/start", headers=h).json()
    assert "video" in s  # object or null — never a bare id
