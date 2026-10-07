"""Central client register with per-client working notes."""

from __future__ import annotations

import streamlit as st

from tracker import repo
from tracker import workflow as wf
from tracker.deadlines import TAX_FORMS

from .common import Ctx, error_text, flash, fmt_date, matches, page_header, t

CHANNELS = list(repo.CLIENT_CHANNELS)


def render(ctx: Ctx) -> None:
    page_header("ลูกค้า", ctx)
    conn = ctx.conn
    can_manage = ctx.role in (wf.OWNER, wf.ADMIN)
    if can_manage:
        _add_client_form(ctx)
    show_inactive = st.toggle(t("แสดงลูกค้าที่เลิกใช้งานแล้ว"), key="client_show_inactive")
    clients = repo.clients(conn, include_inactive=show_inactive)

    search = st.text_input(t("ค้นหาชื่อลูกค้า"), key="client_search")
    view = clients[matches(clients["name"], search)] if search else clients
    view = view.reset_index(drop=True)
    event = st.dataframe(
        view.assign(vat=view["vat_registered"].map({1: t("จด"), 0: "-"}),
                    emp=view["has_employees"].map({1: t("มี"), 0: "-"}),
                    business=view["business_type"].map(t), channel_name=view["channel"].map(t),
                    client_name=view["name"].map(t), primary=view["primary_staff"].map(t),
                    state=view["active"].map({1: t("ใช้งานอยู่"), 0: t("เลิกใช้")}),
                    backup=view["backup_staff"].map(lambda n: t(n) if isinstance(n, str) else "-"))
        [["client_name", "business", "vat", "emp", "primary", "backup", "channel_name", "state"]],
        column_config={
            "client_name": st.column_config.TextColumn(t("ลูกค้า"), width="large"),
            "business": t("ประเภทธุรกิจ"),
            "vat": "VAT",
            "emp": t("ลูกจ้าง"),
            "primary": t("ผู้รับผิดชอบหลัก"),
            "backup": t("สำรอง"),
            "channel_name": t("ช่องทางติดต่อ"),
            "state": t("สถานะ"),
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
    if c["primary_staff_id"] not in workers.index or (c["backup_staff_id"] and c["backup_staff_id"] not in workers.index):
        # someone left the office: still show them so the record can be opened and corrected
        everyone = repo.staff(conn, include_inactive=True)
        workers = everyone[everyone["role"] == wf.ACCOUNTANT].set_index("id")["name"]

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
    if not c["active"]:
        st.warning(t("ลูกค้ารายนี้เลิกใช้งานแล้ว ไม่อยู่ในรายการงานและรายงาน ข้อมูลเดิมยังอยู่ครบ"))
        if can_edit and st.button(t("กลับมาใช้งานลูกค้ารายนี้"), key=f"reactivate_{client_id}", type="primary"):
            repo.set_client_active(conn, client_id, True)
            flash(t("กลับมาใช้งาน {name} แล้ว", name=t(c["name"])))
            st.rerun()
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
    if can_edit and c["active"]:
        _profile_form(ctx, c)


def _add_client_form(ctx: Ctx) -> None:
    conn = ctx.conn
    staff = repo.staff(conn)
    workers = staff[staff["role"] == wf.ACCOUNTANT].set_index("id")["name"]
    ids = workers.index.tolist()
    with st.expander(t("เพิ่มลูกค้าใหม่")):
        with st.form("add_client", clear_on_submit=True):
            name = st.text_input(t("ชื่อลูกค้า"), max_chars=120)
            b1, b2 = st.columns(2)
            business = b1.text_input(t("ประเภทธุรกิจ"), placeholder=t("เช่น ค้าปลีก, บริการ"))
            channel = b2.selectbox(t("ช่องทางแจ้งเตือน"), CHANNELS, format_func=t, key="new_client_channel")
            contact = st.text_input(t("LINE ID / อีเมล"), key="new_client_contact")
            k1, k2, k3 = st.columns(3)
            vat = k1.checkbox(t("จดทะเบียนภาษีมูลค่าเพิ่ม (VAT)"))
            employees = k2.checkbox(t("มีลูกจ้าง"))
            individuals = k3.checkbox(t("จ่ายเงินให้บุคคลธรรมดา (หัก ณ ที่จ่าย)"))
            p1, p2 = st.columns(2)
            primary = p1.selectbox(t("ผู้รับผิดชอบหลัก"), ids, format_func=lambda i: t(workers[i]), key="new_client_primary")
            backup = p2.selectbox(t("ผู้รับผิดชอบสำรอง"), ids, index=min(1, len(ids) - 1),
                                  format_func=lambda i: t(workers[i]), key="new_client_backup")
            notes = st.text_area(t("วิธีทำงานและข้อควรระวัง (ให้คนที่รับช่วงต่ออ่านแล้วทำงานต่อได้)"), key="new_client_notes")
            st.caption(t("ระบบสร้างรายการเอกสารและแบบภาษีมาตรฐานจากตัวเลือกด้านบน แก้เพิ่มได้หลังบันทึก "
                         "และเพิ่มงานให้ลูกค้าในรอบงานล่าสุดทันที"))
            if st.form_submit_button(t("เพิ่มลูกค้า"), type="primary"):
                try:
                    repo.add_client(conn, name=name, business_type=business, vat_registered=vat,
                                    has_employees=employees, pays_individuals=individuals, channel=channel,
                                    contact=contact, primary_staff_id=int(primary), backup_staff_id=int(backup),
                                    notes=notes)
                except ValueError as exc:
                    st.error(error_text(exc))
                else:
                    flash(t("เพิ่มลูกค้า {name} แล้ว", name=name.strip()))
                    st.rerun()


def _profile_form(ctx: Ctx, c) -> None:
    conn = ctx.conn
    client_id = int(c["id"])
    with st.expander(t("ปรับโปรไฟล์ภาษีและเอกสารของลูกค้า")):
        with st.form(f"client_profile_{client_id}"):
            business = st.text_input(t("ประเภทธุรกิจ"), c["business_type"])
            k1, k2 = st.columns(2)
            vat = k1.checkbox(t("จดทะเบียนภาษีมูลค่าเพิ่ม (VAT)"), bool(c["vat_registered"]))
            employees = k2.checkbox(t("มีลูกจ้าง"), bool(c["has_employees"]))
            forms = st.multiselect(t("แบบภาษีที่ยื่นทุกเดือน"), list(TAX_FORMS),
                                   default=repo.client_forms(conn, client_id), format_func=t)
            current_docs = repo.client_doc_types(conn, client_id)
            docs = st.multiselect(t("เอกสารที่ต้องส่งทุกเดือน"), repo.known_doc_types(conn),
                                  default=current_docs, format_func=t)
            if st.form_submit_button(t("บันทึกโปรไฟล์"), type="primary"):
                try:
                    repo.update_client_profile(conn, client_id, business_type=business, vat_registered=vat,
                                               has_employees=employees, forms=forms, doc_types=docs)
                except ValueError as exc:
                    st.error(error_text(exc))
                else:
                    flash(t("บันทึกโปรไฟล์ {name} แล้ว", name=t(c["name"])))
                    st.rerun()
        st.caption(t("แบบหรือเอกสารที่เพิ่มใหม่ปรากฏในรอบงานล่าสุดทันที ส่วนที่เอาออกจะหายจากรอบนั้นเฉพาะรายการที่ยังไม่มีใครเริ่มทำ"))
    if st.button(t("เลิกใช้งานลูกค้ารายนี้"), key=f"deactivate_{client_id}"):
        repo.set_client_active(conn, client_id, False)
        flash(t("เลิกใช้งาน {name} แล้ว กลับมาใช้ใหม่ได้ภายหลัง", name=t(c["name"])))
        st.rerun()
    st.caption(t("เลิกใช้งานคือซ่อนลูกค้าออกจากงานและรอบงานใหม่ ไม่ลบข้อมูล"))
