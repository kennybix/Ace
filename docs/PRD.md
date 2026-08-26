# Ace — Product Requirements Document (MVP)

**Status:** Draft v0.5 — 2026-07-15 (v0.3 added question-type profiling and format-faithful generation; v0.4 locked POC vertical = CIRE + user-selectable multi-model LLMs; v0.5 resolves CIRE = Canadian Investment Regulatory Exam (CIRO) with official seed corpus in `resources/`, makes Ace exam-agnostic by design, and adds cognitive-level profiling)
**Companion doc:** [CONCEPT.md](CONCEPT.md)

---

## 1. Goal

Ship a mobile app where a candidate can: pick a supported exam, upload their study materials, take a diagnostic, receive a personalized study plan, complete adaptive daily sessions, and track a Readiness Score through to exam day — with every generated question grounded in and cited to their own materials.

**MVP success statement:** a real candidate uses Ace as their *primary* prep tool for a full exam cycle and reports they would pay for it again.

## 2. Target user & personas

**Persona A — "Resit Rachael" (primary).** 24–35, working full-time, preparing for a professional accounting exam (ICAN/ACCA) she has failed once. Studies nights/weekends. Has the official textbooks as PDFs. Needs structure and confidence more than more content.

**Persona B — "Cert-sprint Chidi."** 25–40, tech worker chasing a certification (PMP, AWS) with a self-imposed 8-week deadline. Time-boxed, metric-driven, wants mock scores and a readiness number.

Both: own smartphones as primary device, materials as PDFs, exam date known in advance, prior experience of unstructured prep failing.

**Candidate #1 (dogfood):** the founder, preparing for the **CIRE exam** (Canadian Investment Regulatory Exam, CIRO) ahead of the Quantoptimus launch. The POC cycle is run end-to-end on this real, personally-staked exam before any external beta.

## 3. Scope

### In (MVP)

| # | Epic | Summary |
|---|------|---------|
| E1 | Onboarding | Free-text exam entry (**any exam — no supported-exam gate**), exam date, weekly study-hours budget, account; known exams matched to cached accelerators |
| E2 | Material ingestion | Upload PDF/EPUB; parse, chunk, embed; map to exam syllabus topics; detect question-bearing content, extract real questions, build the exam's question-type profile |
| E3 | Diagnostic | ~30-question calibrated baseline across syllabus topics |
| E4 | Study plan | Agent-generated plan backwards from exam date; visible & editable |
| E5 | Daily session player | Adaptive drills across the exam's detected question types (MCQ, true/false, fill-in-the-gap, matching, numeric/calculation) + grounded explanations with source citations; spaced repetition |
| E6 | Readiness dashboard | Per-topic and overall Readiness Score, streaks, plan progress |
| E7 | Mock exam mode | Timed full mocks at plan milestones, assembled to the detected format mix and mark weightings, with score report |
| E8 | Agent re-planning | Nightly re-plan from performance data; plan-change notifications |
| E9 | Content builder | Agent-built micro-lessons, revision sheets, flashcards — grounded in user materials with citations |
| E10 | Video curation | Curated short YouTube videos per topic (embedded player), quality-filtered, with watch-checks |
| E11 | Gamification core | XP, streaks, topic mastery badges, daily quests, journey map; adult-toned |
| E12 | Model picker | User-selectable LLM (Opus 4.8, Fable 5, GPT-5.5, GPT-5.6) via the CLI proxy gateway; switchable anytime; config-driven model list |

### Out (explicitly deferred)

- Essay/constructed-response grading; OSCE/practical formats. Detected essay/case-study prompts are still *captured and shown* in final-week revision with a grounded marking-guide outline for self-assessment — Ace just doesn't grade them ("explain it back" concept checks are a Phase 3 stretch, not exam-grade essay marking)
- Verified/marketplace question packs; any licensed third-party content
- Social/community features, leaderboards/leagues (gamification is single-player in MVP)
- Web app for candidates (admin web only), offline-first mode, i18n
- Payments (MVP cycles are free/beta-code gated; billing lands post-validation)

### Exam-agnostic by design

Users upload materials for **any exam**; it is the agent's responsibility to take it from there. There is no supported-exam list gating onboarding. The agent derives the topic tree from the uploads — parsed from a syllabus document when present, inferred from tables of contents and content structure when not — along with the question-type profile and plan. "Known" exams (starting with CIRE) carry cached accelerators: pre-parsed topic tree, default format profile, pooled video playlists. Accelerators improve cold-start quality; their absence never blocks a user.

### POC exam vertical — DECIDED: CIRE (Canadian Investment Regulatory Exam, CIRO)

Dogfooded by the founder (see §2). Official seed corpus in `resources/` (CIRO, January 2025):

- **Syllabus** — exam parameters: 1 paper, **110 MCQs, 2 hours**, proctored (remote or in person), 3 attempts allowed. Nine weighted elements (indicative Qs): regulatory framework 11, prospective client relationships 11, scope of client relationship 17, complaints handling 6, market & company analysis 9, market integrity/trade execution/settlement 13, securities/managed products/mutual funds 21, derivatives 6, conflicts of interest & ethics 16. Learning outcomes per element (e.g. 1.1–1.11, 3.1–3.17) are each tagged with a cognitive level — **Remember / Understand / Apply / Analyze** (cumulative). This is the ready-made CIRE topic tree.
- **Practice exam** — cleanly parseable: stable item IDs (`CIRO_E_0000NN`), numbered stems, four options A–D. Extraction target for the real-question bank and the style anchor set.
- **Study guidance** — CIRO's own prep advice; feeds planner defaults for this exam.

CIRE implication for generation: the format profile is 100% MCQ, so format-faithfulness for CIRE = matching the **cognitive mix** (recall vs. calculation vs. scenario MCQs) and element weights. Scale verticals post-POC: ICAN Foundation + ACCA Applied Knowledge; alternates PMP / AWS SAA.

## 4. Core user journey

1. **Day 0:** Download → pick exam + date + hours/week → upload textbook, past-question & syllabus PDFs → ingestion runs (minutes, with progress), surfacing the detected question-type profile ("Your exam: 60% MCQ, 25% calculations, 15% fill-in-the-gap — confirm?") → take a diagnostic that mirrors that format mix → see baseline topic map → receive plan ("11 weeks, 5 sessions/week, here's why").
2. **Daily:** Notification → open today's quest (~30–45 min, mixed media): a 2–3 min agent-built micro-lesson on the new topic → optionally a curated short video with a 2–3 question watch-check → adaptive drill + spaced-rep review, answering with a confidence tag (sure / think so / guessing) → each answer gets a grounded explanation with a "source: Ch. 4, p. 112" citation tappable to the passage → session ends with topic-score deltas, XP, and streak update.
3. **Weekly:** Readiness Score update + plan adjustments summarized ("Moved 2 extra sessions to Corporate Law — accuracy stuck at 54%") + any new mastery badges.
4. **Milestones:** Timed mock exams ("boss fights") at ~60%, ~85% of plan; final-week taper with revision sheets, flashcard sprints, and an exam-day brief.

## 5. Agent design

Single orchestrated agent (LangGraph) with distinct graph nodes rather than free chat:

- **Ingestion node** — parse (PDF/EPUB), chunk, embed. **Derives the exam's topic tree from the uploads themselves**: if a syllabus document is detected, parse its structure (elements, learning outcomes, weightings, cognitive-level tags — CIRE's syllabus yields all four); otherwise infer a topic tree from tables of contents and content structure, and present it for user confirmation. Every chunk is then mapped to that tree. Additionally detects **question-bearing content** (past-question papers, end-of-chapter exercises, worked examples): extracts each real question (+ answer/solution where present) into a private per-user question bank keyed to stable item IDs where the source provides them, classifies it by **format and cognitive level** (remember/understand/apply/analyze), and aggregates a **question-type profile** for the exam — format mix, cognitive mix, mark weightings, option counts, command-verb style. Profile and topic tree are shown to the user at onboarding for confirmation; both are cached per exam as accelerators for later users of the same exam.
- **Planner node** — constraint-based plan builder: inputs = exam date, hours/week, topic weights (from syllabus), baseline scores; output = dated session schedule. Deterministic core with LLM-assisted sequencing rationale.
- **Question generator node** — RAG-grounded, **format-faithful** generation per topic, driven by the question-type profile. Serving priority: (1) real extracted questions from the user's own uploads, verbatim; (2) generated questions matching the detected formats **and cognitive mix** (for an all-MCQ exam like CIRE: the right blend of recall, calculation, and scenario MCQs, weighted per element), using extracted questions as few-shot style anchors. Auto-gradable types in MVP: MCQ, true/false, fill-in-the-gap, matching, numeric/calculation (tolerance-checked). Detected essay/case-study prompts are stored for revision-sheet self-assessment, not graded. Hard rules unchanged: every generated question must cite ≥1 source chunk; ungroundable questions are discarded (confidence gating); duplicates filtered by embedding similarity (including near-dupes of extracted real questions); difficulty tagged.
- **Content builder node** — micro-lessons (2–3 min reads), revision sheets, and flashcards synthesized from the user's chunks for the day's topic, citations mandatory. If uploads don't cover a topic, emits a "coverage gap" flag to the planner instead of inventing content.
- **Curator node** — per-topic YouTube search (YouTube Data API v3), filtered by duration (≤ ~15 min), engagement quality, channel signal, and relevance (transcript/embedding match to the topic). Output is a per-exam-topic playlist that is **pooled across users** (videos are public content, unlike uploads) and cached; a report button removes bad picks for everyone. Videos play via the official embedded player — never downloaded or re-hosted (YouTube ToS).
- **Explainer node** — answer explanations grounded in the cited chunks only.
- **Assessor node** — updates per-topic mastery from **multiple signals**: drill accuracy (IRT-lite / Elo-style), timed-mock scores, confidence calibration (confidence tag vs. correctness), spaced-recall check results, and video watch-check results. Readiness Score is the weighted composite; the per-signal breakdown is visible to the user. Mastery is also tracked **per question format** ("strong on MCQ, weak on calculations"), and the re-planner uses it — weak formats get more reps, mirroring how the exam will actually test.
- **Re-planner node** — nightly batch: re-scores plan vs. actuals, reshuffles remaining sessions, drafts the user-facing change note.

**Quality bar (non-negotiable):** no generated question or explanation is shown without a source citation. A "report question" action feeds a kill-list; kill rate is a tracked metric.

**Model layer:** every node is model-agnostic — all LLM calls go through one OpenAI-compatible client pointed at the CLI proxy gateway, which provisions **Opus 4.8 (`claude-opus-4-8`), Fable 5 (`claude-fable-5`), GPT-5.5, and GPT-5.6**. The user picks their model in-app and can switch at any time; the choice is stored per user and applies to *subsequent* generation (next nightly batch, on-demand explanations) — existing prepared sessions are not regenerated on switch. Grounding, citation, and confidence-gating rules are enforced identically regardless of model. The available-model list is server config, so adding or retiring a model never requires an app release.

**Cost/latency:** sessions are pre-generated in the nightly batch, not live — the session player reads prepared items, so daily UX has zero LLM latency and generation cost is batchable (and varies with the user's selected model).

## 6. Screens (MVP)

1. Onboarding flow (exam / date / hours)
2. Upload & ingestion status
3. Diagnostic runner
4. Plan overview (calendar + topic view)
5. Today / session player (micro-lesson → optional embedded video + watch-check → questions rendered in format-specific widgets [MCQ, true/false, fill-gap, matching, numeric] with confidence tag → grounded explanation → XP/streak payoff)
6. Readiness dashboard (composite score + per-signal breakdown, topic heat-map, streak, badges, journey map)
7. Mock exam runner ("boss fight" framing) + score report
8. Flashcard sprint (spaced-rep deck for final-week taper)
9. Settings (exam date change, hours change, re-upload, **LLM model picker** — switch anytime, applies to new content)

## 7. Tech stack & local conventions

- **Mobile:** Expo / React Native (TypeScript)
- **Backend:** FastAPI + LangGraph (Python), Postgres + pgvector
- **LLM:** multi-model via the CLI proxy gateway (OpenAI-compatible, **:8317** in dev; proxy provisions prod access too) — Opus 4.8, Fable 5, GPT-5.5, GPT-5.6; user-selectable in-app (E12); model list is server config
- **Local dev conventions:** backend **:8040**, admin web (if/when) **:3030**, Postgres **:5445** (8030/5443/5444 were taken by other local projects)
- **Ingestion:** reuse/extend ReadAPage's PDF/EPUB parsing pipeline where practical
- **Video:** YouTube Data API v3 for curation; official YouTube embedded player (`react-native-youtube-iframe` or equivalent) for playback — no downloading/re-hosting
- **Notifications:** Expo push
- **Repo:** `~/Documents/Projects/Ace` — monorepo (`apps/mobile`, `apps/api`, `docs/`)

## 8. Metrics

| Stage | Metric | MVP target |
|-------|--------|-----------|
| Activation | % of signups completing diagnostic + receiving plan | ≥ 60% |
| Engagement | Sessions completed per user per week | ≥ 4 |
| Engagement | D7 / D30 retention among activated users | 50% / 30% |
| Engagement | Daily quest completion rate (opened → finished) | ≥ 70% |
| Engagement | Video watch-through rate on curated picks | ≥ 60% |
| Quality | Reported-question kill rate | < 2% of served questions |
| Quality | Video report rate on curated picks | < 5% |
| Quality | Readiness Score calibration vs. mock scores | correlation ≥ 0.7 |
| Outcome | Beta cohort self-reported pass rate + would-pay-again | qualitative gate |

## 9. Risks & mitigations

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Generated questions wrong/off-syllabus | **High** — trust is the product | Grounding + citation mandatory; confidence gating; report-question kill-list; spot-check pipeline before beta |
| Users lack good PDFs to upload | High | Syllabus PDFs are public for target exams; publish a "what to upload" guide (explicitly: include past questions); verified packs later |
| Question-type profile wrong (misclassified formats, or uploads contain no past questions) | Medium | Profile shown for user confirmation at onboarding and editable in settings; per-vertical default profile (from public exam format specs) as prior/fallback; per-format mastery flags anomalies |
| Ingestion quality on scanned/image PDFs | Medium | OCR fallback; flag low-quality uploads at ingest time with guidance |
| Plan feels generic → churn | Medium | Re-planner must produce *visible, explained* changes weekly; plan is editable |
| Copyright: users upload pirated content | Medium | ToS: users upload materials they own; content is private per-user, never pooled or redistributed |
| Curated videos are low-quality or subtly wrong | Medium | Multi-factor curation filters; watch-checks catch comprehension gaps; report button prunes the shared playlist; videos supplement, never replace, grounded drills |
| Videos get deleted/region-blocked/monetized with heavy ads | Medium | Nightly availability check on pooled playlists; ≥2 backup picks per topic; degrade gracefully to lesson+drill |
| YouTube ToS / API quota | Low | Embed-only via official player; curation is batched + pooled per exam so API quota scales with topics, not users |
| Gamification feels childish to professionals → tone damage | Medium | Adult-toned copy; badges tied to real syllabus milestones; every mechanic skippable; no leagues in MVP |
| Quality/format drift across the four LLMs | Medium | Grounding + gating are enforced outside the model; per-model kill-rate tracked in the quality dashboard; a model that underperforms gets pulled from the config list |
| Seasonality (exam-cycle demand spikes) | Low (MVP) | Two verticals with offset exam calendars post-MVP |

## 10. Open decisions

1. ~~Vertical~~ **RESOLVED 2026-07-15: POC = CIRE** — Canadian Investment Regulatory Exam (CIRO). Official syllabus, practice exam, and study guidance obtained (`resources/`); no remaining blocker on E2.
1b. **Default LLM for new users** (all four remain selectable): needs a bake-off on CIRE-style generation quality vs. batch cost during Phase 1.
2. **Diagnostic source:** generated-from-materials only, or hand-curated seed set per vertical for calibration quality? (Recommend a small hand-curated seed set — one-time effort, big calibration win.)
3. Readiness Score model: simple weighted composite vs. IRT-lite — start simple, upgrade behind the same UI; signal weights need tuning against mock scores during beta.
4. Video curation refresh cadence: curate once per exam cycle with nightly availability checks (recommended) vs. continuous re-curation.
5. Gamification depth for launch: XP + streaks + badges + quests (recommended) vs. also shipping the journey map in MVP.
6. Beta distribution: TestFlight/Play internal track + beta codes vs. public soft launch.

## 11. Roadmap sketch

- **Phase 0 (docs → skeleton):** parse the three CIRO PDFs in `resources/` into the CIRE accelerator — topic tree (9 elements, learning outcomes with cognitive tags and element weights), default question-type profile, extracted practice-exam question bank; repo scaffold; CLI proxy model routing smoke test (all four models).
- **Phase 1 (engine):** ingestion → syllabus mapping → question extraction + type profiling → grounded format-faithful generation (all five auto-gradable types) + micro-lesson/flashcard generation with gating; video curation pipeline; all CLI-testable before any UI.
- **Phase 2 (loop):** diagnostic, planner, mixed-media session player (lesson → video + watch-check → drill with confidence tags), multi-signal assessor, nightly re-planner.
- **Phase 3 (polish & fun):** readiness dashboard with per-signal breakdown, XP/streaks/badges/quests, journey map, mock "boss fights", flashcard sprints, notifications, exam-day flow. Stretch: "explain it back" concept checks.
- **Phase 4 (POC → beta):** founder runs a full CIRE cycle as the POC gate (real exam, real stakes); fix what the dogfood surfaces; then 20–50 external candidates in one exam cycle; validate §8 gates; then payments.
