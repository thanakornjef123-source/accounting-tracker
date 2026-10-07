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
from tracker.i18n import DEFAULT_LANG, LANG_NAMES, LANGS, date_text, period_text, translate
from tracker.periods import add_months

DB_PATH = Path(os.environ.get("TRACKER_DB", Path(__file__).resolve().parent.parent / "data" / "tracker.db"))


# ---------------------------------------------------------------- language

def lang() -> str:
    value = st.session_state.get("lang", DEFAULT_LANG)
    return value if value in LANGS else DEFAULT_LANG


def t(text: str, **params) -> str:
    """Translate a Thai source sentence into the language chosen in the sidebar."""
    return translate(text, lang(), **params)


def fmt_date(iso) -> str:
    return date_text(date.fromisoformat(iso), lang()) if isinstance(iso, str) and iso else "-"


def fmt_day(d: date) -> str:
    return date_text(d, lang())


def period_label(period: str) -> str:
    return period_text(period, lang())


def matches(names, query: str):
    """Rows whose name contains ``query``, in the stored Thai text or as shown in the current language."""
    needle = query.lower()
    return names.str.lower().str.contains(needle, regex=False) | names.map(t).str.lower().str.contains(needle, regex=False)


def days_text(days: int) -> str:
    if days < 0:
        return t("เลยกำหนด {n} วัน", n=-days)
    if days == 0:
        return t("ครบกำหนดวันนี้")
    return t("อีก {n} วัน", n=days)


def error_text(exc: Exception) -> str:
    """A translated message for an error raised by the tracker package."""
    if isinstance(exc, wf.WorkflowError):
        return t(exc.key, **{k: t(v) for k, v in exc.params.items()})
    return t(str(exc))


def _init_lang() -> None:
    if "lang" not in st.session_state:
        wanted = st.query_params.get("lang")
        st.session_state["lang"] = wanted if wanted in LANGS else DEFAULT_LANG


def _remember_lang() -> None:
    st.query_params["lang"] = st.session_state["lang"]


# ---------------------------------------------------------------- state

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


def page_header(title: str, ctx: Ctx, caption: str | None = None) -> None:
    st.title(t(title))
    st.caption(
        f"{t('รอบงาน')} {period_label(ctx.period)} · {t('วันที่')} {fmt_day(ctx.today)} · "
        f"{t('ใช้งานในฐานะ')} {t(ctx.user_name)} ({t(wf.ROLE_LABELS[ctx.role])})"
        + (f" · {caption}" if caption else "")
    )
    show_flash()


def _open_period(conn: sqlite3.Connection, period: str) -> None:
    created = repo.open_period(conn, period)
    st.session_state["period"] = period
    flash(t("เปิดรอบงาน {period} แล้ว สร้างงาน {n} รายการ", period=period_label(period), n=created))


def _reset_demo(conn: sqlite3.Connection) -> None:
    seed.reset(conn)
    st.session_state["period"] = repo.periods(conn)[0]
    flash(t("โหลดข้อมูลตัวอย่างใหม่แล้ว"))


def sidebar(conn: sqlite3.Connection) -> Ctx:
    staff = repo.staff(conn)
    with st.sidebar:
        st.radio("Language / ภาษา", LANGS, key="lang", horizontal=True, format_func=LANG_NAMES.get,
                 on_change=_remember_lang)
        st.caption(t("กรณีศึกษา · ข้อมูลทั้งหมดเป็นข้อมูลจำลอง"))

        names = staff.set_index("id")
        user_id = st.selectbox(
            t("ใช้งานในฐานะ"),
            staff["id"].tolist(),
            format_func=lambda i: f"{t(names.at[i, 'name'])} · {t(wf.ROLE_LABELS[names.at[i, 'role']])}",
            key="user_id",
            help=t("ระบบตัวอย่างไม่มีการล็อกอิน เลือกบทบาทเพื่อดูว่าแต่ละคนทำอะไรได้บ้าง"),
        )
        periods = repo.periods(conn)
        if "period" in st.session_state and st.session_state["period"] not in periods:
            del st.session_state["period"]
        period = st.selectbox(t("รอบงาน (เดือนของบัญชี)"), periods, format_func=period_label, key="period")

        with st.expander(t("ตั้งค่าเดโม")):
            current = repo.today(conn)
            new_today = st.date_input(t("วันที่จำลอง"), current,
                                      help=t("ทุกหน้าคำนวณวันค้างและวันเลยกำหนดจากวันนี้"))
            if new_today != current:
                repo.set_setting(conn, "today", new_today.isoformat())
                st.rerun()
            nxt = add_months(periods[0], 1)
            st.button(t("เปิดรอบงาน {period}", period=period_label(nxt)), width="stretch",
                      on_click=_open_period, args=(conn, nxt))
            st.button(t("ล้างข้อมูลและโหลดข้อมูลตัวอย่างใหม่"), width="stretch",
                      on_click=_reset_demo, args=(conn,))

    row = staff.set_index("id").loc[user_id]
    return Ctx(conn, int(user_id), row["name"], row["role"], period, repo.today(conn))
