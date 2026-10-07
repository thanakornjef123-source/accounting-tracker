"""SQLite connection and schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS staff (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL,
    role    TEXT NOT NULL CHECK (role IN ('owner', 'accountant', 'admin'))
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
    notes            TEXT NOT NULL DEFAULT ''
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


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def is_empty(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT COUNT(*) FROM staff").fetchone()[0] == 0
