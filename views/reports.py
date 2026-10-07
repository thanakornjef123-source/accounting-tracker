"""Standard monthly client report generated from data in the system."""

from __future__ import annotations

import streamlit as st

from tracker import repo
from tracker import workflow as wf

from .common import Ctx, flash, lang, page_header, period_label, t


def render(ctx: Ctx) -> None:
    page_header("รายงานลูกค้า", ctx)
    conn = ctx.conn
    clients = repo.clients(conn).set_index("id")
    tasks = repo.tasks(conn, ctx.period)
    report_tasks = tasks[tasks["task_type"] == wf.CLIENT_REPORT].set_index("client_id")

    sent = int((report_tasks["status"] == wf.DONE).sum())
    st.caption(t("ส่งรายงานรอบนี้แล้ว {sent} / {total} ราย · ทุกรายใช้แม่แบบเดียวกัน",
                 sent=sent, total=len(report_tasks)))

    def label(client_id: int) -> str:
        status = report_tasks.at[client_id, "status"] if client_id in report_tasks.index else None
        state = t("ส่งแล้ว") if status == wf.DONE else t("ยังไม่ส่ง")
        return f"{t(clients.at[client_id, 'name'])}  ·  {state}"

    client_id = st.selectbox(t("ลูกค้า"), clients.index.tolist(), format_func=label, key="report_client")
    report = repo.client_report(conn, client_id, ctx.period, lang())

    with st.container(border=True):
        st.markdown(report)

    a, b = st.columns(2)
    a.download_button(
        t("ดาวน์โหลดรายงาน (.md)"),
        report,
        file_name=f"report_{ctx.period}_{client_id:02d}.md",
        mime="text/markdown",
        width="stretch",
    )
    if client_id not in report_tasks.index:
        return
    task = report_tasks.loc[client_id]
    if task["status"] == wf.DONE:
        b.button(t("ส่งรายงานแล้ว"), disabled=True, width="stretch")
    elif ctx.role == wf.ADMIN:
        b.button(t("พนักงานบัญชีหรือเจ้าของเป็นผู้ส่ง"), disabled=True, width="stretch")
    elif b.button(t("บันทึกว่าส่งรายงานให้ลูกค้าแล้ว"), type="primary", width="stretch"):
        task_id = int(task["id"])
        if task["status"] == wf.TODO:
            repo.act_on_task(conn, task_id, "start", ctx.user_id)
        message = repo.act_on_task(conn, task_id, "complete", ctx.user_id)
        flash(t("บันทึกการส่งรายงาน {period} แล้ว", period=period_label(ctx.period)))
        if message:
            flash(t("แจ้งลูกค้าอัตโนมัติ: {message}", message=message), "info")
        st.rerun()
