"""
utils/print_manager.py
Central print manager — all printing goes through here.

Public API
----------
print_receipt(receipt, parent)              — auto-prints at checkout
print_void(receipt, refund, user, parent)   — dialog for supervisor
print_refund(receipt, refund, user, parent) — dialog for supervisor
print_session(session, ..., parent)         — dialog for supervisor
reprint_receipt(receipt_number, parent)     — auto-prints to receipt printer
print_label(product, copies, printer, parent) — stub for future cash tab

Routing
-------
Auto-print (receipt, reprint):
  Uses ThermalPrinter (QPrinter) → configured receipt printer or OS default.
  No dialog shown.

Dialog-print (void, refund, session):
  Uses QPrintPreviewDialog — user sees preview and can pick any printer.
  Defaults to OS default printer.

All functions:
  - Return True on success, False on failure/cancel
  - Never raise — print errors never roll back transactions
  - Always save a .txt copy to receipts/ folder
"""

from __future__ import annotations
import os
from datetime import datetime
from config import RECEIPT_DIR


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_biz_and_currency() -> tuple[dict, str]:
    from core.db_config import get_business, get as cfg_get
    return get_business(), cfg_get("currency_symbol", "$")


def _save_text(filename: str, text: str):
    """Always save a .txt copy to receipts/."""
    os.makedirs(RECEIPT_DIR, exist_ok=True)
    try:
        with open(os.path.join(RECEIPT_DIR, filename), "w", encoding="utf-8") as f:
            f.write(text)
    except Exception as e:
        print(f"[PrintManager] Could not save text copy: {e}")


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _safe_num(receipt_number: str) -> str:
    return receipt_number.replace("#", "").replace("/", "-").strip()


def _auto_print(text: str, parent=None) -> bool:
    """
    Print without a dialog using the configured receipt printer.
    Falls back to OS default if no printer is configured.
    """
    from utils.thermal_printer import ThermalPrinter, PrinterError
    try:
        with ThermalPrinter.from_config() as p:
            p.print_text(text)
        return True
    except PrinterError as e:
        print(f"[PrintManager] Auto-print error: {e}")
        if parent:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                parent, "Printer Error",
                f"{e}\n\nA text copy has been saved to the receipts folder."
            )
        return False
    except Exception as e:
        print(f"[PrintManager] Unexpected print error: {e}")
        return False


def _dialog_print(text: str, parent=None) -> bool:
    """
    Print via QPrintPreviewDialog — user sees preview and picks printer.
    Defaults to OS default printer.
    """
    try:
        from PyQt6.QtPrintSupport import QPrinter, QPrintPreviewDialog
        from PyQt6.QtGui          import QPainter, QFont

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setColorMode(QPrinter.ColorMode.GrayScale)

        dlg = QPrintPreviewDialog(printer, parent)
        dlg.setWindowTitle("Print Preview")
        dlg.resize(900, 650)

        def _paint(preview_printer: QPrinter):
            # paintRequested passes a QPrinter, not a QPainter
            painter = QPainter()
            try:
                if not painter.begin(preview_printer):
                    return
                font = QFont("Courier New", 9)
                font.setStyleHint(QFont.StyleHint.Monospace)
                painter.setFont(font)

                fm        = painter.fontMetrics()
                line_h    = fm.height() + 1
                page_rect = preview_printer.pageRect(QPrinter.Unit.DevicePixel)
                x         = int(page_rect.left()) + 10
                y_start   = int(page_rect.top())  + 10
                y_max     = int(page_rect.bottom()) - 10
                y         = y_start

                for line in text.split("\n"):
                    painter.drawText(x, y + fm.ascent(), line)
                    y += line_h
                    if y + line_h > y_max:
                        preview_printer.newPage()
                        y = y_start

                painter.end()
            except Exception as e:
                print(f"[PrintManager] Paint error: {e}")
                try: painter.end()
                except Exception: pass

        dlg.paintRequested.connect(_paint)
        result = dlg.exec()
        return result == QPrintPreviewDialog.DialogCode.Accepted

    except Exception as e:
        print(f"[PrintManager] Dialog print error: {e}")
        if parent:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(parent, "Printer Error", str(e))
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def print_receipt(receipt: dict, parent=None) -> bool:
    """Auto-print sale receipt at checkout — no dialog."""
    try:
        from utils.receipt_formatter import format_sale
        biz, currency = _get_biz_and_currency()
        text = format_sale(receipt, biz, currency)
        _save_text(f"receipt_{_safe_num(receipt['receipt_number'])}_{_stamp()}.txt", text)
        return _auto_print(text, parent)
    except Exception as e:
        print(f"[PrintManager] print_receipt error: {e}")
        return False


def print_void(receipt: dict, refund: dict,
               voided_by_user: dict = None, parent=None) -> bool:
    """Print void notice via preview dialog."""
    try:
        from utils.receipt_formatter import format_void
        biz, currency = _get_biz_and_currency()
        voided_by = voided_by_user.get("full_name", "") if voided_by_user else ""
        reason    = refund.get("reason", "") if refund else ""
        text = format_void(receipt, biz, voided_by=voided_by,
                           reason=reason, currency=currency)
        _save_text(f"void_{_safe_num(receipt['receipt_number'])}_{_stamp()}.txt", text)
        return _dialog_print(text, parent)
    except Exception as e:
        print(f"[PrintManager] print_void error: {e}")
        return False


def print_refund(receipt: dict, refund: dict,
                 refunded_by_user: dict = None, parent=None) -> bool:
    """Print refund receipt via preview dialog."""
    try:
        from utils.receipt_formatter import format_refund
        biz, currency = _get_biz_and_currency()
        refunded_by = refunded_by_user.get("full_name", "") if refunded_by_user else ""
        reason      = refund.get("reason", "") if refund else ""
        amount      = refund.get("amount", receipt.get("total", 0))
        refund_type = refund.get("refund_type", "full") if refund else "full"
        text = format_refund(receipt, biz, refund_amount=amount,
                             refund_type=refund_type, refunded_by=refunded_by,
                             reason=reason, currency=currency)
        _save_text(f"refund_{_safe_num(receipt['receipt_number'])}_{_stamp()}.txt", text)
        return _dialog_print(text, parent)
    except Exception as e:
        print(f"[PrintManager] print_refund error: {e}")
        return False


def print_session(session: dict, report_type: str = "full",
                  copies: int = 1, parent=None) -> bool:
    """Print session Z-report via preview dialog."""
    try:
        from utils.receipt_formatter import format_session
        from core.db_checkout import (
            session_totals, session_group_totals,
            session_voided_receipts, get_session_receipts,
            get_receipt_by_id,
        )
        from core.db_users import get_user_by_id

        biz, currency = _get_biz_and_currency()
        totals    = session_totals(session["id"])
        grp_totals = session_group_totals(session["id"])
        voided    = session_voided_receipts(session["id"])

        all_receipts = None
        if report_type == "full":
            receipts     = get_session_receipts(session["id"])
            all_receipts = [get_receipt_by_id(r["id"]) for r in receipts
                            if r.get("status") == "completed"]

        cashier      = get_user_by_id(session["user_id"])
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
            opened_by=opened_by, closed_by=closed_by,
            currency=currency, report_type=report_type,
            group_totals=grp_totals, voided_receipts=voided,
            all_receipts=all_receipts,
        )
        _save_text(f"session_{session['id']:04d}_{report_type}_{_stamp()}.txt", text)
        return _dialog_print(text, parent)

    except Exception as e:
        print(f"[PrintManager] print_session error: {e}")
        return False


def reprint_receipt(receipt_number: str, parent=None) -> bool:
    """Reprint a past receipt — auto-prints to receipt printer, no dialog."""
    try:
        from core.db_checkout import get_receipt_by_number
        receipt = get_receipt_by_number(receipt_number)
        if not receipt:
            if parent:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(parent, "Not Found",
                    f"Receipt {receipt_number} not found.")
            return False
        from utils.receipt_formatter import format_sale
        biz, currency = _get_biz_and_currency()
        text = format_sale(receipt, biz, currency)
        _save_text(f"reprint_{_safe_num(receipt['receipt_number'])}_{_stamp()}.txt", text)
        return _auto_print(text, parent)
    except Exception as e:
        print(f"[PrintManager] reprint_receipt error: {e}")
        return False


def print_label(product: dict, copies: int = 1,
                printer_name: str = "", parent=None) -> bool:
    """Stub — label printing handled by price tag tab UI."""
    try:
        from core.db_config import get as cfg_get
        if not printer_name:
            printer_name = cfg_get("label_printer_name", "")
        print(f"[Label] {product['name']} x{copies} → {printer_name or 'no printer'}")
        return True
    except Exception as e:
        print(f"[PrintManager] Label print error: {e}")
        return False
