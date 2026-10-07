import pytest

from tracker import db, repo, seed
from tracker import workflow as wf

OWNER_ID, ACCOUNTANT_ID, ADMIN_ID = 1, 2, 5


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    seed.seed(c)
    yield c
    c.close()


def test_seed_has_40_clients_and_two_periods(conn):
    assert len(repo.clients(conn)) == 40
    assert repo.periods(conn) == ["2026-09", "2026-08"]


def test_open_period_is_idempotent(conn):
    created = repo.open_period(conn, "2026-10")
    assert created > 0
    assert repo.open_period(conn, "2026-10") == 0


def test_receiving_last_document_notifies_client_once(conn):
    period = "2026-09"
    summary = repo.document_summary(conn, period)
    client_id = int(summary[summary["received"] < summary["required"]].iloc[0]["client_id"])
    docs = repo.documents(conn, period)
    outstanding = docs[(docs["client_id"] == client_id) & (docs["status"] != repo.DOC_RECEIVED)]

    messages = repo.update_documents(conn, [
        {"id": int(d.id), "status": repo.DOC_RECEIVED, "channel": "LINE", "note": ""}
        for d in outstanding.itertuples()
    ])
    assert repo.docs_complete(conn, client_id, period)
    assert len(messages) == 1 and "ครบแล้ว" in messages[0]

    # Saving again does not send a second message
    again = repo.update_documents(conn, [
        {"id": int(outstanding.iloc[0]["id"]), "status": repo.DOC_RECEIVED, "channel": "อีเมล", "note": "x"}
    ])
    assert again == []


def test_receiving_requires_channel(conn):
    doc_id = int(repo.documents(conn, "2026-09").iloc[0]["id"])
    with pytest.raises(ValueError):
        repo.update_documents(conn, [{"id": doc_id, "status": repo.DOC_RECEIVED, "channel": None}])


def test_reminders_only_go_to_clients_missing_documents(conn):
    summary = repo.document_summary(conn, "2026-09")
    expected = int((summary["received"] < summary["required"]).sum())
    assert len(repo.remind_outstanding(conn, "2026-09")) == expected


def _task_id(conn, status, task_type=None):
    t = repo.tasks(conn, "2026-09")
    t = t[t["status"] == status]
    if task_type:
        t = t[t["task_type"] == task_type]
    return int(t.iloc[0]["id"])


def test_full_tax_return_flow_notifies_client_when_filed(conn):
    task_id = _task_id(conn, wf.TODO, "ภ.ง.ด.53")
    assert repo.act_on_task(conn, task_id, "start", ACCOUNTANT_ID) is None
    repo.act_on_task(conn, task_id, "submit", ACCOUNTANT_ID)
    assert repo.task(conn, task_id)["submitted_on"] == "2026-10-12"
    repo.act_on_task(conn, task_id, "approve", OWNER_ID)
    message = repo.act_on_task(conn, task_id, "file", ACCOUNTANT_ID)
    assert repo.task(conn, task_id)["status"] == wf.DONE
    assert "ยื่นแบบ ภ.ง.ด.53" in message
    assert len(repo.task_events(conn, task_id)) == 4


def test_returned_task_keeps_reason(conn):
    task_id = _task_id(conn, wf.REVIEW)
    repo.act_on_task(conn, task_id, "return", OWNER_ID, "ยอดภาษีขายไม่ตรงกับรายงาน")
    assert repo.task(conn, task_id)["status"] == wf.DOING
    assert repo.last_return_comment(conn, task_id) == "ยอดภาษีขายไม่ตรงกับรายงาน"


def test_accountant_cannot_approve_in_repo(conn):
    with pytest.raises(wf.WorkflowError):
        repo.act_on_task(conn, _task_id(conn, wf.REVIEW), "approve", ACCOUNTANT_ID)


def test_reassign_to_admin_rejected(conn):
    with pytest.raises(ValueError):
        repo.reassign_task(conn, _task_id(conn, wf.TODO), ADMIN_ID, OWNER_ID)


def test_reassign_moves_task(conn):
    task_id = _task_id(conn, wf.TODO)
    repo.reassign_task(conn, task_id, 4, OWNER_ID)
    assert repo.task(conn, task_id)["assignee_id"] == 4


def test_workload_counts_open_tasks_per_accountant(conn):
    counts = repo.workload(conn, "2026-09")
    open_tasks = repo.tasks(conn, "2026-09").query("status != 'done'")
    assert int(counts.to_numpy().sum()) == len(open_tasks)
    assert list(counts.index) == ["สมชาย", "นภา", "กิตติ"]


def test_changing_rule_recomputes_open_due_dates(conn):
    repo.update_rule(conn, "ภ.พ.30", 15, 20)
    assert repo.recompute_due_dates(conn, "2026-09") > 0
    vat = repo.tasks(conn, "2026-09").query("task_type == 'ภ.พ.30' and status != 'done'")
    assert set(vat["due_date"]) == {"2026-10-20"}


def test_client_report_lists_outstanding_documents(conn):
    summary = repo.document_summary(conn, "2026-09")
    row = summary[summary["received"] < summary["required"]].iloc[0]
    report = repo.client_report(conn, int(row["client_id"]), "2026-09")
    assert "รบกวนส่งเอกสารที่ยังขาด" in report
    assert "nan" not in report
