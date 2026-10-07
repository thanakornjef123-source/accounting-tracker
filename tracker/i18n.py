"""Thai / English display text.

Thai is the source language: the Thai sentence is the lookup key, so code that
has not been translated still shows readable Thai. Values stored in the
database (task types, form names, channels) stay Thai; only what is shown on
screen goes through ``translate``.

A dictionary value is either a string or a ``(singular, plural)`` pair; the pair
is chosen by the ``n`` keyword argument.
"""

from __future__ import annotations

from datetime import date

from .en import EN
from .periods import THAI_MONTHS_SHORT, parse_period

LANGS = ("th", "en")
DEFAULT_LANG = "th"
LANG_NAMES = {"th": "ไทย", "en": "English"}

EN_MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _company_name(text: str) -> str | None:
    """'บริษัท X จำกัด' -> 'X Co., Ltd.' and 'ห้างหุ้นส่วนจำกัด X' -> 'X Ltd. Partnership'."""
    if text.startswith("บริษัท ") and text.endswith(" จำกัด"):
        core = text[len("บริษัท "):-len(" จำกัด")]
        return f"{EN.get(core, core)} Co., Ltd."
    if text.startswith("ห้างหุ้นส่วนจำกัด "):
        core = text[len("ห้างหุ้นส่วนจำกัด "):]
        return f"{EN.get(core, core)} Ltd. Partnership"
    return None


def translate(text: str, lang: str = DEFAULT_LANG, **params) -> str:
    if lang == "en":
        found = EN.get(text) or _company_name(text) or text
        if isinstance(found, tuple):
            found = found[0] if params.get("n") == 1 else found[1]
        text = found
    return text.format(**params) if params else text


def date_text(d: date, lang: str = DEFAULT_LANG) -> str:
    if lang == "en":
        return f"{d.day} {EN_MONTHS_SHORT[d.month - 1]} {d.year}"
    return f"{d.day} {THAI_MONTHS_SHORT[d.month - 1]} {d.year + 543}"


def period_text(period: str, lang: str = DEFAULT_LANG) -> str:
    year, month = parse_period(period)
    if lang == "en":
        return f"{EN_MONTHS_SHORT[month - 1]} {year}"
    return f"{THAI_MONTHS_SHORT[month - 1]} {year + 543}"
