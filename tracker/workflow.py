"""Task status workflow.

Bookkeeping and every tax return must be reviewed and approved by the owner
before they are finished; a tax return is then filed by the accountant.
Client reports do not need approval.

    todo -> doing -> review -> approved -> done   (tax returns)
    todo -> doing -> review -> done               (bookkeeping)
    todo -> doing -> done                         (client report)

The owner can send a task under review back to ``doing`` with a comment.
"""

from __future__ import annotations

from dataclasses import dataclass

from .deadlines import TAX_FORMS

BOOKKEEPING = "บันทึกบัญชี"
CLIENT_REPORT = "รายงานลูกค้า"

TASK_ORDER = (BOOKKEEPING, *TAX_FORMS, CLIENT_REPORT)

OWNER = "owner"
ACCOUNTANT = "accountant"
ADMIN = "admin"

ROLE_LABELS = {OWNER: "เจ้าของ", ACCOUNTANT: "พนักงานบัญชี", ADMIN: "ธุรการ"}

TODO, DOING, REVIEW, APPROVED, DONE = "todo", "doing", "review", "approved", "done"
OPEN_STATUSES = (TODO, DOING, REVIEW, APPROVED)

STATUS_LABELS = {
    TODO: "ยังไม่เริ่ม",
    DOING: "กำลังทำ",
    REVIEW: "รอเจ้าของตรวจ",
    APPROVED: "อนุมัติแล้ว รอยื่น",
    DONE: "เสร็จ",
}


def is_tax_form(task_type: str) -> bool:
    return task_type in TAX_FORMS


def needs_review(task_type: str) -> bool:
    return task_type == BOOKKEEPING or is_tax_form(task_type)


def done_label(task_type: str) -> str:
    return "ยื่นแล้ว" if is_tax_form(task_type) else "เสร็จ"


def status_label(task_type: str, status: str) -> str:
    return done_label(task_type) if status == DONE else STATUS_LABELS[status]


@dataclass(frozen=True)
class Action:
    key: str
    label: str
    needs_comment: bool = False


START = Action("start", "เริ่มทำ")
SUBMIT = Action("submit", "ส่งให้เจ้าของตรวจ")
APPROVE = Action("approve", "อนุมัติ")
RETURN = Action("return", "ส่งกลับให้แก้", needs_comment=True)
FILE = Action("file", "บันทึกว่ายื่นแล้ว")
COMPLETE = Action("complete", "ทำเสร็จแล้ว")

ACTIONS = {a.key: a for a in (START, SUBMIT, APPROVE, RETURN, FILE, COMPLETE)}


class WorkflowError(ValueError):
    pass


def available_actions(task_type: str, status: str, role: str) -> list[Action]:
    if role == ADMIN:
        return []
    actions: list[Action] = []
    if status == TODO:
        actions.append(START)
    elif status == DOING:
        actions.append(SUBMIT if needs_review(task_type) else COMPLETE)
    elif status == REVIEW and role == OWNER:
        actions += [APPROVE, RETURN]
    elif status == APPROVED and is_tax_form(task_type):
        actions.append(FILE)
    return actions


def next_status(task_type: str, status: str, action_key: str, role: str, comment: str = "") -> str:
    allowed = {a.key: a for a in available_actions(task_type, status, role)}
    if action_key not in allowed:
        raise WorkflowError(
            f"ทำ '{ACTIONS[action_key].label if action_key in ACTIONS else action_key}' "
            f"กับงานสถานะ '{status_label(task_type, status)}' ในบทบาท "
            f"'{ROLE_LABELS.get(role, role)}' ไม่ได้"
        )
    if allowed[action_key].needs_comment and not comment.strip():
        raise WorkflowError("ต้องใส่เหตุผลเมื่อส่งงานกลับให้แก้")
    if action_key in (START.key, RETURN.key):
        return DOING
    if action_key == SUBMIT.key:
        return REVIEW
    if action_key == APPROVE.key:
        return APPROVED if is_tax_form(task_type) else DONE
    return DONE  # FILE, COMPLETE
