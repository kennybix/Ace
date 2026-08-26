"""Extensive hardening sweep: no endpoint may 500 on weird states; cross-user and
cross-exam linkage is impossible; double submissions never double-award."""

import uuid

import pytest
from fastapi.testclient import TestClient

from ace_api.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _auth(client):
    email = f"hd-{uuid.uuid4().hex[:8]}@example.com"
    code = client.post("/auth/otp", json={"email": email}).json()["dev_code"]
    token = client.post("/auth/verify", json={"email": email, "code": code}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_empty_exam_never_500s(client):
    """A materials-less unknown exam ('PMP' fresh): every endpoint answers 2xx/4xx, never 5xx."""
    h = _auth(client)
    exam_id = client.post("/exams", json={"name": "Fresh Unknown Cert",
                                          "exam_date": "2026-12-01"}, headers=h).json()["exam_id"]
    client.post(f"/exams/{exam_id}/confirm", headers=h)
    calls = [
        ("GET", f"/exams/{exam_id}"),
        ("GET", f"/exams/{exam_id}/topic-tree"),
        ("GET", f"/exams/{exam_id}/question-profile"),
        ("GET", f"/exams/{exam_id}/sources"),
        ("GET", f"/exams/{exam_id}/readiness"),
        ("GET", f"/exams/{exam_id}/plan"),
        ("GET", f"/exams/{exam_id}/plan/today"),
        ("GET", f"/exams/{exam_id}/plan/next"),
        ("POST", f"/exams/{exam_id}/plan/rebuild"),
        ("POST", f"/exams/{exam_id}/diagnostic/start"),
        ("POST", f"/exams/{exam_id}/mocks/start"),
        ("POST", f"/exams/{exam_id}/enrich-explanations"),
        ("DELETE", f"/exams/{exam_id}/preloaded-questions"),
        ("POST", f"/exams/{exam_id}/preloaded-questions/restore"),
    ]
    for method, path in calls:
        r = client.request(method, path, headers=h)
        assert r.status_code < 500, f"{method} {path} -> {r.status_code}: {r.text[:120]}"


def test_past_exam_date_is_clear_error(client):
    h = _auth(client)
    exam_id = client.post("/exams", json={"name": "CIRE", "exam_date": "2020-01-01"},
                          headers=h).json()["exam_id"]
    r = client.post(f"/exams/{exam_id}/plan/rebuild", headers=h)
    assert r.status_code == 400
    assert "past" in r.json()["detail"]


def _cire_with_diag(client, h):
    exam_id = client.post("/exams", json={"name": "CIRE", "exam_date": "2026-10-20",
                                          "weekly_hours": 7}, headers=h).json()["exam_id"]
    client.post(f"/exams/{exam_id}/confirm", headers=h)
    d = client.post(f"/exams/{exam_id}/diagnostic/start", headers=h).json()
    return exam_id, d


def test_cross_user_linkage_impossible(client):
    ha = _auth(client)
    exam_a, da = _cire_with_diag(client, ha)
    hb = _auth(client)
    exam_b, db_ = _cire_with_diag(client, hb)

    qa = da["question_ids"][0]
    # B cannot report A's question, fetch its payload, or link attempts to A's session
    assert client.post(f"/questions/{qa}/report", json={"reason": "x"},
                       headers=hb).status_code == 404
    got = client.post("/questions/batch", json={"ids": [qa]}, headers=hb).json()["questions"]
    assert got == []
    r = client.post("/attempts", json={"exam_id": exam_b, "question_id": db_["question_ids"][0],
                                       "session_id": da["session_id"],
                                       "answer": {"index": 0}}, headers=hb)
    assert r.status_code == 400  # A's session id rejected
    # B cannot open A's session
    assert client.post(f"/sessions/{da['session_id']}/open", headers=hb).status_code == 404


def test_mock_resubmit_never_double_awards(client):
    h = _auth(client)
    exam_id, d = _cire_with_diag(client, h)
    for qid in d["question_ids"]:
        client.post("/attempts", json={"exam_id": exam_id, "question_id": qid,
                                       "session_id": d["session_id"],
                                       "answer": {"index": 0}}, headers=h)
    client.post(f"/exams/{exam_id}/diagnostic/{d['session_id']}/complete", headers=h)
    m = client.post(f"/exams/{exam_id}/mocks/start", headers=h).json()
    for q in m["questions"][:5]:
        client.post("/attempts", json={"exam_id": exam_id, "question_id": q["id"],
                                       "mock_id": m["mock_id"], "answer": {"index": 0}},
                    headers=h)
    client.post(f"/exams/{exam_id}/mocks/{m['mock_id']}/submit", headers=h)
    xp1 = client.get("/me/gamify", headers=h).json()["xp"]
    client.post(f"/exams/{exam_id}/mocks/{m['mock_id']}/submit", headers=h)
    xp2 = client.get("/me/gamify", headers=h).json()["xp"]
    assert xp1 == xp2
