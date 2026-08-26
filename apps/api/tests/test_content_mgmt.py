"""Content-management: browsable topic tree, visible sources, removable preloaded pack,
document deletion with grounding cleanup."""

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from ace_api.main import app
from tests.conftest import GUIDANCE_PDF


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _auth(client):
    email = f"cm-{uuid.uuid4().hex[:8]}@example.com"
    code = client.post("/auth/otp", json={"email": email}).json()["dev_code"]
    token = client.post("/auth/verify", json={"email": email, "code": code}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _mkexam(client, h) -> int:
    r = client.post("/exams", json={"name": "CIRE", "exam_date": "2026-10-01",
                                    "weekly_hours": 5}, headers=h)
    return r.json()["exam_id"]


def test_topic_tree_is_browsable_with_counts(client):
    h = _auth(client)
    exam_id = _mkexam(client, h)
    r = client.get(f"/exams/{exam_id}/topic-tree", headers=h)
    topics = r.json()["topics"]
    assert len(topics) == 102
    parents = [t for t in topics if t["parent_id"] is None]
    assert len(parents) == 9
    # real questions are attached and visible per topic
    assert sum(t["question_count"] for t in topics) >= 110
    assert all("mastery" in t and "attempts" in t for t in topics)


def test_sources_lists_preloaded_pack_and_uploads(client):
    h = _auth(client)
    exam_id = _mkexam(client, h)
    r = client.get(f"/exams/{exam_id}/sources", headers=h)
    src = r.json()
    assert src["preloaded"] is not None
    assert src["preloaded"]["active_questions"] == 110
    assert src["preloaded"]["topics"] == 102
    assert "CIRO" in src["preloaded"]["provenance"] or "CIRE" in src["preloaded"]["name"]

    with open(GUIDANCE_PDF, "rb") as f:
        client.post(f"/exams/{exam_id}/documents",
                    files={"file": ("guidance.pdf", f, "application/pdf")}, headers=h)
    for _ in range(50):
        docs = client.get(f"/exams/{exam_id}/sources", headers=h).json()["documents"]
        if docs and all(d["parse_status"] == "parsed" for d in docs):
            break
        time.sleep(0.2)
    assert docs[0]["chunks"] > 0


def test_preloaded_pack_remove_and_restore(client):
    h = _auth(client)
    exam_id = _mkexam(client, h)
    r = client.delete(f"/exams/{exam_id}/preloaded-questions", headers=h)
    assert r.json()["removed"] == 110
    src = client.get(f"/exams/{exam_id}/sources", headers=h).json()
    assert src["preloaded"]["active_questions"] == 0
    assert src["preloaded"]["removed_questions"] == 110
    # diagnostic can't run on an empty environment — correct failure, not silence
    assert client.post(f"/exams/{exam_id}/diagnostic/start", headers=h).status_code == 400

    r = client.post(f"/exams/{exam_id}/preloaded-questions/restore", headers=h)
    assert r.json()["restored"] == 110
    src = client.get(f"/exams/{exam_id}/sources", headers=h).json()
    assert src["preloaded"]["active_questions"] == 110


def test_document_delete_cleans_grounded_content(client):
    h = _auth(client)
    exam_id = _mkexam(client, h)
    with open(GUIDANCE_PDF, "rb") as f:
        doc_id = client.post(f"/exams/{exam_id}/documents",
                             files={"file": ("guidance.pdf", f, "application/pdf")},
                             headers=h).json()["document_id"]
    for _ in range(50):
        st = client.get(f"/exams/{exam_id}/ingestion-status", headers=h).json()
        if all(d["parse_status"] == "parsed" for d in st["documents"]):
            break
        time.sleep(0.2)

    r = client.delete(f"/exams/{exam_id}/documents/{doc_id}", headers=h)
    body = r.json()
    assert body["deleted"] is True
    assert body["chunks_removed"] > 0
    src = client.get(f"/exams/{exam_id}/sources", headers=h).json()
    assert src["documents"] == []
