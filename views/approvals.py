"""Owner's review queue, ordered by what is due first, with how long each has waited."""

from __future__ import annotations

import streamlit as st

from tracker import repo
from tracker import workflow as wf

from .common import Ctx, days_text, error_text, flash, fmt_date, page_header, t


def render(ctx: Ctx) -> None:
    page_header("รออนุมัติ", ctx)
    conn = ctx.conn
    tasks = repo.tasks(conn, ctx.period)
    queue = tasks[tasks["status"] == wf.REVIEW].sort_values(["due_date", "waiting_days"], ascending=[True, False])
    approved = tasks[tasks["status"] == wf.APPROVED]

    c1, c2, c3 = st.columns(3)
    c1.metric(t("รอตรวจ"), t("{n} งาน", n=len(queue)))
    c2.metric(t("ค้างนานสุด"), t("{n} วัน", n=int(queue["waiting_days"].max())) if not queue.empty else "-")
    c3.metric(t("ครบกำหนดภายใน 3 วัน"), t("{n} งาน", n=int((queue["days_left"] <= 3).sum())))

    if not ctx.is_owner:
        st.info(t("หน้านี้สำหรับเจ้าของ เลือก 'ใช้งานในฐานะ' เป็นเจ้าของที่แถบด้านซ้ายเพื่ออนุมัติหรือส่งกลับ"))

    if queue.empty:
        st.success(t("ไม่มีงานรอตรวจ"))
    for row in queue.itertuples():
        with st.container(border=True):
            info, actions = st.columns([3, 2])
            urgent = "🔴 " if row.days_left <= 3 else ""
            info.markdown(f"**{urgent}{t(row.task_type)}** · {t(row.client)}")
            info.caption(t("ส่งโดย {name} · รอมา {n} วัน · กำหนด {date} ({left})",
                           name=t(row.assignee), n=int(row.waiting_days), date=fmt_date(row.due_date),
                           left=days_text(int(row.days_left))))
            if not ctx.is_owner:
                continue
            reason = actions.text_input(t("เหตุผลถ้าส่งกลับ"), key=f"why_{row.id}", label_visibility="collapsed",
                                        placeholder=t("เหตุผลถ้าส่งกลับ"))
            a, b = actions.columns(2)
            if a.button(t("อนุมัติ"), key=f"ok_{row.id}", type="primary", width="stretch"):
                repo.act_on_task(conn, row.id, "approve", ctx.user_id)
                flash(t("อนุมัติแล้ว: {task} · {client}", task=t(row.task_type), client=t(row.client)))
                st.rerun()
            if b.button(t("ส่งกลับ"), key=f"back_{row.id}", width="stretch"):
                try:
                    repo.act_on_task(conn, row.id, "return", ctx.user_id, reason)
                except wf.WorkflowError as exc:
                    st.error(error_text(exc))
                else:
                    flash(t("ส่งกลับให้ {name} แก้แล้ว", name=t(row.assignee)), "warning")
                    st.rerun()

    if not approved.empty:
        st.subheader(t("อนุมัติแล้ว รอพนักงานยื่น"))
        st.dataframe(
            approved.assign(due=approved["due_date"].map(fmt_date),
                            left=approved["days_left"].map(lambda d: days_text(int(d))),
                            task_name=approved["task_type"].map(t), client=approved["client"].map(t),
                            assignee=approved["assignee"].map(t))
            [["client", "task_name", "assignee", "due", "left"]],
            column_config={"client": t("ลูกค้า"), "task_name": t("แบบ"), "assignee": t("ผู้ยื่น"),
                           "due": t("กำหนด"), "left": t("เหลือเวลา")},
            hide_index=True,
            width="stretch",
        )
