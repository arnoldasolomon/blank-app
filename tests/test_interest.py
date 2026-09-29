from datetime import date

import pytest

from recovery.interest import (
    Invoice,
    compound_interest,
    due_date,
    evaluate_invoice,
    format_inr,
    statutory_annual_rate,
)
from recovery.templates import LANGUAGES, TEMPLATES, TIERS, render


def test_statutory_rate_is_three_times_bank_rate():
    assert statutory_annual_rate(5.5) == pytest.approx(0.165)


def test_due_date_defaults_to_15_days_without_agreement():
    assert due_date(date(2026, 1, 1), None) == date(2026, 1, 16)


def test_due_date_caps_agreed_credit_at_45_days():
    assert due_date(date(2026, 1, 1), 90) == date(2026, 2, 15)
    assert due_date(date(2026, 1, 1), 30) == date(2026, 1, 31)


def test_compound_interest_whole_months():
    # 12 monthly rests at 16.5% p.a. on 1 lakh
    expected = 100000 * (1 + 0.165 / 12) ** 12 - 100000
    assert compound_interest(100000, date(2025, 1, 10), date(2026, 1, 10), 0.165) == pytest.approx(expected, abs=0.01)


def test_compound_interest_partial_month():
    expected = 100000 * (1 + 0.165 / 12) * (1 + 0.165 / 12 * 15 / 30) - 100000
    assert compound_interest(100000, date(2026, 1, 1), date(2026, 2, 16), 0.165) == pytest.approx(expected, abs=0.01)


def test_compound_interest_month_end_start():
    # Jan 31 + 1 month clamps to Feb 28; Mar 31 is 2 whole months later
    expected = 100000 * (1 + 0.01) ** 2 - 100000
    assert compound_interest(100000, date(2026, 1, 31), date(2026, 3, 31), 0.12) == pytest.approx(expected, abs=0.01)


def test_no_interest_before_due_date():
    result = evaluate_invoice(Invoice("A", date(2026, 9, 20), 50000, 0, 45), date(2026, 9, 29), 5.5)
    assert result.days_overdue == 0
    assert result.interest == 0


def test_part_payment_reduces_principal():
    result = evaluate_invoice(Invoice("A", date(2026, 1, 1), 100000, 40000, None), date(2026, 9, 29), 5.5)
    assert result.outstanding == 60000
    assert result.interest > 0


def test_supply_before_udyam_registration_gets_no_interest():
    result = evaluate_invoice(
        Invoice("A", date(2021, 1, 1), 100000), date(2026, 9, 29), 5.5, udyam_registration_date=date(2022, 1, 1)
    )
    assert result.interest == 0
    assert any("Udyam" in w for w in result.warnings)
    assert any("time-barred" in w for w in result.warnings)


@pytest.mark.parametrize(
    "amount, expected",
    [(0, "0.00"), (999, "999.00"), (1000, "1,000.00"), (123456.5, "1,23,456.50"), (12345678, "1,23,45,678.00")],
)
def test_format_inr(amount, expected):
    assert format_inr(amount) == expected


@pytest.mark.parametrize("language", list(LANGUAGES))
@pytest.mark.parametrize("tier", list(TIERS))
def test_every_template_renders(language, tier):
    assert set(TEMPLATES[language]) == set(TIERS) | {"waiver"}
    text = render(
        language, tier, offer_waiver=True, buyer="B", supplier="S", udyam="U", invoices="I1",
        principal="1,000.00", interest="10.00", total="1,010.00", max_days=30, as_of="29-09-2026",
        deadline_days=7,
    )
    assert "1,000.00" in text or "1,010.00" in text
    assert "{" not in text
