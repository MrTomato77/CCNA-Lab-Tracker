PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS labs (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL,
    file_path   TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS progress (
    lab_id      TEXT PRIMARY KEY,
    status      TEXT NOT NULL DEFAULT 'not_started'
                CHECK(status IN ('not_started', 'in_progress', 'done')),
    time_spent  INTEGER NOT NULL DEFAULT 0,
    last_opened TEXT DEFAULT NULL,
    FOREIGN KEY (lab_id) REFERENCES labs(id)
);

CREATE TABLE IF NOT EXISTS attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lab_id      TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    duration    INTEGER DEFAULT NULL,
    FOREIGN KEY (lab_id) REFERENCES labs(id)
);
