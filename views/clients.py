"""Central client register with per-client working notes."""

from __future__ import annotations

import streamlit as st

from tracker import repo
from tracker import workflow as wf

from .common import Ctx, error_text, flash, fmt_date, matches, page_header, t

CHANNELS = ["LINE", "อีเมล"]


def render(ctx: Ctx) -> None:
    page_header("ลูกค้า", ctx)
    conn = ctx.conn
    clients = repo.clients(conn)

    search = st.text_input(t("ค้นหาชื่อลูกค้า"), key="client_search")
    view = clients[matches(clients["name"], search)] if search else clients
    view = view.reset_index(drop=True)
    event = st.dataframe(
        view.assign(vat=view["vat_registered"].map({1: t("จด"), 0: "-"}),
                    emp=view["has_employees"].map({1: t("มี"), 0: "-"}),
                    business=view["business_type"].map(t), channel_name=view["channel"].map(t),
                    client_name=view["name"].map(t), primary=view["primary_staff"].map(t),
                    backup=view["backup_staff"].map(lambda n: t(n) if isinstance(n, str) else "-"))
        [["client_name", "business", "vat", "emp", "primary", "backup", "channel_name"]],
        column_config={
            "client_name": st.column_config.TextColumn(t("ลูกค้า"), width="large"),
            "business": t("ประเภทธุรกิจ"),
            "vat": "VAT",
            "emp": t("ลูกจ้าง"),
            "primary": t("ผู้รับผิดชอบหลัก"),
            "backup": t("สำรอง"),
            "channel_name": t("ช่องทางติดต่อ"),
        },
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key="client_table",
        height=360,
    )
    selected = event.selection.rows if event and event.selection else []
    if not selected:
        st.caption(t("{n} ราย · คลิกที่แถวเพื่อดูและแก้ข้อมูลลูกค้า", n=len(view)))
        return
    _detail(ctx, int(view.iloc[selected[0]]["id"]))


def _detail(ctx: Ctx, client_id: int) -> None:
    conn = ctx.conn
    c = repo.client(conn, client_id)
    staff = repo.staff(conn)
    workers = staff[staff["role"] == wf.ACCOUNTANT].set_index("id")["name"]

    st.divider()
    st.subheader(t(c["name"]))
    a, b = st.columns(2)
    a.markdown("**" + t("เอกสารที่ต้องส่งทุกเดือน") + "**  \n"
               + "  \n".join(f"- {t(d)}" for d in repo.client_doc_types(conn, client_id)))
    b.markdown("**" + t("แบบภาษีที่ยื่นทุกเดือน") + "**  \n"
               + "  \n".join(f"- {t(f)}" for f in repo.client_forms(conn, client_id)))

    tasks = repo.tasks(conn, ctx.period)
    mine = tasks[tasks["client_id"] == client_id]
    st.markdown("**" + t("สถานะงานรอบนี้") + "**")
    st.dataframe(
        mine.assign(due=mine["due_date"].map(fmt_date), task_name=mine["task_type"].map(t),
                    status_name=mine["status_label"].map(t),
                    assignee_name=mine["assignee"].map(t))[["task_name", "status_name", "assignee_name", "due"]],
        column_config={"task_name": t("งาน"), "status_name": t("สถานะ"), "assignee_name": t("ผู้รับผิดชอบ"),
                       "due": t("กำหนด")},
        hide_index=True, width="stretch",
    )

    can_edit = ctx.role in (wf.OWNER, wf.ADMIN)
    with st.form(f"client_form_{client_id}"):
        st.markdown("**" + t("ข้อมูลการทำงานกับลูกค้า") + "**")
        f1, f2 = st.columns(2)
        ids = workers.index.tolist()
        primary = f1.selectbox(t("ผู้รับผิดชอบหลัก"), ids, index=ids.index(c["primary_staff_id"]),
                               format_func=lambda i: t(workers[i]), disabled=not can_edit)
        backup = f2.selectbox(t("ผู้รับผิดชอบสำรอง"), ids,
                              index=ids.index(c["backup_staff_id"]) if c["backup_staff_id"] in ids else 0,
                              format_func=lambda i: t(workers[i]), disabled=not can_edit)
        f3, f4 = st.columns(2)
        channel = f3.selectbox(t("ช่องทางแจ้งเตือน"), CHANNELS, format_func=t,
                               index=CHANNELS.index(c["channel"]), disabled=not can_edit)
        contact = f4.text_input(t("LINE ID / อีเมล"), c["contact"], disabled=not can_edit)
        notes = st.text_area(
            t("วิธีทำงานและข้อควรระวัง (ให้คนที่รับช่วงต่ออ่านแล้วทำงานต่อได้)"), c["notes"], height=120,
        )
        if st.form_submit_button(t("บันทึก"), type="primary"):
            try:
                repo.update_client(conn, client_id, primary_staff_id=int(primary), backup_staff_id=int(backup),
                                   channel=channel, contact=contact, notes=notes)
            except ValueError as exc:
                st.error(error_text(exc))
            else:
                flash(t("บันทึกข้อมูล {name} แล้ว", name=t(c["name"])))
                st.rerun()
    if not can_edit:
        st.caption(t("พนักงานบัญชีแก้ได้เฉพาะบันทึกข้อควรระวัง ส่วนผู้รับผิดชอบและช่องทางติดต่อให้เจ้าของหรือธุรการแก้"))
    st.caption(t("เปลี่ยนผู้รับผิดชอบหลักมีผลกับงานของรอบที่เปิดใหม่ งานที่มีอยู่แล้วย้ายได้ที่หน้างาน"))
