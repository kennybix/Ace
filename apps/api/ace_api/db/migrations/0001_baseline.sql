CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email         text UNIQUE NOT NULL,
    selected_model text NOT NULL DEFAULT 'gpt-5.5',
    timezone      text NOT NULL DEFAULT 'UTC',
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE otp_codes (
    email      text NOT NULL,
    code       text NOT NULL,
    expires_at timestamptz NOT NULL,
    used       boolean NOT NULL DEFAULT false
);
CREATE INDEX ON otp_codes (email);

CREATE TABLE accelerators (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exam_key        text UNIQUE NOT NULL,
    display_name    text NOT NULL,
    topic_tree      jsonb NOT NULL,
    default_profile jsonb NOT NULL,
    planner_defaults jsonb NOT NULL DEFAULT '{}',
    video_playlists jsonb NOT NULL DEFAULT '[]',
    provenance      text NOT NULL DEFAULT '',
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE exams (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id        bigint NOT NULL REFERENCES users(id),
    name_raw       text NOT NULL,
    accelerator_id bigint REFERENCES accelerators(id),
    exam_date      date,
    weekly_hours   int NOT NULL DEFAULT 5,
    status         text NOT NULL DEFAULT 'onboarding',  -- onboarding|ingesting|confirming|active|done
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE documents (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exam_id      bigint NOT NULL REFERENCES exams(id),
    filename     text NOT NULL,
    sha256       text NOT NULL,
    kind         text NOT NULL DEFAULT 'unknown',  -- syllabus|textbook|past_questions|guidance|notes|unknown
    parse_status text NOT NULL DEFAULT 'pending',  -- pending|parsing|parsed|failed
    page_count   int,
    stored_path  text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE topics (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exam_id   bigint REFERENCES exams(id),
    accelerator_id bigint REFERENCES accelerators(id),
    parent_id bigint REFERENCES topics(id),
    code      text NOT NULL,
    title     text NOT NULL,
    weight    real NOT NULL DEFAULT 0,
    cognitive_levels text[] NOT NULL DEFAULT '{}',
    source    text NOT NULL DEFAULT 'syllabus_parsed'  -- syllabus_parsed|toc_inferred|user_edited
);
CREATE INDEX ON topics (exam_id);

CREATE TABLE chunks (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id bigint NOT NULL REFERENCES documents(id),
    exam_id     bigint NOT NULL REFERENCES exams(id),
    page_from   int NOT NULL,
    page_to     int NOT NULL,
    text        text NOT NULL,
    embedding   vector(256),
    topic_id    bigint REFERENCES topics(id)
);
CREATE INDEX ON chunks (exam_id);
CREATE INDEX ON chunks (topic_id);

CREATE TABLE questions (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exam_id         bigint REFERENCES exams(id),
    accelerator_id  bigint REFERENCES accelerators(id),
    topic_id        bigint REFERENCES topics(id),
    source          text NOT NULL,          -- extracted|generated
    format          text NOT NULL,          -- mcq|tf|gap|match|numeric
    cognitive_level text NOT NULL DEFAULT 'understand',
    payload         jsonb NOT NULL,
    citations       jsonb NOT NULL DEFAULT '[]',
    difficulty      real NOT NULL DEFAULT 0.5,
    status          text NOT NULL DEFAULT 'active',  -- active|killed|pending_review
    model_id        text,
    prompt_version  text,
    external_item_id text,
    embedding       vector(256),
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT generated_needs_citations CHECK (source <> 'generated' OR jsonb_array_length(citations) > 0)
);
CREATE INDEX ON questions (exam_id, topic_id, status);

CREATE TABLE question_reports (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    question_id bigint NOT NULL REFERENCES questions(id),
    user_id     bigint NOT NULL REFERENCES users(id),
    reason      text NOT NULL DEFAULT '',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE plans (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exam_id      bigint NOT NULL REFERENCES exams(id),
    version      int NOT NULL,
    rationale    text NOT NULL DEFAULT '',
    status       text NOT NULL DEFAULT 'active',  -- active|superseded
    generated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE plan_items (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id     bigint NOT NULL REFERENCES plans(id),
    day         date NOT NULL,
    topic_ids   bigint[] NOT NULL DEFAULT '{}',
    kind        text NOT NULL DEFAULT 'learn',  -- learn|review|mock|taper
    est_minutes int NOT NULL DEFAULT 40,
    status      text NOT NULL DEFAULT 'pending' -- pending|prepared|done|skipped
);
CREATE INDEX ON plan_items (plan_id, day);

CREATE TABLE lessons (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exam_id        bigint NOT NULL REFERENCES exams(id),
    topic_id       bigint REFERENCES topics(id),
    kind           text NOT NULL DEFAULT 'micro_lesson',  -- micro_lesson|revision_sheet|flashcard
    body           text NOT NULL,
    citations      jsonb NOT NULL DEFAULT '[]',
    model_id       text,
    prompt_version text,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_item_id     bigint REFERENCES plan_items(id),
    exam_id          bigint NOT NULL REFERENCES exams(id),
    kind             text NOT NULL DEFAULT 'daily',  -- daily|diagnostic
    prepared_payload jsonb NOT NULL DEFAULT '{}',
    model_id         text,
    started_at       timestamptz,
    completed_at     timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE mocks (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exam_id            bigint NOT NULL REFERENCES exams(id),
    blueprint          jsonb NOT NULL,
    question_ids       bigint[] NOT NULL DEFAULT '{}',
    started_at         timestamptz,
    submitted_at       timestamptz,
    score              real,
    per_element_scores jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE attempts (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id  bigint REFERENCES sessions(id),
    mock_id     bigint REFERENCES mocks(id),
    question_id bigint NOT NULL REFERENCES questions(id),
    exam_id     bigint NOT NULL REFERENCES exams(id),
    answer      jsonb NOT NULL,
    correct     boolean NOT NULL,
    confidence  text,                     -- sure|think|guess
    ms_taken    int,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON attempts (exam_id, question_id);

CREATE TABLE mastery (
    exam_id       bigint NOT NULL REFERENCES exams(id),
    topic_id      bigint NOT NULL REFERENCES topics(id),
    rating        real NOT NULL DEFAULT 0.3,
    per_format    jsonb NOT NULL DEFAULT '{}',
    per_cognitive jsonb NOT NULL DEFAULT '{}',
    n_attempts    int NOT NULL DEFAULT 0,
    updated_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (exam_id, topic_id)
);

CREATE TABLE readiness_snapshots (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exam_id   bigint NOT NULL REFERENCES exams(id),
    day       date NOT NULL DEFAULT CURRENT_DATE,
    composite real NOT NULL,
    signals   jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE review_queue (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exam_id     bigint NOT NULL REFERENCES exams(id),
    question_id bigint NOT NULL REFERENCES questions(id),
    due_at      timestamptz NOT NULL,
    interval_d  real NOT NULL DEFAULT 1,
    ease        real NOT NULL DEFAULT 2.5,
    UNIQUE (exam_id, question_id)
);

CREATE TABLE videos (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exam_id         bigint REFERENCES exams(id),
    accelerator_id  bigint REFERENCES accelerators(id),
    topic_id        bigint REFERENCES topics(id),
    youtube_id      text NOT NULL,
    title           text NOT NULL DEFAULT '',
    duration_s      int NOT NULL DEFAULT 0,
    curation_score  real NOT NULL DEFAULT 0,
    status          text NOT NULL DEFAULT 'active',  -- active|dead|reported
    last_checked_at timestamptz
);

CREATE TABLE watch_checks (
    video_id     bigint NOT NULL REFERENCES videos(id),
    question_ids bigint[] NOT NULL DEFAULT '{}',
    PRIMARY KEY (video_id)
);

CREATE TABLE xp_events (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id    bigint NOT NULL REFERENCES users(id),
    amount     int NOT NULL,
    reason     text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE streaks (
    user_id          bigint PRIMARY KEY REFERENCES users(id),
    current          int NOT NULL DEFAULT 0,
    best             int NOT NULL DEFAULT 0,
    last_active_date date
);

CREATE TABLE badges (
    user_id    bigint NOT NULL REFERENCES users(id),
    badge_key  text NOT NULL,
    awarded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, badge_key)
);
