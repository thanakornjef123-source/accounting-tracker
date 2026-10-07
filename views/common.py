"""Shared state and small UI helpers for every page."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import streamlit as st

from tracker import db, repo, seed
from tracker import workflow as wf
from tracker.periods import add_months, thai_date, thai_label

DB_PATH = Path(os.environ.get("TRACKER_DB", Path(__file__).resolve().parent.parent / "data" / "tracker.db"))


@st.cache_resource
def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(DB_PATH)
    if db.is_empty(conn):
        seed.seed(conn)
    return conn


@dataclass
class Ctx:
    conn: sqlite3.Connection
    user_id: int
    user_name: str
    role: str
    period: str
    today: date

    @property
    def is_owner(self) -> bool:
        return self.role == wf.OWNER


def flash(message: str, kind: str = "success") -> None:
    st.session_state.setdefault("_flash", []).append((kind, message))


def show_flash() -> None:
    for kind, message in st.session_state.pop("_flash", []):
        getattr(st, kind)(message)


def days_text(days: int) -> str:
    if days < 0:
        return f"เลยกำหนด {-days} วัน"
    if days == 0:
        return "ครบกำหนดวันนี้"
    return f"อีก {days} วัน"


def fmt_date(iso) -> str:
    return thai_date(date.fromisoformat(iso)) if isinstance(iso, str) and iso else "-"


def page_header(title: str, ctx: Ctx, caption: str | None = None) -> None:
    st.title(title)
    st.caption(
        f"รอบงาน {thai_label(ctx.period)} · วันที่ {thai_date(ctx.today)} · "
        f"ใช้งานในฐานะ {ctx.user_name} ({wf.ROLE_LABELS[ctx.role]})"
        + (f" · {caption}" if caption else "")
    )
    show_flash()


def _open_period(conn: sqlite3.Connection, period: str) -> None:
    """Button callback: runs before the page reruns, so it may change the period picker."""
    created = repo.open_period(conn, period)
    st.session_state["period"] = period
    flash(f"เปิดรอบงาน {thai_label(period)} แล้ว สร้างงาน {created} รายการ")


def _reset_demo(conn: sqlite3.Connection) -> None:
    seed.reset(conn)
    st.session_state["period"] = repo.periods(conn)[0]
    flash("โหลดข้อมูลตัวอย่างใหม่แล้ว")


def sidebar(conn: sqlite3.Connection) -> Ctx:
    staff = repo.staff(conn)
    with st.sidebar:
        st.caption("กรณีศึกษา · ข้อมูลทั้งหมดเป็นข้อมูลจำลอง")

        user_id = st.selectbox(
            "ใช้งานในฐานะ",
            staff["id"].tolist(),
            format_func=lambda i: f"{staff.set_index('id').at[i, 'name']} · "
                                  f"{wf.ROLE_LABELS[staff.set_index('id').at[i, 'role']]}",
            key="user_id",
            help="ระบบตัวอย่างไม่มีการล็อกอิน เลือกบทบาทเพื่อดูว่าแต่ละคนทำอะไรได้บ้าง",
        )
        periods = repo.periods(conn)
        period = st.selectbox("รอบงาน (เดือนของบัญชี)", periods, format_func=thai_label, key="period")

        with st.expander("ตั้งค่าเดโม"):
            current = repo.today(conn)
            new_today = st.date_input("วันที่จำลอง", current, help="ทุกหน้าคำนวณวันค้างและวันเลยกำหนดจากวันนี้")
            if new_today != current:
                repo.set_setting(conn, "today", new_today.isoformat())
                st.rerun()
            nxt = add_months(periods[0], 1)
            st.button(f"เปิดรอบงาน {thai_label(nxt)}", width="stretch",
                      on_click=_open_period, args=(conn, nxt))
            st.button("ล้างข้อมูลและโหลดข้อมูลตัวอย่างใหม่", width="stretch",
                      on_click=_reset_demo, args=(conn,))

    row = staff.set_index("id").loc[user_id]
    return Ctx(conn, int(user_id), row["name"], row["role"], period, repo.today(conn))
