"""Client notification outbox (simulated)."""

from __future__ import annotations

import streamlit as st

from tracker import repo
from tracker.periods import thai_label

from .common import Ctx, fmt_date, page_header

ALL = "ทั้งหมด"


def render(ctx: Ctx) -> None:
    page_header("แจ้งเตือนลูกค้า", ctx)
    st.info(
        "ระบบส่งข้อความหาลูกค้าอัตโนมัติเมื่อสถานะเปลี่ยน: ได้รับเอกสารครบ, ยื่นภาษีแล้ว, ส่งรายงานแล้ว "
        "และเมื่อสำนักงานกดเตือนเรื่องเอกสาร ลูกค้าไม่ต้องเข้าระบบ\n\n"
        "ในเดโมนี้ข้อความถูกบันทึกไว้ที่นี่ ไม่ได้ส่งจริง ระบบจริงจะต่อกับ LINE Messaging API และอีเมล "
        "ข้อความบอกเฉพาะสถานะ ไม่แนบเอกสารหรือตัวเลขทางการเงิน เพื่อลดความเสี่ยงด้านข้อมูลส่วนบุคคล"
    )
    df = repo.notifications(ctx.conn)

    f1, f2, f3 = st.columns(3)
    period = f1.selectbox("รอบงาน", [ALL, *repo.periods(ctx.conn)],
                          format_func=lambda p: p if p == ALL else thai_label(p), key="notif_period")
    event = f2.selectbox("ประเภท", [ALL, *repo.EVENT_LABELS], format_func=lambda e: repo.EVENT_LABELS.get(e, e),
                         key="notif_event")
    search = f3.text_input("ค้นหาลูกค้า", key="notif_search")
    if period != ALL:
        df = df[df["period"] == period]
    if event != ALL:
        df = df[df["event"] == event]
    if search:
        df = df[df["client"].str.contains(search, case=False, regex=False)]

    st.caption(f"{len(df)} ข้อความ")
    st.dataframe(
        df.assign(date=df["created_on"].map(fmt_date), kind=df["event"].map(repo.EVENT_LABELS))
        [["date", "client", "kind", "channel", "contact", "message"]],
        column_config={
            "date": "วันที่",
            "kind": "ประเภท",
            "client": "ลูกค้า",
            "channel": "ช่องทาง",
            "contact": "ส่งถึง",
            "message": st.column_config.TextColumn("ข้อความ", width="large"),
        },
        hide_index=True,
        width="stretch",
        height=520,
    )
