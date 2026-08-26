"""Topics as destinations: detail, on-demand lesson, keyless video curation, ad-hoc drill."""

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
    email = f"td-{uuid.uuid4().hex[:8]}@example.com"
    code = client.post("/auth/otp", json={"email": email}).json()["dev_code"]
    token = client.post("/auth/verify", json={"email": email, "code": code}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _cire_with_material(client, h) -> int:
    exam_id = client.post("/exams", json={"name": "CIRE", "exam_date": "2026-10-20",
                                          "weekly_hours": 5}, headers=h).json()["exam_id"]
    with open(GUIDANCE_PDF, "rb") as f:
        client.post(f"/exams/{exam_id}/documents",
                    files={"file": ("g.pdf", f, "application/pdf")}, headers=h)
    for _ in range(50):
        st = client.get(f"/exams/{exam_id}/ingestion-status", headers=h).json()
        if all(d["parse_status"] == "parsed" for d in st["documents"]):
            break
        time.sleep(0.2)
    return exam_id


def _some_topic(client, h, exam_id) -> int:
    topics = client.get(f"/exams/{exam_id}/topic-tree", headers=h).json()["topics"]
    return next(t["id"] for t in topics if t["parent_id"] is not None
                and t["question_count"] > 0)


def test_topic_detail_lesson_and_drill(client):
    h = _auth(client)
    exam_id = _cire_with_material(client, h)
    tid = _some_topic(client, h, exam_id)

    d = client.get(f"/topics/{tid}", headers=h).json()
    assert d["question_count"] > 0 and d["lesson"] is None

    # on-demand lesson gets written, then reused
    l1 = client.post(f"/topics/{tid}/lesson", headers=h).json()
    assert l1["created"] is True and len(l1["body"]) > 20
    l2 = client.post(f"/topics/{tid}/lesson", headers=h).json()
    assert l2["created"] is False and l2["lesson_id"] == l1["lesson_id"]
    assert client.get(f"/topics/{tid}", headers=h).json()["lesson"] is not None

    # ad-hoc drill session opens and serves questions
    drill = client.post(f"/topics/{tid}/drill", headers=h).json()
    assert drill["count"] > 0
    s = client.post(f"/sessions/{drill['session_id']}/open", headers=h).json()
    assert len(s["questions"]) == drill["count"]


def test_keyless_video_curation_validates_via_oembed(client, monkeypatch):
    from ace_api.jobs import videos as vids

    async def fake_oembed(youtube_id):
        return {"title": "Canadian securities regulatory framework explained",
                "author_name": "FinanceChan"}

    async def no_data_api(exam_id, topic_id):
        return 0  # force the keyless path regardless of env key

    monkeypatch.setattr(vids, "_oembed", fake_oembed)
    monkeypatch.setattr(vids, "curate_topic", no_data_api)
    h = _auth(client)
    exam_id = _cire_with_material(client, h)
    topics = client.get(f"/exams/{exam_id}/topic-tree", headers=h).json()["topics"]
    tid = next(t["id"] for t in topics if t["parent_id"] is None and "regulatory" in
               t["title"].lower())

    v1 = client.post(f"/topics/{tid}/video", headers=h).json()
    assert v1["video"] is not None and v1["created"] is True
    assert v1["video"]["youtube_id"] == "fakevid0000"[:11]
    v2 = client.post(f"/topics/{tid}/video", headers=h).json()
    assert v2["created"] is False  # cached, not re-curated


def test_dead_video_ids_filtered(client, monkeypatch):
    from ace_api.jobs import videos as vids

    async def dead_oembed(youtube_id):
        return None  # video does not exist

    async def no_data_api(exam_id, topic_id):
        return 0

    monkeypatch.setattr(vids, "_oembed", dead_oembed)
    monkeypatch.setattr(vids, "curate_topic", no_data_api)
    h = _auth(client)
    exam_id = _cire_with_material(client, h)
    tid = _some_topic(client, h, exam_id)
    v = client.post(f"/topics/{tid}/video", headers=h).json()
    assert v["video"] is None  # hallucinated id never stored


def test_drill_works_on_thin_subtopic_via_element_pool(client):
    """A subtopic with zero questions of its own still drills — borrowing its element's pool."""
    import psycopg
    from psycopg.rows import dict_row

    from ace_api.config import settings

    h = _auth(client)
    exam_id = _cire_with_material(client, h)
    with psycopg.connect(settings().database_url, row_factory=dict_row) as db:
        thin = db.execute(
            """SELECT t.id FROM topics t WHERE t.exam_id=%s AND t.parent_id IS NOT NULL
               AND NOT EXISTS (SELECT 1 FROM questions q WHERE q.topic_id=t.id
                               AND q.status='active') LIMIT 1""", (exam_id,)).fetchone()
    assert thin is not None
    r = client.post(f"/topics/{thin['id']}/drill", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] > 0
    assert body["scope"] == "element"


def test_lesson_rewrite_creates_new_deeper_version(client):
    h = _auth(client)
    exam_id = _cire_with_material(client, h)
    tid = _some_topic(client, h, exam_id)
    l1 = client.post(f"/topics/{tid}/lesson", headers=h).json()
    l2 = client.post(f"/topics/{tid}/lesson?rewrite=true", headers=h).json()
    assert l2["created"] is True and l2["lesson_id"] != l1["lesson_id"]
    d = client.get(f"/topics/{tid}", headers=h).json()
    assert d["lesson"]["id"] == l2["lesson_id"]  # latest wins


def test_topic_of_other_user_is_forbidden(client):
    h1 = _auth(client)
    exam_id = client.post("/exams", json={"name": "CIRE"}, headers=h1).json()["exam_id"]
    topics = client.get(f"/exams/{exam_id}/topic-tree", headers=h1).json()["topics"]
    h2 = _auth(client)
    assert client.get(f"/topics/{topics[0]['id']}", headers=h2).status_code == 404
