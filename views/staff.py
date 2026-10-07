"""Team: add or retire staff and set passwords. Owner only."""

from __future__ import annotations

import streamlit as st

from tracker import auth, repo
from tracker import workflow as wf

from .common import Ctx, error_text, flash, page_header, t


def render(ctx: Ctx) -> None:
    page_header("ทีมงาน", ctx)
    if not ctx.is_owner:
        st.info(t("เจ้าของเป็นผู้จัดการทีมงานและรหัสผ่าน"))
        return
    conn = ctx.conn
    staff = repo.staff(conn, include_inactive=True)
    hashes = {r["id"]: bool(r["password_hash"]) for r in conn.execute("SELECT id, password_hash FROM staff")}

    st.dataframe(
        staff.assign(role_name=staff["role"].map(lambda r: t(wf.ROLE_LABELS[r])),
                     person=staff["name"].map(t),
                     state=staff["active"].map({1: t("ใช้งานอยู่"), 0: t("เลิกใช้")}),
                     has_password=staff["id"].map(lambda i: t("ตั้งแล้ว") if hashes.get(i) else "-"))
        [["person", "role_name", "state", "has_password"]],
        column_config={"person": t("ชื่อ"), "role_name": t("บทบาท"), "state": t("สถานะ"),
                       "has_password": t("รหัสผ่าน")},
        hide_index=True, width="stretch",
    )
    if not auth.auth_enabled():
        st.caption(t("ตอนนี้เปิดให้ใช้งานโดยไม่ล็อกอิน (โหมดเดโม) ตั้ง TRACKER_AUTH=1 เพื่อบังคับให้ใส่ชื่อและรหัสผ่าน"))

    left, right = st.columns(2, gap="large")
    with left:
        st.subheader(t("เพิ่มพนักงาน"))
        with st.form("add_staff", clear_on_submit=True):
            name = st.text_input(t("ชื่อ"), max_chars=60)
            role = st.selectbox(t("บทบาท"), list(wf.ROLE_LABELS), format_func=lambda r: t(wf.ROLE_LABELS[r]),
                                index=1, key="new_staff_role")
            password = st.text_input(t("รหัสผ่านเริ่มต้น (ถ้ามี)"), type="password", key="new_staff_password")
            if st.form_submit_button(t("เพิ่มพนักงาน"), type="primary"):
                try:
                    if password:
                        auth.check_strength(password)
                    staff_id = repo.add_staff(conn, name, role)
                    if password:
                        auth.set_password(conn, staff_id, password)
                except ValueError as exc:
                    st.error(error_text(exc))
                else:
                    flash(t("เพิ่มพนักงาน {name} แล้ว", name=name.strip()))
                    st.rerun()

    with right:
        st.subheader(t("จัดการพนักงาน"))
        ids = staff["id"].tolist()
        names = staff.set_index("id")
        person = st.selectbox(t("พนักงาน"), ids, key="staff_pick",
                              format_func=lambda i: f"{t(names.at[i, 'name'])} · {t(wf.ROLE_LABELS[names.at[i, 'role']])}")
        with st.form("set_password", clear_on_submit=True):
            new_password = st.text_input(t("รหัสผ่านใหม่"), type="password", key="reset_password")
            st.caption(t("อย่างน้อย 8 ตัวอักษร มีทั้งตัวอักษรและตัวเลข"))
            if st.form_submit_button(t("ตั้งรหัสผ่าน")):
                try:
                    auth.set_password(conn, int(person), new_password)
                except ValueError as exc:
                    st.error(error_text(exc))
                else:
                    flash(t("ตั้งรหัสผ่านของ {name} แล้ว", name=t(names.at[person, "name"])))
                    st.rerun()
        with st.form("rename_staff", clear_on_submit=True):
            new_name = st.text_input(t("เปลี่ยนชื่อเป็น"), key="rename_input", max_chars=60)
            if st.form_submit_button(t("เปลี่ยนชื่อ")):
                try:
                    repo.rename_staff(conn, int(person), new_name)
                except ValueError as exc:
                    st.error(error_text(exc))
                else:
                    flash(t("เปลี่ยนชื่อเป็น {name} แล้ว", name=new_name.strip()))
                    st.rerun()
        active = bool(names.at[person, "active"])
        if st.button(t("เลิกใช้งานพนักงานคนนี้") if active else t("กลับมาใช้งานพนักงานคนนี้"), key="staff_toggle"):
            try:
                repo.set_staff_active(conn, int(person), not active)
            except ValueError as exc:
                st.error(error_text(exc))
            else:
                flash(t("เปลี่ยนสถานะของ {name} แล้ว", name=t(names.at[person, "name"])))
                st.rerun()
