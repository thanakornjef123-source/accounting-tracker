import pytest

from tracker import workflow as wf


def walk(task_type, actions):
    status = wf.TODO
    for action, role, *comment in actions:
        status = wf.next_status(task_type, status, action, role, *(comment or [""]))
    return status


def test_tax_return_needs_owner_approval_then_filing():
    assert walk("ภ.พ.30", [
        ("start", wf.ACCOUNTANT),
        ("submit", wf.ACCOUNTANT),
        ("approve", wf.OWNER),
    ]) == wf.APPROVED
    assert wf.next_status("ภ.พ.30", wf.APPROVED, "file", wf.ACCOUNTANT) == wf.DONE


def test_bookkeeping_is_done_once_approved():
    assert walk(wf.BOOKKEEPING, [
        ("start", wf.ACCOUNTANT), ("submit", wf.ACCOUNTANT), ("approve", wf.OWNER),
    ]) == wf.DONE


def test_client_report_skips_review():
    assert walk(wf.CLIENT_REPORT, [("start", wf.ACCOUNTANT), ("complete", wf.ACCOUNTANT)]) == wf.DONE


def test_accountant_cannot_approve():
    with pytest.raises(wf.WorkflowError):
        wf.next_status("ภ.ง.ด.53", wf.REVIEW, "approve", wf.ACCOUNTANT)


def test_cannot_file_before_approval():
    with pytest.raises(wf.WorkflowError):
        wf.next_status("ภ.ง.ด.53", wf.REVIEW, "file", wf.ACCOUNTANT)


def test_return_requires_reason():
    with pytest.raises(wf.WorkflowError):
        wf.next_status("ภ.ง.ด.53", wf.REVIEW, "return", wf.OWNER, "  ")
    assert wf.next_status("ภ.ง.ด.53", wf.REVIEW, "return", wf.OWNER, "ยอดไม่ตรง") == wf.DOING


def test_admin_has_no_task_actions():
    assert wf.available_actions("ภ.พ.30", wf.TODO, wf.ADMIN) == []
