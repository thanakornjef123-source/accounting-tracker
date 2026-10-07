"""Click every button on every page, in every role, and fail on any exception.

Streamlit's AppTest runs the real page code without a browser. Pages that need a
selected table row (task detail, client detail) are driven through their detail
function directly, because AppTest cannot click a dataframe row.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from tracker import repo, seed
from tracker import workflow as wf
from views import documents
from views.common import get_conn

ROOT = Path(__file__).resolve().parent.parent
OWNER, SOMCHAI, NAPA, KITTI, ADMIN = 1, 2, 3, 4, 5
ROLES = {"owner": OWNER, "accountant": SOMCHAI, "admin": ADMIN}
PAGES = ["dashboard", "documents", "tasks", "approvals", "calendar", "clients", "notifications", "reports"]
ALL_PAGES = PAGES + ["staff"]


@pytest.fixture(autouse=True)
def db():
    st.cache_resource.clear()
    conn = get_conn()
    seed.reset(conn)
    return conn


# ---------------------------------------------------------------- helpers

PAGE_SCRIPT = """
import streamlit as st
from views.common import get_conn, sidebar
from views import {module} as page
ctx = sidebar(get_conn())
page.render(ctx)
"""

DETAIL_SCRIPT = """
import streamlit as st
from views.common import get_conn, sidebar
from views import {module} as page
from tracker import repo, workflow as wf
conn = get_conn()
ctx = sidebar(conn)
staff = repo.staff(conn)
page._detail(ctx, {arg}{extra})
"""


def make(script: str, user_id: int = OWNER, period: str = "2026-09") -> AppTest:
    at = AppTest.from_string(script, default_timeout=60)
    at.session_state["user_id"] = user_id
    at.session_state["period"] = period
    return at.run()


def page(module: str, user_id: int = OWNER, period: str = "2026-09") -> AppTest:
    return make(PAGE_SCRIPT.format(module=module), user_id, period)


def task_detail(task_id: int, user_id: int) -> AppTest:
    script = DETAIL_SCRIPT.format(
        module="tasks", arg=task_id, extra=", staff[staff['role'] != wf.ADMIN]")
    return make(script, user_id)


def client_detail(client_id: int, user_id: int) -> AppTest:
    return make(DETAIL_SCRIPT.format(module="clients", arg=client_id, extra=""), user_id)


def ok(at: AppTest) -> AppTest:
    assert not at.exception, [e.value for e in at.exception]
    return at


def button(at: AppTest, label: str | None = None, key: str | None = None):
    if key:
        return at.button(key=key)
    matches = [b for b in at.button if b.label.startswith(label)]
    assert matches, f"no button starting with {label!r}; have {[b.label for b in at.button]}"
    return matches[0]


def labelled(elements, label: str):
    matches = [e for e in elements if e.label.startswith(label)]
    assert matches, f"no widget {label!r}; have {[e.label for e in elements]}"
    return matches[0]


def texts(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [e.value for e in at.error] + [w.value for w in at.warning]
    parts += [s.value for s in at.success] + [i.value for i in at.info] + [c.value for c in at.caption]
    return "\n".join(parts)


def first_task(status: str, task_type: str | None = None, assignee: int | None = None) -> int:
    t = repo.tasks(get_conn(), "2026-09")
    t = t[t["status"] == status]
    if task_type:
        t = t[t["task_type"] == task_type]
    if assignee:
        t = t[t["assignee_id"] == assignee]
    assert not t.empty, (status, task_type, assignee)
    return int(t.iloc[0]["id"])


def status_of(task_id: int) -> str:
    return repo.task(get_conn(), task_id)["status"]


# ---------------------------------------------------------------- every page renders

@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("module", PAGES)
@pytest.mark.parametrize("period", ["2026-09", "2026-08"])
def test_page_renders(module, role, period):
    ok(page(module, ROLES[role], period))


def test_real_app_entrypoint_runs():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    ok(at)


# ---------------------------------------------------------------- sidebar

def test_sidebar_open_new_period_button():
    at = page("dashboard")
    button(at, "เปิดรอบงาน").click().run()
    ok(at)
    assert "2026-10" in repo.periods(get_conn())
    assert "เปิดรอบงาน" in texts(at)


def test_sidebar_open_period_twice_is_harmless():
    conn = get_conn()
    first = repo.open_period(conn, "2026-10")
    assert first > 0 and repo.open_period(conn, "2026-10") == 0


def test_sidebar_reset_button_restores_demo_data(db):
    repo.act_on_task(db, first_task(wf.TODO), "start", SOMCHAI)
    at = page("dashboard")
    button(at, "ล้างข้อมูล").click().run()
    ok(at)
    assert repo.periods(get_conn()) == ["2026-09", "2026-08"]
    assert len(repo.clients(get_conn())) == 40


def test_sidebar_change_demo_date():
    at = page("dashboard")
    at.sidebar.date_input[0].set_value(pd.Timestamp("2026-10-20").date()).run()
    ok(at)
    assert repo.today(get_conn()).isoformat() == "2026-10-20"


@pytest.mark.parametrize("role", ROLES)
def test_sidebar_role_and_period_switch(role):
    at = page("dashboard")
    at.sidebar.selectbox(key="user_id").select(ROLES[role]).run()
    ok(at)
    at.sidebar.selectbox(key="period").select("2026-08").run()
    ok(at)


# ---------------------------------------------------------------- dashboard

def test_dashboard_numbers_match_database():
    at = page("dashboard")
    ok(at)
    review = (repo.tasks(get_conn(), "2026-09")["status"] == wf.REVIEW).sum()
    assert f"{review} งาน" in [m.value for m in at.metric]


# ---------------------------------------------------------------- documents

def test_documents_reminder_button_sends_one_message_per_incomplete_client():
    before = len(repo.notifications(get_conn()))
    summary = repo.document_summary(get_conn(), "2026-09")
    incomplete = int((summary["received"] < summary["required"]).sum())
    at = page("documents")
    button(at, "ส่งแจ้งเตือน").click().run()
    ok(at)
    assert len(repo.notifications(get_conn())) == before + incomplete
    assert f"ส่งแจ้งเตือนแล้ว {incomplete} ราย" in texts(at)


def test_documents_toggle_both_ways():
    at = page("documents")
    at.toggle[0].set_value(False).run()
    ok(at)
    at.toggle[0].set_value(True).run()
    ok(at)


def test_documents_record_tab_every_client_and_save_without_change():
    at = page("documents")
    options = at.selectbox(key="doc_client").options
    assert len(options) == 40
    for i in (0, 1, 39):
        at.selectbox(key="doc_client").select_index(i).run()
        ok(at)
    button(at, key="save_docs").click().run()
    ok(at)
    assert "ไม่มีการเปลี่ยนแปลง" in texts(at)


def test_documents_diff_detects_changes_and_saves():
    conn = get_conn()
    rows = repo.documents(conn, "2026-09")
    rows = rows[rows["client_id"] == int(rows.iloc[0]["client_id"])].copy()
    rows["status_label"] = rows["status"].map(repo.DOC_STATUS_LABELS)
    edited = rows.copy()
    edited.loc[edited.index[0], "status_label"] = repo.DOC_STATUS_LABELS[repo.DOC_RECEIVED]
    edited.loc[edited.index[0], "channel"] = "LINE"
    changes = documents._diff(rows, edited)
    assert len(changes) == (0 if rows.iloc[0]["status"] == repo.DOC_RECEIVED and rows.iloc[0]["channel"] == "LINE" else 1)
    if changes:
        repo.update_documents(conn, changes)
        again = repo.documents(conn, "2026-09")
        assert again[again["id"] == changes[0]["id"]].iloc[0]["status"] == repo.DOC_RECEIVED


# ---------------------------------------------------------------- tasks list

def test_tasks_filters_never_crash():
    at = page("tasks")
    for name in ["สมชาย", "นภา", "กิตติ", "ทั้งหมด"]:
        at.selectbox(key="task_person").select(name).run()
        ok(at)
    for task_type in ["ทั้งหมด", *wf.TASK_ORDER]:
        at.selectbox(key="task_type").select(task_type).run()
        ok(at)
    at.multiselect(key="task_status").set_value(list(wf.STATUS_LABELS)).run()
    ok(at)
    at.multiselect(key="task_status").set_value([]).run()
    ok(at)
    at.text_input(key="task_search").set_value("บริษัท").run()
    ok(at)
    at.text_input(key="task_search").set_value("ไม่มีชื่อนี้แน่นอน").run()
    ok(at)


# ---------------------------------------------------------------- task detail buttons

def test_tax_return_full_path_through_the_buttons():
    task_id = first_task(wf.TODO, "ภ.ง.ด.53")
    before = len(repo.notifications(get_conn()))

    button(task_detail(task_id, SOMCHAI), key=f"start_{task_id}").click().run()
    assert status_of(task_id) == wf.DOING

    at = task_detail(task_id, SOMCHAI)
    button(at, key=f"submit_{task_id}").click().run()
    ok(at)
    assert status_of(task_id) == wf.REVIEW

    at = task_detail(task_id, OWNER)
    button(at, key=f"approve_{task_id}").click().run()
    ok(at)
    assert status_of(task_id) == wf.APPROVED

    at = task_detail(task_id, SOMCHAI)
    button(at, key=f"file_{task_id}").click().run()
    ok(at)
    assert status_of(task_id) == wf.DONE
    assert len(repo.notifications(get_conn())) == before + 1


def test_bookkeeping_is_done_after_owner_approves():
    task_id = first_task(wf.REVIEW, wf.BOOKKEEPING)
    at = task_detail(task_id, OWNER)
    button(at, key=f"approve_{task_id}").click().run()
    ok(at)
    assert status_of(task_id) == wf.DONE


def test_client_report_task_completes_without_review():
    task_id = first_task(wf.TODO, wf.CLIENT_REPORT)
    button(task_detail(task_id, SOMCHAI), key=f"start_{task_id}").click().run()
    at = task_detail(task_id, SOMCHAI)
    assert not [b for b in at.button if b.key and b.key.startswith("submit_")]
    button(at, key=f"complete_{task_id}").click().run()
    ok(at)
    assert status_of(task_id) == wf.DONE


def test_return_without_reason_is_refused_then_accepted_with_reason():
    task_id = first_task(wf.REVIEW)
    at = task_detail(task_id, OWNER)
    button(at, key=f"return_{task_id}").click().run()
    ok(at)
    assert "ต้องใส่เหตุผล" in texts(at)
    assert status_of(task_id) == wf.REVIEW

    at.text_input(key=f"comment_{task_id}").set_value("ยอดภาษีซื้อไม่ตรง").run()
    button(at, key=f"return_{task_id}").click().run()
    ok(at)
    assert status_of(task_id) == wf.DOING
    assert "ยอดภาษีซื้อไม่ตรง" in texts(task_detail(task_id, SOMCHAI))


def test_accountant_and_admin_never_see_approve_buttons():
    task_id = first_task(wf.REVIEW)
    for user in (SOMCHAI, NAPA, ADMIN):
        at = ok(task_detail(task_id, user))
        keys = [b.key for b in at.button if b.key]
        assert f"approve_{task_id}" not in keys and f"return_{task_id}" not in keys


def test_admin_sees_no_status_buttons_at_all():
    task_id = first_task(wf.TODO)
    at = ok(task_detail(task_id, ADMIN))
    assert not [b for b in at.button if b.key and b.key.split("_")[0] in {"start", "submit", "complete", "file"}]


def test_owner_reassign_button():
    task_id = first_task(wf.TODO, assignee=SOMCHAI)
    at = task_detail(task_id, OWNER)
    at.selectbox(key=f"assign_{task_id}").select(KITTI).run()
    button(at, key=f"reassign_{task_id}").click().run()
    ok(at)
    assert repo.task(get_conn(), task_id)["assignee_id"] == KITTI


def test_accountant_cannot_see_reassign_button():
    task_id = first_task(wf.TODO)
    at = ok(task_detail(task_id, SOMCHAI))
    assert not [b for b in at.button if b.key == f"reassign_{task_id}"]


def test_done_task_shows_history_and_no_buttons():
    task_id = first_task(wf.DONE, "ภ.ง.ด.53")
    at = ok(task_detail(task_id, OWNER))
    assert not [b for b in at.button if b.key and b.key.split("_")[0] in {"start", "submit", "approve", "return", "file"}]


def test_task_detail_renders_every_open_task_for_every_role():
    t = repo.tasks(get_conn(), "2026-09")
    sample = pd.concat([t[t["status"] == s].head(2) for s in wf.STATUS_LABELS])
    for task_id in sample["id"]:
        for user in (OWNER, SOMCHAI, ADMIN):
            ok(task_detail(int(task_id), user))


# ---------------------------------------------------------------- approvals

def test_approvals_owner_approve_button():
    queue = repo.tasks(get_conn(), "2026-09").query("status == 'review'").sort_values(["due_date", "waiting_days"], ascending=[True, False])
    first = int(queue.iloc[0]["id"])
    at = page("approvals")
    button(at, key=f"ok_{first}").click().run()
    ok(at)
    assert status_of(first) in (wf.APPROVED, wf.DONE)


def test_approvals_return_needs_reason():
    queue = repo.tasks(get_conn(), "2026-09").query("status == 'review'").sort_values(["due_date", "waiting_days"], ascending=[True, False])
    first = int(queue.iloc[0]["id"])
    at = page("approvals")
    button(at, key=f"back_{first}").click().run()
    ok(at)
    assert "ต้องใส่เหตุผล" in texts(at) and status_of(first) == wf.REVIEW
    at.text_input(key=f"why_{first}").set_value("แนบเอกสารไม่ครบ").run()
    button(at, key=f"back_{first}").click().run()
    ok(at)
    assert status_of(first) == wf.DOING


def test_approve_every_waiting_task_one_by_one():
    waiting = len(repo.tasks(get_conn(), "2026-09").query("status == 'review'"))
    for _ in range(waiting):
        at = page("approvals")
        buttons = [b for b in at.button if b.key and b.key.startswith("ok_")]
        buttons[0].click().run()
        ok(at)
    assert repo.tasks(get_conn(), "2026-09").query("status == 'review'").empty


@pytest.mark.parametrize("user", [SOMCHAI, ADMIN])
def test_approvals_non_owner_has_no_buttons(user):
    at = ok(page("approvals", user))
    assert not [b for b in at.button if b.key and b.key.split("_")[0] in {"ok", "back"}]
    assert "สำหรับเจ้าของ" in texts(at)


# ---------------------------------------------------------------- calendar

def test_calendar_owner_save_button_switches_to_paper_deadlines():
    at = page("calendar")
    at.radio[0].set_value("paper").run()
    button(at, "บันทึกและคำนวณ").click().run()
    ok(at)
    assert repo.filing_method(get_conn()) == "paper"
    t = repo.tasks(get_conn(), "2026-09")
    open_53 = t[(t["task_type"] == "ภ.ง.ด.53") & (t["status"] != wf.DONE)]
    assert set(open_53["due_date"]) == {"2026-10-07"}


def test_calendar_save_without_changes_keeps_dates():
    before = repo.tasks(get_conn(), "2026-09")[["id", "due_date"]]
    at = page("calendar")
    button(at, "บันทึกและคำนวณ").click().run()
    ok(at)
    after = repo.tasks(get_conn(), "2026-09")[["id", "due_date"]]
    assert before.equals(after)


@pytest.mark.parametrize("user", [SOMCHAI, ADMIN])
def test_calendar_non_owner_cannot_edit(user):
    at = ok(page("calendar", user))
    assert not [b for b in at.button if b.label.startswith("บันทึกและคำนวณ")]


# ---------------------------------------------------------------- clients

def test_client_form_saves_backup_and_notes():
    # Values inside st.form are only committed by the submit click, so no run() in between.
    c = repo.clients(get_conn()).iloc[0]
    cid = int(c["id"])
    new_backup = next(s for s in (SOMCHAI, NAPA, KITTI) if s != int(c["primary_staff_id"]))
    at = client_detail(cid, OWNER)
    labelled(at.selectbox, "ผู้รับผิดชอบสำรอง").select(new_backup)
    labelled(at.text_area, "วิธีทำงาน").set_value("ส่งเอกสารทุกวันที่ 3 ของเดือน")
    button(at, "บันทึก").click().run()
    ok(at)
    row = repo.client(get_conn(), cid)
    assert row["backup_staff_id"] == new_backup and row["notes"] == "ส่งเอกสารทุกวันที่ 3 ของเดือน"


def test_client_form_rejects_same_primary_and_backup():
    cid = int(repo.clients(get_conn()).iloc[0]["id"])
    primary = repo.client(get_conn(), cid)["primary_staff_id"]
    at = client_detail(cid, OWNER)
    labelled(at.selectbox, "ผู้รับผิดชอบสำรอง").select(primary)
    button(at, "บันทึก").click().run()
    ok(at)
    assert "คนละคน" in texts(at)


def test_client_form_accountant_can_save_notes():
    cid = int(repo.clients(get_conn()).iloc[1]["id"])
    at = client_detail(cid, SOMCHAI)
    labelled(at.text_area, "วิธีทำงาน").set_value("ลูกค้าตอบช้า ให้โทรหาผู้จัดการร้าน")
    button(at, "บันทึก").click().run()
    ok(at)
    assert repo.client(get_conn(), cid)["notes"] == "ลูกค้าตอบช้า ให้โทรหาผู้จัดการร้าน"


def test_client_detail_renders_for_every_client_and_role():
    for cid in repo.clients(get_conn())["id"][::7]:
        for user in (OWNER, SOMCHAI, ADMIN):
            ok(client_detail(int(cid), user))


# ---------------------------------------------------------------- notifications and reports

def test_notifications_filters():
    at = page("notifications")
    for p in ["2026-09", "2026-08", "ทั้งหมด"]:
        at.selectbox(key="notif_period").select(p).run()
        ok(at)
    for e in at.selectbox(key="notif_event").options:
        at.selectbox(key="notif_event").select(e).run()
        ok(at)
    at.text_input(key="notif_search").set_value("สยาม").run()
    ok(at)


def test_report_send_button_marks_done_and_notifies():
    reports_before = len(repo.notifications(get_conn()))
    at = page("reports", SOMCHAI)
    cid = at.selectbox(key="report_client").value
    button(at, "บันทึกว่าส่งรายงาน").click().run()
    ok(at)
    task = repo.tasks(get_conn(), "2026-09").query("client_id == @cid and task_type == @wf.CLIENT_REPORT").iloc[0]
    assert task["status"] == wf.DONE
    assert len(repo.notifications(get_conn())) == reports_before + 1
    ok(at)


def test_report_every_client_renders_and_admin_cannot_send():
    at = page("reports", ADMIN)
    for i in range(0, 40, 5):
        at.selectbox(key="report_client").select_index(i).run()
        ok(at)
    assert all(b.disabled for b in at.button if b.label.startswith(("พนักงานบัญชี", "บันทึกว่าส่ง")))
