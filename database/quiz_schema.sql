-- Quiz / practice module schema. Lives in the same labs.db file but shares
-- no foreign keys with the lab tracker tables — both halves can be wiped or
-- rebuilt independently.

CREATE TABLE IF NOT EXISTS questions (
    id              INTEGER PRIMARY KEY,
    pool            TEXT    NOT NULL,
    topic           INTEGER NOT NULL,
    prompt_en       TEXT    NOT NULL,
    prompt_th       TEXT,
    choices_json    TEXT    NOT NULL,
    correct_labels  TEXT    NOT NULL,
    explanation     TEXT,
    source_table    INTEGER,
    image_filenames TEXT    NOT NULL DEFAULT '[]',
    needs_review    INTEGER NOT NULL DEFAULT 0,
    CHECK (pool IN ('A','B','C','D'))
);

CREATE TABLE IF NOT EXISTS quiz_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pool            TEXT    NOT NULL,
    started_at      TEXT    NOT NULL,
    ended_at        TEXT,
    total_seen      INTEGER NOT NULL DEFAULT 0,
    total_correct   INTEGER NOT NULL DEFAULT 0,
    CHECK (pool IN ('A','B','C','D','ALL'))
);

CREATE TABLE IF NOT EXISTS quiz_answers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL,
    question_id     INTEGER NOT NULL,
    selected_labels TEXT    NOT NULL,
    is_correct      INTEGER NOT NULL,
    answered_at     TEXT    NOT NULL,
    FOREIGN KEY (session_id)  REFERENCES quiz_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (question_id) REFERENCES questions(id)
);

CREATE INDEX IF NOT EXISTS idx_questions_pool         ON questions(pool);
CREATE INDEX IF NOT EXISTS idx_questions_needs_review ON questions(needs_review);
CREATE INDEX IF NOT EXISTS idx_answers_session        ON quiz_answers(session_id);

-- v2: per-question mastery state. Separate from `questions` so that a
-- `POST /api/quiz/reset` is a clean DELETE on this table without touching
-- source content. A question is mastered when correct_streak >= 2.
CREATE TABLE IF NOT EXISTS question_progress (
    question_id     INTEGER PRIMARY KEY,
    correct_streak  INTEGER NOT NULL DEFAULT 0,
    last_seen_at    TEXT,
    last_answer_at  TEXT,
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_progress_streak ON question_progress(correct_streak);
