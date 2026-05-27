"""
utils/print_manager.py
Receipt and label printing manager.

Currently a stub — real printer integration comes later.
The checkout dialog calls print_receipt() non-blocking,
so if printing fails the transaction still saves cleanly.
"""

from __future__ import annotations
import os
from datetime import datetime
from config import RECEIPT_DIR


# ── Receipt printing ──────────────────────────────────────────────────────────

def print_receipt(receipt: dict, printer_name: str = "", parent=None) -> bool:
    """
    Print a receipt to the configured thermal or normal printer.
    Falls back to saving a text file in receipts/ if no printer is set.

    Returns True on success, False on failure.
    """
    try:
        text = _format_receipt_text(receipt)

        # Save text copy regardless
        _save_receipt_text(receipt["receipt_number"], text)

        if not printer_name:
            from core.db_config import get as cfg_get
            printer_name = cfg_get("thermal_printer_name", "")

        if printer_name:
            return _print_to_printer(printer_name, text)

        # No printer configured — silently succeed (text already saved)
        return True

    except Exception as e:
        print(f"[PrintManager] Receipt print error: {e}")
        return False


def _format_receipt_text(receipt: dict) -> str:
    from core.db_config import get_business, get as cfg_get
    biz     = get_business()
    width   = 42
    div     = "─" * width
    c       = lambda s: s.center(width)
    r       = lambda l, v: f"{l:<{width-len(str(v))}}{v}"
    lines   = []

    lines.append(c(biz.get("name", "POS System")))
    if biz.get("address"): lines.append(c(biz["address"]))
    if biz.get("phone"):   lines.append(c(f"Tel: {biz['phone']}"))
    if biz.get("tax_id"):  lines.append(c(f"TRN: {biz['tax_id']}"))
    lines.append(div)

    lines.append(r("Receipt:", receipt["receipt_number"]))
    lines.append(r("Date:", str(receipt["created_at"])[:16]))
    lines.append(r("Method:", receipt["payment_method"].capitalize()))
    lines.append(div)

    lines.append(f"{'Item':<22}{'Qty':>4}{'Price':>8}{'Total':>8}")
    lines.append(div)
    for item in receipt.get("items", []):
        name = item["product_name"][:21]
        lines.append(f"{name:<22}{item['quantity']:>4}{item['unit_price']:>8.2f}{item['line_total']:>8.2f}")

    lines.append(div)
    lines.append(r("Subtotal:", f"${receipt['subtotal']:.2f}"))
    lines.append(r("GCT:",      f"${receipt['gct_amount']:.2f}"))
    if receipt.get("discount_amount", 0) > 0:
        lines.append(r("Discount:", f"-${receipt['discount_amount']:.2f}"))
    lines.append(r("TOTAL:",    f"${receipt['total']:.2f}"))

    if receipt.get("cash_tendered"):
        lines.append(r("Cash:",   f"${receipt['cash_tendered']:.2f}"))
    if receipt.get("change_given") and receipt["change_given"] > 0:
        lines.append(r("Change:", f"${receipt['change_given']:.2f}"))
    if receipt.get("card_amount"):
        lines.append(r("Card:",   f"${receipt['card_amount']:.2f}"))

    lines.append(div)
    footer = biz.get("receipt_footer", "Thank you for your business!")
    lines.append(c(footer))
    lines.append("")

    return "\n".join(lines)


def _save_receipt_text(receipt_number: str, text: str):
    """Save receipt as a .txt file in the receipts directory."""
    os.makedirs(RECEIPT_DIR, exist_ok=True)
    safe_num = receipt_number.replace("#", "").replace("/", "-")
    fname    = f"receipt_{safe_num}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    fpath    = os.path.join(RECEIPT_DIR, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(text)


def _print_to_printer(printer_name: str, text: str) -> bool:
    """
    Send text to a system printer.
    Uses python-escpos for thermal printers when available,
    falls back to system print command on Linux / win32api on Windows.
    """
    try:
        # Try python-escpos (thermal)
        import escpos.printer as ep
        # This is a basic example — real implementation needs printer detection
        # p = ep.Usb(0x04b8, 0x0e03)  # Epson TM-T88
        # p.text(text); p.cut()
        raise NotImplementedError("Configure printer USB/network IDs in print_manager.py")
    except (ImportError, NotImplementedError):
        pass

    # Linux lp / lpr fallback
    try:
        import subprocess
        tmp = os.path.join(RECEIPT_DIR, "_tmp_print.txt")
        with open(tmp, "w") as f: f.write(text)
        result = subprocess.run(["lp", "-d", printer_name, tmp], capture_output=True)
        return result.returncode == 0
    except Exception:
        pass

    # Windows fallback (no deps)
    try:
        import win32api, win32print
        tmp = os.path.join(RECEIPT_DIR, "_tmp_print.txt")
        with open(tmp, "w") as f: f.write(text)
        win32api.ShellExecute(0, "print", tmp, f'/d:"{printer_name}"', ".", 0)
        return True
    except Exception:
        pass

    return False


# ── Label printing ────────────────────────────────────────────────────────────

def print_label(product: dict, copies: int = 1,
                printer_name: str = "", parent=None) -> bool:
    """
    Print a shelf price label.
    Stub — label UI will call this when implemented.
    """
    try:
        if not printer_name:
            from core.db_config import get as cfg_get
            printer_name = cfg_get("label_printer_name", "")

        text = _format_label_text(product)
        print(f"[Label] {product['name']} x{copies} → {printer_name or 'no printer'}")
        return True
    except Exception as e:
        print(f"[PrintManager] Label print error: {e}")
        return False


def _format_label_text(product: dict) -> str:
    lines = [
        product.get("brand", ""),
        product["name"],
        f"${product['selling_price']:.2f}",
        product.get("barcode", ""),
    ]
    return "\n".join(l for l in lines if l)
