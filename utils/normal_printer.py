"""
utils/normal_printer.py
Prints receipt text to a normal (A4/Letter/Legal) printer using
PyQt6's QPrinter and QPainter.

The receipt text prints compact at the top of the page in a
monospace font — looks like a thermal receipt, remaining page
space is left blank.  Long session reports paginate automatically.

Public API
----------
print_text_normal(text, show_dialog, parent)
    → (True, None) on success
    → (False, error_str) on failure / cancel

get_available_printers() → list[str]
get_default_printer()    → str
"""

from __future__ import annotations

from PyQt6.QtPrintSupport import QPrinter, QPrinterInfo, QPrintDialog
from PyQt6.QtGui          import QPainter, QFont, QFontMetrics, QPageLayout, QPageSize
from PyQt6.QtCore         import QMarginsF

_PAPER_SIZES: dict[str, QPageSize.PageSizeId] = {
    "A4":     QPageSize.PageSizeId.A4,
    "Letter": QPageSize.PageSizeId.Letter,
    "Legal":  QPageSize.PageSizeId.Legal,
}


def _load_settings() -> dict:
    """Read normal printer settings from db_config."""
    try:
        from core.db_config import get as cfg_get
        return {
            "printer_name": cfg_get("normal_printer_name", ""),
            "paper_size":   cfg_get("normal_paper_size",   "A4"),
        }
    except Exception:
        return {"printer_name": "", "paper_size": "A4"}


def _make_printer(settings: dict, show_dialog: bool = False,
                  parent=None) -> tuple:
    """
    Configure and return (QPrinter, True) or (None, False) if cancelled.
    show_dialog=True presents the OS print dialog (used for reprints).
    """
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setColorMode(QPrinter.ColorMode.GrayScale)

    size_id = _PAPER_SIZES.get(
        settings.get("paper_size", "A4"), QPageSize.PageSizeId.A4
    )
    printer.setPageLayout(QPageLayout(
        QPageSize(size_id),
        QPageLayout.Orientation.Portrait,
        QMarginsF(10, 10, 10, 10),
        QPageLayout.Unit.Millimeter,
    ))

    saved_name = settings.get("printer_name", "").strip()
    if saved_name:
        for info in QPrinterInfo.availablePrinters():
            if info.printerName() == saved_name:
                printer.setPrinterName(saved_name)
                break
        # If not found in the list, set name anyway — OS may still accept it
        if printer.printerName() != saved_name:
            printer.setPrinterName(saved_name)

    if show_dialog:
        dlg = QPrintDialog(printer, parent)
        if dlg.exec() != QPrintDialog.DialogCode.Accepted:
            return None, False

    return printer, True


def print_text_normal(text: str, show_dialog: bool = False,
                      parent=None) -> tuple[bool, str | None]:
    """
    Print pre-formatted receipt text to a normal printer.

    Args:
        text:        Formatted receipt string (newline-delimited).
        show_dialog: If True, show OS print dialog before printing.
                     Use True for manual reprints, False for auto-print.
        parent:      QWidget parent (for dialog).

    Returns:
        (True, None)          — success
        (False, reason_str)   — cancelled or error
    """
    settings         = _load_settings()
    printer, ok      = _make_printer(settings, show_dialog, parent)
    if not ok:
        return False, "Print cancelled"
    if printer is None:
        return False, "No printer available"

    painter = QPainter()
    try:
        if not painter.begin(printer):
            return False, "Could not open printer"

        font = QFont("Courier New", 9)
        font.setStyleHint(QFont.StyleHint.Monospace)
        painter.setFont(font)

        fm          = painter.fontMetrics()
        line_h      = fm.height() + 2
        page_rect   = printer.pageRect(QPrinter.Unit.DevicePixel)
        x           = int(page_rect.left())  + 20
        y_start     = int(page_rect.top())   + 20
        y_max       = int(page_rect.bottom()) - 20
        y           = y_start

        for line in text.split("\n"):
            # Hard-wrap lines that are too wide (rare at 42-char receipt width)
            max_px = int(page_rect.width()) - 40
            while fm.horizontalAdvance(line) > max_px and len(line) > 1:
                # Find break point
                cut = len(line) - 1
                while cut > 0 and fm.horizontalAdvance(line[:cut]) > max_px:
                    cut -= 1
                painter.drawText(x, y + fm.ascent(), line[:cut])
                y += line_h
                line = line[cut:]
                if y + line_h > y_max:
                    printer.newPage()
                    y = y_start

            painter.drawText(x, y + fm.ascent(), line)
            y += line_h

            if y + line_h > y_max:
                printer.newPage()
                y = y_start

        painter.end()
        return True, None

    except Exception as e:
        try:
            painter.end()
        except Exception:
            pass
        return False, str(e)


def get_available_printers() -> list[str]:
    """Return names of all printers visible to the OS."""
    return [info.printerName() for info in QPrinterInfo.availablePrinters()]


def get_default_printer() -> str:
    """Return the OS default printer name, or '' if none."""
    info = QPrinterInfo.defaultPrinter()
    return info.printerName() if info else ""
