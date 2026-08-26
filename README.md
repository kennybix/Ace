# Ace

**An agentic exam-prep platform.** Upload your own study materials, set your exam date,
and Ace runs the entire prep cycle: it derives the syllabus, builds a day-by-day plan
backwards from exam day, drills you with grounded questions, explains every answer,
and improves its own content while you sleep.

Built as a self-hosted personal product (Android app + FastAPI backend on a home server),
dogfooded against a real certification exam.

## What makes it interesting

**Grounding is enforced in code, not prompts.** Every generated question and lesson must
cite source chunks from the user's uploaded materials; uncited output is discarded at the
gate. Payload schemas are validated per format, near-duplicates are rejected by embedding
similarity, and correct answers are stripped server-side so they can never leak to the
client before an attempt.

**A critic sits between generation and the user.** Draft questions go through an LLM
judge (pass / revise / fail) checking answerability, single-best-answer, distractor
quality, and clarity — with full revisions applied when salvageable. In live testing the
critic caught real ungrounded claims the generator produced and rewrote them.

**Content improves nightly, unattended.** A systemd-timed agent cycle replaces reported
questions, re-audits old ones against current standards, rewrites thin lessons, tops up
under-stocked topics, curates YouTube videos (search → LLM relevance judge → embeddability
check), and enriches every MCQ with why-right/why-wrong notes for all four options.

**Exam-agnostic by design.** Known exams load a pre-parsed "accelerator" (official syllabus
→ topic tree with per-element weights and cognitive levels; official practice exams →
question banks extracted deterministically with golden tests). Unknown exams get an
AI-written **starter pack** — topic tree plus study notes stored as a clearly-labeled
document, feeding the same gated pipeline — with an honest refusal when the model doesn't
know the exam.

**The study loop is a real model, not a streak counter.** EWMA mastery per topic (weighted
by answer confidence), SM-2-style spaced repetition, format-aware generation matching the
exam's real question mix, and a multi-signal readiness composite (drill accuracy, mock
scores, confidence calibration, recall) rolled up per syllabus element.

**The mobile client assumes the network is hostile.** Candidate probing (Tailscale →
LAN) with mid-session self-healing retry, per-endpoint timeout budgets (generation gets
90s, reads get 12s), session restore for interrupted diagnostics and drills, and error
states with retries on every async path — most of them added after piloting the app like
a user and logging every dead end.

## Architecture

```
apps/
  api/        FastAPI + Postgres/pgvector (raw SQL via psycopg3, no ORM)
    ace_api/engine/    generation, critic, lessons, flashcards, explanations,
                       planner, assessor, readiness, starter packs, improvement cycle
    ace_api/routers/   ~40 endpoints; JWT auth (email OTP)
    tests/             55 tests: E2E journeys, golden parses, cross-user security,
                       an "empty exam never 500s" sweep
  mobile/     Expo / React Native (Android), design-token UI system, WebView video embeds
infra/        docker-compose (pg16+pgvector), nightly backup script with SSD mirroring
docs/         concept, PRD, implementation plan, device-build guide
```

Operational pieces (systemd user units, not in-repo): API service with boot ordering and
auto-restart, a 5-minute health watchdog, a 02:00 content-improvement timer, and a 03:00
backup timer with 14-day rotation.

LLM access goes through any OpenAI-compatible endpoint (`ACE_LLM_BASE_URL`); model choice
is per-user and switchable in-app, with dialect normalization absorbing cross-model JSON
quirks and quality gates enforced identically regardless of model.

## Running it

```bash
# backend
make db-up migrate           # postgres+pgvector in docker (:5445)
cp apps/api/.env.example apps/api/.env   # add your LLM endpoint/key
make dev                     # API on :8040
make test

# mobile
cd apps/mobile && npm install && npm start   # Expo; see docs/DEVICE_BUILD.md for APK builds
# server addresses go in apps/mobile/app.local.json (gitignored), see app.config.js
```

**Bring your own corpus:** `resources/` is gitignored — study materials are copyrighted
and stay local. Drop an exam's official PDFs there to build an accelerator
(`make accelerate`), or just upload materials in-app; the starter pack covers exams with
no materials at all.

## Status

A working personal project, built fast and hardened by use — not a hosted service.
Single-server deployment, OTP codes echoed in-app (safe only behind a private network),
Android only. MIT licensed.
