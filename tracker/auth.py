"""Passwords and sign-in.

Sign-in is optional: the portfolio demo runs without it (anyone can pick a
role). Set the environment variable ``TRACKER_AUTH=1`` to require a name and
password. Passwords are stored only as salted PBKDF2-SHA256 hashes.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
import threading
import time

from . import repo
from . import workflow as wf

ITERATIONS = 240_000
MIN_LENGTH = 8
MAX_FAILURES = 5          # wrong passwords allowed ...
WINDOW_SECONDS = 300      # ... within this time, then the name is locked for the same time

_failures: dict[str, list[float]] = {}
_failures_lock = threading.Lock()


def _key(name: str) -> str:
    return " ".join(name.split()).lower()


def seconds_locked(name: str, now: float | None = None) -> int:
    """How long this name must wait before trying again (0 when it may try now)."""
    now = time.time() if now is None else now
    with _failures_lock:
        recent = [t for t in _failures.get(_key(name), []) if now - t < WINDOW_SECONDS]
        _failures[_key(name)] = recent
        if len(recent) >= MAX_FAILURES:
            return int(WINDOW_SECONDS - (now - recent[0])) + 1
    return 0


def record_failure(name: str, now: float | None = None) -> None:
    with _failures_lock:
        _failures.setdefault(_key(name), []).append(time.time() if now is None else now)


def clear_failures(name: str) -> None:
    with _failures_lock:
        _failures.pop(_key(name), None)


def auth_enabled() -> bool:
    return os.environ.get("TRACKER_AUTH", "").strip().lower() in {"1", "true", "yes", "on"}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def check_strength(password: str) -> None:
    if len(password) < MIN_LENGTH:
        raise ValueError("รหัสผ่านต้องยาวอย่างน้อย 8 ตัวอักษร")
    if password.isdigit() or password.isalpha():
        raise ValueError("รหัสผ่านต้องมีทั้งตัวอักษรและตัวเลข")


@repo.locked
def set_password(conn: sqlite3.Connection, staff_id: int, password: str) -> None:
    check_strength(password)
    conn.execute("UPDATE staff SET password_hash = ? WHERE id = ?", (hash_password(password), staff_id))
    conn.commit()


def authenticate(conn: sqlite3.Connection, name: str, password: str) -> int | None:
    """The staff id when the name and password match an active account, else None."""
    row = conn.execute(
        "SELECT id, password_hash FROM staff WHERE active = 1 AND lower(name) = lower(?)",
        (" ".join(name.split()),),
    ).fetchone()
    # Always do one hash so the time taken does not reveal whether the name exists
    stored = row["password_hash"] if row and row["password_hash"] else hash_password("x")
    ok = verify_password(password, stored)
    return int(row["id"]) if row and row["password_hash"] and ok else None


def owner_needs_setup(conn: sqlite3.Connection) -> bool:
    """True until some active owner has a password: the first visitor then sets it."""
    return conn.execute(
        "SELECT COUNT(*) FROM staff WHERE role = ? AND active = 1 AND password_hash != ''", (wf.OWNER,)
    ).fetchone()[0] == 0


def first_owner_id(conn: sqlite3.Connection) -> int:
    return int(conn.execute(
        "SELECT id FROM staff WHERE role = ? AND active = 1 ORDER BY id LIMIT 1", (wf.OWNER,)).fetchone()["id"])
