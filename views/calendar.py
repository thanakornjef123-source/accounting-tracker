"""Filing deadlines: the rules, the holidays, and the dates they produce."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from tracker import repo
from tracker.deadlines import EFILING, PAPER, filing_deadline

from .common import Ctx, days_text, flash, fmt_date, lang, page_header, period_label, t

METHOD_LABELS = {EFILING: "ยื่นทางอินเทอร์เน็ต", PAPER: "ยื่นแบบกระดาษ"}


def render(ctx: Ctx) -> None:
    page_header("ปฏิทินกำหนดยื่น", ctx)
    conn = ctx.conn
    rules = repo.rules(conn)
    hol = repo.holidays(conn)
    method = repo.filing_method(conn)

    st.subheader(t("กำหนดยื่นของรอบ {period}", period=period_label(ctx.period)))
    c_form, c_paper, c_online, c_used, c_left = (
        t("แบบ"), t("กระดาษ"), t("อินเทอร์เน็ต"), t("สำนักงานใช้"), t("เหลือเวลา"))
    rows = []
    for form, rule in rules.items():
        paper = filing_deadline(ctx.period, rule, PAPER, hol)
        online = filing_deadline(ctx.period, rule, EFILING, hol)
        used = online if method == EFILING else paper
        rows.append({c_form: t(form), c_paper: fmt_date(paper.isoformat()),
                     c_online: fmt_date(online.isoformat()),
                     c_used: t(METHOD_LABELS[method]), c_left: days_text((used - ctx.today).days)})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption(t(
        "วันกำหนดอ้างอิงปฏิทินภาษีของกรมสรรพากร (rd.go.th) ถ้าตรงวันเสาร์ อาทิตย์ หรือวันหยุดในรายการด้านล่าง "
        "ระบบเลื่อนไปวันทำการถัดไปให้อัตโนมัติ"))

    if not ctx.is_owner:
        st.info(t("เจ้าของเป็นผู้แก้กติกาวันกำหนดและวันหยุด"))
        _holiday_table(hol)
        return

    st.divider()
    left, right = st.columns(2, gap="large")
    with left:
        st.subheader(t("กติกาวันกำหนด"))
        new_method = st.radio(t("สำนักงานยื่นแบบโดย"), list(METHOD_LABELS), format_func=lambda m: t(METHOD_LABELS[m]),
                              index=list(METHOD_LABELS).index(method), horizontal=True)
        paper_col, online_col = t("กระดาษ (วันที่)"), t("อินเทอร์เน็ต (วันที่)")
        rule_df = pd.DataFrame([{c_form: r.form, paper_col: r.paper_day, online_col: r.efiling_day}
                                for r in rules.values()])
        edited_rules = st.data_editor(
            rule_df, hide_index=True, width="stretch", disabled=[c_form],
            column_config={
                paper_col: st.column_config.NumberColumn(min_value=1, max_value=28, step=1),
                online_col: st.column_config.NumberColumn(min_value=1, max_value=28, step=1),
            },
            key=f"rule_editor_{lang()}",
        )
        st.caption(t("การขยายเวลายื่นทางอินเทอร์เน็ต 8 วันมาจากประกาศกระทรวงการคลังที่ต่ออายุเป็นช่วง ๆ "
                     "ถ้าประกาศเปลี่ยน แก้ตัวเลขที่นี่"))

    with right:
        st.subheader(t("วันหยุดราชการ"))
        hol_df = repo.holidays_df(conn)
        hol_df["day"] = pd.to_datetime(hol_df["day"]).dt.date
        edited_hol = st.data_editor(
            hol_df, num_rows="dynamic", hide_index=True, width="stretch",
            column_config={"day": st.column_config.DateColumn(t("วันที่"), required=True, format="YYYY-MM-DD"),
                           "name": st.column_config.TextColumn(t("ชื่อวันหยุด"), required=True)},
            key=f"holiday_editor_{lang()}",
        )
        st.caption(t("เพิ่มวันหยุดตามประกาศจริงของแต่ละปี ข้อมูลตัวอย่างใส่ไว้เฉพาะวันที่ตรวจกับปฏิทินกรมสรรพากรแล้ว"))

    if st.button(t("บันทึกและคำนวณกำหนดส่งของงานที่ยังไม่เสร็จใหม่"), type="primary"):
        repo.set_setting(conn, "filing_method", new_method)
        for r in edited_rules.itertuples(index=False):
            repo.update_rule(conn, r[0], int(r[1]), int(r[2]))
        repo.replace_holidays(conn, [
            (d.isoformat() if isinstance(d, date) else str(d)[:10], str(n))
            for d, n in zip(edited_hol["day"], edited_hol["name"]) if pd.notna(d) and n
        ])
        changed = sum(repo.recompute_due_dates(conn, p) for p in repo.periods(conn))
        flash(t("บันทึกแล้ว ปรับกำหนดส่งของงานที่ยังไม่เสร็จ {n} งาน", n=changed))
        st.rerun()


def _holiday_table(hol: list[date]) -> None:
    st.markdown("##### " + t("วันหยุดที่ระบบใช้เลื่อนวันกำหนด"))
    if hol:
        st.write(", ".join(fmt_date(d.isoformat()) for d in hol))
    else:
        st.caption(t("ยังไม่มีวันหยุดในระบบ"))
