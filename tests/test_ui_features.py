"""UI flows for the gap-fix features: team page, add client, blank office, login gate."""

import os

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from test_ui_buttons import ADMIN, OWNER, SOMCHAI, make, ok, page
from tracker import repo, seed
from views.common import get_conn


@pytest.fixture(autouse=True)
def db():
    st.cache_resource.clear()
    conn = get_conn()
    seed.reset(conn)
    return conn


def _submit(at, label):
    [b for b in at.button if b.label == label][0].click()
    return at.run()


def test_team_page_owner_adds_staff_and_sets_password(db):
    at = ok(page("staff"))
    at.text_input(key="new_staff_password").set_value("goodpass1")
    [ti for ti in at.text_input if ti.label == "ชื่อ"][0].set_value("พนักงานใหม่")
    at = ok(_submit(at, "เพิ่มพนักงาน"))
    assert "พนักงานใหม่" in set(repo.staff(db)["name"])
    row = db.execute("SELECT password_hash FROM staff WHERE name = 'พนักงานใหม่'").fetchone()
    assert row["password_hash"] and "goodpass1" not in row["password_hash"]


def test_team_page_rejects_weak_password(db):
    at = ok(page("staff"))
    at.text_input(key="reset_password").set_value("weak")
    at = ok(_submit(at, "ตั้งรหัสผ่าน"))
    assert at.error


@pytest.mark.parametrize("uid", [SOMCHAI, ADMIN])
def test_team_page_is_owner_only(uid):
    at = ok(page("staff", uid))
    assert at.info and not at.text_input


def test_add_client_form_creates_client(db):
    at = ok(page("clients"))
    [ti for ti in at.text_input if ti.label == "ชื่อลูกค้า"][0].set_value("ห้างทดสอบ")
    at.text_input(key="new_client_contact").set_value("@hang")
    at.selectbox(key="new_client_backup").select_index(1)
    at = ok(_submit(at, "เพิ่มลูกค้า"))
    assert not at.error
    assert "ห้างทดสอบ" in set(repo.clients(db)["name"])


def test_add_client_form_shows_validation_error(db):
    at = ok(page("clients"))
    [ti for ti in at.text_input if ti.label == "ชื่อลูกค้า"][0].set_value("ห้างเสีย")
    at.selectbox(key="new_client_channel").select("อีเมล")
    at.text_input(key="new_client_contact").set_value("not-an-email")
    at.selectbox(key="new_client_backup").select_index(1)
    at = ok(_submit(at, "เพิ่มลูกค้า"))
    assert at.error
    assert "ห้างเสีย" not in set(repo.clients(db)["name"])


def _auth_script():
    return ("from views.common import get_conn, sidebar\nfrom views import dashboard\n"
            "dashboard.render(sidebar(get_conn()))\n")


def test_login_gate_blocks_until_signed_in(monkeypatch):
    monkeypatch.setenv("TRACKER_AUTH", "1")
    conn = get_conn()
    from tracker import auth
    auth.set_password(conn, OWNER, "goodpass1")
    at = AppTest.from_string(_auth_script(), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    assert not any("ภาพรวม" in t.value for t in at.title)  # gated: dashboard not rendered
    assert at.text_input  # the sign-in form


def test_wrong_password_is_rejected_and_right_one_signs_in(monkeypatch):
    monkeypatch.setenv("TRACKER_AUTH", "1")
    from tracker import auth
    auth.clear_failures("วิไล")
    auth.set_password(get_conn(), OWNER, "goodpass1")
    at = AppTest.from_string(_auth_script(), default_timeout=60).run()
    fields = list(at.text_input)
    fields[0].set_value("วิไล")
    fields[1].set_value("wrongpass9")
    at = _submit_first_form(at)
    assert at.error and "auth_user" not in at.session_state
    fields = list(at.text_input)
    fields[0].set_value("วิไล")
    fields[1].set_value("goodpass1")
    at = _submit_first_form(at)
    assert not at.exception and at.session_state["auth_user"] == OWNER
    auth.clear_failures("วิไล")


def _submit_first_form(at):
    at.button[0].click()
    return at.run()


def test_clients_page_without_any_accountant_does_not_crash():
    c = get_conn()
    c.execute("UPDATE staff SET active = 0 WHERE role = 'accountant'")
    c.commit()
    ok(page("clients"))
