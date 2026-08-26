# Ace — Concept

**One-liner:** Ace is an agentic mobile app that owns your entire exam prep — upload your study materials, tell it your exam date, and it plans, drills, measures, and re-plans every day until you pass.

---

## The problem

Professional exam candidates (accounting, project management, tech certifications, nursing, law) face the same three failures:

1. **No plan, just materials.** They have a 900-page textbook, a syllabus PDF, and 11 weeks. Nobody turns that into "what do I do for 45 minutes today?"
2. **Static practice.** Question banks (UWorld, Kaplan, Quizlet decks) don't adapt. Candidates grind questions on topics they already know and avoid the ones they're weak in.
3. **No feedback on readiness.** Most candidates walk into the exam hall with no calibrated sense of whether they'd pass today. Anxiety fills the gap.

The stakes are high (career progression, salary bands, licensure), the deadlines are hard, and the willingness to pay is proven — this is one of the few consumer education segments where people reliably spend money.

## The solution: an accountability agent, not a chatbot tutor

Every prep app now has "AI explanations." That is table stakes, not a product. Ace's differentiator is that the agent **owns the prep cycle end to end**:

### The Ace Loop

1. **Onboard** — name your exam (*any* exam — there is no supported-exam gate), set the exam date, upload your own materials (PDF/EPUB: textbooks, syllabus, notes, past questions you legally own). The agent takes it from there.
2. **Diagnose** — a calibrated diagnostic test maps your baseline across the syllabus.
3. **Plan** — the agent builds a study plan *backwards from exam day*: topics sequenced by weight, weakness, and spaced-repetition science, sized to your available hours.
4. **Drill** — daily adaptive sessions in mixed media: a short agent-built micro-lesson on today's topic, a curated short YouTube video when one earns its place, then practice questions generated from and grounded in *your* materials — in the same question formats your actual exam uses — with explanations that cite the exact page/section they came from.
5. **Measure** — a live **Readiness Score** per topic and overall, built from multiple signals — drill accuracy, timed mocks, confidence calibration (how sure you said you were vs. how right you were), spaced-recall checks, and video comprehension checks — updated after every session.
6. **Re-plan** — the agent continuously reshuffles the remaining weeks: more reps on weak topics, taper before exam day, timed full mock exams at the right milestones.

The user's only job is to show up for today's session. Ace decides what today's session is.

## Content strategy (the real moat question)

Official question banks are copyrighted, and purely LLM-invented questions drift off-syllabus and are occasionally wrong — unacceptable when someone's career is on the line. Ace's answer:

- **Any exam, by design.** Ace never says "exam not supported." The user uploads whatever materials they have for whatever exam they face; the agent derives everything from there — the topic tree (parsed from a syllabus document when one is uploaded, inferred from tables of contents and content structure when not), the question-type profile, and the plan. Exams Ace has seen before (starting with CIRE) get cached topic trees, format profiles, and pooled video playlists as *accelerators* — never as a gate.
- **User-uploaded materials are the source of truth.** All generated questions and explanations are RAG-grounded in the user's own documents, with citations. This sidesteps licensing entirely (same move as ReadAPage) and keeps content on-syllabus by construction.
- **Format-faithful questions.** During ingestion, Ace detects question-bearing content in the uploads (past-question papers, end-of-chapter exercises) and builds a **question-type profile** of the exam along two dimensions: *format* (MCQ, true/false, fill-in-the-gap, matching, calculations/workings, essay prompts — mix, house style, command verbs, option counts, mark weightings) and *cognitive level* (remember / understand / apply / analyze — so an all-MCQ exam like CIRE still gets the right blend of recall, calculation, and scenario questions). Real extracted questions are served back verbatim as drills — they're the user's own materials, private to them — and newly generated questions mirror the detected formats and style, so practice feels like the actual paper.
- **Agent-built lessons, same grounding rule.** The agent also *builds* content — micro-lessons, revision sheets, flashcards — but always synthesized from the user's materials with citations. Where the uploads don't cover a syllabus topic, Ace flags the gap and suggests what to find, rather than inventing content.
- **Curated video layer.** For each topic, the agent curates short (≤ ~15 min), high-quality YouTube videos — public content, embedded in-app via the official player (never downloaded or re-hosted), filtered for length, credibility, and relevance, and followed by a quick comprehension check. Different explanation, zero licensing cost, and a welcome break from reading.
- **Confidence gating.** Questions the generator can't ground to a source passage are discarded, never shown.
- **Later:** verified, human-reviewed question packs per exam vertical as a premium layer; possible partnerships with tuition houses.

## Make it fun (gamification, adult-toned)

Exam prep is a grind; the app that wins is the one candidates *want* to open. Ace layers Duolingo-style mechanics tuned for professionals — motivating, never childish:

- **Streaks & daily quests** — today's session framed as a small, completable quest ("Clear 12 questions in Company Law; keep the 9-day streak").
- **XP and topic mastery badges** — visible progress per syllabus topic; badges map to real milestones ("Corporate Reporting: Mastered").
- **Mock exams as boss fights** — timed milestone mocks framed as the challenge they are, with a proper score-report payoff.
- **The journey map** — the whole plan visualized as a path from Day 0 to exam day, so every session visibly moves you forward.

Single-player only at first — the competition is the exam, not other users. Leaderboards/leagues stay deferred until the core loop proves itself.

## Beachhead

Launch deep on one vertical at a time, not broad.

- **POC (decided 2026-07-15): the CIRE exam** — the **Canadian Investment Regulatory Exam** from **CIRO** (Canadian Investment Regulatory Organization). The founder is candidate #1 — taking the certification ahead of the Quantoptimus launch — so the POC cycle is a true dogfood: Ace's first full exam cycle is run by its builder, with real stakes. Official seed materials are already in `resources/`: the January 2025 syllabus (110 MCQs, 2 hours, proctored, 9 weighted elements, learning outcomes tagged Remember/Understand/Apply/Analyze), a practice exam with stable item IDs, and CIRO's study guidance.
- **Scale verticals (post-POC): ICAN / ACCA** (professional accounting) — huge candidate volume in Nigeria and across Africa, hard multi-stage exams, strong resit/repeat-purchase dynamics, MCQ-heavy early stages that fit the engine. PMP and AWS certifications are strong alternates.

## Business model

- **Pay per exam cycle**, not open-ended subscription: "Ace until your exam date" — e.g. ₦-denominated locally, USD internationally. Matches how candidates think and spend.
- Churn-by-success is a feature: passed candidates are testimonials and referral engines.
- Later: premium verified question packs, resit discounts, employer/tuition-house B2B seats.

## Why this, why now, why us

- Agentic planning loops (plan → act → measure → re-plan) are now reliable enough to run a multi-week program autonomously.
- We already have the building blocks from prior projects: LangGraph agent orchestration (SME Operations Agent), PDF/EPUB ingestion and paced daily sessions (ReadAPage).
- Exam prep is deadline-driven — urgency does the marketing.

## Name

**Ace** — to ace an exam. Short, verb-able ("Ace it"), works globally.
