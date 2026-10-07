"""Helpers for monthly work periods.

A *period* is the month whose books are being closed, written as ``"YYYY-MM"``.
Work for period 2026-09 (September) is filed in October 2026.
"""

from __future__ import annotations

from datetime import date

THAI_MONTHS_SHORT = [
    "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]


def parse_period(period: str) -> tuple[int, int]:
    year_str, month_str = period.split("-")
    year, month = int(year_str), int(month_str)
    if not 1 <= month <= 12:
        raise ValueError(f"invalid month in period {period!r}")
    return year, month


def make_period(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def add_months(period: str, months: int) -> str:
    year, month = parse_period(period)
    index = year * 12 + (month - 1) + months
    return make_period(index // 12, index % 12 + 1)


def period_of(d: date) -> str:
    return make_period(d.year, d.month)


def filing_month(period: str) -> tuple[int, int]:
    """Year and month in which the period's monthly returns are filed."""
    return parse_period(add_months(period, 1))


def thai_label(period: str) -> str:
    """'2026-09' -> 'ก.ย. 2569' (Buddhist Era year)."""
    year, month = parse_period(period)
    return f"{THAI_MONTHS_SHORT[month - 1]} {year + 543}"


def thai_date(d: date) -> str:
    return f"{d.day} {THAI_MONTHS_SHORT[d.month - 1]} {d.year + 543}"
