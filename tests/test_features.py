"""Gap-fix features: reopen, filing reference, ownership, clients, staff, auth, backup, blank DB."""

import sqlite3

import pytest

from tracker import auth, db, repo, seed
from tracker import workflow as wf

OWNER_ID = 1


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    seed.seed(c)
    yield c
    c.close()


def _staff(conn, role):
    return int(conn.execute("SELECT id FROM staff WHERE role = ? AND active = 1 ORDER BY id", (role,)).fetchone()["id"])


def _new_client(conn, **kw):
    args = dict(name="ร้านทดสอบ จำกัด", business_type="ร้านค้า", vat_registered=True, has_employees=False,
                pays_individuals=False, channel="LINE", contact="@test", primary_staff_id=_staff(conn, "accountant"),
                backup_staff_id=None)
    args.update(kw)
    return repo.add_client(conn, **args)


# ---- workflow
def test_owner_can_reopen_done_and_approved_only_with_comment():
    for status in (wf.APPROVED, wf.DONE):
        keys = [a.key for a in wf.available_actions("ภ.พ.30", status, wf.OWNER)]
        assert "reopen" in keys
    assert "reopen" not in [a.key for a in wf.available_actions("ภ.พ.30", wf.DOING, wf.OWNER)]
    assert "reopen" not in [a.key for a in wf.available_actions("ภ.พ.30", wf.DONE, wf.ACCOUNTANT)]
    with pytest.raises(wf.WorkflowError):
        wf.next_status("ภ.พ.30", wf.DONE, "reopen", wf.OWNER, "")
    assert wf.next_status("ภ.พ.30", wf.DONE, "reopen", wf.OWNER, "แก้ตัวเลข") == wf.DOING


def test_reopen_clears_dates_and_reference(conn):
    row = conn.execute("SELECT id FROM tasks WHERE status = 'done' AND filing_ref != '' LIMIT 1").fetchone()
    if row is None:
        row = conn.execute("SELECT id FROM tasks WHERE status = 'done' LIMIT 1").fetchone()
    repo.act_on_task(conn, row["id"], "reopen", OWNER_ID, comment="แก้ไข")
    t = repo.task(conn, row["id"])
    assert t["status"] == wf.DOING
    assert not t["done_on"] and not t["filing_ref"]


def test_filing_reference_saved_and_limited(conn):
    row = conn.execute("SELECT id FROM tasks WHERE status = 'approved' LIMIT 1").fetchone()
    assert row, "seed should contain an approved task"
    with pytest.raises((ValueError, wf.WorkflowError)):
        repo.act_on_task(conn, row["id"], "file", OWNER_ID, reference="x" * 41)
    repo.act_on_task(conn, row["id"], "file", OWNER_ID, reference=" REF-123 ")
    assert repo.task(conn, row["id"])["filing_ref"] == "REF-123"


def test_accountant_cannot_act_on_others_tasks(conn):
    acc = _staff(conn, "accountant")
    other = conn.execute(
        "SELECT t.* FROM tasks t JOIN clients c ON c.id = t.client_id "
        "WHERE t.assignee_id != ? AND IFNULL(c.backup_staff_id, 0) != ? AND t.status = 'todo' LIMIT 1",
        (acc, acc)).fetchone()
    assert other
    assert not repo.can_act(conn, other, acc)
    assert repo.can_act(conn, other, OWNER_ID)
    with pytest.raises(wf.WorkflowError):
        repo.act_on_task(conn, other["id"], "start", acc)


# ---- contacts and clients
def test_validate_contact():
    repo.validate_contact("อีเมล", "a@b.co")
    repo.validate_contact("LINE", "@shop")
    for ch, c in [("อีเมล", "nope"), ("LINE", "has space"), ("LINE", ""), ("อีเมล", "  ")]:
        with pytest.raises(ValueError):
            repo.validate_contact(ch, c)


def test_add_client_creates_tasks_and_documents(conn):
    n_before = len(repo.clients(conn))
    cid = _new_client(conn)
    assert len(repo.clients(conn)) == n_before + 1
    period = repo.periods(conn)[0]
    assert (repo.tasks(conn, period)["client_id"] == cid).any()
    assert (repo.document_summary(conn, period)["client_id"] == cid).any()


def test_add_client_rejects_bad_input(conn):
    with pytest.raises(ValueError):
        _new_client(conn, name="   ")
    with pytest.raises(ValueError):
        _new_client(conn, channel="อีเมล", contact="bad")


def test_deactivate_hides_client_from_lists(conn):
    cid = _new_client(conn)
    repo.set_client_active(conn, cid, False)
    assert cid not in set(repo.clients(conn)["id"])
    assert not (repo.tasks(conn)["client_id"] == cid).any()
    repo.set_client_active(conn, cid, True)
    assert cid in set(repo.clients(conn)["id"])


# ---- staff
def test_staff_management(conn):
    sid = repo.add_staff(conn, "สมใจ", "accountant")
    with pytest.raises(ValueError):
        repo.add_staff(conn, "สมใจ", "accountant")
    with pytest.raises(ValueError):
        repo.add_staff(conn, "", "accountant")
    with pytest.raises(ValueError):
        repo.add_staff(conn, "คนใหม่", "king")
    repo.rename_staff(conn, sid, "สมใจ ใหม่")
    repo.set_staff_active(conn, sid, False)
    assert sid not in set(repo.staff(conn)["id"])


def test_cannot_deactivate_last_owner_or_staff_with_work(conn):
    owners = conn.execute("SELECT id FROM staff WHERE role = 'owner' AND active = 1").fetchall()
    for o in owners[1:]:
        repo.set_staff_active(conn, o["id"], False)
    with pytest.raises(ValueError):
        repo.set_staff_active(conn, owners[0]["id"], False)
    with pytest.raises(wf.WorkflowError):
        repo.set_staff_active(conn, _staff(conn, "accountant"), False)


# ---- documents history and backup
def test_document_changes_are_logged(conn):
    period = repo.periods(conn)[0]
    docs = repo.documents(conn, period)
    row = docs[docs["status"] != "received"].iloc[0]
    cid = int(row["client_id"])
    before = len(repo.document_events(conn, cid, period))
    repo.update_documents(conn, [{"id": int(row["id"]), "status": "received", "channel": "LINE", "note": ""}],
                          actor_id=OWNER_ID)
    assert len(repo.document_events(conn, cid, period)) == before + 1


def test_backup_is_a_valid_database(conn, tmp_path):
    data = repo.backup_bytes(conn)
    p = tmp_path / "b.db"
    p.write_bytes(data)
    copy = sqlite3.connect(p)
    assert copy.execute("SELECT COUNT(*) FROM clients").fetchone()[0] == len(repo.clients(conn))
    copy.close()


# ---- blank DB
def test_blank_db_is_usable():
    c = db.connect(":memory:")
    seed.init_blank(c)
    assert not repo.is_demo(c)
    assert len(repo.staff(c)) == 1 and repo.staff(c).iloc[0]["role"] == "owner"
    assert len(repo.clients(c)) == 0
    with pytest.raises(ValueError):  # no accountant yet
        repo.add_client(c, name="ลูกค้าแรก", business_type="ร้านค้า", vat_registered=False, has_employees=False,
                        pays_individuals=False, channel="LINE", contact="@first", primary_staff_id=1,
                        backup_staff_id=None)
    acc = repo.add_staff(c, "นักบัญชี", "accountant")
    cid = repo.add_client(c, name="ลูกค้าแรก", business_type="ร้านค้า", vat_registered=False, has_employees=False,
                          pays_individuals=False, channel="LINE", contact="@first", primary_staff_id=acc,
                          backup_staff_id=None)
    assert cid
    assert repo.periods(c)
    c.close()


def test_old_database_is_migrated(tmp_path):
    p = tmp_path / "old.db"
    old = sqlite3.connect(p)
    old.executescript("CREATE TABLE staff (id INTEGER PRIMARY KEY, name TEXT, role TEXT);"
                      "INSERT INTO staff VALUES (1, 'เจ้าของ', 'owner');")
    old.commit()
    old.close()
    c = db.connect(str(p))
    cols = {r["name"] for r in c.execute("PRAGMA table_info(staff)")}
    assert {"active", "password_hash"} <= cols
    c.close()


# ---- auth
def test_password_hash_and_verify():
    h = auth.hash_password("abcd1234")
    assert h != "abcd1234" and auth.verify_password("abcd1234", h)
    assert not auth.verify_password("abcd12345", h)
    assert auth.hash_password("abcd1234") != h  # salted


@pytest.mark.parametrize("pw", ["short1", "allletters", "12345678", ""])
def test_weak_passwords_rejected(pw):
    with pytest.raises(ValueError):
        auth.check_strength(pw)


def test_authenticate_and_first_owner_setup():
    c = db.connect(":memory:")
    seed.init_blank(c)
    assert auth.owner_needs_setup(c)
    oid = auth.first_owner_id(c)
    auth.set_password(c, oid, "goodpass1")
    assert not auth.owner_needs_setup(c)
    assert auth.authenticate(c, "เจ้าของ", "goodpass1") == oid
    assert auth.authenticate(c, "เจ้าของ", "wrong") is None
    assert auth.authenticate(c, "ไม่มี", "goodpass1") is None
    c.close()


def test_lockout_after_repeated_failures():
    name = "locktest"
    auth.clear_failures(name)
    for i in range(5):
        auth.record_failure(name, now=1000.0 + i)
    assert auth.seconds_locked(name, now=1010.0) > 0
    assert auth.seconds_locked(name, now=1000.0 + 400) == 0
    auth.clear_failures(name)
    assert auth.seconds_locked(name, now=1010.0) == 0
