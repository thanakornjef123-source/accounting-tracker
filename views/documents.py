"""Document intake: one register for every channel, and who still owes what."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from tracker import repo

from .common import Ctx, error_text, flash, fmt_date, lang, page_header, t


def render(ctx: Ctx) -> None:
    page_header("เอกสารลูกค้า", ctx)
    summary_tab, record_tab = st.tabs([t("ใครยังขาดอะไร"), t("บันทึกการรับเอกสาร")])
    with summary_tab:
        _summary(ctx)
    with record_tab:
        _record(ctx)


def _summary(ctx: Ctx) -> None:
    summary = repo.document_summary(ctx.conn, ctx.period)
    incomplete = summary[summary["received"] < summary["required"]]

    c1, c2, c3 = st.columns(3)
    c1.metric(t("เอกสารครบแล้ว"), t("{n} ราย", n=len(summary) - len(incomplete)))
    c2.metric(t("ยังไม่ครบ"), t("{n} ราย", n=len(incomplete)))
    c3.metric(t("ต้องขอใหม่ (อ่านไม่ออก/ไม่ถูกต้อง)"), t("{n} ฉบับ", n=int(summary["resubmit"].sum())))

    only_open = st.toggle(t("แสดงเฉพาะลูกค้าที่เอกสารยังไม่ครบ"), value=True)
    view = incomplete if only_open else summary
    view = view.assign(outstanding=view["outstanding"].map(_translate_list), client=view["client"].map(t),
                       primary_staff=view["primary_staff"].map(t))
    st.dataframe(
        view[["client", "primary_staff", "received", "required", "outstanding"]],
        column_config={
            "client": st.column_config.TextColumn(t("ลูกค้า"), width="large"),
            "primary_staff": t("ผู้รับผิดชอบ"),
            "received": st.column_config.ProgressColumn(
                t("ได้รับแล้ว"), min_value=0, max_value=int(summary["required"].max() or 1),
                format=t("%d ฉบับ")),
            "required": st.column_config.NumberColumn(t("ต้องส่ง"), format=t("%d ฉบับ")),
            "outstanding": st.column_config.TextColumn(t("ยังขาด / ต้องขอใหม่"), width="large"),
        },
        hide_index=True,
        width="stretch",
    )

    if incomplete.empty:
        st.success(t("ลูกค้าทุกรายส่งเอกสารครบแล้ว"))
        return
    st.markdown("##### " + t("แจ้งเตือนลูกค้าที่ยังขาดเอกสาร"))
    st.caption(t("ส่งข้อความเดียวต่อราย บอกเฉพาะชื่อเอกสารที่ยังขาด ทางช่องทางที่ลูกค้าใช้ (LINE หรืออีเมล)"))
    if st.button(t("ส่งแจ้งเตือน {n} ราย", n=len(incomplete)), type="primary"):
        sent = repo.remind_outstanding(ctx.conn, ctx.period)
        flash(t("ส่งแจ้งเตือนแล้ว {n} ราย ดูข้อความได้ที่หน้าแจ้งเตือนลูกค้า", n=len(sent)))
        st.rerun()


def _translate_list(joined) -> str:
    if not isinstance(joined, str):
        return ""
    return ", ".join(t(x) for x in joined.split(", "))


def _record(ctx: Ctx) -> None:
    docs = repo.documents(ctx.conn, ctx.period)
    summary = repo.document_summary(ctx.conn, ctx.period).set_index("client_id")

    def label(client_id: int) -> str:
        row = summary.loc[client_id]
        left = int(row["required"] - row["received"])
        state = t("ครบแล้ว") if left == 0 else t("ขาด {n} ฉบับ", n=left)
        return f"{t(row['client'])}  ·  {state}"

    client_id = st.selectbox(t("ลูกค้า"), summary.index.tolist(), format_func=label, key="doc_client")
    rows = docs[docs["client_id"] == client_id].copy()
    rows["status_label"] = rows["status"].map(lambda s: t(repo.DOC_STATUS_LABELS[s]))
    rows["doc_name"] = rows["doc_type"].map(t)
    rows["received"] = rows["received_on"].map(fmt_date)
    rows["channel"] = rows["channel"].map(lambda c: t(c) if isinstance(c, str) and c else None)

    st.caption(t("แก้สถานะ ช่องทาง หรือหมายเหตุในตาราง แล้วกดบันทึก เอกสารจากทุกช่องทางลงทะเบียนที่นี่ที่เดียว"))
    edited = st.data_editor(
        rows[["id", "doc_name", "status_label", "channel", "note", "received"]],
        column_config={
            "id": None,
            "doc_name": st.column_config.TextColumn(t("เอกสาร"), disabled=True),
            "status_label": st.column_config.SelectboxColumn(
                t("สถานะ"), options=[t(v) for v in repo.DOC_STATUS_LABELS.values()], required=True),
            "channel": st.column_config.SelectboxColumn(t("ช่องทางที่ได้รับ"), options=[t(c) for c in repo.DOC_CHANNELS]),
            "note": st.column_config.TextColumn(t("หมายเหตุ"), width="large"),
            "received": st.column_config.TextColumn(t("วันที่รับ"), disabled=True),
        },
        hide_index=True,
        width="stretch",
        key=f"doc_editor_{client_id}_{ctx.period}_{lang()}",
    )

    if st.button(t("บันทึก"), type="primary", key="save_docs"):
        changes = _diff(rows, edited)
        if not changes:
            st.info(t("ไม่มีการเปลี่ยนแปลง"))
            return
        try:
            messages = repo.update_documents(ctx.conn, changes)
        except ValueError as exc:
            st.error(error_text(exc))
            return
        flash(t("บันทึกแล้ว {n} รายการ", n=len(changes)))
        for m in messages:
            flash(t("แจ้งลูกค้าอัตโนมัติ: {message}", message=m), "info")
        st.rerun()


def _diff(before: pd.DataFrame, after: pd.DataFrame) -> list[dict]:
    label_to_status = {t(v): k for k, v in repo.DOC_STATUS_LABELS.items()}
    label_to_channel = {t(c): c for c in repo.DOC_CHANNELS}
    changes = []
    old = before.set_index("id")
    for row in after.itertuples(index=False):
        prev = old.loc[row.id]
        status = label_to_status[row.status_label]
        channel = label_to_channel.get(row.channel) if isinstance(row.channel, str) and row.channel else None
        note = row.note if isinstance(row.note, str) else ""
        prev_channel = label_to_channel.get(prev["channel"]) if isinstance(prev["channel"], str) else None
        if (status, channel, note) != (prev["status"], prev_channel, prev["note"] or ""):
            changes.append({"id": int(row.id), "status": status, "channel": channel, "note": note})
    return changes
