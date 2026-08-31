"""
Money math, in one place, so invoice/quotation/PO/receipt totals are
computed identically. Order of operations: discount is applied to the
line's gross amount, tax is applied to the post-discount amount.
"""
from dataclasses import dataclass

from .schemas import LineItem


@dataclass
class LineTotals:
    gross: float
    discount_amount: float
    taxable_amount: float
    tax_amount: float
    line_total: float


@dataclass
class DocumentTotals:
    subtotal: float          # sum of gross, pre-discount
    discount_total: float
    tax_total: float
    grand_total: float


def compute_line(item: LineItem) -> LineTotals:
    gross = item.quantity * item.unit_price
    discount_amount = gross * (item.discount_pct / 100)
    taxable = gross - discount_amount
    tax_amount = taxable * (item.tax_pct / 100)
    return LineTotals(
        gross=gross,
        discount_amount=discount_amount,
        taxable_amount=taxable,
        tax_amount=tax_amount,
        line_total=taxable + tax_amount,
    )


def compute_totals(items: list[LineItem]) -> DocumentTotals:
    subtotal = discount_total = tax_total = 0.0
    for item in items:
        lt = compute_line(item)
        subtotal += lt.gross
        discount_total += lt.discount_amount
        tax_total += lt.tax_amount
    grand_total = subtotal - discount_total + tax_total
    return DocumentTotals(
        subtotal=subtotal,
        discount_total=discount_total,
        tax_total=tax_total,
        grand_total=grand_total,
    )
