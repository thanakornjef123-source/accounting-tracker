"""Task list: filter, pick one, move it forward or hand it to someone else."""

from __future__ import annotations

import streamlit as st

from tracker import repo
from tracker import workflow as wf

from .common import Ctx, days_text, error_text, flash, fmt_date, matches, page_header, t

ALL = "ทั้งหมด"


def _all_or(value: str) -> str:
    return t(value)


def render(ctx: Ctx) -> None:
    page_header("งาน", ctx)
    conn = ctx.conn
    tasks = repo.tasks(conn, ctx.period)
    staff = repo.staff(conn)
    workers = staff[staff["role"] != wf.ADMIN]

    f1, f2, f3, f4 = st.columns([2, 3, 2, 2])
    people = [ALL, *workers["name"]]
    default_person = ctx.user_name if ctx.role == wf.ACCOUNTANT else ALL
    person = f1.selectbox(t("ผู้รับผิดชอบ"), people, index=people.index(default_person),
                          format_func=_all_or, key="task_person")
    statuses = f2.multiselect(t("สถานะ"), list(wf.STATUS_LABELS), default=list(wf.OPEN_STATUSES),
                              format_func=lambda s: t(wf.STATUS_LABELS[s]), key="task_status")
    task_type = f3.selectbox(t("ประเภทงาน"), [ALL, *wf.TASK_ORDER], format_func=_all_or, key="task_type")
    search = f4.text_input(t("ค้นหาลูกค้า"), key="task_search")

    view = tasks
    if person != ALL:
        view = view[view["assignee"] == person]
    if statuses:
        view = view[view["status"].isin(statuses)]
    if task_type != ALL:
        view = view[view["task_type"] == task_type]
    if search:
        view = view[matches(view["client"], search)]
    view = view.reset_index(drop=True)

    st.caption(t("{n} งาน · คลิกที่แถวเพื่อดูรายละเอียดและอัปเดตสถานะ", n=len(view)))
    table = view.assign(
        due=view["due_date"].map(fmt_date),
        left=[("⚠️ " if o else "") + days_text(int(d)) if s != wf.DONE else "-"
              for d, o, s in zip(view["days_left"], view["overdue"], view["status"])],
        task_name=view["task_type"].map(t), client_name=view["client"].map(t), assignee_name=view["assignee"].map(t),
        status_name=view["status_label"].map(t),
    )
    event = st.dataframe(
        table[["client_name", "task_name", "assignee_name", "status_name", "due", "left"]],
        column_config={
            "client_name": st.column_config.TextColumn(t("ลูกค้า"), width="large"),
            "task_name": t("งาน"),
            "assignee_name": t("ผู้รับผิดชอบ"),
            "status_name": t("สถานะ"),
            "due": t("กำหนด"),
            "left": t("เหลือเวลา"),
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
    tk = repo.task(conn, task_id)
    c = repo.client(conn, tk["client_id"])
    row = repo.tasks(conn, tk["period"]).set_index("id").loc[task_id]

    st.divider()
    st.subheader(f"{t(tk['task_type'])} · {t(c['name'])}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(t("สถานะ"), t(row["status_label"]))
    m2.metric(t("กำหนด"), fmt_date(tk["due_date"]),
              days_text(int(row["days_left"])) if tk["status"] != wf.DONE else None,
              delta_color="off", delta_arrow="off")
    m3.metric(t("ผู้รับผิดชอบ"), t(row["assignee"]))
    m4.metric(t("ผู้รับผิดชอบสำรอง"), t(repo.staff_name(conn, c["backup_staff_id"])) if c["backup_staff_id"] else "-")

    if not repo.docs_complete(conn, c["id"], tk["period"]) and tk["status"] in (wf.TODO, wf.DOING):
        st.warning(t("ลูกค้ารายนี้ยังส่งเอกสารเดือนนี้ไม่ครบ ดูรายละเอียดที่หน้าเอกสารลูกค้า"))
    returned = repo.last_return_comment(conn, task_id)
    if returned and tk["status"] == wf.DOING:
        st.error(t("เจ้าของส่งกลับให้แก้: {reason}", reason=returned))
    if c["notes"]:
        st.info(t("ข้อควรระวังของลูกค้ารายนี้: {notes}", notes=t(c["notes"])))

    actions = wf.available_actions(tk["task_type"], tk["status"], ctx.role)
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("##### " + t("อัปเดตสถานะ"))
        if not actions:
            if tk["status"] == wf.REVIEW and not ctx.is_owner:
                st.caption(t("งานนี้รอเจ้าของตรวจ เปลี่ยนผู้ใช้เป็นเจ้าของที่แถบด้านซ้ายเพื่ออนุมัติ"))
            elif tk["status"] == wf.DONE:
                st.caption(t("งานนี้เสร็จแล้ว"))
            else:
                st.caption(t("บทบาทนี้อัปเดตงานบัญชีไม่ได้"))
        comment = ""
        if any(a.needs_comment for a in actions):
            comment = st.text_input(t("เหตุผลที่ส่งกลับ (ถ้าส่งกลับ)"), key=f"comment_{task_id}")
        cols = st.columns(max(len(actions), 1))
        for col, action in zip(cols, actions):
            if col.button(t(action.label), key=f"{action.key}_{task_id}", width="stretch",
                          type="primary" if not action.needs_comment else "secondary"):
                try:
                    message = repo.act_on_task(conn, task_id, action.key, ctx.user_id, comment)
                except wf.WorkflowError as exc:
                    st.error(error_text(exc))
                else:
                    flash(f"{t(action.label)}: {t(tk['task_type'])} · {t(c['name'])}")
                    if message:
                        flash(t("แจ้งลูกค้าอัตโนมัติ: {message}", message=message), "info")
                    st.rerun()

    with right:
        st.markdown("##### " + t("มอบหมายงาน"))
        if tk["status"] == wf.DONE:
            st.caption(t("งานที่เสร็จแล้วเปลี่ยนผู้รับผิดชอบไม่ได้"))
        elif not ctx.is_owner:
            st.caption(t("เจ้าของเป็นผู้ย้ายงานระหว่างพนักงาน"))
        else:
            names = workers.set_index("id")["name"]
            new_id = st.selectbox(t("ย้ายงานไปให้"), names.index.tolist(), format_func=lambda i: t(names[i]),
                                  index=names.index.tolist().index(tk["assignee_id"]), key=f"assign_{task_id}")
            if st.button(t("ย้ายงาน"), key=f"reassign_{task_id}", disabled=new_id == tk["assignee_id"]):
                repo.reassign_task(conn, task_id, int(new_id), ctx.user_id)
                flash(t("ย้ายงานไปให้ {name} แล้ว", name=t(names[new_id])))
                st.rerun()

    history = repo.task_events(conn, task_id)
    if not history.empty:
        with st.expander(t("ประวัติการเปลี่ยนแปลง")):
            history["action"] = history["action"].map(
                lambda k: t(wf.ACTIONS[k].label) if k in wf.ACTIONS else t("ย้ายงาน"))
            history["at"] = history["at"].map(fmt_date)
            history["actor"] = history["actor"].map(t)
            st.dataframe(history[["at", "actor", "action", "comment"]],
                         column_config={"at": t("วันที่"), "actor": t("ผู้ทำ"), "action": t("การกระทำ"),
                                        "comment": t("หมายเหตุ")},
                         hide_index=True, width="stretch")
