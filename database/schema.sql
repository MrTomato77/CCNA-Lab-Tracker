PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS labs (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL,
    file_path   TEXT DEFAULT NULL,
    docs_path   TEXT DEFAULT NULL
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

-- Binary asset store: makes the DB the single portable source of truth.
-- Lab PDFs, quiz images, and Packet Tracer .pka files live here as BLOBs so
-- the whole dataset moves with labs.db (no separate docs/, data/, labs/ dirs,
-- no machine-specific absolute paths). Populated by scripts/bundle_assets.py.
CREATE TABLE IF NOT EXISTS assets (
    kind         TEXT NOT NULL,           -- 'pdf' | 'image' | 'pka'
    name         TEXT NOT NULL,           -- 'LAB-01.pdf' | 'Q-0001-0.png' | 'LAB-01.pka'
    content_type TEXT NOT NULL,
    bytes        BLOB NOT NULL,
    PRIMARY KEY (kind, name)
);
