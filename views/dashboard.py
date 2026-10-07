"""Overview: what needs attention this period."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from tracker import repo
from tracker import workflow as wf

from . import theme
from .common import Ctx, days_text, fmt_date, page_header, t

STATUS_COLORS = theme.STATUS_COLORS


def render(ctx: Ctx) -> None:
    page_header("ภาพรวม", ctx)
    conn = ctx.conn

    docs = repo.document_summary(conn, ctx.period)
    tasks = repo.tasks(conn, ctx.period)
    open_tasks = tasks[tasks["status"] != wf.DONE]
    review = tasks[tasks["status"] == wf.REVIEW]
    overdue = open_tasks[open_tasks["overdue"]]
    deadlines = repo.upcoming_deadlines(conn, ctx.period)
    next_deadline = deadlines[(deadlines["days_left"] >= 0) & (deadlines["not_filed"] > 0)].head(1)

    c1, c2, c3, c4 = st.columns(4)
    incomplete = int((docs["received"] < docs["required"]).sum())
    c1.metric(t("ลูกค้าที่เอกสารยังไม่ครบ"), t("{a} / {b} ราย", a=incomplete, b=len(docs)))
    oldest = int(review["waiting_days"].max()) if not review.empty else 0
    c2.metric(t("งานรอเจ้าของตรวจ"), t("{n} งาน", n=len(review)),
              t("ค้างนานสุด {n} วัน", n=oldest) if oldest else None, delta_color="off", delta_arrow="off")
    c3.metric(t("งานเลยกำหนด"), t("{n} งาน", n=len(overdue)))
    if next_deadline.empty:
        c4.metric(t("กำหนดยื่นถัดไป"), "-")
    else:
        d = next_deadline.iloc[0]
        c4.metric(t("กำหนดยื่นถัดไป ({date})", date=fmt_date(d["due_date"])), t(d["task_type"]),
                  t("ยังไม่ยื่น {n} ราย", n=d["not_filed"]) + " · " + days_text(int(d["days_left"])),
                  delta_color="off", delta_arrow="off")

    left, right = st.columns(2, gap="large")

    with left:
        st.subheader(t("ภาระงานที่ยังเปิดอยู่ รายคน"))
        st.caption(t("นับงานทุกประเภทในรอบนี้ที่ยังไม่เสร็จ ใช้ดูว่าใครงานล้น ใครพอรับเพิ่มได้"))
        _workload_chart(repo.workload(conn, ctx.period))
        with st.expander(t("ดูเป็นตาราง")):
            table = repo.workload(conn, ctx.period).rename(
                columns={k: t(v) for k, v in wf.STATUS_LABELS.items()}, index=t)
            table[t("รวม")] = table.sum(axis=1)
            st.dataframe(table, width="stretch")

    with right:
        st.subheader(t("กำหนดยื่นภาษีรอบนี้"))
        if deadlines.empty:
            st.info(t("รอบนี้ยังไม่มีงานยื่นภาษี"))
        else:
            view = deadlines.assign(
                due=deadlines["due_date"].map(fmt_date),
                left=deadlines["days_left"].map(lambda d: days_text(int(d))),
                filed=deadlines["total"] - deadlines["not_filed"],
            )
            view["progress"] = view["filed"] / view["total"] * 100
            view["count"] = [t("{a} / {b} ราย", a=f, b=n) for f, n in zip(view["filed"], view["total"])]
            view["task_type"] = view["task_type"].map(t)
            st.dataframe(
                view[["task_type", "due", "left", "progress", "count"]],
                column_config={
                    "task_type": t("แบบ"),
                    "due": t("กำหนดยื่น"),
                    "left": t("เหลือเวลา"),
                    "progress": st.column_config.ProgressColumn(t("ยื่นแล้ว"), min_value=0, max_value=100,
                                                                format="%.0f%%"),
                    "count": t("จำนวน"),
                },
                hide_index=True,
                width="stretch",
            )

        st.subheader(t("งานของฉันใน 7 วันข้างหน้า"))
        mine = open_tasks[(open_tasks["assignee_id"] == ctx.user_id) & (open_tasks["days_left"] <= 7)]
        if ctx.is_owner:
            mine = review
            st.caption(t("สำหรับเจ้าของ แสดงงานที่รอตรวจแทน"))
        if mine.empty:
            st.success(t("ไม่มีงานเร่งด่วน"))
        else:
            st.dataframe(
                mine.assign(client=mine["client"].map(t), due=mine["due_date"].map(fmt_date),
                            left=mine["days_left"].map(lambda d: days_text(int(d))),
                            task_type=mine["task_type"].map(t), status_label=mine["status_label"].map(t))
                [["client", "task_type", "status_label", "due", "left"]],
                column_config={"client": t("ลูกค้า"), "task_type": t("งาน"), "status_label": t("สถานะ"),
                               "due": t("กำหนด"), "left": t("เหลือเวลา")},
                hide_index=True,
                width="stretch",
            )


def _workload_chart(counts: pd.DataFrame) -> None:
    counts = counts.rename(index=t)
    long = counts.reset_index().melt(id_vars="assignee", var_name="status", value_name="tasks")
    long["status_name"] = long["status"].map(lambda k: t(wf.STATUS_LABELS[k]))
    long["order"] = long["status"].map({s: i for i, s in enumerate(wf.OPEN_STATUSES)})
    totals = counts.sum(axis=1).reset_index(name="total")

    colors = [STATUS_COLORS[s] for s in wf.OPEN_STATUSES]
    labels = [t(wf.STATUS_LABELS[s]) for s in wf.OPEN_STATUSES]
    font = "IBM Plex Sans Thai, Noto Sans Thai, Leelawadee UI, Tahoma, sans-serif"

    bars = alt.Chart(long).mark_bar(height=24, stroke="#FFFFFF", strokeWidth=2, cornerRadiusEnd=4).encode(
        y=alt.Y("assignee:N", title=None, sort=list(counts.index)),
        x=alt.X("sum(tasks):Q", title=t("จำนวนงาน"), axis=alt.Axis(grid=True, tickMinStep=5)),
        color=alt.Color("status_name:N", scale=alt.Scale(domain=labels, range=colors),
                        legend=alt.Legend(orient="top", title=None, columns=2, labelLimit=0)),
        order=alt.Order("order:Q"),
        tooltip=[alt.Tooltip("assignee:N", title=t("ผู้รับผิดชอบ")), alt.Tooltip("status_name:N", title=t("สถานะ")),
                 alt.Tooltip("tasks:Q", title=t("จำนวนงาน"))],
    )
    labels_layer = alt.Chart(totals).mark_text(align="left", dx=6, fontSize=12, font=font, fontWeight=600).encode(
        y=alt.Y("assignee:N", sort=list(counts.index)),
        x="total:Q",
        text=alt.Text("total:Q"),
        color=alt.value(theme.PURPLE_DEEP),
    )
    chart = (bars + labels_layer).properties(height=60 * len(counts) + 40).configure(
        background="transparent", font=font,
    ).configure_axis(
        gridColor=theme.LINE, domainColor=theme.LINE, tickColor=theme.LINE,
        labelColor=theme.MUTED, titleColor=theme.MUTED, labelFont=font, titleFont=font,
    ).configure_legend(labelColor=theme.INK, labelFont=font, symbolType="square")
    st.altair_chart(chart, width="stretch")
