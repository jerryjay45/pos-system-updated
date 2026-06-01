"""
utils/receipt_formatter.py
Pure text formatting for all receipt types — no printing, no DB access.

All functions take plain dicts (already fetched from the DB) and return
a single formatted string ready to send to the printer or save to disk.

Paper width: 80mm  →  42 characters at 12 CPI (standard ESC/POS default).
"""

from __future__ import annotations
from datetime import datetime

WIDTH = 42


# ── Layout helpers ────────────────────────────────────────────────────────────

def _div(char: str = "─") -> str:
    return char * WIDTH

def _center(text: str) -> str:
    return text.center(WIDTH)

def _right(label: str, value: str) -> str:
    """Left-aligned label, right-aligned value on one line."""
    space = WIDTH - len(label) - len(value)
    return f"{label}{' ' * max(1, space)}{value}"

def _wrap(text: str, indent: int = 0) -> list[str]:
    """Word-wrap text to WIDTH, with optional indent on continuation lines."""
    words  = text.split()
    lines  = []
    line   = ""
    prefix = " " * indent
    for word in words:
        if len(line) + len(word) + (1 if line else 0) <= WIDTH:
            line = f"{line} {word}".lstrip()
        else:
            if line:
                lines.append(line)
            line = prefix + word
    if line:
        lines.append(line)
    return lines or [""]

def _cur(amount: float, symbol: str = "$") -> str:
    return f"{symbol}{amount:.2f}"

def _ts(dt_str: str) -> str:
    """Format a datetime string to 'DD/MM/YYYY HH:MM'."""
    try:
        dt = datetime.fromisoformat(str(dt_str))
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(dt_str)[:16]

def _header(biz: dict) -> list[str]:
    lines = []
    lines.append(_center(biz.get("name", "POS System")))
    if biz.get("address"):
        for l in _wrap(biz["address"]):
            lines.append(_center(l))
    if biz.get("phone"):
        lines.append(_center(f"Tel: {biz['phone']}"))
    if biz.get("tax_id"):
        lines.append(_center(f"TRN: {biz['tax_id']}"))
    lines.append(_div())
    return lines

def _footer(biz: dict) -> list[str]:
    lines = [_div()]
    msg = biz.get("receipt_footer", "Thank you for your business!")
    for l in _wrap(msg):
        lines.append(_center(l))
    lines.append("")
    lines.append("")
    return lines


# ── Sale receipt ──────────────────────────────────────────────────────────────

def format_sale(receipt: dict, biz: dict, currency: str = "$") -> str:
    """
    Format a completed sale receipt.

    receipt — dict from get_receipt_by_id() including 'items' list.
    biz     — dict from get_business().
    """
    lines = _header(biz)

    lines.append(_right("Receipt:", receipt["receipt_number"]))
    lines.append(_right("Date:",    _ts(receipt["created_at"])))
    lines.append(_right("Method:",  receipt["payment_method"].capitalize()))
    if receipt.get("cashier_name"):
        lines.append(_right("Cashier:", receipt["cashier_name"]))
    lines.append(_div())

    # Items
    col = WIDTH - 22 - 8   # remaining after name(22) and total(8)
    qty_w, price_w = 4, col - 4
    lines.append(f"{'Item':<22}{'Qty':>{qty_w}}{'Price':>{price_w}}{'Total':>8}")
    lines.append(_div())
    for item in receipt.get("items", []):
        name  = item["product_name"][:21]
        qty   = str(item["quantity"])
        price = f"{item['unit_price']:.2f}"
        total = f"{item['line_total']:.2f}"
        lines.append(f"{name:<22}{qty:>{qty_w}}{price:>{price_w}}{total:>8}")
        if item.get("discount_amount", 0) > 0:
            lines.append(f"  {'Discount:':<20}{'-'+_cur(item['discount_amount'], currency):>8}")

    lines.append(_div())
    lines.append(_right("Subtotal:", _cur(receipt["subtotal"], currency)))
    lines.append(_right("GCT (16.5%):", _cur(receipt["gct_amount"], currency)))
    if receipt.get("discount_amount", 0) > 0:
        lines.append(_right("Discount:", f"-{_cur(receipt['discount_amount'], currency)}"))
    lines.append(_right("TOTAL:", _cur(receipt["total"], currency)))
    lines.append(_div("-"))

    # Payment breakdown
    method = receipt["payment_method"]
    if method == "cash":
        lines.append(_right("Cash Tendered:", _cur(receipt.get("cash_tendered", 0), currency)))
        if receipt.get("change_given", 0) > 0:
            lines.append(_right("Change:", _cur(receipt["change_given"], currency)))
    elif method == "card":
        lines.append(_right("Card:", _cur(receipt["total"], currency)))
    elif method == "split":
        if receipt.get("cash_tendered"):
            lines.append(_right("Cash:", _cur(receipt["cash_tendered"], currency)))
        if receipt.get("card_amount"):
            lines.append(_right("Card:", _cur(receipt["card_amount"], currency)))
        if receipt.get("change_given", 0) > 0:
            lines.append(_right("Change:", _cur(receipt["change_given"], currency)))

    lines += _footer(biz)
    return "\n".join(lines)


# ── Void receipt ──────────────────────────────────────────────────────────────

def format_void(receipt: dict, biz: dict,
                voided_by: str = "", reason: str = "",
                currency: str = "$") -> str:
    """
    Format a void notice to print alongside or instead of the original.

    receipt   — the original receipt dict (with items).
    voided_by — name of the supervisor/manager who voided.
    reason    — void reason string.
    """
    lines = _header(biz)

    lines.append(_center("*** VOID ***"))
    lines.append(_div())
    lines.append(_right("Original Receipt:", receipt["receipt_number"]))
    lines.append(_right("Sale Date:",        _ts(receipt["created_at"])))
    lines.append(_right("Voided:",           _ts(datetime.now().isoformat())))
    if voided_by:
        lines.append(_right("Voided By:", voided_by))
    lines.append(_div())

    if reason:
        lines.append("Reason:")
        for l in _wrap(reason, indent=2):
            lines.append(l)
        lines.append("")

    # Original items
    lines.append(f"{'Item':<28}{'Total':>14}")
    lines.append(_div())
    for item in receipt.get("items", []):
        name  = item["product_name"][:27]
        total = _cur(item["line_total"], currency)
        lines.append(f"{name:<28}{total:>14}")

    lines.append(_div())
    lines.append(_right("Original Total:", _cur(receipt["total"], currency)))
    lines.append(_right("Amount Voided:", _cur(receipt["total"], currency)))
    lines.append(_div())
    lines.append(_center("THIS SALE HAS BEEN VOIDED"))

    lines += _footer(biz)
    return "\n".join(lines)


# ── Refund receipt ────────────────────────────────────────────────────────────

def format_refund(receipt: dict, biz: dict,
                  refund_amount: float,
                  refund_type: str = "full",
                  refunded_by: str = "",
                  reason: str = "",
                  currency: str = "$") -> str:
    """
    Format a refund receipt.

    receipt      — the original receipt dict.
    refund_amount — actual amount being refunded.
    refund_type  — 'full' or 'partial'.
    """
    lines = _header(biz)

    label = "*** FULL REFUND ***" if refund_type == "full" else "*** PARTIAL REFUND ***"
    lines.append(_center(label))
    lines.append(_div())
    lines.append(_right("Original Receipt:", receipt["receipt_number"]))
    lines.append(_right("Sale Date:",        _ts(receipt["created_at"])))
    lines.append(_right("Refunded:",         _ts(datetime.now().isoformat())))
    if refunded_by:
        lines.append(_right("Refunded By:", refunded_by))
    lines.append(_div())

    if reason:
        lines.append("Reason:")
        for l in _wrap(reason, indent=2):
            lines.append(l)
        lines.append("")

    lines.append(_right("Original Total:", _cur(receipt["total"], currency)))
    lines.append(_div("-"))
    lines.append(_right("REFUND AMOUNT:", _cur(refund_amount, currency)))
    lines.append(_div())
    lines.append(_center("Please retain this receipt"))

    lines += _footer(biz)
    return "\n".join(lines)


# ── Session summary ───────────────────────────────────────────────────────────

def format_session(session: dict, totals: dict, cashier_name: str,
                   biz: dict, opened_by: str = "",
                   closed_by: str = "", currency: str = "$") -> str:
    """
    Format a session summary / Z-report.

    session      — session row dict (id, opened_at, closed_at, status).
    totals       — dict from session_totals() in db_checkout.
    cashier_name — full name of the cashier for this session.
    opened_by    — name of supervisor who opened (optional).
    closed_by    — name of supervisor who closed (optional).
    """
    lines = _header(biz)

    lines.append(_center("SESSION SUMMARY"))
    lines.append(_div())
    lines.append(_right("Session #:", f"{session['id']:04d}"))
    lines.append(_right("Cashier:",   cashier_name))
    lines.append(_right("Opened:",    _ts(session["opened_at"])))
    if session.get("closed_at"):
        lines.append(_right("Closed:", _ts(session["closed_at"])))
    if opened_by:
        lines.append(_right("Opened By:", opened_by))
    if closed_by:
        lines.append(_right("Closed By:", closed_by))
    lines.append(_right("Status:", session["status"].capitalize()))
    lines.append(_div())

    # Transaction counts
    lines.append(_center("TRANSACTIONS"))
    lines.append(_div("-"))
    txn   = totals.get("transaction_count", 0)
    void  = totals.get("voided_count", 0)
    ref   = totals.get("refunded_count", 0)
    compl = txn - void - ref
    lines.append(_right("Completed:", str(compl)))
    lines.append(_right("Voided:",    str(void)))
    lines.append(_right("Refunded:",  str(ref)))
    lines.append(_right("Total:",     str(txn)))
    lines.append(_div())

    # Sales totals
    lines.append(_center("SALES TOTALS"))
    lines.append(_div("-"))
    sales    = totals.get("total_sales", 0) or 0
    gct      = totals.get("total_gct", 0) or 0
    discount = totals.get("total_discount", 0) or 0
    net      = sales - gct
    lines.append(_right("Gross Sales:",   _cur(sales, currency)))
    lines.append(_right("Less GCT:",      f"-{_cur(gct, currency)}"))
    lines.append(_right("Net Sales:",     _cur(net, currency)))
    if discount > 0:
        lines.append(_right("Discounts Given:", _cur(discount, currency)))
    lines.append(_div())
    lines.append(_right("GCT COLLECTED:", _cur(gct, currency)))
    lines.append(_div())

    lines.append(_center(f"Printed: {_ts(datetime.now().isoformat())}"))

    lines += _footer(biz)
    return "\n".join(lines)
