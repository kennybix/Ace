from contextlib import asynccontextmanager

from fastapi import FastAPI

from ace_api import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.open_pool()
    yield
    await db.close_pool()


def create_app() -> FastAPI:
    app = FastAPI(title="Ace API", version="0.1.0", lifespan=lifespan)

    # Creation paths surface LLM outages as a clear "budget exhausted" 503, never a raw 500 —
    # everything already generated keeps serving from Postgres regardless.
    from fastapi.responses import JSONResponse

    from ace_api.llm.client import LLMError

    @app.exception_handler(LLMError)
    async def llm_unavailable(request, exc: LLMError):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.get("/health")
    async def health():
        row = await db.fetch_one("SELECT 1 AS ok")
        return {"status": "ok", "db": bool(row and row["ok"] == 1)}

    from ace_api.routers import (auth, exams, gamify, mocks, models, plan, questions, sessions,
                                 topics, videos)

    for r in (auth, exams, plan, sessions, mocks, questions, gamify, models, videos, topics):
        app.include_router(r.router)
    return app


app = create_app()
