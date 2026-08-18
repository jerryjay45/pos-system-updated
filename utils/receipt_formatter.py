"""
utils/receipt_formatter.py
Pure text formatting for all receipt types — no printing, no DB access.

All functions take plain dicts (already fetched from the DB) and return
a single formatted string ready to send to the printer or save to disk.

Column width is derived from the configured paper width
(core.db_config "receipt_paper_width_mm") via
utils.printer_capabilities.columns_for_width_mm() — 12 CPI, with a
40-column (76mm) fallback if nothing is configured. Every function
below accepts an optional `width` override; when omitted it reads the
current setting, so a manager changing paper size in Settings is
reflected on the next print without any code change.

Each format_* function (format_sale, format_void, format_refund,
format_session) has a *_lines() counterpart returning the same content
as a list of (text, kind) tuples instead of a joined string. kind is
one of "biz_name", "title", "total", "div", "normal" — used by
utils.escpos_builder to decide what to bold/enlarge when printing with
real ESC/POS commands. format_*() itself is just "\n".join(text for
text, kind in format_*_lines()); the plain-text behaviour is unchanged.
"""

from __future__ import annotations
from datetime import datetime

Line = tuple[str, str]   # (text, kind)


def get_width() -> int:
    """Current receipt column width, from the configured paper size."""
    from utils.printer_capabilities import columns_for_width_mm, FALLBACK_COLUMNS
    try:
        from core.db_config import get as cfg_get
        mm = cfg_get("receipt_paper_width_mm", "")
        if not mm:
            return FALLBACK_COLUMNS
        return columns_for_width_mm(mm)
    except Exception:
        return FALLBACK_COLUMNS


def _lines_to_text(lines: list[Line]) -> str:
    return "\n".join(text for text, _kind in lines)


# ── Layout helpers ────────────────────────────────────────────────────────────

def _div(width: int, char: str = "-") -> str:
    return char * width

def _center(text: str, width: int) -> str:
    return text.center(width)

def _right(label: str, value: str, width: int) -> str:
    """Left-aligned label, right-aligned value on one line."""
    space = width - len(label) - len(value)
    return f"{label}{' ' * max(1, space)}{value}"

def _wrap(text: str, width: int, indent: int = 0) -> list[str]:
    """Word-wrap text to width, with optional indent on continuation lines."""
    words  = text.split()
    lines  = []
    line   = ""
    prefix = " " * indent
    for word in words:
        if len(line) + len(word) + (1 if line else 0) <= width:
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

def _header(biz: dict, width: int) -> list[Line]:
    lines: list[Line] = [(_center(biz.get("name", "POS System"), width), "biz_name")]
    if biz.get("address"):
        for l in _wrap(biz["address"], width):
            lines.append((_center(l, width), "normal"))
    if biz.get("phone"):
        lines.append((_center(f"Tel: {biz['phone']}", width), "normal"))
    if biz.get("tax_id"):
        lines.append((_center(f"TRN: {biz['tax_id']}", width), "normal"))
    lines.append((_div(width), "div"))
    return lines

def _footer(biz: dict, width: int) -> list[Line]:
    lines: list[Line] = [(_div(width), "div")]
    msg = biz.get("receipt_footer", "Thank you for your business!")
    for l in _wrap(msg, width):
        lines.append((_center(l, width), "normal"))
    lines.append(("", "normal"))
    lines.append(("", "normal"))
    return lines


# ── Sale receipt ──────────────────────────────────────────────────────────────

def format_sale_lines(receipt: dict, biz: dict, currency: str = "$",
                      width: int | None = None) -> list[Line]:
    w = width if width is not None else get_width()
    lines = _header(biz, w)

    lines.append((_right("Receipt:", receipt["receipt_number"], w), "normal"))
    lines.append((_right("Date:",    _ts(receipt["created_at"]), w), "normal"))
    lines.append((_right("Method:",  receipt["payment_method"].capitalize(), w), "normal"))
    if receipt.get("cashier_name"):
        lines.append((_right("Cashier:", receipt["cashier_name"], w), "normal"))
    lines.append((_div(w), "div"))

    # Items — name/qty/price/total columns scaled to paper width
    total_w = 8
    qty_w   = 4
    name_w  = max(14, w - qty_w - 6 - total_w)
    price_w = w - name_w - qty_w - total_w
    lines.append((f"{'Item':<{name_w}}{'Qty':>{qty_w}}{'Price':>{price_w}}{'Total':>{total_w}}", "normal"))
    lines.append((_div(w), "div"))
    for item in receipt.get("items", []):
        name  = item["product_name"][:name_w - 1]
        qty   = str(item["quantity"])
        price = f"{item['unit_price']:.2f}"
        total = f"{item['line_total']:.2f}"
        lines.append((f"{name:<{name_w}}{qty:>{qty_w}}{price:>{price_w}}{total:>{total_w}}", "normal"))
        if item.get("discount_amount", 0) > 0:
            lines.append((_right("  Discount:", f"-{_cur(item['discount_amount'], currency)}", w), "normal"))

    lines.append((_div(w), "div"))
    lines.append((_right("Subtotal:", _cur(receipt["subtotal"], currency), w), "normal"))
    lines.append((_right("GCT (16.5%):", _cur(receipt["gct_amount"], currency), w), "normal"))
    if receipt.get("discount_amount", 0) > 0:
        lines.append((_right("Discount:", f"-{_cur(receipt['discount_amount'], currency)}", w), "normal"))
    lines.append((_right("TOTAL:", _cur(receipt["total"], currency), w), "total"))
    lines.append((_div(w, "-"), "div"))

    # Payment breakdown
    method = receipt["payment_method"]
    if method == "cash":
        lines.append((_right("Cash Tendered:", _cur(receipt.get("cash_tendered", 0), currency), w), "normal"))
        if receipt.get("change_given", 0) > 0:
            lines.append((_right("Change:", _cur(receipt["change_given"], currency), w), "normal"))
    elif method == "card":
        lines.append((_right("Card:", _cur(receipt["total"], currency), w), "normal"))
    elif method == "split":
        if receipt.get("cash_tendered"):
            lines.append((_right("Cash:", _cur(receipt["cash_tendered"], currency), w), "normal"))
        if receipt.get("card_amount"):
            lines.append((_right("Card:", _cur(receipt["card_amount"], currency), w), "normal"))
        if receipt.get("change_given", 0) > 0:
            lines.append((_right("Change:", _cur(receipt["change_given"], currency), w), "normal"))

    lines += _footer(biz, w)
    return lines


def format_sale(receipt: dict, biz: dict, currency: str = "$",
                width: int | None = None) -> str:
    """
    Format a completed sale receipt.

    receipt — dict from get_receipt_by_id() including 'items' list.
    biz     — dict from get_business().
    """
    return _lines_to_text(format_sale_lines(receipt, biz, currency, width))


# ── Void receipt ──────────────────────────────────────────────────────────────

def format_void_lines(receipt: dict, biz: dict,
                      voided_by: str = "", reason: str = "",
                      currency: str = "$", width: int | None = None) -> list[Line]:
    w = width if width is not None else get_width()
    lines = _header(biz, w)

    lines.append((_center("*** VOID ***", w), "title"))
    lines.append((_div(w), "div"))
    lines.append((_right("Original Receipt:", receipt["receipt_number"], w), "normal"))
    lines.append((_right("Sale Date:",        _ts(receipt["created_at"]), w), "normal"))
    lines.append((_right("Voided:",           _ts(datetime.now().isoformat()), w), "normal"))
    if voided_by:
        lines.append((_right("Voided By:", voided_by, w), "normal"))
    lines.append((_div(w), "div"))

    if reason:
        lines.append(("Reason:", "normal"))
        for l in _wrap(reason, w, indent=2):
            lines.append((l, "normal"))
        lines.append(("", "normal"))

    # Original items
    total_w = 10
    name_w  = max(10, w - total_w)
    lines.append((f"{'Item':<{name_w}}{'Total':>{total_w}}", "normal"))
    lines.append((_div(w), "div"))
    for item in receipt.get("items", []):
        name  = item["product_name"][:name_w - 1]
        total = _cur(item["line_total"], currency)
        lines.append((f"{name:<{name_w}}{total:>{total_w}}", "normal"))

    lines.append((_div(w), "div"))
    lines.append((_right("Original Total:", _cur(receipt["total"], currency), w), "normal"))
    lines.append((_right("Amount Voided:", _cur(receipt["total"], currency), w), "total"))
    lines.append((_div(w), "div"))
    lines.append((_center("THIS SALE HAS BEEN VOIDED", w), "title"))

    lines += _footer(biz, w)
    return lines


def format_void(receipt: dict, biz: dict,
                voided_by: str = "", reason: str = "",
                currency: str = "$", width: int | None = None) -> str:
    """
    Format a void notice to print alongside or instead of the original.

    receipt   — the original receipt dict (with items).
    voided_by — name of the supervisor/manager who voided.
    reason    — void reason string.
    """
    return _lines_to_text(format_void_lines(receipt, biz, voided_by, reason, currency, width))


# ── Refund receipt ────────────────────────────────────────────────────────────

def format_refund_lines(receipt: dict, biz: dict,
                        refund_amount: float,
                        refund_type: str = "full",
                        refunded_by: str = "",
                        reason: str = "",
                        currency: str = "$",
                        width: int | None = None) -> list[Line]:
    w = width if width is not None else get_width()
    lines = _header(biz, w)

    label = "*** FULL REFUND ***" if refund_type == "full" else "*** PARTIAL REFUND ***"
    lines.append((_center(label, w), "title"))
    lines.append((_div(w), "div"))
    lines.append((_right("Original Receipt:", receipt["receipt_number"], w), "normal"))
    lines.append((_right("Sale Date:",        _ts(receipt["created_at"]), w), "normal"))
    lines.append((_right("Refunded:",         _ts(datetime.now().isoformat()), w), "normal"))
    if refunded_by:
        lines.append((_right("Refunded By:", refunded_by, w), "normal"))
    lines.append((_div(w), "div"))

    if reason:
        lines.append(("Reason:", "normal"))
        for l in _wrap(reason, w, indent=2):
            lines.append((l, "normal"))
        lines.append(("", "normal"))

    lines.append((_right("Original Total:", _cur(receipt["total"], currency), w), "normal"))
    lines.append((_div(w, "-"), "div"))
    lines.append((_right("REFUND AMOUNT:", _cur(refund_amount, currency), w), "total"))
    lines.append((_div(w), "div"))
    lines.append((_center("Please retain this receipt", w), "normal"))

    lines += _footer(biz, w)
    return lines


def format_refund(receipt: dict, biz: dict,
                  refund_amount: float,
                  refund_type: str = "full",
                  refunded_by: str = "",
                  reason: str = "",
                  currency: str = "$",
                  width: int | None = None) -> str:
    """
    Format a refund receipt.

    receipt      — the original receipt dict.
    refund_amount — actual amount being refunded.
    refund_type  — 'full' or 'partial'.
    """
    return _lines_to_text(format_refund_lines(
        receipt, biz, refund_amount, refund_type, refunded_by, reason, currency, width))


# ── Session summary ───────────────────────────────────────────────────────────

def format_session_lines(session: dict, totals: dict, cashier_name: str,
                         biz: dict, opened_by: str = "",
                         closed_by: str = "", currency: str = "$",
                         report_type: str = "full",
                         group_totals: list = None,
                         voided_receipts: list = None,
                         all_receipts: list = None,
                         width: int | None = None) -> list[Line]:
    w = width if width is not None else get_width()
    lines = _header(biz, w)

    title = "FULL Z-REPORT" if report_type == "full" else "SESSION SUMMARY"
    lines.append((_center(title, w), "title"))
    lines.append((_div(w), "div"))
    lines.append((_right("Session #:", f"{session['id']:04d}", w), "normal"))
    lines.append((_right("Cashier:",   cashier_name, w), "normal"))
    lines.append((_right("Opened:",    _ts(session["opened_at"]), w), "normal"))
    if session.get("closed_at"):
        lines.append((_right("Closed:", _ts(session["closed_at"]), w), "normal"))
    if opened_by:
        lines.append((_right("Opened By:", opened_by, w), "normal"))
    if closed_by:
        lines.append((_right("Closed By:", closed_by, w), "normal"))
    lines.append((_right("Status:", session["status"].capitalize(), w), "normal"))
    lines.append((_div(w), "div"))

    # ── Transaction counts ─────────────────────────────────────────────
    lines.append((_center("TRANSACTIONS", w), "title"))
    lines.append((_div(w, "-"), "div"))
    txn   = totals.get("transaction_count", 0)
    void  = totals.get("voided_count", 0)
    ref   = totals.get("refunded_count", 0)
    compl = txn - void - ref
    lines.append((_right("Completed:", str(compl), w), "normal"))
    lines.append((_right("Voided:",    str(void), w), "normal"))
    lines.append((_right("Refunded:",  str(ref), w), "normal"))
    lines.append((_right("Total:",     str(txn), w), "normal"))
    lines.append((_div(w), "div"))

    # ── Full report: line items per receipt ────────────────────────────
    if report_type == "full" and all_receipts:
        lines.append((_center("LINE ITEMS", w), "title"))
        lines.append((_div(w, "-"), "div"))
        item_name_w = max(10, w - 16)
        for receipt in all_receipts:
            if receipt.get("status") != "completed":
                continue
            lines.append((f"  {receipt['receipt_number']}  {_ts(receipt['created_at'])}", "normal"))
            for item in receipt.get("items", []):
                name  = item["product_name"][:item_name_w]
                qty   = str(item["quantity"])
                total = _cur(item["line_total"], currency)
                lines.append((f"    {name:<{item_name_w}} {qty:>3}x {total:>7}", "normal"))
            lines.append((_right("  Receipt Total:", _cur(receipt["total"], currency), w), "normal"))
            lines.append(("", "normal"))
        lines.append((_div(w), "div"))

    # ── Sales totals ───────────────────────────────────────────────────
    lines.append((_center("SALES TOTALS", w), "title"))
    lines.append((_div(w, "-"), "div"))
    sales    = totals.get("total_sales", 0) or 0
    gct      = totals.get("total_gct", 0) or 0
    discount = totals.get("total_discount", 0) or 0
    subtotal = sales - gct
    lines.append((_right("Subtotal (ex-GCT):", _cur(subtotal, currency), w), "normal"))
    lines.append((_right("GCT Collected:",     _cur(gct, currency), w), "normal"))
    if discount > 0:
        lines.append((_right("Discounts Given:", f"-{_cur(discount, currency)}", w), "normal"))
    lines.append((_div(w, "-"), "div"))
    lines.append((_right("GROSS SALES:", _cur(sales, currency), w), "total"))
    lines.append((_div(w), "div"))

    # ── Product group totals ───────────────────────────────────────────
    if group_totals:
        lines.append((_center("SALES BY GROUP", w), "title"))
        lines.append((_div(w, "-"), "div"))
        for g in group_totals:
            label = f"{g['group_name']} ({g['item_count']} items)"
            lines.append((_right(label, _cur(g["total_sales"], currency), w), "normal"))
        lines.append((_div(w), "div"))

    # ── Voided transactions ────────────────────────────────────────────
    if voided_receipts:
        lines.append((_center("VOIDED TRANSACTIONS", w), "title"))
        lines.append((_div(w, "-"), "div"))
        for v in voided_receipts:
            lines.append((_right(
                f"  {v['receipt_number']}  {_ts(v['created_at'])}",
                _cur(v["total"], currency), w
            ), "normal"))
            if v.get("reason"):
                lines.append((f"    Reason: {v['reason'][:30]}", "normal"))
        lines.append((_div(w), "div"))
    elif void > 0:
        lines.append((_center(f"({void} voided transaction{'s' if void != 1 else ''} — no details)", w), "normal"))
        lines.append((_div(w), "div"))

    lines.append((_center(f"Printed: {_ts(datetime.now().isoformat())}", w), "normal"))
    lines += _footer(biz, w)
    return lines


def format_session(session: dict, totals: dict, cashier_name: str,
                   biz: dict, opened_by: str = "",
                   closed_by: str = "", currency: str = "$",
                   report_type: str = "full",
                   group_totals: list = None,
                   voided_receipts: list = None,
                   all_receipts: list = None,
                   width: int | None = None) -> str:
    """
    Format a session summary / Z-report.

    report_type — 'full' (all line items + totals) or 'summary' (totals only)
    group_totals    — list of {group_name, total_sales, item_count}
    voided_receipts — list of voided receipt dicts
    all_receipts    — list of all receipts (used for full report line items)
    """
    return _lines_to_text(format_session_lines(
        session, totals, cashier_name, biz, opened_by, closed_by, currency,
        report_type, group_totals, voided_receipts, all_receipts, width))
