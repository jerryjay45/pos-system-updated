"""
utils/print_manager.py
Central print manager — all printing goes through here.

Public API
----------
print_receipt(receipt, parent)          — sale receipt after checkout
print_void(receipt, refund, user, parent) — void notice
print_refund(receipt, refund, user, parent) — refund receipt
print_session(session, parent)          — session summary / Z-report
reprint_receipt(receipt_number, parent) — reprint any past receipt

All functions:
  - Return True on success, False on failure
  - Never raise — failures are logged and silently swallowed so a
    print error never rolls back a transaction
  - Save a .txt copy to receipts/ regardless of printer state
"""

from __future__ import annotations
import os
from datetime import datetime
from config import RECEIPT_DIR


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_biz_and_currency() -> tuple[dict, str]:
    from core.db_config import get_business, get as cfg_get
    return get_business(), cfg_get("currency_symbol", "$")


def _save_text(filename: str, text: str):
    """Always save a .txt copy to receipts/."""
    os.makedirs(RECEIPT_DIR, exist_ok=True)
    fpath = os.path.join(RECEIPT_DIR, filename)
    try:
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception as e:
        print(f"[PrintManager] Could not save text copy: {e}")


def _send_to_printer(text: str, parent=None) -> bool:
    """
    Send text to the configured thermal printer.
    Returns True on success, False if no printer or on error.
    Shows a user-friendly error dialog if parent is provided.
    """
    from utils.thermal_printer import ThermalPrinter, PrinterError
    printer = ThermalPrinter.from_config()

    if not printer.is_configured:
        # No printer set — silent success (text already saved)
        return True

    try:
        with printer as p:
            p.print_text(text)
            p.cut()
        return True

    except PrinterError as e:
        print(f"[PrintManager] Printer error: {e}")
        if parent:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                parent, "Printer Error",
                f"Could not print to '{printer._name}'.\n\n{e}\n\n"
                f"A text copy has been saved to the receipts folder."
            )
        return False

    except Exception as e:
        print(f"[PrintManager] Unexpected print error: {e}")
        return False


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def _safe_num(receipt_number: str) -> str:
    return receipt_number.replace("#", "").replace("/", "-").strip()


# ── Public API ────────────────────────────────────────────────────────────────

def print_receipt(receipt: dict, parent=None) -> bool:
    """Print a completed sale receipt."""
    try:
        from utils.receipt_formatter import format_sale
        biz, currency = _get_biz_and_currency()
        text = format_sale(receipt, biz, currency)

        _save_text(f"receipt_{_safe_num(receipt['receipt_number'])}_{_stamp()}.txt", text)
        return _send_to_printer(text, parent)

    except Exception as e:
        print(f"[PrintManager] print_receipt error: {e}")
        return False


def print_void(receipt: dict, refund: dict,
               voided_by_user: dict = None, parent=None) -> bool:
    """Print a void notice for a voided receipt."""
    try:
        from utils.receipt_formatter import format_void
        biz, currency = _get_biz_and_currency()
        voided_by = voided_by_user.get("full_name", "") if voided_by_user else ""
        reason    = refund.get("reason", "") if refund else ""
        text = format_void(receipt, biz,
                           voided_by=voided_by,
                           reason=reason,
                           currency=currency)

        _save_text(f"void_{_safe_num(receipt['receipt_number'])}_{_stamp()}.txt", text)
        return _send_to_printer(text, parent)

    except Exception as e:
        print(f"[PrintManager] print_void error: {e}")
        return False


def print_refund(receipt: dict, refund: dict,
                 refunded_by_user: dict = None, parent=None) -> bool:
    """Print a refund receipt."""
    try:
        from utils.receipt_formatter import format_refund
        biz, currency = _get_biz_and_currency()
        refunded_by  = refunded_by_user.get("full_name", "") if refunded_by_user else ""
        reason       = refund.get("reason", "") if refund else ""
        amount       = refund.get("amount", receipt.get("total", 0))
        refund_type  = refund.get("refund_type", "full") if refund else "full"
        text = format_refund(receipt, biz,
                             refund_amount=amount,
                             refund_type=refund_type,
                             refunded_by=refunded_by,
                             reason=reason,
                             currency=currency)

        _save_text(f"refund_{_safe_num(receipt['receipt_number'])}_{_stamp()}.txt", text)
        return _send_to_printer(text, parent)

    except Exception as e:
        print(f"[PrintManager] print_refund error: {e}")
        return False


def print_session(session: dict, parent=None) -> bool:
    """Print a session summary / Z-report."""
    try:
        from utils.receipt_formatter import format_session
        from core.db_checkout import session_totals
        from core.db_users import get_user_by_id

        biz, currency = _get_biz_and_currency()
        totals = session_totals(session["id"])

        cashier = get_user_by_id(session["user_id"])
        cashier_name = cashier["full_name"] if cashier else "Unknown"

        opened_by, closed_by = "", ""
        if session.get("opened_by"):
            u = get_user_by_id(session["opened_by"])
            opened_by = u["full_name"] if u else ""
        if session.get("closed_by"):
            u = get_user_by_id(session["closed_by"])
            closed_by = u["full_name"] if u else ""

        text = format_session(
            session, totals, cashier_name, biz,
            opened_by=opened_by,
            closed_by=closed_by,
            currency=currency
        )

        _save_text(f"session_{session['id']:04d}_{_stamp()}.txt", text)
        return _send_to_printer(text, parent)

    except Exception as e:
        print(f"[PrintManager] print_session error: {e}")
        return False


def reprint_receipt(receipt_number: str, parent=None) -> bool:
    """Reprint any past receipt by receipt number (e.g. '#0041')."""
    try:
        from core.db_checkout import get_receipt_by_number
        receipt = get_receipt_by_number(receipt_number)
        if not receipt:
            if parent:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(parent, "Not Found",
                    f"Receipt {receipt_number} not found.")
            return False
        return print_receipt(receipt, parent)

    except Exception as e:
        print(f"[PrintManager] reprint_receipt error: {e}")
        return False


# ── Label printing (stub — label UI to follow) ────────────────────────────────

def print_label(product: dict, copies: int = 1,
                printer_name: str = "", parent=None) -> bool:
    """Print a shelf price label. Full implementation with label UI."""
    try:
        from core.db_config import get as cfg_get
        if not printer_name:
            printer_name = cfg_get("label_printer_name", "")
        # Label formatting will be handled by the label designer UI
        print(f"[Label] {product['name']} x{copies} → {printer_name or 'no printer'}")
        return True
    except Exception as e:
        print(f"[PrintManager] Label print error: {e}")
        return False
