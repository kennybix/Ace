"""YouTube curation: search → filter → rank → store, pooled per exam topic.

Real search requires ACE_YOUTUBE_API_KEY; without it curation is a no-op (sessions degrade
gracefully to lesson + drills). Watch-check questions are generated from video metadata +
topic chunks through the same gated LLM path. Embed-only playback — never download/re-host."""

from __future__ import annotations

import httpx

from ace_api import db
from ace_api.config import settings

# For niche exams the best explainer may have 300 views — popularity floors kill exactly
# the right content. Keep loose spam floors; the LLM relevance judge does the real vetting.
MAX_DURATION_S = 22 * 60
MIN_DURATION_S = 2 * 60
MIN_VIEWS = 100


async def curate_for_topic(exam_id: int, topic_id: int) -> int:
    """Curate with the Data API when a key works; fall back to the keyless LLM+oEmbed path
    (key missing, API blocked/quota'd — curation must never 500)."""
    if settings().youtube_api_key:
        try:
            n = await curate_topic(exam_id, topic_id)
            if n:
                return n
        except Exception:
            pass
    return await curate_topic_via_llm(exam_id, topic_id)


async def curate_topic_via_llm(exam_id: int, topic_id: int) -> int:
    """Keyless curation: the LLM proposes well-known videos; each candidate must prove it
    exists via YouTube's oEmbed (keyless, ToS-fine) and its REAL title must match the topic.
    Hallucinated/dead IDs are filtered out by construction."""
    import json as _json
    import re as _re

    from ace_api.llm.client import chat_json

    topic = await db.fetch_one("SELECT code, title FROM topics WHERE id=%s", (topic_id,))
    exam = await db.fetch_one("SELECT name_raw FROM exams WHERE id=%s", (exam_id,))
    try:
        out = await chat_json(
            "suggest_videos",
            "Output ONLY JSON: {\"videos\":[{\"id\": \"11-char YouTube id\", \"title\": str, "
            "\"channel\": str}]}. Suggest up to 5 REAL, popular educational YouTube videos "
            "you are confident exist (major channels, >100k views) teaching the topic for "
            "this exam. If unsure a video exists, omit it.",
            _json.dumps({"exam": exam["name_raw"], "topic": f"{topic['code']} {topic['title']}"}),
        )
    except Exception:
        return 0
    candidates = out.get("videos", []) if isinstance(out, dict) else []
    topic_words = {w for w in _re.findall(r"[a-z]{4,}", topic["title"].lower())}
    stored = 0
    for cand in candidates[:5]:
        vid = str(cand.get("id", ""))
        if not _re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
            continue
        meta = await _oembed(vid)
        if not meta:
            continue  # does not exist — hallucination filtered
        real_title = meta.get("title", "")
        title_words = set(_re.findall(r"[a-z]{4,}", real_title.lower()))
        overlap = len(topic_words & title_words)
        generic = {"exam", "investment", "canadian", "securities", "course"}
        if overlap == 0 and not (title_words & generic):
            continue  # exists but clearly off-topic
        await db.execute(
            """INSERT INTO videos (exam_id, topic_id, youtube_id, title, duration_s,
                                   curation_score)
               VALUES (%s,%s,%s,%s,0,%s)""",
            (exam_id, topic_id, vid, real_title[:300], 0.3 + 0.2 * min(overlap, 3)))
        stored += 1
        if stored >= 2:
            break
    return stored


async def _oembed(youtube_id: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://www.youtube.com/oembed",
                                 params={"url": f"https://youtu.be/{youtube_id}",
                                         "format": "json"})
        return r.json() if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


async def curate_topic(exam_id: int, topic_id: int) -> int:
    key = settings().youtube_api_key
    if not key:
        return 0
    topic = await db.fetch_one("SELECT code, title FROM topics WHERE id=%s", (topic_id,))
    queries = _search_queries(topic["title"])
    seen: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=30) as client:
        for q in queries:
            r = await client.get("https://www.googleapis.com/youtube/v3/search",
                                 params={"part": "snippet", "q": q, "type": "video",
                                         "maxResults": 8, "videoDuration": "medium",
                                         "relevanceLanguage": "en", "key": key})
            r.raise_for_status()
            for i in r.json().get("items", []):
                seen[i["id"]["videoId"]] = i
        ids = ",".join(seen.keys())
        if not ids:
            return 0
        d = await client.get("https://www.googleapis.com/youtube/v3/videos",
                             params={"part": "contentDetails,statistics,snippet,status",
                                     "id": ids, "key": key})
        d.raise_for_status()
    candidates = []
    for v in d.json().get("items", []):
        if not v.get("status", {}).get("embeddable", False):
            continue  # owner disabled embedding — useless for in-app playback
        dur = _iso_seconds(v["contentDetails"]["duration"])
        if not (MIN_DURATION_S <= dur <= MAX_DURATION_S):
            continue
        stats = v.get("statistics", {})
        views = int(stats.get("viewCount", 0))
        if views < MIN_VIEWS:
            continue
        likes = int(stats.get("likeCount", 0))
        candidates.append({
            "id": v["id"], "title": v["snippet"]["title"][:200],
            "channel": v["snippet"]["channelTitle"][:100],
            "description": v["snippet"].get("description", "")[:200],
            "duration_s": dur, "views": views,
            "score": min(views / 1e6, 1.0) * 0.5 + (likes / max(views, 1)) * 50 * 0.5,
        })
    if not candidates:
        return 0
    # keyword search returns loose matches — an LLM judge decides what actually TEACHES
    # the topic. Nothing unvetted gets stored.
    relevant_ids = await _judge_relevance(topic["title"], candidates)
    stored = 0
    for c in candidates:
        if c["id"] not in relevant_ids:
            continue
        await db.execute(
            """INSERT INTO videos (exam_id, topic_id, youtube_id, title, duration_s, curation_score)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (exam_id, topic_id, c["id"], c["title"][:300], c["duration_s"], c["score"]))
        stored += 1
        if stored >= 2:
            break
    return stored


async def _judge_relevance(topic_title: str, candidates: list[dict]) -> set[str]:
    import json as _json

    from ace_api.llm.client import chat_json
    try:
        out = await chat_json(
            "rank_videos",
            "Output ONLY JSON {\"relevant_ids\": [str, ...]}. You vet YouTube videos for an "
            "exam-prep app. Return ids of ONLY the videos whose title/description shows they "
            "actually TEACH the given topic. Interviews, press releases, news, vlogs, or "
            "loosely related content are NOT relevant. Empty list if none qualify.",
            _json.dumps({"topic": topic_title,
                         "candidates": [{k: c[k] for k in ("id", "title", "channel",
                                                           "description")}
                                        for c in candidates]}),
        )
        ids = out.get("relevant_ids", []) if isinstance(out, dict) else []
        return {str(i) for i in ids}
    except Exception:
        return set()


def _search_queries(title: str) -> list[str]:
    """Formal learning-outcome titles make terrible search queries — derive two variants:
    the proper-noun core ('Canadian Securities Administrators CSA explained') and a
    distilled keyword form."""
    import re
    t = re.sub(r"^(understand|remember|apply|analyz?e|analyse)\b( the)?\s*", "",
               title, flags=re.I)
    t = t.split(" Consider")[0].split(". ")[0]
    t = re.sub(r"[()/•:]", " ", t)
    stop = {"the", "and", "of", "for", "with", "that", "their", "a", "an", "to", "in",
            "on", "by", "or", "its", "as", "is", "are", "be"}
    words = [w for w in t.split() if w.lower() not in stop]
    queries = []
    propers = re.findall(r"(?:[A-Z][A-Za-z]+ )+(?:[A-Z][A-Za-z]+|[A-Z]{2,})", t)
    if propers:
        queries.append(max(propers, key=len).strip() + " explained")
    queries.append(" ".join(words[:5]) + " explained")
    return list(dict.fromkeys(queries))[:2]


def _iso_seconds(iso: str) -> int:
    import re
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


async def check_availability() -> dict:
    """Nightly: mark dead videos (oEmbed 404) so backups get promoted."""
    rows = await db.fetch_all("SELECT id, youtube_id FROM videos WHERE status='active'")
    dead = 0
    async with httpx.AsyncClient(timeout=15) as client:
        for r in rows:
            try:
                resp = await client.get("https://www.youtube.com/oembed",
                                        params={"url": f"https://youtu.be/{r['youtube_id']}",
                                                "format": "json"})
                if resp.status_code in (400, 401, 403, 404):
                    await db.execute("UPDATE videos SET status='dead', last_checked_at=now() "
                                     "WHERE id=%s", (r["id"],))
                    dead += 1
                else:
                    await db.execute("UPDATE videos SET last_checked_at=now() WHERE id=%s", (r["id"],))
            except httpx.HTTPError:
                continue
    return {"checked": len(rows), "dead": dead}
