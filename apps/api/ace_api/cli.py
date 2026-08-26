"""`ace` CLI — Phase 1 harness + ops commands."""

from __future__ import annotations

import asyncio
import json

import typer

app = typer.Typer(no_args_is_help=True)


@app.command()
def migrate():
    from ace_api.db.migrate import run_migrations
    typer.echo(f"applied: {run_migrations()}")


@app.command()
def accelerate(resources_dir: str = typer.Argument("../../resources")):
    """Build the CIRE accelerator from the official CIRO PDFs."""
    from ace_api.engine.accelerator import build_cire

    async def run():
        out = await build_cire(resources_dir)
        from ace_api import db as _db
        await _db.close_pool()
        return out

    out = asyncio.run(run())
    typer.echo(json.dumps({k: v for k, v in out.items() if k != "profile"}, indent=2))
    typer.echo("cognitive_mix: " + json.dumps(out["profile"]["cognitive_mix"]))


@app.command("llm-smoke")
def llm_smoke():
    """One structured call through every registered model via the gateway."""
    from ace_api.config import settings
    from ace_api.llm.client import chat_json

    async def run():
        results = {}
        for m in settings().llm_models:
            try:
                out = await chat_json(
                    "plan_rationale",
                    "You are a JSON API endpoint. Output ONLY a JSON object, no prose, "
                    "no questions, no markdown. Schema: {\"rationale\": string}",
                    json.dumps({"instruction": "return exactly {\"rationale\": \"pong\"}"}),
                    model_id=m["id"])
                results[m["id"]] = "ok: " + str(out)[:80]
            except Exception as e:
                results[m["id"]] = f"FAIL: {e}"
        return results

    for k, v in asyncio.run(run()).items():
        typer.echo(f"{k}: {v}")


@app.command()
def generate(topic_code: str, n: int = 5, fmt: str = "mcq", exam_id: int = typer.Option(...),
             model: str = ""):
    """Generate gated, grounded questions for a topic of an exam."""
    from ace_api.engine.generator import generate_for_topic

    async def run():
        out = await generate_for_topic(exam_id, topic_code, fmt, n, model or None)
        from ace_api import db as _db
        await _db.close_pool()
        return out

    out = asyncio.run(run())
    typer.echo(json.dumps(out, indent=2, default=str))


@app.command()
def nightly():
    """Nightly batch: prepare upcoming sessions for all active exams + video availability check.
    Schedule via cron: `0 2 * * * cd .../apps/api && uv run ace nightly`."""
    from ace_api.engine.session_prep import nightly as prep
    from ace_api.jobs.videos import check_availability

    async def run():
        out = {"prep": await prep()}
        try:
            out["videos"] = await check_availability()
        except Exception as e:
            out["videos"] = {"error": str(e)[:100]}
        from ace_api import db as _db
        await _db.close_pool()
        return out

    typer.echo(json.dumps(asyncio.run(run())))


if __name__ == "__main__":
    app()
