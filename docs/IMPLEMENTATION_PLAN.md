# Ace — Implementation Plan

**Status:** v1.0 — 2026-07-15
**Inputs:** [PRD v0.5](PRD.md), [CONCEPT.md](CONCEPT.md), CIRO seed corpus in `resources/`
**Builder profile:** solo founder-engineer + AI pair; sequencing favors one workstream at a time with CLI-verifiable milestones.

---

## 0. Guiding principles for the build

1. **Engine before UI.** Phases 0–1 produce a pipeline that is fully exercisable from the CLI against the real CIRE corpus. If question quality isn't there, no amount of app polish matters — prove it first.
2. **The CIRE corpus is the test fixture.** The three CIRO PDFs are real, structured, and known — every pipeline stage has a golden expected output derivable from them (9 elements, ~100 learning outcomes, 12+ practice items per parse target).
3. **Everything the agent produces is a row, not a chat message.** Topic trees, profiles, questions, plans, lessons are typed records in Postgres with provenance (source chunks, model, prompt version). No opaque blobs.
4. **Dogfood pressure from Phase 2.** As soon as the loop closes end-to-end, the founder's own CIRE prep runs on it daily — bugs get found by the person who can fix them.
5. **Model-agnostic at every call site.** One LLM client wrapper; model comes from user prefs → request context. No node ever hardcodes a model.

---

## 1. Repo scaffold

```
Ace/
├── apps/
│   ├── api/                    # FastAPI + LangGraph (Python 3.12, uv)
│   │   ├── ace_api/
│   │   │   ├── main.py         # app factory, routers
│   │   │   ├── config.py       # pydantic-settings; ports, LLM gateway URL, model list
│   │   │   ├── db/             # psycopg pool, typed query layer, SQL migrations
│   │   │   ├── routers/        # auth, uploads, exams, plan, sessions, mocks, gamify, models
│   │   │   ├── agent/          # LangGraph graphs + nodes (§4)
│   │   │   ├── llm/            # OpenAI-compatible client wrapper, model registry, prompt store
│   │   │   ├── jobs/           # worker: ingestion, nightly batch, video checks
│   │   │   └── cli.py          # `ace` CLI (typer) — Phase 1 harness
│   │   └── tests/
│   ├── mobile/                 # Expo / React Native (TypeScript, Expo Router)
│   │   ├── app/                # routes = screens (PRD §6)
│   │   ├── components/         # question widgets, video embed, charts, gamify
│   │   └── lib/                # API client (generated from OpenAPI), stores
│   └── admin/                  # (deferred; only if beta ops demands it)
├── packages/
│   └── shared/                 # JSON Schemas for question payloads; TS types generated
├── infra/
│   └── docker-compose.yml      # postgres:16 + pgvector on :5443
├── resources/                  # CIRO seed corpus (already present)
└── docs/
```

**Tooling decisions (locked unless they fight back):**

| Concern | Choice | Rationale |
|---|---|---|
| Python env | `uv` + Python 3.12 | fast, lockfile, house-compatible |
| DB access | **psycopg 3** (direct Postgres) — raw SQL in a typed query layer (`db/queries/*.sql` + pydantic row models), no ORM | full control over pgvector ops and jsonb queries; one less abstraction; Procrastinate already runs on psycopg |
| Migrations | plain-SQL files via **yoyo-migrations** | versioned, reviewable DDL; no ORM metadata coupling |
| Job queue | **Procrastinate** (Postgres-native) | no Redis to run; jobs are transactional with app data; nightly batch + ingestion are its only consumers at MVP scale |
| Auth | Email + 6-digit OTP, JWT (httponly refresh) | no password storage, no third-party dependency |
| Mobile state | TanStack Query + Zustand | server-state vs. UI-state split |
| API client | OpenAPI-generated TS client into `apps/mobile/lib` | one source of truth for types |
| PDF parsing | PyMuPDF primary; `ocrmypdf` fallback path for scanned uploads | CIRO PDFs are born-digital; OCR only when text layer missing |
| Embeddings | via CLI proxy if it exposes an embeddings route, else a local sentence-transformer; **decide in Phase 0 smoke test** | keeps provider optionality |
| LLM calls | one `llm/client.py` wrapper over OpenAI-compatible `/chat/completions` at the gateway; JSON-schema response format for all generation | model id injected per call |

Ports per house convention: API **:8040**, Postgres **:5445**, LLM gateway **:8317** (dev). Expo dev server default. *(Original picks 8030/5443 were already taken on this machine by other local services — ReadAPage holds 5443, IléAra holds 5444.)*

> **Build notes (2026-07-15, Phase 0–3 executed).** Three pragmatic substitutions vs. the plan, same contracts:
> 1. **Migrations:** a ~30-line ordered plain-SQL runner (`db/migrate.py` + `schema_migrations` table) instead of yoyo-migrations — zero deps, same reviewable `.sql` files.
> 2. **Jobs:** ingestion runs via FastAPI BackgroundTasks; the nightly batch is `ace nightly` (cron-able) instead of a Procrastinate worker. Procrastinate remains the upgrade path when job volume demands a real queue.
> 3. **Agent graphs:** implemented as explicit async pipeline functions (`engine/*.py`) rather than LangGraph `StateGraph`s — same node decomposition (§4), deterministic and unit-testable; swapping in LangGraph later is mechanical.
> Also: LLM client ships a deterministic **fake mode** (`ACE_LLM_FAKE` / no key) so the entire pipeline and test suite run without gateway credentials; the live 4-model smoke (`ace llm-smoke`) needs `ACE_LLM_API_KEY` in `apps/api/.env`.

---

## 2. Data model (Postgres + pgvector)

Core tables, key columns only (full DDL lives in versioned SQL migration files):

**Identity & prefs**
- `users` — id, email, created_at, `selected_model` (text, FK-checked against model registry config), timezone
- `model_registry` — **config, not DB** (`config.py` / env): `[{id, label, gateway_model_id, enabled}]` for Opus 4.8, Fable 5, GPT-5.5, GPT-5.6

**Exam & content**
- `exams` — id, user_id, `name_raw` (free text as typed), `accelerator_id` (nullable), exam_date, weekly_hours, status
- `accelerators` — id, `exam_key` (e.g. `cire-ciro-2025`), topic_tree (jsonb), default_profile (jsonb), video_playlists (jsonb), provenance; **pooled across users**
- `documents` — id, exam_id, filename, sha256, kind (detected: syllabus | textbook | past_questions | guidance | notes), parse_status, page_count
- `chunks` — id, document_id, page_from/to, text, embedding (vector), `topic_id` (nullable until mapped)
- `topics` — id, exam_id, parent_id, code (`"3.2"`), title, weight (indicative Qs or inferred), cognitive_levels (text[]), source (syllabus_parsed | toc_inferred | user_edited)

**Questions**
- `questions` — id, exam_id, topic_id, `source` (extracted | generated), `format` (mcq | tf | gap | match | numeric), `cognitive_level`, payload (jsonb, per-format discriminated schema in `packages/shared`), citations (jsonb: [{chunk_id, page}] — **NOT NULL for generated**), difficulty, `status` (active | killed | pending_review), model_id + prompt_version (for generated), external_item_id (e.g. `CIRO_E_000017` for extracted)
- `question_reports` — question_id, user_id, reason, created_at → feeds kill-list job

**Plan & study**
- `plans` — id, exam_id, version, generated_at, rationale (text), status (active | superseded)
- `plan_items` — id, plan_id, date, topic_ids[], kind (learn | review | mock | taper), est_minutes, status
- `sessions` — id, plan_item_id, started/completed_at, prepared_payload (jsonb: ordered items — lesson_id, video_id, question_ids), model_id used at prep time
- `attempts` — id, session_id | mock_id, question_id, answer (jsonb), correct (bool), confidence (sure | think | guess), ms_taken
- `lessons` — id, topic_id, kind (micro_lesson | revision_sheet | flashcard), body (md), citations (jsonb), model_id, prompt_version
- `mocks` — id, exam_id, blueprint (jsonb: per-element counts mirroring profile), score, per_element_scores (jsonb)

**Mastery & readiness**
- `mastery` — exam_id, topic_id, rating (float), per_format (jsonb), per_cognitive (jsonb), updated_at
- `readiness_snapshots` — exam_id, date, composite (float), signals (jsonb: accuracy, mock, calibration, recall, watch_check)
- `review_queue` — question_id/flashcard_id, due_at, interval, ease (SM-2-lite)

**Videos & gamification**
- `videos` — id, accelerator_id | exam_id, topic_id, youtube_id, duration_s, curation_score, status (active | dead | reported), last_checked_at
- `watch_checks` — video_id, question_ids[]
- `xp_events` — user_id, amount, reason, created_at; `streaks` — user_id, current, best, last_active_date; `badges` — user_id, badge_key, awarded_at

---

## 3. API surface (FastAPI routers)

- `auth`: `POST /auth/otp`, `POST /auth/verify`, `POST /auth/refresh`
- `exams`: `POST /exams` (name, date, hours), `GET /exams/{id}`, `PATCH /exams/{id}` (date/hours changes → triggers re-plan job)
- `uploads`: `POST /exams/{id}/documents` (multipart), `GET /exams/{id}/ingestion-status` (SSE or poll)
- `profile`: `GET/PUT /exams/{id}/topic-tree`, `GET/PUT /exams/{id}/question-profile` (confirmation/edit at onboarding)
- `diagnostic`: `POST /exams/{id}/diagnostic/start`, `POST /attempts`, `GET /exams/{id}/diagnostic/result`
- `plan`: `GET /exams/{id}/plan`, `GET /plan-items/today`
- `sessions`: `POST /plan-items/{id}/session/start`, `POST /attempts` (shared), `POST /sessions/{id}/complete`
- `mocks`: `POST /exams/{id}/mocks/start`, `.../submit`, `GET .../report`
- `readiness`: `GET /exams/{id}/readiness` (composite + signals + heat-map + per-format)
- `questions`: `POST /questions/{id}/report`
- `gamify`: `GET /me/gamify` (xp, streak, badges, quest state)
- `models`: `GET /models` (registry), `PUT /me/model`
- `videos`: `POST /videos/{id}/report`

Explanations are pre-generated with questions (same batch) — no live-LLM endpoint needed in the hot path. On-demand "explain differently" can come post-MVP.

---

## 4. Agent graphs (LangGraph)

Three separately-invoked graphs rather than one mega-graph — they run at different times with different triggers:

### 4.1 Ingestion graph (trigger: document upload; runs per document, then a finalize step per exam)
```
classify_document → parse_extract_text → chunk_embed
  → [if syllabus] parse_topic_tree
  → [if question-bearing] extract_questions → classify_questions (format + cognitive)
  → map_chunks_to_topics
finalize (per exam, after all docs): merge_topic_tree → build_question_profile → emit_confirmation_payload
```
- `parse_topic_tree`: LLM-structured extraction into the topics schema (elements → outcomes → cognitive tags → weights). CIRE golden test: must recover 9 elements with weights {11,11,17,6,9,13,21,6,16} and outcome counts per element.
- `extract_questions`: layout-aware; keyed to item-ID patterns when present (`CIRO_E_\d+`), else numbered-stem heuristics + LLM segmentation. Golden test: 100% of practice-exam items recovered with 4 options each.
- Coverage gaps (topics with < N mapped chunks) flagged to planner.

### 4.2 Prep graph (trigger: nightly batch per user, and immediately after diagnostic)
```
assess (recompute mastery from new attempts)
  → replan (diff plan vs. actuals; reshuffle remaining plan_items; draft change note)
  → prepare_sessions (next 1–2 days):
      pick_targets (topics + formats + cognitive mix per profile & weakness)
      → build_lesson (if new topic)
      → select_video (from curated pool; skip if none passes bar)
      → assemble_questions (extracted-first, then generate → gate → dedupe)
      → write session.prepared_payload
```
- Generation gating (hard, in code not prompt): citations non-empty & resolvable → else discard; embedding near-dupe check vs. served + extracted; per-model kill-rate metric emitted.
- Runs under the **user's selected model** captured at batch time.

### 4.3 Curation graph (trigger: new accelerator topic tree, weekly refresh, nightly availability check)
```
per topic: search_youtube → filter (duration/engagement/channel) → transcript_relevance_score
  → rank → store top-3 + build watch_check questions (grounded in transcript + user-material chunks)
availability job: HEAD-check stored videos nightly → mark dead → promote backups
```

**Prompt store:** versioned prompt templates in `apps/api/ace_api/llm/prompts/` (files, git-versioned); every generated row records prompt_version — enables A/B and regression evals.

---

## 5. Phase plan

Estimates assume focused solo effort with AI pair; a phase is "days of real work," not calendar promises.

### Phase 0 — Skeleton + CIRE accelerator (≈ 4–6 days)

| # | Task | Acceptance criteria |
|---|---|---|
| 0.1 | Monorepo scaffold, docker-compose (pg16+pgvector :5443), uv project, baseline SQL migration + psycopg pool wiring, CI (lint+test) | `make dev` boots API :8030 against fresh DB; healthcheck green |
| 0.2 | LLM client wrapper + model registry config | `ace llm smoke` runs one structured-output call through **all four models** via gateway :8317 and prints per-model latency/token cost |
| 0.3 | Embeddings decision spike | pick gateway-embeddings vs. local model; recorded in this doc §1 table |
| 0.4 | Parse CIRE syllabus → `accelerators` row | golden test passes: 9 elements, correct weights, outcomes with cognitive tags |
| 0.5 | Extract practice exam → question bank | 100% item recovery, stable IDs, 4 options each; answers wired if present in corpus (else flagged) |
| 0.6 | Parse study guidance → planner defaults blob | stored on accelerator; human-readable dump reviewed |

**Exit gate:** the CIRE accelerator exists as data, reproducibly built by `ace accelerate resources/`.

### Phase 1 — Generation engine, CLI-verified (≈ 10–15 days)

| # | Task | Acceptance criteria |
|---|---|---|
| 1.1 | Ingestion graph end-to-end for arbitrary uploads (classify → chunk → embed → map) | `ace ingest <pdf> --exam <id>` on a non-CIRE textbook produces a confirmable inferred topic tree |
| 1.2 | Question-profile builder (format × cognitive × weights) | CIRE profile: 100% MCQ, element weights match syllabus |
| 1.3 | Grounded generation for all 5 auto-gradable formats + gating + dedupe | `ace generate --topic 3.2 --n 10 --model <m>`: every question carries resolvable citations; ungroundable are logged-discarded |
| 1.4 | Micro-lesson / revision-sheet / flashcard builder | `ace lesson --topic 7.1` outputs cited markdown |
| 1.5 | Auto-grader per format (incl. numeric tolerance) | unit tests per format; adversarial cases (negatives, units) |
| 1.6 | **Model bake-off** on CIRE: N=30 questions/model across cognitive levels; blind-rated rubric (groundedness, plausible distractors, style match vs. real items) | scorecard in docs; **default model decided** (PRD §10.1b closed) |
| 1.7 | Eval harness as pytest marker + golden sets | `make eval` runs regression on prompt/prompt-version changes |

**Exit gate:** founder reviews 50 generated CIRE questions blind-mixed with 12 real ones; ≥80% of generated rated "would not look out of place on the paper."

### Phase 2 — The loop closes (≈ 15–20 days)

| # | Task | Acceptance criteria |
|---|---|---|
| 2.1 | Auth (OTP), exams, uploads, ingestion-status APIs | OpenAPI complete; TS client generated |
| 2.2 | Expo app skeleton: onboarding flow (exam free-text, date, hours) → upload → ingestion progress → tree/profile confirmation | runs on founder's physical device via EAS dev build |
| 2.3 | Diagnostic: blueprint from profile (scaled ~30Q), runner UI, baseline mastery | diagnostic result renders topic heat-map |
| 2.4 | Planner v1 (deterministic core + LLM rationale) | plan visibly backwards-from-exam-date; editable hours/date triggers re-plan |
| 2.5 | Session player: lesson → question widgets (5 formats) → confidence tag → citation-linked explanation | full session completable offline-tolerant (queued attempts) |
| 2.6 | Assessor + review queue (SM-2-lite) + nightly prep job (Procrastinate) | next-day session exists every morning; plan-change notes generated |
| 2.7 | Readiness composite v1 + dashboard screen | composite + signal breakdown + per-format bars |
| **DOGFOOD GATE** | **Founder starts real CIRE prep on the app** | daily use begins; issues filed from lived experience |

### Phase 3 — Polish & fun (≈ 10–14 days, overlaps founder's prep)

| # | Task | Acceptance criteria |
|---|---|---|
| 3.1 | Video curation graph + embedded player + watch-checks | ≥1 vetted video for ≥70% of CIRE topics; dead-link job live |
| 3.2 | Gamification: XP events, streaks, badges, daily quest framing | XP/streak visible in session close; 8–10 launch badges |
| 3.3 | Mock engine: blueprint-faithful 110Q/2h timed mode + report | mock #1 taken by founder at ~60% plan mark |
| 3.4 | Journey map + notifications (Expo push) | daily quest push at user-chosen hour |
| 3.5 | Flashcard sprint + final-week taper + exam-day brief | taper plan_items auto-scheduled |
| 3.6 | Model picker in Settings + per-model kill-rate dashboard (simple admin query first) | switch applies to next batch; kill-rate by model queryable |
| 3.7 | Stretch: "explain it back" concept checks | only if 3.1–3.6 land |

### Phase 4 — POC gate → beta (calendar-bound to exam date)

1. Founder completes full CIRE cycle; **the exam result is data** either way — capture readiness-score-vs-outcome calibration.
2. Fix list from dogfood; hardening (rate limits, error budgets, backup/restore drill on :5443 data).
3. TestFlight/Play internal track; 20–50 external candidates (any exam — exam-agnostic path gets real coverage here); PRD §8 metric gates.
4. Payments (per-exam-cycle) only after gates pass.

---

## 6. Testing & quality strategy

- **Golden-set tests** (pytest): CIRE syllabus parse, practice-exam extraction, profile build — run in CI on every change to parsing/prompts.
- **Generation evals** (`make eval`): per prompt-version × model: groundedness (citations resolve & support), format validity (schema), style match (LLM-judge vs. real-item anchors), duplicate rate. Regression-blocked merges on >5% degradation.
- **Auto-grader unit tests** per format, adversarial inputs.
- **Kill-rate telemetry**: `question_reports / questions_served` per model & prompt-version from day one of dogfood.
- **E2E smoke** (Phase 2+): scripted API-level run — create exam → ingest fixture → diagnostic → plan → session → attempt → readiness — in CI against dockerized stack.
- **Mobile**: component tests for the 5 question widgets; manual device passes per release (solo-scale honesty: no Detox until beta).

## 7. Cross-cutting concerns

- **Provenance everywhere:** every generated artifact stores {model_id, prompt_version, citations}. Debugging bad content = SQL query, not archaeology.
- **Cost control:** nightly batch generates ≤2 days ahead; per-user daily token budget logged; bake-off informs default model economics.
- **Privacy:** uploads private per user (S3-compatible or local disk in dev; decide at 2.1); pooled artifacts are only derived-from-public data (accelerators from official docs, video playlists).
- **YouTube ToS:** embed-only playback; API quota budgeted (curation batched per accelerator, not per user).
- **Secrets/config:** pydantic-settings + `.env`; no secrets in repo.

## 8. Dependencies & prerequisites to line up early

| Item | Needed by | Action |
|---|---|---|
| YouTube Data API key (quota tier ok for batch curation) | 3.1 | create GCP project early in Phase 2 |
| Apple Developer + Play Console accounts | 2.2 (dev builds), 4.3 (distribution) | start Apple enrollment early (slow) |
| CIRE registration + exam date for founder | Dogfood gate | registration confirms the real deadline the plan builds toward |
| CLI proxy: confirm all four model ids + embeddings route + JSON-schema output support | 0.2/0.3 | smoke test is task 0.2 |
| Answer key for practice exam (verify whether in corpus or separate download) | 0.5 | check `resources/` PDFs' later pages; fetch from CIRO if separate |

## 9. Out of plan (unchanged from PRD)

Essay grading, OSCE, marketplace/verified packs, social/leagues, candidate web app, i18n, payments-before-validation.

---

*Next action when approved: execute Phase 0, task 0.1.*
