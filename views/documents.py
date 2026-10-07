"""Document intake: one register for every channel, and who still owes what."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from tracker import repo

from .common import Ctx, flash, fmt_date, page_header

LABEL_TO_STATUS = {v: k for k, v in repo.DOC_STATUS_LABELS.items()}


def render(ctx: Ctx) -> None:
    page_header("เอกสารลูกค้า", ctx)
    summary_tab, record_tab = st.tabs(["ใครยังขาดอะไร", "บันทึกการรับเอกสาร"])
    with summary_tab:
        _summary(ctx)
    with record_tab:
        _record(ctx)


def _summary(ctx: Ctx) -> None:
    summary = repo.document_summary(ctx.conn, ctx.period)
    incomplete = summary[summary["received"] < summary["required"]]

    c1, c2, c3 = st.columns(3)
    c1.metric("เอกสารครบแล้ว", f"{len(summary) - len(incomplete)} ราย")
    c2.metric("ยังไม่ครบ", f"{len(incomplete)} ราย")
    c3.metric("ต้องขอใหม่ (อ่านไม่ออก/ไม่ถูกต้อง)", f"{int(summary['resubmit'].sum())} ฉบับ")

    only_open = st.toggle("แสดงเฉพาะลูกค้าที่เอกสารยังไม่ครบ", value=True)
    view = incomplete if only_open else summary
    st.dataframe(
        view[["client", "primary_staff", "received", "required", "outstanding"]],
        column_config={
            "client": st.column_config.TextColumn("ลูกค้า", width="large"),
            "primary_staff": "ผู้รับผิดชอบ",
            "received": st.column_config.ProgressColumn(
                "ได้รับแล้ว", min_value=0, max_value=int(summary["required"].max() or 1), format="%d ฉบับ"),
            "required": st.column_config.NumberColumn("ต้องส่ง", format="%d ฉบับ"),
            "outstanding": st.column_config.TextColumn("ยังขาด / ต้องขอใหม่", width="large"),
        },
        hide_index=True,
        width="stretch",
    )

    if incomplete.empty:
        st.success("ลูกค้าทุกรายส่งเอกสารครบแล้ว")
        return
    st.markdown("##### แจ้งเตือนลูกค้าที่ยังขาดเอกสาร")
    st.caption("ส่งข้อความเดียวต่อราย บอกเฉพาะชื่อเอกสารที่ยังขาด ทางช่องทางที่ลูกค้าใช้ (LINE หรืออีเมล)")
    if st.button(f"ส่งแจ้งเตือน {len(incomplete)} ราย", type="primary"):
        sent = repo.remind_outstanding(ctx.conn, ctx.period)
        flash(f"ส่งแจ้งเตือนแล้ว {len(sent)} ราย ดูข้อความได้ที่หน้าแจ้งเตือนลูกค้า")
        st.rerun()


def _record(ctx: Ctx) -> None:
    docs = repo.documents(ctx.conn, ctx.period)
    summary = repo.document_summary(ctx.conn, ctx.period).set_index("client_id")

    def label(client_id: int) -> str:
        row = summary.loc[client_id]
        left = int(row["required"] - row["received"])
        return f"{row['client']}  ·  {'ครบแล้ว' if left == 0 else f'ขาด {left} ฉบับ'}"

    client_id = st.selectbox("ลูกค้า", summary.index.tolist(), format_func=label, key="doc_client")
    rows = docs[docs["client_id"] == client_id].copy()
    rows["status_label"] = rows["status"].map(repo.DOC_STATUS_LABELS)
    rows["received"] = rows["received_on"].map(fmt_date)
    rows["channel"] = rows["channel"].where(rows["channel"].notna(), None)

    st.caption("แก้สถานะ ช่องทาง หรือหมายเหตุในตาราง แล้วกดบันทึก เอกสารจากทุกช่องทางลงทะเบียนที่นี่ที่เดียว")
    edited = st.data_editor(
        rows[["id", "doc_type", "status_label", "channel", "note", "received"]],
        column_config={
            "id": None,
            "doc_type": st.column_config.TextColumn("เอกสาร", disabled=True),
            "status_label": st.column_config.SelectboxColumn(
                "สถานะ", options=list(repo.DOC_STATUS_LABELS.values()), required=True),
            "channel": st.column_config.SelectboxColumn("ช่องทางที่ได้รับ", options=list(repo.DOC_CHANNELS)),
            "note": st.column_config.TextColumn("หมายเหตุ", width="large"),
            "received": st.column_config.TextColumn("วันที่รับ", disabled=True),
        },
        hide_index=True,
        width="stretch",
        key=f"doc_editor_{client_id}_{ctx.period}",
    )

    if st.button("บันทึก", type="primary", key="save_docs"):
        changes = _diff(rows, edited)
        if not changes:
            st.info("ไม่มีการเปลี่ยนแปลง")
            return
        try:
            messages = repo.update_documents(ctx.conn, changes)
        except ValueError as exc:
            st.error(str(exc))
            return
        flash(f"บันทึกแล้ว {len(changes)} รายการ")
        for m in messages:
            flash(f"แจ้งลูกค้าอัตโนมัติ: {m}", "info")
        st.rerun()


def _diff(before: pd.DataFrame, after: pd.DataFrame) -> list[dict]:
    changes = []
    old = before.set_index("id")
    for row in after.itertuples(index=False):
        prev = old.loc[row.id]
        status = LABEL_TO_STATUS[row.status_label]
        channel = row.channel if isinstance(row.channel, str) and row.channel else None
        note = row.note if isinstance(row.note, str) else ""
        prev_channel = prev["channel"] if isinstance(prev["channel"], str) else None
        if (status, channel, note) != (prev["status"], prev_channel, prev["note"] or ""):
            changes.append({"id": int(row.id), "status": status, "channel": channel, "note": note})
    return changes
