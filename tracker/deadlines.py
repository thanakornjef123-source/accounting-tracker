"""Filing-deadline rules.

Default days follow the Revenue Department tax calendar for 2569 (2026):

* Withholding tax (ภ.ง.ด.1, 3, 53): paper by the 7th, e-filing by the 15th
  of the following month.
* VAT (ภ.พ.30): paper by the 15th, e-filing by the 23rd.

A deadline that falls on a weekend or a listed public holiday moves to the
next business day (e.g. ภ.พ.30 for Sep 2026 is due 26 Oct 2026 because
23 Oct is Chulalongkorn Day). The e-filing extension comes from a Ministry of
Finance announcement that is renewed from time to time, so the days are stored
as editable settings rather than hard-coded in the app logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from .periods import filing_month

PAPER = "paper"
EFILING = "efiling"


@dataclass(frozen=True)
class FormRule:
    form: str
    paper_day: int
    efiling_day: int

    def day_for(self, method: str) -> int:
        if method == PAPER:
            return self.paper_day
        if method == EFILING:
            return self.efiling_day
        raise ValueError(f"unknown filing method {method!r}")


DEFAULT_RULES: dict[str, FormRule] = {
    "ภ.ง.ด.1": FormRule("ภ.ง.ด.1", 7, 15),
    "ภ.ง.ด.3": FormRule("ภ.ง.ด.3", 7, 15),
    "ภ.ง.ด.53": FormRule("ภ.ง.ด.53", 7, 15),
    "ภ.พ.30": FormRule("ภ.พ.30", 15, 23),
}

TAX_FORMS = tuple(DEFAULT_RULES)


def is_business_day(d: date, holidays: Iterable[date]) -> bool:
    return d.weekday() < 5 and d not in set(holidays)


def next_business_day(d: date, holidays: Iterable[date]) -> date:
    """Return ``d`` itself if it is a business day, else the next one."""
    holiday_set = set(holidays)
    while d.weekday() >= 5 or d in holiday_set:
        d += timedelta(days=1)
    return d


def filing_deadline(
    period: str,
    rule: FormRule,
    method: str,
    holidays: Iterable[date] = (),
) -> date:
    year, month = filing_month(period)
    nominal = date(year, month, rule.day_for(method))
    return next_business_day(nominal, holidays)


def nominal_day_in_filing_month(period: str, day: int, holidays: Iterable[date] = ()) -> date:
    """An internal due date on a given day of the filing month, shifted to a business day."""
    year, month = filing_month(period)
    return next_business_day(date(year, month, day), holidays)
