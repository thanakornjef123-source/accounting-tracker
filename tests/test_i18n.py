"""The Thai / English switch: every sentence has an English text, and no page leaks Thai in English mode."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from tracker import repo, seed
from tracker.en import EN
from tracker.i18n import date_text, period_text, translate
from views.common import get_conn

from test_ui_buttons import PAGES, ROLES

ROOT = Path(__file__).resolve().parent.parent
THAI = re.compile("[฀-๿]")
PLACEHOLDER = re.compile(r"\{(\w+)\}")


@pytest.fixture(autouse=True)
def db():
    st.cache_resource.clear()
    conn = get_conn()
    seed.reset(conn)
    return conn


def _source_sentences() -> set[str]:
    """Every Thai literal passed to t(), tr(), page_header() or raised as an error."""
    found: set[str] = set()
    files = [ROOT / "app.py", *(ROOT / "views").glob("*.py"), *(ROOT / "tracker").glob("*.py")]
    for path in files:
        if path.name in ("en.py", "i18n.py"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.args:
                if node.func.id in {"t", "tr", "page_header", "page", "translate", "ValueError", "WorkflowError"}:
                    arg = node.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and THAI.search(arg.value):
                        found.add(arg.value)
    return found


def test_every_sentence_in_the_code_has_an_english_text():
    missing = sorted(s for s in _source_sentences() if s not in EN)
    assert not missing, f"add these to tracker/en.py: {missing}"


def test_english_texts_keep_the_same_placeholders():
    for thai, english in EN.items():
        for value in (english if isinstance(english, tuple) else (english,)):
            assert set(PLACEHOLDER.findall(thai)) >= set(PLACEHOLDER.findall(value)) - {"n"} or \
                set(PLACEHOLDER.findall(thai)) == set(PLACEHOLDER.findall(value)), (thai, value)
        assert not THAI.search(" ".join(english if isinstance(english, tuple) else [english])), thai


def test_plural_and_dates():
    assert translate("{n} งาน", "en", n=1) == "1 task"
    assert translate("{n} งาน", "en", n=3) == "3 tasks"
    assert translate("{n} งาน", "th", n=3) == "3 งาน"
    assert translate("อีก {n} วัน", "en", n=1) == "1 day left"
    assert translate("ข้อความที่ไม่มีในพจนานุกรม", "en") == "ข้อความที่ไม่มีในพจนานุกรม"
    from datetime import date
    assert date_text(date(2026, 10, 12), "en") == "12 Oct 2026"
    assert date_text(date(2026, 10, 12), "th") == "12 ต.ค. 2569"
    assert period_text("2026-09", "en") == "Sep 2026"
    assert period_text("2026-09", "th") == "ก.ย. 2569"


def test_company_names_are_translated():
    assert translate("บริษัท สยามรุ่งเรือง จำกัด", "en") == "Siam Rungrueang Co., Ltd."
    assert translate("ห้างหุ้นส่วนจำกัด บัวขาวสปา", "en") == "Buakhao Spa Ltd. Partnership"
    assert translate("บริษัท สยามรุ่งเรือง จำกัด", "th") == "บริษัท สยามรุ่งเรือง จำกัด"


def _visible_text(at: AppTest) -> list[str]:
    out: list[str] = []
    for group in (at.markdown, at.title, at.header, at.subheader, at.caption, at.error, at.warning,
                  at.success, at.info):
        out += [e.value for e in group]
    for group in (at.button, at.selectbox, at.multiselect, at.text_input, at.text_area, at.toggle, at.radio,
                  at.date_input, at.number_input, at.checkbox, at.metric):
        out += [e.label for e in group]
    for group in (at.selectbox, at.multiselect, at.radio):
        for widget in group:
            out += [str(o) for o in widget.options]
    out += [m.value for m in at.metric] + [m.delta for m in at.metric if m.delta]
    out += [tab.label for tab in at.tabs] + [x.label for x in at.expander]
    return [s for s in out if isinstance(s, str) and THAI.search(s)]


def english(module: str, user_id: int):
    at = AppTest.from_string(
        f"import streamlit as st\nfrom views.common import get_conn, sidebar, _init_lang\nfrom views import {module} as page\n"
        "_init_lang()\nctx = sidebar(get_conn())\npage.render(ctx)\n",
        default_timeout=60,
    )
    at.session_state["user_id"] = user_id
    at.session_state["period"] = "2026-09"
    at.session_state["lang"] = "en"
    return at.run()


@pytest.mark.parametrize("module", PAGES)
@pytest.mark.parametrize("role", ROLES)
def test_no_thai_left_in_english_mode(module, role):
    at = english(module, ROLES[role])
    assert not at.exception, [e.value for e in at.exception]
    leaks = _visible_text(at)
    # the language picker itself names Thai in Thai on purpose
    leaks = [s for s in leaks if "Language" not in s and s != "ไทย"]
    assert not leaks, leaks[:5]


def test_language_switch_in_sidebar_changes_the_page():
    at = AppTest.from_string(
        "from views.common import get_conn, sidebar, _init_lang\nfrom views import dashboard\n"
        "_init_lang()\ndashboard.render(sidebar(get_conn()))\n", default_timeout=60).run()
    assert any("ภาพรวม" in t.value for t in at.title)
    at.radio(key="lang").set_value("en").run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("Overview" in t.value for t in at.title)
    # (switching back is not driven here: AppTest re-evaluates format_func outside the script run)


def test_english_client_report_has_no_thai():
    conn = get_conn()
    client_id = int(repo.document_summary(conn, "2026-09").iloc[0]["client_id"])
    report = repo.client_report(conn, client_id, "2026-09", "en")
    assert not THAI.search(report), THAI.findall(report)[:10]
    assert "Monthly status report" in report


def test_the_main_app_starts_in_both_languages():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception
    at.radio(key="lang").set_value("en").run()
    assert not at.exception, [e.value for e in at.exception]
