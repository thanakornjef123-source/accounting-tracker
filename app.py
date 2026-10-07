"""Accounting-office job tracker (case study). Run with: streamlit run app.py"""

import streamlit as st

from views import approvals, calendar, clients, dashboard, documents, notifications, reports, tasks, theme
from views.common import get_conn, sidebar

st.set_page_config(page_title="ระบบติดตามงานสำนักงานบัญชี", page_icon="assets/mark.svg", layout="wide")

theme.inject()

conn = get_conn()
ctx = sidebar(conn)


def page(module, title: str, icon: str, url: str, default: bool = False) -> st.Page:
    return st.Page(lambda: module.render(ctx), title=title, icon=icon, url_path=url, default=default)


navigation = st.navigation({
    "งานประจำวัน": [
        page(dashboard, "ภาพรวม", ":material/dashboard:", "overview", default=True),
        page(documents, "เอกสารลูกค้า", ":material/folder_open:", "documents"),
        page(tasks, "งาน", ":material/task_alt:", "tasks"),
        page(approvals, "รออนุมัติ", ":material/approval:", "approvals"),
    ],
    "ลูกค้า": [
        page(clients, "ข้อมูลลูกค้า", ":material/groups:", "clients"),
        page(notifications, "แจ้งเตือนลูกค้า", ":material/notifications:", "notifications"),
        page(reports, "รายงานลูกค้า", ":material/description:", "reports"),
    ],
    "ตั้งค่า": [
        page(calendar, "ปฏิทินกำหนดยื่น", ":material/event:", "deadlines"),
    ],
})
navigation.run()
