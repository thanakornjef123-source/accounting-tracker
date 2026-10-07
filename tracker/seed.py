"""Synthetic demo data.

Everything here is invented: the office, staff, clients, contacts and
statuses. Contacts use example.com and made-up LINE IDs.
"""

from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta

from . import repo
from . import workflow as wf
from .deadlines import DEFAULT_RULES

DEMO_TODAY = date(2026, 10, 12)
HISTORY_PERIOD = "2026-08"
CURRENT_PERIOD = "2026-09"

STAFF = [
    (1, "วิไล", wf.OWNER),
    (2, "สมชาย", wf.ACCOUNTANT),
    (3, "นภา", wf.ACCOUNTANT),
    (4, "กิตติ", wf.ACCOUNTANT),
    (5, "ปราณี", wf.ADMIN),
]
# Uneven on purpose: the case study's workload problem (issue 6)
PRIMARY_SHARE = [2] * 17 + [3] * 14 + [4] * 9

HOLIDAYS = [
    ("2026-10-23", "วันปิยมหาราช"),
]

NAME_PARTS = [
    "สยามรุ่งเรือง", "ทองดีการค้า", "บ้านสวนฟาร์ม", "รุ่งอรุณเทรดดิ้ง", "ศรีนครวัสดุ", "เจริญผลซัพพลาย",
    "นำชัยออโต้", "ใบไม้เขียวคาเฟ่", "ฟ้าใสคลีนนิ่ง", "มั่นคงก่อสร้าง", "ภูผาทัวร์", "ดีไซน์ดีสตูดิโอ",
    "ข้าวหอมโภชนา", "ไทยรักษ์พลาสติก", "สุขใจเฮลท์", "เกียรติทองขนส่ง", "พรพิมลแฟชั่น", "เมืองเก่ามีเดีย",
    "กรีนเทคโซลูชั่น", "นาคาเฟอร์นิเจอร์", "แสงทองการพิมพ์", "บัวขาวสปา", "ลานนาออร์แกนิก", "ชลบุรีซีฟู้ด",
    "พัฒนาไอที", "เรือนไทยโฮมสเตย์", "สามพรานเกษตร", "ปัญญาติวเตอร์", "ดาวเหนือเอ็นจิเนียริ่ง", "อิ่มสุขเบเกอรี่",
    "วิวัฒน์อิเล็กทริก", "ทะเลงามรีสอร์ท", "มิตรภาพการยาง", "ช่างดีเซอร์วิส", "รวมใจสหกิจ", "ใจดีเพ็ทช็อป",
    "นิยมยนต์พาร์ท", "บางกอกบิวตี้", "ขวัญใจการเกษตร", "เก้าดาวลอจิสติกส์",
]
BUSINESS_TYPES = [
    "ค้าปลีก", "ค้าส่ง", "ร้านอาหาร/คาเฟ่", "บริการ", "ก่อสร้าง", "ขนส่ง", "ผลิต", "ออนไลน์",
]
NOTE_TEMPLATES = [
    "ส่ง statement เป็นรูปถ่ายจาก LINE มักไม่ชัด ให้ขอไฟล์ PDF จากแอปธนาคารแทน",
    "มีบัญชีธนาคาร 2 บัญชี (บัญชีขายหน้าร้าน และบัญชีโอนจ่ายซัพพลายเออร์) ต้องขอให้ครบทั้งสองบัญชี",
    "เจ้าของสะดวกคุยช่วงเย็นหลัง 18:00 น. ตอนกลางวันให้ติดต่อผู้จัดการร้าน",
    "ค่าเช่าที่จ่ายให้บุคคลธรรมดาต้องหัก ภ.ง.ด.3 ทุกเดือน ลูกค้ามักลืมส่งหนังสือรับรองการหัก",
    "ใบกำกับภาษีซื้อจากซัพพลายเออร์รายใหญ่มาช้า ประมาณวันที่ 5 ของเดือน",
    "ขายผ่าน marketplace ให้ดาวน์โหลดรายงานยอดขายจากระบบร้านค้าเอง ไม่ต้องรอลูกค้า",
    "มีพนักงานรายวันเปลี่ยนบ่อย ตรวจรายชื่อในสรุปเงินเดือนเทียบเดือนก่อนทุกครั้ง",
    "",
]


def _doc_types(vat: bool, employees: bool) -> list[str]:
    docs = ["รายการเดินบัญชีธนาคาร", "บิล/ใบเสร็จค่าใช้จ่าย"]
    docs += ["ใบกำกับภาษีซื้อ", "ใบกำกับภาษีขาย"] if vat else ["ใบแจ้งหนี้/ใบเสร็จขาย"]
    if employees:
        docs.append("สรุปเงินเดือนพนักงาน")
    return docs


def _forms(vat: bool, employees: bool, pays_individuals: bool) -> list[str]:
    forms = ["ภ.ง.ด.53"]
    if employees:
        forms.append("ภ.ง.ด.1")
    if pays_individuals:
        forms.append("ภ.ง.ด.3")
    if vat:
        forms.append("ภ.พ.30")
    return forms


def _business_days_before(d: date, n: int) -> date:
    while n > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def seed(conn: sqlite3.Connection, rng_seed: int = 42) -> None:
    rng = random.Random(rng_seed)

    conn.executemany("INSERT INTO staff (id, name, role) VALUES (?, ?, ?)", STAFF)
    conn.executemany(
        "INSERT INTO deadline_rules (form, paper_day, efiling_day) VALUES (?, ?, ?)",
        [(r.form, r.paper_day, r.efiling_day) for r in DEFAULT_RULES.values()],
    )
    conn.executemany("INSERT INTO holidays (day, name) VALUES (?, ?)", HOLIDAYS)
    for key, value in {
        "today": DEMO_TODAY.isoformat(),
        "filing_method": "efiling",
        "bookkeeping_day": "10",
        "report_day": "28",
    }.items():
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))

    primaries = PRIMARY_SHARE[:]
    rng.shuffle(primaries)
    for i, part in enumerate(NAME_PARTS, start=1):
        legal = "บริษัท {} จำกัด" if rng.random() < 0.7 else "ห้างหุ้นส่วนจำกัด {}"
        vat = rng.random() < 0.6
        employees = rng.random() < 0.55
        pays_individuals = rng.random() < 0.6
        channel = "LINE" if rng.random() < 0.7 else "อีเมล"
        contact = f"@demo{i:02d}" if channel == "LINE" else f"client{i:02d}@example.com"
        primary = primaries[i - 1]
        backup = rng.choice([s for s in (2, 3, 4) if s != primary])
        conn.execute(
            """INSERT INTO clients (id, name, business_type, vat_registered, has_employees, channel,
                   contact, primary_staff_id, backup_staff_id, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (i, legal.format(part), rng.choice(BUSINESS_TYPES), int(vat), int(employees), channel,
             contact, primary, backup, rng.choice(NOTE_TEMPLATES)),
        )
        conn.executemany(
            "INSERT INTO client_doc_types (client_id, doc_type) VALUES (?, ?)",
            [(i, d) for d in _doc_types(vat, employees)],
        )
        conn.executemany(
            "INSERT INTO client_forms (client_id, form) VALUES (?, ?)",
            [(i, f) for f in _forms(vat, employees, pays_individuals)],
        )
    conn.commit()

    _seed_finished_period(conn, rng, HISTORY_PERIOD)
    _seed_current_period(conn, rng, CURRENT_PERIOD)


def _set_today(conn: sqlite3.Connection, d: date) -> None:
    conn.execute("UPDATE settings SET value = ? WHERE key = 'today'", (d.isoformat(),))


def _seed_finished_period(conn: sqlite3.Connection, rng: random.Random, period: str) -> None:
    """A fully closed month, so reports and notifications have history."""
    repo.open_period(conn, period)
    for doc in conn.execute("SELECT id FROM documents WHERE period = ?", (period,)).fetchall():
        conn.execute(
            "UPDATE documents SET status = 'received', channel = ?, received_on = ? WHERE id = ?",
            (rng.choice(repo.DOC_CHANNELS), date(2026, 9, rng.randint(1, 9)).isoformat(), doc["id"]),
        )
    for t in conn.execute("SELECT id, due_date, task_type FROM tasks WHERE period = ?", (period,)).fetchall():
        due = date.fromisoformat(t["due_date"])
        done = _business_days_before(due, rng.randint(0, 2))
        submitted = _business_days_before(done, rng.randint(1, 3)) if wf.needs_review(t["task_type"]) else None
        conn.execute(
            "UPDATE tasks SET status = 'done', submitted_on = ?, approved_on = ?, done_on = ? WHERE id = ?",
            (submitted and submitted.isoformat(), submitted and done.isoformat(), done.isoformat(), t["id"]),
        )
    conn.commit()

    for c in conn.execute("SELECT id FROM clients").fetchall():
        _set_today(conn, date(2026, 9, 9))
        repo._notify(conn, c["id"], period, repo.EVENT_DOCS_COMPLETE,
                     f"สำนักงานได้รับเอกสารประจำเดือน ส.ค. 2569 ครบแล้ว ขอบคุณค่ะ")
        for t in conn.execute(
            "SELECT task_type, done_on FROM tasks WHERE client_id = ? AND period = ? ORDER BY done_on",
            (c["id"], period),
        ).fetchall():
            _set_today(conn, date.fromisoformat(t["done_on"]))
            if wf.is_tax_form(t["task_type"]):
                repo._notify(conn, c["id"], period, repo.EVENT_FILED,
                             f"สำนักงานยื่นแบบ {t['task_type']} ประจำเดือน ส.ค. 2569 เรียบร้อยแล้ว")
            elif t["task_type"] == wf.CLIENT_REPORT:
                repo._notify(conn, c["id"], period, repo.EVENT_REPORT_SENT,
                             "สำนักงานส่งรายงานประจำเดือน ส.ค. 2569 ให้แล้ว")
    _set_today(conn, DEMO_TODAY)
    conn.commit()


def _seed_current_period(conn: sqlite3.Connection, rng: random.Random, period: str) -> None:
    """The month in progress as of DEMO_TODAY: a realistic mix of states."""
    repo.open_period(conn, period)
    on = DEMO_TODAY

    for c in conn.execute("SELECT id FROM clients").fetchall():
        docs = conn.execute(
            "SELECT id FROM documents WHERE client_id = ? AND period = ?", (c["id"], period)
        ).fetchall()
        roll = rng.random()
        if roll < 0.62:
            outstanding = []
        else:
            outstanding = rng.sample([d["id"] for d in docs], k=min(len(docs), rng.choice([1, 1, 2, 3])))
        resubmit = outstanding[:1] if outstanding and rng.random() < 0.3 else []
        for d in docs:
            if d["id"] in resubmit:
                conn.execute(
                    "UPDATE documents SET status = 'resubmit', channel = 'LINE', note = ? WHERE id = ?",
                    ("รูปถ่ายไม่ชัด อ่านยอดเงินไม่ออก", d["id"]),
                )
            elif d["id"] not in outstanding:
                conn.execute(
                    "UPDATE documents SET status = 'received', channel = ?, received_on = ? WHERE id = ?",
                    (rng.choice(repo.DOC_CHANNELS), date(2026, 10, rng.randint(1, 9)).isoformat(), d["id"]),
                )
        complete = not outstanding

        tasks = {
            t["task_type"]: t["id"]
            for t in conn.execute(
                "SELECT id, task_type FROM tasks WHERE client_id = ? AND period = ?", (c["id"], period)
            ).fetchall()
        }

        def set_task(task_id: int, status: str, submitted_days: int | None = None) -> None:
            submitted = _business_days_before(on, submitted_days) if submitted_days is not None else None
            approved = on - timedelta(days=1) if status in (wf.APPROVED, wf.DONE) else None
            done = on - timedelta(days=rng.randint(0, 2)) if status == wf.DONE else None
            conn.execute(
                "UPDATE tasks SET status = ?, submitted_on = ?, approved_on = ?, done_on = ? WHERE id = ?",
                (status, submitted and submitted.isoformat(), approved and approved.isoformat(),
                 done and done.isoformat(), task_id),
            )

        if complete:
            bk = rng.choices([wf.DONE, wf.REVIEW, wf.DOING], weights=[45, 35, 20])[0]
        else:
            bk = rng.choice([wf.TODO, wf.DOING])
        set_task(tasks[wf.BOOKKEEPING], bk, rng.randint(1, 6) if bk in (wf.REVIEW, wf.DONE) else None)

        for form in ("ภ.ง.ด.1", "ภ.ง.ด.3", "ภ.ง.ด.53"):
            if form not in tasks:
                continue
            if bk == wf.DONE:
                st = rng.choices([wf.DONE, wf.APPROVED, wf.REVIEW, wf.DOING], weights=[20, 25, 35, 20])[0]
            elif bk == wf.REVIEW:
                st = rng.choice([wf.DOING, wf.TODO])
            else:
                st = wf.TODO
            set_task(tasks[form], st, rng.randint(1, 5) if st in (wf.REVIEW, wf.APPROVED, wf.DONE) else None)

        if "ภ.พ.30" in tasks:
            st = rng.choice([wf.DOING, wf.TODO]) if bk == wf.DONE else wf.TODO
            set_task(tasks["ภ.พ.30"], st)

    conn.commit()

    for c in conn.execute("SELECT id FROM clients").fetchall():
        if repo.docs_complete(conn, c["id"], period):
            _set_today(conn, date(2026, 10, 9))
            repo._notify(conn, c["id"], period, repo.EVENT_DOCS_COMPLETE,
                         "สำนักงานได้รับเอกสารประจำเดือน ก.ย. 2569 ครบแล้ว ขอบคุณค่ะ")
        for t in conn.execute(
            "SELECT task_type, done_on FROM tasks WHERE client_id = ? AND period = ? AND status = 'done'",
            (c["id"], period),
        ).fetchall():
            if wf.is_tax_form(t["task_type"]):
                _set_today(conn, date.fromisoformat(t["done_on"]))
                repo._notify(conn, c["id"], period, repo.EVENT_FILED,
                             f"สำนักงานยื่นแบบ {t['task_type']} ประจำเดือน ก.ย. 2569 เรียบร้อยแล้ว")
    _set_today(conn, DEMO_TODAY)
    conn.commit()


def reset(conn: sqlite3.Connection) -> None:
    """Wipe everything and load the demo data again."""
    for table in ("notifications", "task_events", "tasks", "documents", "client_forms",
                  "client_doc_types", "clients", "holidays", "deadline_rules", "settings", "staff"):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    seed(conn)
