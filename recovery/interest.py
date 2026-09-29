"""Delayed-payment calculations under the MSMED Act, 2006.

- Section 15: buyer must pay by the agreed date, which cannot exceed 45 days
  from acceptance. With no written agreement, payment is due within 15 days.
- Section 16: overdue amounts carry compound interest with monthly rests at
  three times the bank rate notified by the RBI.

These are estimates for drafting reminders. The Facilitation Council computes
the final figure; part-payment timing and bank-rate changes over the overdue
period are not modelled here.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

MAX_AGREED_CREDIT_DAYS = 45
DEFAULT_CREDIT_DAYS_NO_AGREEMENT = 15
LIMITATION_DAYS = 3 * 365


@dataclass
class Invoice:
    invoice_no: str
    delivery_date: date
    amount: float
    amount_paid: float = 0.0
    agreed_credit_days: int | None = None  # None = no written agreement


@dataclass
class InvoiceResult:
    invoice_no: str
    delivery_date: date
    due_date: date
    outstanding: float
    days_overdue: int
    interest: float
    warnings: list[str]

    @property
    def total_due(self) -> float:
        return self.outstanding + self.interest


def statutory_annual_rate(bank_rate_pct: float) -> float:
    """Section 16 rate: three times the RBI bank rate, as a fraction."""
    return 3 * bank_rate_pct / 100


def due_date(delivery_date: date, agreed_credit_days: int | None) -> date:
    if agreed_credit_days is None:
        days = DEFAULT_CREDIT_DAYS_NO_AGREEMENT
    else:
        days = min(max(agreed_credit_days, 0), MAX_AGREED_CREDIT_DAYS)
    return delivery_date + timedelta(days=days)


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def compound_interest(principal: float, start: date, as_of: date, annual_rate: float) -> float:
    """Interest with monthly rests from `start` to `as_of`.

    Whole calendar months compound; the leftover days accrue simple interest
    on the compounded balance (pro rata over 30 days).
    """
    if principal <= 0 or as_of <= start:
        return 0.0
    monthly_rate = annual_rate / 12
    months = 0
    while _add_months(start, months + 1) <= as_of:
        months += 1
    leftover_days = (as_of - _add_months(start, months)).days
    balance = principal * (1 + monthly_rate) ** months
    balance *= 1 + monthly_rate * leftover_days / 30
    return round(balance - principal, 2)


def evaluate_invoice(
    invoice: Invoice,
    as_of: date,
    bank_rate_pct: float,
    udyam_registration_date: date | None = None,
) -> InvoiceResult:
    outstanding = max(invoice.amount - invoice.amount_paid, 0.0)
    due = due_date(invoice.delivery_date, invoice.agreed_credit_days)
    days_overdue = max((as_of - due).days, 0)
    warnings = []

    eligible = True
    if udyam_registration_date and invoice.delivery_date < udyam_registration_date:
        eligible = False
        warnings.append(
            "Supplied before Udyam registration: statutory interest likely not claimable "
            "(Silpi Industries v. KSRTC, 2021)."
        )
    if invoice.agreed_credit_days is not None and invoice.agreed_credit_days > MAX_AGREED_CREDIT_DAYS:
        warnings.append(f"Agreed credit of {invoice.agreed_credit_days} days capped at 45 by Section 15.")
    if days_overdue > LIMITATION_DAYS:
        warnings.append("Overdue more than 3 years: may be time-barred, check with an advocate.")

    interest = 0.0
    if eligible and days_overdue > 0:
        interest = compound_interest(outstanding, due, as_of, statutory_annual_rate(bank_rate_pct))

    return InvoiceResult(
        invoice_no=invoice.invoice_no,
        delivery_date=invoice.delivery_date,
        due_date=due,
        outstanding=round(outstanding, 2),
        days_overdue=days_overdue,
        interest=interest,
        warnings=warnings,
    )


def format_inr(amount: float) -> str:
    """Indian digit grouping: 1234567.5 -> '12,34,567.50'."""
    negative = amount < 0
    whole, frac = f"{abs(amount):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{'-' if negative else ''}{whole}.{frac}"
