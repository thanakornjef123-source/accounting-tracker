"""SQLite connection and schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS staff (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('owner', 'accountant', 'admin')),
    active        INTEGER NOT NULL DEFAULT 1,
    password_hash TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS clients (
    id               INTEGER PRIMARY KEY,
    name             TEXT NOT NULL UNIQUE,
    business_type    TEXT NOT NULL,
    vat_registered   INTEGER NOT NULL DEFAULT 0,
    has_employees    INTEGER NOT NULL DEFAULT 0,
    channel          TEXT NOT NULL CHECK (channel IN ('LINE', 'อีเมล')),
    contact          TEXT NOT NULL,
    primary_staff_id INTEGER NOT NULL REFERENCES staff(id),
    backup_staff_id  INTEGER REFERENCES staff(id),
    notes            TEXT NOT NULL DEFAULT '',
    active           INTEGER NOT NULL DEFAULT 1
);

-- Documents each client must send every month
CREATE TABLE IF NOT EXISTS client_doc_types (
    client_id INTEGER NOT NULL REFERENCES clients(id),
    doc_type  TEXT NOT NULL,
    PRIMARY KEY (client_id, doc_type)
);

-- Monthly tax returns each client files
CREATE TABLE IF NOT EXISTS client_forms (
    client_id INTEGER NOT NULL REFERENCES clients(id),
    form      TEXT NOT NULL,
    PRIMARY KEY (client_id, form)
);

CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY,
    client_id   INTEGER NOT NULL REFERENCES clients(id),
    period      TEXT NOT NULL,
    doc_type    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'missing'
                CHECK (status IN ('missing', 'received', 'resubmit')),
    channel     TEXT,
    received_on TEXT,
    note        TEXT NOT NULL DEFAULT '',
    UNIQUE (client_id, period, doc_type)
);

CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY,
    client_id    INTEGER NOT NULL REFERENCES clients(id),
    period       TEXT NOT NULL,
    task_type    TEXT NOT NULL,
    assignee_id  INTEGER NOT NULL REFERENCES staff(id),
    status       TEXT NOT NULL DEFAULT 'todo'
                 CHECK (status IN ('todo', 'doing', 'review', 'approved', 'done')),
    due_date     TEXT NOT NULL,
    submitted_on TEXT,
    approved_on  TEXT,
    done_on      TEXT,
    filing_ref   TEXT NOT NULL DEFAULT '',
    UNIQUE (client_id, period, task_type)
);

CREATE TABLE IF NOT EXISTS task_events (
    id          INTEGER PRIMARY KEY,
    task_id     INTEGER NOT NULL REFERENCES tasks(id),
    actor_id    INTEGER NOT NULL REFERENCES staff(id),
    action      TEXT NOT NULL,
    from_status TEXT,
    to_status   TEXT,
    comment     TEXT NOT NULL DEFAULT '',
    at          TEXT NOT NULL
);

-- Who changed which document and when
CREATE TABLE IF NOT EXISTS doc_events (
    id          INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    actor_id    INTEGER REFERENCES staff(id),
    from_status TEXT NOT NULL,
    to_status   TEXT NOT NULL,
    channel     TEXT,
    note        TEXT NOT NULL DEFAULT '',
    at          TEXT NOT NULL
);

-- Outbox of client notifications (simulated: nothing is actually sent)
CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY,
    client_id  INTEGER NOT NULL REFERENCES clients(id),
    period     TEXT NOT NULL,
    channel    TEXT NOT NULL,
    contact    TEXT NOT NULL,
    event      TEXT NOT NULL,
    message    TEXT NOT NULL,
    created_on TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS deadline_rules (
    form        TEXT PRIMARY KEY,
    paper_day   INTEGER NOT NULL CHECK (paper_day BETWEEN 1 AND 28),
    efiling_day INTEGER NOT NULL CHECK (efiling_day BETWEEN 1 AND 28)
);

CREATE TABLE IF NOT EXISTS holidays (
    day  TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


# Columns added after the first release, for databases created by an older version
MIGRATIONS = [
    ("staff", "active", "INTEGER NOT NULL DEFAULT 1"),
    ("staff", "password_hash", "TEXT NOT NULL DEFAULT ''"),
    ("clients", "active", "INTEGER NOT NULL DEFAULT 1"),
    ("tasks", "filing_ref", "TEXT NOT NULL DEFAULT ''"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column, definition in MIGRATIONS:
        have = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    conn.commit()


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")  # readers do not block the writer
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def is_empty(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT COUNT(*) FROM staff").fetchone()[0] == 0
