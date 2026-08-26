"""Minimal ordered plain-SQL migration runner (no ORM, per implementation plan)."""

from __future__ import annotations

from pathlib import Path

import psycopg

from ace_api.config import settings

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def run_migrations(database_url: str | None = None) -> list[str]:
    url = database_url or settings().database_url
    applied: list[str] = []
    with psycopg.connect(url) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz DEFAULT now())"
        )
        done = {r[0] for r in db.execute("SELECT name FROM schema_migrations").fetchall()}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in done:
                continue
            db.execute(path.read_text())
            db.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
            applied.append(path.name)
        db.commit()
    return applied
