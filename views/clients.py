"""Central client register with per-client working notes."""

from __future__ import annotations

import streamlit as st

from tracker import repo
from tracker import workflow as wf

from .common import Ctx, flash, fmt_date, page_header


def render(ctx: Ctx) -> None:
    page_header("ลูกค้า", ctx)
    conn = ctx.conn
    clients = repo.clients(conn)

    search = st.text_input("ค้นหาชื่อลูกค้า", key="client_search")
    view = clients[clients["name"].str.contains(search, case=False, regex=False)] if search else clients
    view = view.reset_index(drop=True)
    event = st.dataframe(
        view.assign(vat=view["vat_registered"].map({1: "จด", 0: "-"}),
                    emp=view["has_employees"].map({1: "มี", 0: "-"}))
        [["name", "business_type", "vat", "emp", "primary_staff", "backup_staff", "channel"]],
        column_config={
            "name": st.column_config.TextColumn("ลูกค้า", width="large"),
            "business_type": "ประเภทธุรกิจ",
            "vat": "VAT",
            "emp": "ลูกจ้าง",
            "primary_staff": "ผู้รับผิดชอบหลัก",
            "backup_staff": "สำรอง",
            "channel": "ช่องทางติดต่อ",
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
        st.caption(f"{len(view)} ราย · คลิกที่แถวเพื่อดูและแก้ข้อมูลลูกค้า")
        return
    _detail(ctx, int(view.iloc[selected[0]]["id"]))


def _detail(ctx: Ctx, client_id: int) -> None:
    conn = ctx.conn
    c = repo.client(conn, client_id)
    staff = repo.staff(conn)
    workers = staff[staff["role"] == wf.ACCOUNTANT].set_index("id")["name"]

    st.divider()
    st.subheader(c["name"])
    a, b = st.columns(2)
    a.markdown("**เอกสารที่ต้องส่งทุกเดือน**  \n" + "  \n".join(f"- {d}" for d in repo.client_doc_types(conn, client_id)))
    b.markdown("**แบบภาษีที่ยื่นทุกเดือน**  \n" + "  \n".join(f"- {f}" for f in repo.client_forms(conn, client_id)))

    tasks = repo.tasks(conn, ctx.period)
    mine = tasks[tasks["client_id"] == client_id]
    st.markdown("**สถานะงานรอบนี้**")
    st.dataframe(
        mine.assign(due=mine["due_date"].map(fmt_date))[["task_type", "status_label", "assignee", "due"]],
        column_config={"task_type": "งาน", "status_label": "สถานะ", "assignee": "ผู้รับผิดชอบ", "due": "กำหนด"},
        hide_index=True, width="stretch",
    )

    can_edit = ctx.role in (wf.OWNER, wf.ADMIN)
    with st.form(f"client_form_{client_id}"):
        st.markdown("**ข้อมูลการทำงานกับลูกค้า**")
        f1, f2 = st.columns(2)
        ids = workers.index.tolist()
        primary = f1.selectbox("ผู้รับผิดชอบหลัก", ids, index=ids.index(c["primary_staff_id"]),
                               format_func=workers.get, disabled=not can_edit)
        backup = f2.selectbox("ผู้รับผิดชอบสำรอง", ids,
                              index=ids.index(c["backup_staff_id"]) if c["backup_staff_id"] in ids else 0,
                              format_func=workers.get, disabled=not can_edit)
        f3, f4 = st.columns(2)
        channel = f3.selectbox("ช่องทางแจ้งเตือน", ["LINE", "อีเมล"],
                               index=["LINE", "อีเมล"].index(c["channel"]), disabled=not can_edit)
        contact = f4.text_input("LINE ID / อีเมล", c["contact"], disabled=not can_edit)
        notes = st.text_area(
            "วิธีทำงานและข้อควรระวัง (ให้คนที่รับช่วงต่ออ่านแล้วทำงานต่อได้)", c["notes"], height=120,
        )
        if st.form_submit_button("บันทึก", type="primary"):
            try:
                repo.update_client(conn, client_id, primary_staff_id=int(primary), backup_staff_id=int(backup),
                                   channel=channel, contact=contact, notes=notes)
            except ValueError as exc:
                st.error(str(exc))
            else:
                flash(f"บันทึกข้อมูล {c['name']} แล้ว")
                st.rerun()
    if not can_edit:
        st.caption("พนักงานบัญชีแก้ได้เฉพาะบันทึกข้อควรระวัง ส่วนผู้รับผิดชอบและช่องทางติดต่อให้เจ้าของหรือธุรการแก้")
    st.caption("เปลี่ยนผู้รับผิดชอบหลักมีผลกับงานของรอบที่เปิดใหม่ งานที่มีอยู่แล้วย้ายได้ที่หน้างาน")
