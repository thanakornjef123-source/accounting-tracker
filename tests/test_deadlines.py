from datetime import date

import pytest

from tracker.deadlines import DEFAULT_RULES, EFILING, PAPER, filing_deadline, next_business_day
from tracker.periods import add_months, thai_label

HOLIDAYS = [date(2026, 10, 23)]  # วันปิยมหาราช


def test_withholding_efiling_due_15th_of_next_month():
    assert filing_deadline("2026-09", DEFAULT_RULES["ภ.ง.ด.53"], EFILING, HOLIDAYS) == date(2026, 10, 15)


def test_withholding_paper_due_7th():
    assert filing_deadline("2026-09", DEFAULT_RULES["ภ.ง.ด.1"], PAPER, HOLIDAYS) == date(2026, 10, 7)


def test_vat_efiling_moves_past_holiday_and_weekend():
    # 23 Oct 2026 is a public holiday (Fri) -> Mon 26 Oct, matching the Revenue Department calendar
    assert filing_deadline("2026-09", DEFAULT_RULES["ภ.พ.30"], EFILING, HOLIDAYS) == date(2026, 10, 26)


def test_deadline_on_sunday_moves_to_monday():
    # 15 Nov 2026 is a Sunday -> 16 Nov, matching the Revenue Department calendar
    assert filing_deadline("2026-10", DEFAULT_RULES["ภ.ง.ด.3"], EFILING) == date(2026, 11, 16)


def test_december_period_files_in_january():
    assert filing_deadline("2026-12", DEFAULT_RULES["ภ.พ.30"], PAPER) == date(2027, 1, 15)


def test_business_day_is_unchanged():
    assert next_business_day(date(2026, 10, 14), HOLIDAYS) == date(2026, 10, 14)


def test_unknown_method_rejected():
    with pytest.raises(ValueError):
        filing_deadline("2026-09", DEFAULT_RULES["ภ.พ.30"], "fax")


def test_period_helpers():
    assert add_months("2026-12", 1) == "2027-01"
    assert add_months("2026-01", -1) == "2025-12"
    assert thai_label("2026-09") == "ก.ย. 2569"
