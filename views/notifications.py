"""Client notification outbox (simulated)."""

from __future__ import annotations

import streamlit as st

from tracker import repo

from .common import Ctx, fmt_date, matches, page_header, period_label, t

ALL = "ทั้งหมด"


def render(ctx: Ctx) -> None:
    page_header("แจ้งเตือนลูกค้า", ctx)
    st.info(
        t("ระบบส่งข้อความหาลูกค้าอัตโนมัติเมื่อสถานะเปลี่ยน: ได้รับเอกสารครบ, ยื่นภาษีแล้ว, ส่งรายงานแล้ว "
          "และเมื่อสำนักงานกดเตือนเรื่องเอกสาร ลูกค้าไม่ต้องเข้าระบบ")
        + "\n\n"
        + t("ในเดโมนี้ข้อความถูกบันทึกไว้ที่นี่ ไม่ได้ส่งจริง ระบบจริงจะต่อกับ LINE Messaging API และอีเมล "
            "ข้อความบอกเฉพาะสถานะ ไม่แนบเอกสารหรือตัวเลขทางการเงิน เพื่อลดความเสี่ยงด้านข้อมูลส่วนบุคคล")
    )
    st.caption(t("ข้อความถึงลูกค้าเขียนเป็นภาษาไทยเสมอ ไม่เปลี่ยนตามภาษาของหน้าจอ"))
    df = repo.notifications(ctx.conn)

    f1, f2, f3 = st.columns(3)
    period = f1.selectbox(t("รอบงาน"), [ALL, *repo.periods(ctx.conn)],
                          format_func=lambda p: t(p) if p == ALL else period_label(p), key="notif_period")
    event = f2.selectbox(t("ประเภท"), [ALL, *repo.EVENT_LABELS],
                         format_func=lambda e: t(repo.EVENT_LABELS.get(e, e)), key="notif_event")
    search = f3.text_input(t("ค้นหาลูกค้า"), key="notif_search")
    if period != ALL:
        df = df[df["period"] == period]
    if event != ALL:
        df = df[df["event"] == event]
    if search:
        df = df[matches(df["client"], search)]

    st.caption(t("{n} ข้อความ", n=len(df)))
    st.download_button(
        t("ดาวน์โหลดตารางนี้ (CSV)"),
        df[["created_on", "client", "event", "channel", "contact", "message"]].to_csv(index=False).encode("utf-8-sig"),
        file_name="notifications.csv", mime="text/csv", key="notif_csv")
    st.dataframe(
        df.assign(date=df["created_on"].map(fmt_date), kind=df["event"].map(lambda e: t(repo.EVENT_LABELS[e])),
                  channel=df["channel"].map(t), client=df["client"].map(t))
        [["date", "client", "kind", "channel", "contact", "message"]],
        column_config={
            "date": t("วันที่"),
            "kind": t("ประเภท"),
            "client": t("ลูกค้า"),
            "channel": t("ช่องทาง"),
            "contact": t("ส่งถึง"),
            "message": st.column_config.TextColumn(t("ข้อความ"), width="large"),
        },
        hide_index=True,
        width="stretch",
        height=520,
    )
