"""Owner's review queue, ordered by what is due first, with how long each has waited."""

from __future__ import annotations

import streamlit as st

from tracker import repo
from tracker import workflow as wf

from .common import Ctx, days_text, flash, fmt_date, page_header


def render(ctx: Ctx) -> None:
    page_header("รออนุมัติ", ctx)
    conn = ctx.conn
    tasks = repo.tasks(conn, ctx.period)
    queue = tasks[tasks["status"] == wf.REVIEW].sort_values(["due_date", "waiting_days"], ascending=[True, False])
    approved = tasks[tasks["status"] == wf.APPROVED]

    c1, c2, c3 = st.columns(3)
    c1.metric("รอตรวจ", f"{len(queue)} งาน")
    c2.metric("ค้างนานสุด", f"{int(queue['waiting_days'].max())} วัน" if not queue.empty else "-")
    c3.metric("ครบกำหนดภายใน 3 วัน", f"{int((queue['days_left'] <= 3).sum())} งาน")

    if not ctx.is_owner:
        st.info("หน้านี้สำหรับเจ้าของ เลือก 'ใช้งานในฐานะ' เป็นเจ้าของที่แถบด้านซ้ายเพื่ออนุมัติหรือส่งกลับ")

    if queue.empty:
        st.success("ไม่มีงานรอตรวจ")
    for row in queue.itertuples():
        with st.container(border=True):
            info, actions = st.columns([3, 2])
            urgent = "🔴 " if row.days_left <= 3 else ""
            info.markdown(f"**{urgent}{row.task_type}** · {row.client}")
            info.caption(
                f"ส่งโดย {row.assignee} · รอมา {int(row.waiting_days)} วัน · "
                f"กำหนด {fmt_date(row.due_date)} ({days_text(int(row.days_left))})"
            )
            if not ctx.is_owner:
                continue
            reason = actions.text_input("เหตุผลถ้าส่งกลับ", key=f"why_{row.id}", label_visibility="collapsed",
                                        placeholder="เหตุผลถ้าส่งกลับ")
            a, b = actions.columns(2)
            if a.button("อนุมัติ", key=f"ok_{row.id}", type="primary", width="stretch"):
                repo.act_on_task(conn, row.id, "approve", ctx.user_id)
                flash(f"อนุมัติแล้ว: {row.task_type} · {row.client}")
                st.rerun()
            if b.button("ส่งกลับ", key=f"back_{row.id}", width="stretch"):
                try:
                    repo.act_on_task(conn, row.id, "return", ctx.user_id, reason)
                except wf.WorkflowError as exc:
                    st.error(str(exc))
                else:
                    flash(f"ส่งกลับให้ {row.assignee} แก้แล้ว", "warning")
                    st.rerun()

    if not approved.empty:
        st.subheader("อนุมัติแล้ว รอพนักงานยื่น")
        st.dataframe(
            approved.assign(due=approved["due_date"].map(fmt_date),
                            left=approved["days_left"].map(lambda d: days_text(int(d))))
            [["client", "task_type", "assignee", "due", "left"]],
            column_config={"client": "ลูกค้า", "task_type": "แบบ", "assignee": "ผู้ยื่น",
                           "due": "กำหนด", "left": "เหลือเวลา"},
            hide_index=True,
            width="stretch",
        )
