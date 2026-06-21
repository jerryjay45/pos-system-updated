"""
utils/thermal_printer.py
Receipt printer driver using QPrinter / OS print spooler.

Replaces the old raw ESC/POS socket/serial/USB driver. Printing now
goes through the OS printer driver — the same way price labels work —
which is compatible with Generic Text Only, Epson TM series with OS
drivers, and any other installed printer.

Usage:
    with ThermalPrinter.from_config() as p:
        p.print_text(text)

If no printer name is configured the OS default printer is used.
"""

from __future__ import annotations


class PrinterError(Exception):
    """Raised when printing fails."""


class ThermalPrinter:
    """
    QPrinter-based receipt printer.
    Context manager — open/close handled automatically.

        with ThermalPrinter.from_config() as p:
            p.print_text(text)

    If printer_name is blank the OS default printer is used.
    """

    def __init__(self, printer_name: str = "", copies: int = 1):
        self._name   = printer_name.strip()
        self._copies = max(1, copies)

    # ── Factory ───────────────────────────────────────────────────────

    @classmethod
    def from_config(cls) -> "ThermalPrinter":
        """Build from the settings DB."""
        try:
            from core.db_config import get as cfg_get
            name   = cfg_get("thermal_printer_name", "").strip()
            copies = int(cfg_get("receipt_copies", "1") or "1")
        except Exception:
            name, copies = "", 1
        return cls(name, copies)

    # ── Context manager ───────────────────────────────────────────────

    def __enter__(self) -> "ThermalPrinter":
        return self

    def __exit__(self, *_):
        pass

    # ── Public API ────────────────────────────────────────────────────

    def print_text(self, text: str) -> "ThermalPrinter":
        """Print plain text. Called once per receipt."""
        for _ in range(self._copies):
            self._do_print(text)
        return self

    def cut(self) -> "ThermalPrinter":
        """No-op — paper cut is handled by the printer driver/form feed."""
        return self

    # ── Properties ────────────────────────────────────────────────────

    @property
    def is_configured(self) -> bool:
        """Always True — blank name uses OS default."""
        return True

    @property
    def connection_type(self) -> str:
        return "os_driver"

    @property
    def copies(self) -> int:
        return self._copies

    # ── Internal ──────────────────────────────────────────────────────

    def _do_print(self, text: str):
        """Send text to the printer via QPrinter."""
        try:
            from PyQt6.QtPrintSupport import QPrinter
            from PyQt6.QtGui          import QPainter, QFont
        except ImportError as e:
            raise PrinterError(f"PyQt6 not available: {e}")

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setColorMode(QPrinter.ColorMode.GrayScale)
        printer.setCopyCount(1)   # we loop copies ourselves

        if self._name:
            printer.setPrinterName(self._name)
        # else: QPrinter uses OS default automatically

        painter = QPainter()
        try:
            if not painter.begin(printer):
                raise PrinterError(
                    f"Could not open printer"
                    f"{': ' + self._name if self._name else ' (OS default)'}.\n"
                    f"Check that the printer is installed and online."
                )

            font = QFont("Courier New", 9)
            font.setStyleHint(QFont.StyleHint.Monospace)
            painter.setFont(font)

            fm        = painter.fontMetrics()
            line_h    = fm.height() + 1
            page_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
            x         = int(page_rect.left()) + 10
            y_start   = int(page_rect.top())  + 10
            y_max     = int(page_rect.bottom()) - 10
            y         = y_start

            for line in text.split("\n"):
                painter.drawText(x, y + fm.ascent(), line)
                y += line_h
                if y + line_h > y_max:
                    printer.newPage()
                    y = y_start

            painter.end()

        except PrinterError:
            try: painter.end()
            except Exception: pass
            raise
        except Exception as e:
            try: painter.end()
            except Exception: pass
            raise PrinterError(str(e))
