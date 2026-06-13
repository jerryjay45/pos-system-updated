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


def _send_to_printer(text: str, parent=None,
                     show_dialog: bool = False) -> bool:
    """
    Route text to the configured printer.

    - If thermal_printer_name is set → thermal path
    - If normal_printer_name is set  → normal (A4) path
    - If both set                    → thermal takes priority for auto-print;
                                       normal used only for reprints (show_dialog=True)
    - If neither set                 → silent success (text saved to file only)
    """
    from core.db_config import get as cfg_get
    thermal_name = cfg_get("thermal_printer_name", "").strip()
    normal_name  = cfg_get("normal_printer_name",  "").strip()

    # Reprints always use the OS print dialog regardless of which printer is set
    if show_dialog:
        try:
            from utils.normal_printer import print_text_normal
            ok, err = print_text_normal(text, show_dialog=True, parent=parent)
            if not ok and err != "Print cancelled":
                _warn_parent(parent, "Printer", err)
            return ok
        except Exception as e:
            _warn_parent(parent, "Printer", str(e))
            return False

    # Auto-print — prefer thermal, fall back to normal
    if thermal_name:
        from utils.thermal_printer import ThermalPrinter, PrinterError
        printer = ThermalPrinter.from_config()
        try:
            with printer as p:
                p.print_text(text)
                p.cut()
            return True
        except PrinterError as e:
            _warn_parent(parent, thermal_name, str(e),
                         extra="A text copy has been saved to the receipts folder.")
            return False
        except Exception as e:
            print(f"[PrintManager] Unexpected print error: {e}")
            return False

    if normal_name:
        try:
            from utils.normal_printer import print_text_normal
            ok, err = print_text_normal(text, show_dialog=False, parent=parent)
            if not ok and err != "Print cancelled":
                _warn_parent(parent, normal_name, err)
            return ok
        except Exception as e:
            _warn_parent(parent, normal_name, str(e))
            return False

    # No printer configured — silent success
    return True


def _warn_parent(parent, printer_name: str, error: str, extra: str = ""):
    print(f"[PrintManager] Printer error ({printer_name}): {error}")
    if parent:
        from PyQt6.QtWidgets import QMessageBox
        msg = f"Could not print to '{printer_name}'.\n\n{error}"
        if extra:
            msg += f"\n\n{extra}"
        QMessageBox.warning(parent, "Printer Error", msg)


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


def print_session(session: dict, report_type: str = "full",
                  copies: int = 1, parent=None) -> bool:
    """Print a session summary / Z-report."""
    try:
        from utils.receipt_formatter import format_session
        from core.db_checkout import (
            session_totals, session_group_totals,
            session_voided_receipts, get_session_receipts,
            get_receipt_by_id,
        )
        from core.db_users import get_user_by_id

        biz, currency = _get_biz_and_currency()
        totals         = session_totals(session["id"])
        grp_totals     = session_group_totals(session["id"])
        voided         = session_voided_receipts(session["id"])

        # Full report needs line items — fetch receipts with items
        all_receipts = None
        if report_type == "full":
            receipts     = get_session_receipts(session["id"])
            all_receipts = [get_receipt_by_id(r["id"]) for r in receipts
                            if r.get("status") == "completed"]

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
            currency=currency,
            report_type=report_type,
            group_totals=grp_totals,
            voided_receipts=voided,
            all_receipts=all_receipts,
        )

        _save_text(f"session_{session['id']:04d}_{report_type}_{_stamp()}.txt", text)

        # Override copies for this call
        from utils.thermal_printer import ThermalPrinter, PrinterError
        printer = ThermalPrinter.from_config()
        printer._copies = copies

        if not printer.is_configured:
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
                QMessageBox.warning(parent, "Printer Error",
                    f"Could not print.\n\n{e}\n\nText copy saved to receipts folder.")
            return False

    except Exception as e:
        print(f"[PrintManager] print_session error: {e}")
        return False


def reprint_receipt(receipt_number: str, parent=None) -> bool:
    """Reprint any past receipt — shows OS print dialog to pick printer."""
    try:
        from core.db_checkout import get_receipt_by_number
        receipt = get_receipt_by_number(receipt_number)
        if not receipt:
            if parent:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(parent, "Not Found",
                    f"Receipt {receipt_number} not found.")
            return False
        try:
            from utils.receipt_formatter import format_sale
            biz, currency = _get_biz_and_currency()
            text = format_sale(receipt, biz, currency)
            _save_text(f"receipt_{_safe_num(receipt['receipt_number'])}_{_stamp()}.txt", text)
            return _send_to_printer(text, parent, show_dialog=True)
        except Exception as e:
            print(f"[PrintManager] reprint format error: {e}")
            return False
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
