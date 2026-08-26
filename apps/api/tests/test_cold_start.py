"""Items 3–5: starter pack cold start, flashcard decks, format-aware generation."""

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from ace_api.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _auth(client):
    email = f"cs-{uuid.uuid4().hex[:8]}@example.com"
    code = client.post("/auth/otp", json={"email": email}).json()["dev_code"]
    token = client.post("/auth/verify", json={"email": email, "code": code}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_starter_pack_bootstraps_unknown_exam(client):
    h = _auth(client)
    exam_id = client.post("/exams", json={"name": "PMP", "exam_date": "2026-12-01"},
                          headers=h).json()["exam_id"]
    r = client.post(f"/exams/{exam_id}/starter-pack", headers=h).json()
    assert r["building"] is True
    for _ in range(50):  # TestClient runs bg tasks after response; poll state
        src = client.get(f"/exams/{exam_id}/sources", headers=h).json()
        starter = [d for d in src["documents"] if "Starter Pack" in d["filename"]]
        if starter and starter[0]["parse_status"] == "parsed":
            break
        time.sleep(0.2)
    assert starter and starter[0]["parse_status"] == "parsed"
    assert starter[0]["chunks"] > 0
    tree = client.get(f"/exams/{exam_id}/topic-tree", headers=h).json()["topics"]
    assert len([t for t in tree if t["parent_id"] is None]) >= 2
    # environment is now functional: lesson + drill work on a starter topic
    child = next(t for t in tree if t["parent_id"] is not None)
    lesson = client.post(f"/topics/{child['id']}/lesson", headers=h)
    assert lesson.status_code == 200
    # second build attempt is a no-op
    again = client.post(f"/exams/{exam_id}/starter-pack", headers=h).json()
    assert again["already"] is True


def test_starter_pack_refuses_accelerator_and_unknown(client):
    h = _auth(client)
    cire = client.post("/exams", json={"name": "CIRE"}, headers=h).json()["exam_id"]
    assert client.post(f"/exams/{cire}/starter-pack", headers=h).status_code == 400
    obscure = client.post("/exams", json={"name": "Totally Unknown Cert 9000"},
                          headers=h).json()["exam_id"]
    client.post(f"/exams/{obscure}/starter-pack", headers=h)
    time.sleep(0.5)
    src = client.get(f"/exams/{obscure}/sources", headers=h).json()
    starter = [d for d in src["documents"] if "Starter Pack" in d["filename"]]
    assert starter and starter[0]["parse_status"] == "failed"  # honest refusal, no invention


def test_flashcard_deck_builds_and_caches(client):
    h = _auth(client)
    exam_id = client.post("/exams", json={"name": "CIRE", "exam_date": "2026-10-20"},
                          headers=h).json()["exam_id"]
    # needs chunks: build starter is blocked (accelerator) — upload real material instead
    from tests.conftest import RESOURCES
    with open(RESOURCES / "CIRE_Element_1_Canadian_Securities_Regulatory_Framework.pdf",
              "rb") as f:
        client.post(f"/exams/{exam_id}/documents",
                    files={"file": ("e1.pdf", f, "application/pdf")}, headers=h)
    for _ in range(50):
        st = client.get(f"/exams/{exam_id}/ingestion-status", headers=h).json()
        if all(d["parse_status"] == "parsed" for d in st["documents"]):
            break
        time.sleep(0.2)
    d1 = client.post(f"/exams/{exam_id}/flashcards", headers=h).json()
    assert len(d1["cards"]) >= 4
    assert all(c["front"] and c["back"] for c in d1["cards"])
    d2 = client.post(f"/exams/{exam_id}/flashcards", headers=h).json()
    assert d2.get("cached") is True and d2["deck_id"] == d1["deck_id"]
    d3 = client.post(f"/exams/{exam_id}/flashcards?rebuild=true", headers=h).json()
    assert d3["deck_id"] != d1["deck_id"]


def test_pick_format_respects_profile():
    import asyncio

    from ace_api import db
    from ace_api.engine.generator import pick_format

    async def run():
        # CIRE accelerator profile is 100% mcq — picker must always return mcq
        row = await db.fetch_one(
            "SELECT e.id FROM exams e WHERE e.accelerator_id IS NOT NULL ORDER BY e.id DESC "
            "LIMIT 1")
        outs = {await pick_format(row["id"]) for _ in range(8)}
        await db.close_pool()
        return outs

    assert asyncio.run(run()) == {"mcq"}
