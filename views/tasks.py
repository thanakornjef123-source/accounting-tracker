"""Task list: filter, pick one, move it forward or hand it to someone else."""

from __future__ import annotations

import streamlit as st

from tracker import repo
from tracker import workflow as wf

from .common import Ctx, days_text, flash, fmt_date, page_header

ALL = "ทั้งหมด"


def render(ctx: Ctx) -> None:
    page_header("งาน", ctx)
    conn = ctx.conn
    tasks = repo.tasks(conn, ctx.period)
    staff = repo.staff(conn)
    workers = staff[staff["role"] != wf.ADMIN]

    f1, f2, f3, f4 = st.columns([2, 3, 2, 2])
    default_person = ctx.user_name if ctx.role == wf.ACCOUNTANT else ALL
    person = f1.selectbox("ผู้รับผิดชอบ", [ALL, *workers["name"]],
                          index=[ALL, *workers["name"]].index(default_person), key="task_person")
    statuses = f2.multiselect("สถานะ", list(wf.STATUS_LABELS), default=list(wf.OPEN_STATUSES),
                              format_func=wf.STATUS_LABELS.get, key="task_status")
    task_type = f3.selectbox("ประเภทงาน", [ALL, *wf.TASK_ORDER], key="task_type")
    search = f4.text_input("ค้นหาลูกค้า", key="task_search")

    view = tasks
    if person != ALL:
        view = view[view["assignee"] == person]
    if statuses:
        view = view[view["status"].isin(statuses)]
    if task_type != ALL:
        view = view[view["task_type"] == task_type]
    if search:
        view = view[view["client"].str.contains(search, case=False, regex=False)]
    view = view.reset_index(drop=True)

    st.caption(f"{len(view)} งาน · คลิกที่แถวเพื่อดูรายละเอียดและอัปเดตสถานะ")
    table = view.assign(
        due=view["due_date"].map(fmt_date),
        left=[("⚠️ " if o else "") + days_text(int(d)) if s != wf.DONE else "-"
                   for d, o, s in zip(view["days_left"], view["overdue"], view["status"])],
    )
    event = st.dataframe(
        table[["client", "task_type", "assignee", "status_label", "due", "left"]],
        column_config={
            "client": st.column_config.TextColumn("ลูกค้า", width="large"),
            "task_type": "งาน",
            "assignee": "ผู้รับผิดชอบ",
            "status_label": "สถานะ",
            "due": "กำหนด",
            "left": "เหลือเวลา",
        },
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key="task_table",
        height=420,
    )

    selected = event.selection.rows if event and event.selection else []
    if not selected:
        return
    _detail(ctx, int(view.iloc[selected[0]]["id"]), workers)


def _detail(ctx: Ctx, task_id: int, workers) -> None:
    conn = ctx.conn
    t = repo.task(conn, task_id)
    c = repo.client(conn, t["client_id"])
    row = repo.tasks(conn, t["period"]).set_index("id").loc[task_id]

    st.divider()
    st.subheader(f"{t['task_type']} · {c['name']}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("สถานะ", row["status_label"])
    m2.metric("กำหนด", fmt_date(t["due_date"]),
              days_text(int(row["days_left"])) if t["status"] != wf.DONE else None, delta_color="off", delta_arrow="off")
    m3.metric("ผู้รับผิดชอบ", row["assignee"])
    m4.metric("ผู้รับผิดชอบสำรอง", repo.staff_name(conn, c["backup_staff_id"]) if c["backup_staff_id"] else "-")

    if not repo.docs_complete(conn, c["id"], t["period"]) and t["status"] in (wf.TODO, wf.DOING):
        st.warning("ลูกค้ารายนี้ยังส่งเอกสารเดือนนี้ไม่ครบ ดูรายละเอียดที่หน้าเอกสารลูกค้า")
    returned = repo.last_return_comment(conn, task_id)
    if returned and t["status"] == wf.DOING:
        st.error(f"เจ้าของส่งกลับให้แก้: {returned}")
    if c["notes"]:
        st.info(f"ข้อควรระวังของลูกค้ารายนี้: {c['notes']}")

    actions = wf.available_actions(t["task_type"], t["status"], ctx.role)
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("##### อัปเดตสถานะ")
        if not actions:
            if t["status"] == wf.REVIEW and not ctx.is_owner:
                st.caption("งานนี้รอเจ้าของตรวจ เปลี่ยนผู้ใช้เป็นเจ้าของที่แถบด้านซ้ายเพื่ออนุมัติ")
            elif t["status"] == wf.DONE:
                st.caption("งานนี้เสร็จแล้ว")
            else:
                st.caption("บทบาทนี้อัปเดตงานบัญชีไม่ได้")
        comment = ""
        if any(a.needs_comment for a in actions):
            comment = st.text_input("เหตุผลที่ส่งกลับ (ถ้าส่งกลับ)", key=f"comment_{task_id}")
        cols = st.columns(max(len(actions), 1))
        for col, action in zip(cols, actions):
            if col.button(action.label, key=f"{action.key}_{task_id}", width="stretch",
                          type="primary" if not action.needs_comment else "secondary"):
                try:
                    message = repo.act_on_task(conn, task_id, action.key, ctx.user_id, comment)
                except wf.WorkflowError as exc:
                    st.error(str(exc))
                else:
                    flash(f"{action.label}: {t['task_type']} · {c['name']}")
                    if message:
                        flash(f"แจ้งลูกค้าอัตโนมัติ: {message}", "info")
                    st.rerun()

    with right:
        st.markdown("##### มอบหมายงาน")
        if t["status"] == wf.DONE:
            st.caption("งานที่เสร็จแล้วเปลี่ยนผู้รับผิดชอบไม่ได้")
        elif not ctx.is_owner:
            st.caption("เจ้าของเป็นผู้ย้ายงานระหว่างพนักงาน")
        else:
            names = workers.set_index("id")["name"]
            new_id = st.selectbox("ย้ายงานไปให้", names.index.tolist(), format_func=names.get,
                                  index=names.index.tolist().index(t["assignee_id"]), key=f"assign_{task_id}")
            if st.button("ย้ายงาน", key=f"reassign_{task_id}", disabled=new_id == t["assignee_id"]):
                repo.reassign_task(conn, task_id, int(new_id), ctx.user_id)
                flash(f"ย้ายงานไปให้ {names[new_id]} แล้ว")
                st.rerun()

    history = repo.task_events(conn, task_id)
    if not history.empty:
        with st.expander("ประวัติการเปลี่ยนแปลง"):
            history["action"] = history["action"].map(
                lambda k: wf.ACTIONS[k].label if k in wf.ACTIONS else "ย้ายงาน")
            history["at"] = history["at"].map(fmt_date)
            st.dataframe(history[["at", "actor", "action", "comment"]],
                         column_config={"at": "วันที่", "actor": "ผู้ทำ", "action": "การกระทำ",
                                        "comment": "หมายเหตุ"},
                         hide_index=True, width="stretch")
