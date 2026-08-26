"""XP, streaks, badges — adult-toned, single-player."""

from __future__ import annotations

from datetime import date, timedelta

from ace_api import db

XP = {"session_complete": 50, "diagnostic_complete": 80, "mock_complete": 150,
      "question_correct": 5, "streak_day": 10}

BADGES = {
    "first_session": "First session completed",
    "streak_7": "7-day streak",
    "streak_30": "30-day streak",
    "first_mock": "First mock exam",
    "mock_pass": "Mock ≥ 60%",
    "topic_mastered": "First topic ≥ 80% mastery",
    "centurion": "500 questions answered",
}


async def award(user_id: int, reason: str, amount: int | None = None) -> None:
    await db.execute("INSERT INTO xp_events (user_id, amount, reason) VALUES (%s,%s,%s)",
                     (user_id, amount if amount is not None else XP.get(reason, 0), reason))


async def touch_streak(user_id: int) -> dict:
    today = date.today()
    row = await db.fetch_one("SELECT * FROM streaks WHERE user_id=%s", (user_id,))
    if not row:
        await db.execute(
            "INSERT INTO streaks (user_id, current, best, last_active_date) VALUES (%s,1,1,%s) "
            "ON CONFLICT (user_id) DO NOTHING", (user_id, today))
        return {"current": 1, "best": 1}
    if row["last_active_date"] == today:
        return {"current": row["current"], "best": row["best"]}
    current = row["current"] + 1 if row["last_active_date"] == today - timedelta(days=1) else 1
    best = max(current, row["best"])
    await db.execute(
        "UPDATE streaks SET current=%s, best=%s, last_active_date=%s WHERE user_id=%s",
        (current, best, today, user_id))
    if current >= 7:
        await grant(user_id, "streak_7")
    if current >= 30:
        await grant(user_id, "streak_30")
    await award(user_id, "streak_day")
    return {"current": current, "best": best}


async def grant(user_id: int, badge_key: str) -> None:
    await db.execute(
        "INSERT INTO badges (user_id, badge_key) VALUES (%s,%s) ON CONFLICT DO NOTHING",
        (user_id, badge_key))


async def summary(user_id: int) -> dict:
    xp = await db.fetch_one("SELECT COALESCE(sum(amount),0) AS xp FROM xp_events WHERE user_id=%s",
                            (user_id,))
    streak = await db.fetch_one("SELECT current, best FROM streaks WHERE user_id=%s", (user_id,))
    badges = await db.fetch_all(
        "SELECT badge_key, awarded_at FROM badges WHERE user_id=%s ORDER BY awarded_at", (user_id,))
    return {"xp": xp["xp"], "level": 1 + int((xp["xp"] / 250) ** 0.7),
            "streak": dict(streak) if streak else {"current": 0, "best": 0},
            "badges": [{"key": b["badge_key"], "label": BADGES.get(b["badge_key"], b["badge_key"]),
                        "awarded_at": str(b["awarded_at"])} for b in badges]}
