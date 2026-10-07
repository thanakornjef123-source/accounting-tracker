"""Queries and changes against the tracker database.

Every function takes an open connection. Functions that change data commit
before returning so each user action is one transaction.
"""

from __future__ import annotations

import functools
import os
import re
import sqlite3
import tempfile
import threading
from datetime import date

import pandas as pd

from . import workflow as wf
from .deadlines import EFILING, FormRule, filing_deadline, nominal_day_in_filing_month
from .i18n import date_text, period_text, translate
from .periods import thai_date, thai_label

DOC_MISSING, DOC_RECEIVED, DOC_RESUBMIT = "missing", "received", "resubmit"
DOC_STATUS_LABELS = {
    DOC_MISSING: "ยังไม่ได้รับ",
    DOC_RECEIVED: "ได้รับแล้ว",
    DOC_RESUBMIT: "ต้องขอใหม่",
}
DOC_CHANNELS = ("LINE", "อีเมล", "กระดาษ", "ลูกค้ามาส่งเอง")

EVENT_DOCS_COMPLETE = "docs_complete"
EVENT_DOCS_REMINDER = "docs_reminder"
EVENT_FILED = "filed"
EVENT_REPORT_SENT = "report_sent"
EVENT_LABELS = {
    EVENT_DOCS_COMPLETE: "ได้รับเอกสารครบ",
    EVENT_DOCS_REMINDER: "เตือนส่งเอกสาร",
    EVENT_FILED: "ยื่นภาษีแล้ว",
    EVENT_REPORT_SENT: "ส่งรายงานแล้ว",
}


# ---------------------------------------------------------------- one writer at a time

_LOCK = threading.RLock()


def locked(fn):
    """Serialise functions that change data: every browser session shares one connection."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _LOCK:
            return fn(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------- settings

def get_setting(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


@locked
def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def today(conn: sqlite3.Connection) -> date:
    """The app's working date. Stored so the demo data never goes stale."""
    value = get_setting(conn, "today")
    return date.fromisoformat(value) if value else date.today()


def filing_method(conn: sqlite3.Connection) -> str:
    return get_setting(conn, "filing_method", EFILING) or EFILING


def internal_day(conn: sqlite3.Connection, key: str, default: int) -> int:
    return int(get_setting(conn, key, str(default)) or default)


# ---------------------------------------------------------------- reference data

def staff(conn: sqlite3.Connection, include_inactive: bool = False) -> pd.DataFrame:
    where = "" if include_inactive else "WHERE active = 1"
    return pd.read_sql_query(f"SELECT id, name, role, active FROM staff {where} ORDER BY id", conn)


def staff_name(conn: sqlite3.Connection, staff_id: int) -> str:
    row = conn.execute("SELECT name FROM staff WHERE id = ?", (staff_id,)).fetchone()
    return row["name"] if row else "-"


def staff_role(conn: sqlite3.Connection, staff_id: int) -> str:
    row = conn.execute("SELECT role FROM staff WHERE id = ?", (staff_id,)).fetchone()
    return row["role"] if row else ""


def holidays(conn: sqlite3.Connection) -> list[date]:
    return [date.fromisoformat(r["day"]) for r in conn.execute("SELECT day FROM holidays ORDER BY day")]


def holidays_df(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query("SELECT day, name FROM holidays ORDER BY day", conn)


@locked
def replace_holidays(conn: sqlite3.Connection, rows: list[tuple[str, str]]) -> None:
    conn.execute("DELETE FROM holidays")
    conn.executemany("INSERT INTO holidays (day, name) VALUES (?, ?)", rows)
    conn.commit()


def rules(conn: sqlite3.Connection) -> dict[str, FormRule]:
    return {
        r["form"]: FormRule(r["form"], r["paper_day"], r["efiling_day"])
        for r in conn.execute("SELECT form, paper_day, efiling_day FROM deadline_rules")
    }


@locked
def update_rule(conn: sqlite3.Connection, form: str, paper_day: int, efiling_day: int) -> None:
    conn.execute(
        "UPDATE deadline_rules SET paper_day = ?, efiling_day = ? WHERE form = ?",
        (paper_day, efiling_day, form),
    )
    conn.commit()


# ---------------------------------------------------------------- clients

def clients(conn: sqlite3.Connection, include_inactive: bool = False) -> pd.DataFrame:
    where = "" if include_inactive else "WHERE c.active = 1"
    return pd.read_sql_query(
        f"""
        SELECT c.id, c.name, c.business_type, c.vat_registered, c.has_employees,
               c.channel, c.contact, c.primary_staff_id, c.backup_staff_id, c.notes, c.active,
               p.name AS primary_staff, b.name AS backup_staff
        FROM clients c
        JOIN staff p ON p.id = c.primary_staff_id
        LEFT JOIN staff b ON b.id = c.backup_staff_id
        {where}
        ORDER BY c.name
        """,
        conn,
    )


def client(conn: sqlite3.Connection, client_id: int) -> sqlite3.Row:
    return conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()


def client_doc_types(conn: sqlite3.Connection, client_id: int) -> list[str]:
    return [r["doc_type"] for r in conn.execute(
        "SELECT doc_type FROM client_doc_types WHERE client_id = ? ORDER BY doc_type", (client_id,))]


def client_forms(conn: sqlite3.Connection, client_id: int) -> list[str]:
    return [r["form"] for r in conn.execute(
        "SELECT form FROM client_forms WHERE client_id = ? ORDER BY form", (client_id,))]


@locked
def update_client(
    conn: sqlite3.Connection,
    client_id: int,
    *,
    primary_staff_id: int,
    backup_staff_id: int | None,
    channel: str,
    contact: str,
    notes: str,
) -> None:
    if backup_staff_id == primary_staff_id:
        raise ValueError("ผู้รับผิดชอบหลักและสำรองต้องเป็นคนละคน")
    validate_contact(channel, contact)
    conn.execute(
        """UPDATE clients SET primary_staff_id = ?, backup_staff_id = ?, channel = ?,
           contact = ?, notes = ? WHERE id = ?""",
        (primary_staff_id, backup_staff_id, channel, contact.strip(), notes.strip(), client_id),
    )
    conn.commit()


# ---------------------------------------------------------------- periods

def periods(conn: sqlite3.Connection) -> list[str]:
    return [r["period"] for r in conn.execute(
        "SELECT DISTINCT period FROM tasks ORDER BY period DESC")]


def is_demo(conn: sqlite3.Connection) -> bool:
    return get_setting(conn, "demo") == "1"


@locked
def ensure_period(conn: sqlite3.Connection) -> None:
    """Make sure at least one period exists: the month before today's date."""
    if not periods(conn):
        from .periods import add_months, period_of
        open_period(conn, add_months(period_of(today(conn)), -1))


@locked
def rename_staff(conn: sqlite3.Connection, staff_id: int, name: str) -> None:
    name = " ".join(name.split())
    if not name:
        raise ValueError("ต้องใส่ชื่อพนักงาน")
    if conn.execute("SELECT 1 FROM staff WHERE name = ? AND active = 1 AND id != ?", (name, staff_id)).fetchone():
        raise ValueError("มีพนักงานชื่อนี้อยู่แล้ว")
    conn.execute("UPDATE staff SET name = ? WHERE id = ?", (name, staff_id))
    conn.commit()


@locked
def open_period(conn: sqlite3.Connection, period: str) -> int:
    """Create the document checklist and tasks for every client. Idempotent.

    Returns the number of tasks created.
    """
    method = filing_method(conn)
    hol = holidays(conn)
    form_rules = rules(conn)
    bookkeeping_due = nominal_day_in_filing_month(period, internal_day(conn, "bookkeeping_day", 10), hol)
    report_due = nominal_day_in_filing_month(period, internal_day(conn, "report_day", 28), hol)

    created = 0
    for c in conn.execute("SELECT id, primary_staff_id FROM clients WHERE active = 1").fetchall():
        for doc_type in client_doc_types(conn, c["id"]):
            conn.execute(
                "INSERT OR IGNORE INTO documents (client_id, period, doc_type) VALUES (?, ?, ?)",
                (c["id"], period, doc_type),
            )
        plan = [(wf.BOOKKEEPING, bookkeeping_due)]
        plan += [
            (form, filing_deadline(period, form_rules[form], method, hol))
            for form in client_forms(conn, c["id"])
        ]
        plan.append((wf.CLIENT_REPORT, report_due))
        for task_type, due in plan:
            cur = conn.execute(
                """INSERT OR IGNORE INTO tasks (client_id, period, task_type, assignee_id, due_date)
                   VALUES (?, ?, ?, ?, ?)""",
                (c["id"], period, task_type, c["primary_staff_id"], due.isoformat()),
            )
            created += cur.rowcount
    conn.commit()
    return created


# ---------------------------------------------------------------- documents

def documents(conn: sqlite3.Connection, period: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT d.id, d.client_id, c.name AS client, d.doc_type, d.status,
               d.channel, d.received_on, d.note
        FROM documents d JOIN clients c ON c.id = d.client_id
        WHERE d.period = ? AND c.active = 1
        ORDER BY c.name, d.doc_type
        """,
        conn,
        params=(period,),
    )


def document_summary(conn: sqlite3.Connection, period: str) -> pd.DataFrame:
    """One row per client: how many documents are outstanding."""
    return pd.read_sql_query(
        """
        SELECT c.id AS client_id, c.name AS client, s.name AS primary_staff,
               COUNT(d.id) AS required,
               SUM(d.status = 'received') AS received,
               SUM(d.status = 'missing') AS missing,
               SUM(d.status = 'resubmit') AS resubmit,
               GROUP_CONCAT(CASE WHEN d.status != 'received' THEN d.doc_type END, ', ') AS outstanding
        FROM clients c
        JOIN staff s ON s.id = c.primary_staff_id
        JOIN documents d ON d.client_id = c.id AND d.period = ?
        WHERE c.active = 1
        GROUP BY c.id
        ORDER BY (COUNT(d.id) - SUM(d.status = 'received')) DESC, c.name
        """,
        conn,
        params=(period,),
    )


def docs_complete(conn: sqlite3.Connection, client_id: int, period: str) -> bool:
    row = conn.execute(
        """SELECT COUNT(*) AS total, SUM(status = 'received') AS ok
           FROM documents WHERE client_id = ? AND period = ?""",
        (client_id, period),
    ).fetchone()
    return row["total"] > 0 and row["ok"] == row["total"]


@locked
def update_documents(
    conn: sqlite3.Connection,
    changes: list[dict],
    actor_id: int | None = None,
) -> list[str]:
    """Apply status/channel/note changes. Returns the notification messages created.

    Each change is ``{"id", "status", "channel", "note"}``. Receiving a document
    requires a channel so every channel lands in one register.
    """
    on = today(conn).isoformat()
    touched: set[tuple[int, str]] = set()
    for ch in changes:
        status = ch["status"]
        if status not in DOC_STATUS_LABELS:
            raise ValueError(f"unknown document status {status!r}")
        channel = ch.get("channel") or None
        if status == DOC_RECEIVED and not channel:
            raise ValueError("ระบุช่องทางที่ได้รับเอกสารด้วย")
        row = conn.execute("SELECT client_id, period, status FROM documents WHERE id = ?", (ch["id"],)).fetchone()
        received_on = on if status == DOC_RECEIVED and row["status"] != DOC_RECEIVED else None
        conn.execute(
            """INSERT INTO doc_events (document_id, actor_id, from_status, to_status, channel, note, at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ch["id"], actor_id, row["status"], status, channel, (ch.get("note") or "").strip(), on),
        )
        conn.execute(
            """UPDATE documents SET status = ?, channel = ?, note = ?,
               received_on = CASE WHEN ? = 'received' THEN COALESCE(?, received_on) ELSE NULL END
               WHERE id = ?""",
            (status, channel, (ch.get("note") or "").strip(), status, received_on, ch["id"]),
        )
        touched.add((row["client_id"], row["period"]))

    messages = []
    for client_id, period in touched:
        if docs_complete(conn, client_id, period) and not _has_event(conn, client_id, period, EVENT_DOCS_COMPLETE):
            messages.append(_notify(
                conn, client_id, period, EVENT_DOCS_COMPLETE,
                f"สำนักงานได้รับเอกสารประจำเดือน {thai_label(period)} ครบแล้ว ขอบคุณค่ะ",
            ))
    conn.commit()
    return messages


@locked
def remind_outstanding(conn: sqlite3.Connection, period: str) -> list[str]:
    """Send one reminder per client that still owes documents."""
    messages = []
    for row in document_summary(conn, period).itertuples():
        if row.required == row.received:
            continue
        messages.append(_notify(
            conn, row.client_id, period, EVENT_DOCS_REMINDER,
            f"เอกสารประจำเดือน {thai_label(period)} ที่สำนักงานยังไม่ได้รับ: {row.outstanding}",
        ))
    conn.commit()
    return messages


# ---------------------------------------------------------------- tasks

TASKS_SQL = """
SELECT t.id, t.client_id, c.name AS client, t.period, t.task_type, t.status,
       t.assignee_id, s.name AS assignee, c.backup_staff_id, t.due_date,
       t.submitted_on, t.approved_on, t.done_on, t.filing_ref
FROM tasks t
JOIN clients c ON c.id = t.client_id
JOIN staff s ON s.id = t.assignee_id
WHERE c.active = 1
"""


def tasks(conn: sqlite3.Connection, period: str | None = None) -> pd.DataFrame:
    sql, params = TASKS_SQL, ()
    if period:
        sql += " AND t.period = ?"
        params = (period,)
    df = pd.read_sql_query(sql + " ORDER BY t.due_date, c.name", conn, params=params)
    return _decorate_tasks(df, today(conn))


def _decorate_tasks(df: pd.DataFrame, on: date) -> pd.DataFrame:
    if df.empty:
        for col in ("status_label", "days_left", "overdue", "waiting_days"):
            df[col] = pd.Series(dtype="object")
        return df
    due = pd.to_datetime(df["due_date"]).dt.date
    df["status_label"] = [wf.status_label(t, s) for t, s in zip(df["task_type"], df["status"])]
    df["days_left"] = [(d - on).days for d in due]
    df["overdue"] = (df["days_left"] < 0) & (df["status"] != wf.DONE)
    submitted = pd.to_datetime(df["submitted_on"]).dt.date
    df["waiting_days"] = [
        (on - s).days if st == wf.REVIEW and pd.notna(s) else None
        for s, st in zip(submitted, df["status"])
    ]
    return df


def task(conn: sqlite3.Connection, task_id: int) -> sqlite3.Row:
    return conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()


@locked
def act_on_task(
    conn: sqlite3.Connection,
    task_id: int,
    action_key: str,
    actor_id: int,
    comment: str = "",
    reference: str = "",
) -> str | None:
    """Move a task through the workflow. Returns a client notification if one was sent."""
    t = task(conn, task_id)
    role = staff_role(conn, actor_id)
    new_status = wf.next_status(t["task_type"], t["status"], action_key, role, comment)
    if not can_act(conn, t, actor_id):
        raise wf.WorkflowError("ทำได้เฉพาะผู้รับผิดชอบหรือผู้สำรองของงานนี้ (เจ้าของทำแทนได้)")
    reference = reference.strip()
    if len(reference) > 40:
        raise ValueError("เลขที่อ้างอิงยาวเกิน 40 ตัวอักษร")
    on = today(conn).isoformat()

    fields = {"status": new_status}
    if new_status == wf.REVIEW:
        fields["submitted_on"] = on
    if action_key == "approve":
        fields["approved_on"] = on
    if action_key == "return":
        fields["submitted_on"] = None
    if action_key == "reopen":
        fields.update(submitted_on=None, approved_on=None, done_on=None, filing_ref="")
    if new_status == wf.DONE:
        fields["done_on"] = on
    if action_key == "file":
        fields["filing_ref"] = reference

    assignments = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE tasks SET {assignments} WHERE id = ?", (*fields.values(), task_id))
    conn.execute(
        """INSERT INTO task_events (task_id, actor_id, action, from_status, to_status, comment, at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (task_id, actor_id, action_key, t["status"], new_status, comment.strip(), on),
    )

    message = None
    if new_status == wf.DONE and wf.is_tax_form(t["task_type"]):
        message = _notify(
            conn, t["client_id"], t["period"], EVENT_FILED,
            f"สำนักงานยื่นแบบ {t['task_type']} ประจำเดือน {thai_label(t['period'])} เรียบร้อยแล้ว",
        )
    elif new_status == wf.DONE and t["task_type"] == wf.CLIENT_REPORT:
        message = _notify(
            conn, t["client_id"], t["period"], EVENT_REPORT_SENT,
            f"สำนักงานส่งรายงานประจำเดือน {thai_label(t['period'])} ให้แล้ว",
        )
    conn.commit()
    return message


@locked
def reassign_task(conn: sqlite3.Connection, task_id: int, assignee_id: int, actor_id: int) -> None:
    t = task(conn, task_id)
    if t["status"] == wf.DONE:
        raise ValueError("งานที่เสร็จแล้วเปลี่ยนผู้รับผิดชอบไม่ได้")
    if staff_role(conn, assignee_id) == wf.ADMIN:
        raise ValueError("มอบหมายงานบัญชีให้ธุรการไม่ได้")
    if not conn.execute("SELECT 1 FROM staff WHERE id = ? AND active = 1", (assignee_id,)).fetchone():
        raise ValueError("มอบหมายงานให้พนักงานที่เลิกใช้งานแล้วไม่ได้")
    conn.execute("UPDATE tasks SET assignee_id = ? WHERE id = ?", (assignee_id, task_id))
    conn.execute(
        """INSERT INTO task_events (task_id, actor_id, action, from_status, to_status, comment, at)
           VALUES (?, ?, 'reassign', ?, ?, ?, ?)""",
        (task_id, actor_id, t["status"], t["status"],
         f"{staff_name(conn, t['assignee_id'])} → {staff_name(conn, assignee_id)}", today(conn).isoformat()),
    )
    conn.commit()


def task_events(conn: sqlite3.Connection, task_id: int) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT e.at, s.name AS actor, e.action, e.from_status, e.to_status, e.comment
           FROM task_events e JOIN staff s ON s.id = e.actor_id
           WHERE e.task_id = ? ORDER BY e.id""",
        conn,
        params=(task_id,),
    )


def last_return_comment(conn: sqlite3.Connection, task_id: int) -> str | None:
    row = conn.execute(
        "SELECT comment FROM task_events WHERE task_id = ? AND action = 'return' ORDER BY id DESC LIMIT 1",
        (task_id,),
    ).fetchone()
    return row["comment"] if row else None


def workload(conn: sqlite3.Connection, period: str) -> pd.DataFrame:
    """Open tasks per accountant by status."""
    df = tasks(conn, period)
    df = df[df["status"] != wf.DONE]
    roster = staff(conn)
    roster = roster[roster["role"] == wf.ACCOUNTANT]
    counts = (
        df.groupby(["assignee", "status"]).size().unstack(fill_value=0)
        .reindex(index=roster["name"], columns=list(wf.OPEN_STATUSES), fill_value=0)
    )
    counts.index.name = "assignee"
    return counts


def upcoming_deadlines(conn: sqlite3.Connection, period: str) -> pd.DataFrame:
    """Each tax form's due date this period with how many clients are not yet filed."""
    df = tasks(conn, period)
    df = df[df["task_type"].map(wf.is_tax_form)]
    if df.empty:
        return pd.DataFrame(columns=["task_type", "due_date", "total", "not_filed", "days_left"])
    grouped = df.groupby(["task_type", "due_date"]).agg(
        total=("id", "count"),
        not_filed=("status", lambda s: int((s != wf.DONE).sum())),
        days_left=("days_left", "first"),
    ).reset_index()
    return grouped.sort_values(["due_date", "task_type"])


# ---------------------------------------------------------------- notifications

def _has_event(conn: sqlite3.Connection, client_id: int, period: str, event: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM notifications WHERE client_id = ? AND period = ? AND event = ?",
        (client_id, period, event),
    ).fetchone() is not None


def _notify(conn: sqlite3.Connection, client_id: int, period: str, event: str, message: str) -> str:
    c = client(conn, client_id)
    conn.execute(
        """INSERT INTO notifications (client_id, period, channel, contact, event, message, created_on)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (client_id, period, c["channel"], c["contact"], event, message, today(conn).isoformat()),
    )
    return f"{c['name']} ({c['channel']}): {message}"


def notifications(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT n.id, n.created_on, c.name AS client, n.period, n.channel, n.contact,
                  n.event, n.message
           FROM notifications n JOIN clients c ON c.id = n.client_id
           ORDER BY n.created_on DESC, n.id DESC""",
        conn,
    )


# ---------------------------------------------------------------- client report

def client_report(conn: sqlite3.Connection, client_id: int, period: str, lang: str = "th") -> str:
    """A standard monthly status report built only from data in the system."""
    def tr(text: str, **params) -> str:
        return translate(text, lang, **params)

    def day(iso) -> str:
        return date_text(date.fromisoformat(iso), lang) if isinstance(iso, str) and iso else "-"

    c = client(conn, client_id)
    docs = documents(conn, period)
    docs = docs[docs["client_id"] == client_id]
    t = tasks(conn, period)
    t = t[t["client_id"] == client_id]

    lines = [
        f"# {tr('รายงานสถานะงานประจำเดือน')} {period_text(period, lang)}",
        "",
        f"**{tr('ลูกค้า')}:** {tr(c['name'])}  ",
        f"**{tr('ผู้รับผิดชอบ')}:** {tr(staff_name(conn, c['primary_staff_id']))}  ",
        f"**{tr('วันที่ออกรายงาน')}:** {date_text(today(conn), lang)}",
        "",
        f"## {tr('เอกสารที่ได้รับ')}",
        "",
        f"| {tr('เอกสาร')} | {tr('สถานะ')} | {tr('ช่องทาง')} | {tr('วันที่รับ')} |",
        "|---|---|---|---|",
    ]
    for d in docs.itertuples():
        channel = tr(d.channel) if isinstance(d.channel, str) and d.channel else "-"
        lines.append(f"| {tr(d.doc_type)} | {tr(DOC_STATUS_LABELS[d.status])} | {channel} | {day(d.received_on)} |")
    lines += ["", f"## {tr('การยื่นแบบภาษี')}", "",
              f"| {tr('แบบ')} | {tr('กำหนดยื่น')} | {tr('สถานะ')} | {tr('วันที่ยื่น')} | {tr('เลขที่อ้างอิง')} |",
              "|---|---|---|---|---|"]
    for r in t[t["task_type"].map(wf.is_tax_form)].itertuples():
        lines.append(f"| {tr(r.task_type)} | {day(r.due_date)} | {tr(r.status_label)} | {day(r.done_on)} | "
                     f"{r.filing_ref or '-'} |")

    outstanding = [tr(x) for x in docs[docs["status"] != DOC_RECEIVED]["doc_type"]]
    lines += ["", f"## {tr('สิ่งที่ต้องดำเนินการต่อ')}", ""]
    if outstanding:
        lines.append(f"- {tr('รบกวนส่งเอกสารที่ยังขาด')}: {', '.join(outstanding)}")
    pending = t[(t["status"] != wf.DONE) & t["task_type"].map(wf.is_tax_form)]
    for r in pending.itertuples():
        lines.append(f"- {tr('สำนักงานกำลังดำเนินการ')} {tr(r.task_type)} ({tr('กำหนดยื่น')} {day(r.due_date)})")
    if not outstanding and pending.empty:
        lines.append(f"- {tr('ไม่มีรายการที่ต้องดำเนินการ งานประจำเดือนนี้เสร็จครบแล้ว')}")
    lines += ["", f"_{tr('รายงานนี้สร้างจากระบบติดตามงานโดยอัตโนมัติ')}_"]
    return "\n".join(lines)


@locked
def recompute_due_dates(conn: sqlite3.Connection, period: str) -> int:
    """Re-apply deadline rules, filing method and holidays to the period's open tasks."""
    method = filing_method(conn)
    hol = holidays(conn)
    form_rules = rules(conn)
    due_by_type = {
        wf.BOOKKEEPING: nominal_day_in_filing_month(period, internal_day(conn, "bookkeeping_day", 10), hol),
        wf.CLIENT_REPORT: nominal_day_in_filing_month(period, internal_day(conn, "report_day", 28), hol),
    }
    for form, rule in form_rules.items():
        due_by_type[form] = filing_deadline(period, rule, method, hol)
    changed = 0
    for task_type, due in due_by_type.items():
        cur = conn.execute(
            """UPDATE tasks SET due_date = ? WHERE period = ? AND task_type = ?
               AND status != 'done' AND due_date != ?""",
            (due.isoformat(), period, task_type, due.isoformat()),
        )
        changed += cur.rowcount
    conn.commit()
    return changed


# ---------------------------------------------------------------- who may act, and input checks

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LINE_RE = re.compile(r"^\S{2,40}$")
CLIENT_CHANNELS = ("LINE", "อีเมล")


def validate_contact(channel: str, contact: str) -> None:
    contact = contact.strip()
    if not contact:
        raise ValueError("ต้องใส่ LINE ID หรืออีเมลของลูกค้า")
    if channel == "อีเมล" and not EMAIL_RE.match(contact):
        raise ValueError("รูปแบบอีเมลไม่ถูกต้อง")
    if channel == "LINE" and not LINE_RE.match(contact):
        raise ValueError("LINE ID ต้องไม่มีช่องว่าง และยาว 2-40 ตัวอักษร")


def can_act(conn: sqlite3.Connection, task_row, actor_id: int) -> bool:
    """The owner may act on any task; an accountant only on tasks they or their backup own."""
    role = staff_role(conn, actor_id)
    if role == wf.OWNER:
        return True
    if role != wf.ACCOUNTANT:
        return False
    backup = client(conn, task_row["client_id"])["backup_staff_id"]
    return actor_id in (task_row["assignee_id"], backup)


# ---------------------------------------------------------------- document history

def document_events(conn: sqlite3.Connection, client_id: int, period: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT e.at, COALESCE(s.name, '-') AS actor, d.doc_type, e.from_status, e.to_status,
                  COALESCE(e.channel, '') AS channel, e.note
           FROM doc_events e
           JOIN documents d ON d.id = e.document_id
           LEFT JOIN staff s ON s.id = e.actor_id
           WHERE d.client_id = ? AND d.period = ?
           ORDER BY e.id DESC""",
        conn,
        params=(client_id, period),
    )


# ---------------------------------------------------------------- client records

def default_doc_types(vat: bool, employees: bool) -> list[str]:
    docs = ["รายการเดินบัญชีธนาคาร", "บิล/ใบเสร็จค่าใช้จ่าย"]
    docs += ["ใบกำกับภาษีซื้อ", "ใบกำกับภาษีขาย"] if vat else ["ใบแจ้งหนี้/ใบเสร็จขาย"]
    if employees:
        docs.append("สรุปเงินเดือนพนักงาน")
    return docs


def default_forms(vat: bool, employees: bool, pays_individuals: bool) -> list[str]:
    forms = ["ภ.ง.ด.53"]
    if employees:
        forms.append("ภ.ง.ด.1")
    if pays_individuals:
        forms.append("ภ.ง.ด.3")
    if vat:
        forms.append("ภ.พ.30")
    return forms


def known_doc_types(conn: sqlite3.Connection) -> list[str]:
    found = {r["doc_type"] for r in conn.execute("SELECT DISTINCT doc_type FROM client_doc_types")}
    return sorted(found | set(default_doc_types(True, True)) | set(default_doc_types(False, False)))


def _check_staff_pair(conn: sqlite3.Connection, primary_staff_id: int, backup_staff_id: int | None) -> None:
    if backup_staff_id == primary_staff_id:
        raise ValueError("ผู้รับผิดชอบหลักและสำรองต้องเป็นคนละคน")
    for staff_id in (primary_staff_id, backup_staff_id):
        if staff_id is None:
            continue
        row = conn.execute("SELECT role, active FROM staff WHERE id = ?", (staff_id,)).fetchone()
        if not row or not row["active"] or row["role"] != wf.ACCOUNTANT:
            raise ValueError("ผู้รับผิดชอบต้องเป็นพนักงานบัญชีที่ยังใช้งานอยู่")


@locked
def add_client(
    conn: sqlite3.Connection,
    *,
    name: str,
    business_type: str,
    vat_registered: bool,
    has_employees: bool,
    pays_individuals: bool,
    channel: str,
    contact: str,
    primary_staff_id: int,
    backup_staff_id: int | None,
    notes: str = "",
) -> int:
    """Create a client with the standard documents and tax forms, and add them to the open period."""
    name = " ".join(name.split())
    if not name:
        raise ValueError("ต้องใส่ชื่อลูกค้า")
    if channel not in CLIENT_CHANNELS:
        raise ValueError("ช่องทางแจ้งเตือนต้องเป็น LINE หรืออีเมล")
    validate_contact(channel, contact)
    _check_staff_pair(conn, primary_staff_id, backup_staff_id)
    try:
        cur = conn.execute(
            """INSERT INTO clients (name, business_type, vat_registered, has_employees, channel, contact,
                   primary_staff_id, backup_staff_id, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, business_type.strip() or "-", int(vat_registered), int(has_employees), channel,
             contact.strip(), primary_staff_id, backup_staff_id, notes.strip()),
        )
    except sqlite3.IntegrityError:
        conn.rollback()
        raise ValueError("มีลูกค้าชื่อนี้อยู่แล้ว") from None
    client_id = int(cur.lastrowid)
    conn.executemany("INSERT INTO client_doc_types (client_id, doc_type) VALUES (?, ?)",
                     [(client_id, d) for d in default_doc_types(vat_registered, has_employees)])
    conn.executemany("INSERT INTO client_forms (client_id, form) VALUES (?, ?)",
                     [(client_id, f) for f in default_forms(vat_registered, has_employees, pays_individuals)])
    conn.commit()
    _open_latest_period(conn)
    return client_id


def _open_latest_period(conn: sqlite3.Connection) -> None:
    existing = periods(conn)
    if existing:
        open_period(conn, existing[0])
    else:  # a blank office: the very first client opens the month before today
        from .periods import add_months, period_of
        open_period(conn, add_months(period_of(today(conn)), -1))


@locked
def update_client_profile(
    conn: sqlite3.Connection,
    client_id: int,
    *,
    business_type: str,
    vat_registered: bool,
    has_employees: bool,
    forms: list[str],
    doc_types: list[str],
) -> None:
    """Change what a client sends and files. New items appear in the latest period; items that were
    removed disappear from it only if nobody has started them, so no recorded work is lost."""
    from .deadlines import TAX_FORMS

    if not doc_types:
        raise ValueError("ต้องเลือกเอกสารที่ลูกค้าต้องส่งอย่างน้อย 1 รายการ")
    if any(f not in TAX_FORMS for f in forms):
        raise ValueError("แบบภาษีที่เลือกไม่ถูกต้อง")
    old_forms, old_docs = set(client_forms(conn, client_id)), set(client_doc_types(conn, client_id))
    conn.execute(
        "UPDATE clients SET business_type = ?, vat_registered = ?, has_employees = ? WHERE id = ?",
        (business_type.strip() or "-", int(vat_registered), int(has_employees), client_id),
    )
    conn.execute("DELETE FROM client_forms WHERE client_id = ?", (client_id,))
    conn.executemany("INSERT INTO client_forms (client_id, form) VALUES (?, ?)", [(client_id, f) for f in forms])
    conn.execute("DELETE FROM client_doc_types WHERE client_id = ?", (client_id,))
    conn.executemany("INSERT INTO client_doc_types (client_id, doc_type) VALUES (?, ?)",
                     [(client_id, d) for d in doc_types])

    latest = (periods(conn) or [None])[0]
    if latest:
        for form in old_forms - set(forms):
            conn.execute("DELETE FROM tasks WHERE client_id = ? AND period = ? AND task_type = ? AND status = 'todo'",
                         (client_id, latest, form))
        for doc in old_docs - set(doc_types):
            ids = [r["id"] for r in conn.execute(
                "SELECT id FROM documents WHERE client_id = ? AND period = ? AND doc_type = ? AND status = 'missing'",
                (client_id, latest, doc))]
            for doc_id in ids:
                conn.execute("DELETE FROM doc_events WHERE document_id = ?", (doc_id,))
                conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    _open_latest_period(conn)


@locked
def set_client_active(conn: sqlite3.Connection, client_id: int, active: bool) -> None:
    """Stop (or resume) working for a client. Nothing is deleted, so history and reports survive."""
    conn.execute("UPDATE clients SET active = ? WHERE id = ?", (int(active), client_id))
    conn.commit()
    if active:
        _open_latest_period(conn)


# ---------------------------------------------------------------- staff

@locked
def add_staff(conn: sqlite3.Connection, name: str, role: str) -> int:
    name = " ".join(name.split())
    if not name:
        raise ValueError("ต้องใส่ชื่อพนักงาน")
    if role not in wf.ROLE_LABELS:
        raise ValueError("บทบาทไม่ถูกต้อง")
    if conn.execute("SELECT 1 FROM staff WHERE name = ? AND active = 1", (name,)).fetchone():
        raise ValueError("มีพนักงานชื่อนี้อยู่แล้ว")
    cur = conn.execute("INSERT INTO staff (name, role) VALUES (?, ?)", (name, role))
    conn.commit()
    return int(cur.lastrowid)


@locked
def set_staff_active(conn: sqlite3.Connection, staff_id: int, active: bool) -> None:
    if not active:
        role = staff_role(conn, staff_id)
        if role == wf.OWNER and conn.execute(
                "SELECT COUNT(*) FROM staff WHERE role = 'owner' AND active = 1 AND id != ?", (staff_id,)
        ).fetchone()[0] == 0:
            raise ValueError("ต้องมีเจ้าของที่ใช้งานอยู่อย่างน้อย 1 คน")
        clients_n = conn.execute(
            "SELECT COUNT(*) FROM clients WHERE active = 1 AND (primary_staff_id = ? OR backup_staff_id = ?)",
            (staff_id, staff_id)).fetchone()[0]
        if clients_n:
            raise wf.WorkflowError("ยังเป็นผู้รับผิดชอบหลักหรือสำรองของลูกค้า {n} ราย ย้ายลูกค้าให้คนอื่นก่อน",
                                   n=str(clients_n))
        tasks_n = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE assignee_id = ? AND status != 'done'", (staff_id,)).fetchone()[0]
        if tasks_n:
            raise wf.WorkflowError("ยังมีงานที่ยังไม่เสร็จ {n} งาน ย้ายงานให้คนอื่นก่อน", n=str(tasks_n))
    conn.execute("UPDATE staff SET active = ? WHERE id = ?", (int(active), staff_id))
    conn.commit()


# ---------------------------------------------------------------- backup

def backup_bytes(conn: sqlite3.Connection) -> bytes:
    """A consistent copy of the whole database, as the bytes of a SQLite file."""
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "backup.db")
        target = sqlite3.connect(path)
        try:
            with _LOCK:
                conn.backup(target)
        finally:
            target.close()
        with open(path, "rb") as handle:
            return handle.read()
