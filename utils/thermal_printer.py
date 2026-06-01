"""
utils/thermal_printer.py
ESC/POS driver for a generic 80mm thermal receipt printer.

Supports three connection types detected automatically from the
printer_name config value:
  - USB:     "USB"  or  "USB001"  or  "usb:VID:PID"
  - Network: "192.168.1.100"  or  "192.168.1.100:9100"
  - Serial:  "/dev/ttyUSB0"  or  "COM3"

Uses python-escpos when available; falls back to raw byte writes
for USB/serial or raw TCP socket writes for network — so it works
even without the library installed.

Usage:
    from utils.thermal_printer import ThermalPrinter
    with ThermalPrinter.from_config() as p:
        p.print_text(formatted_text)
        p.cut()
"""

from __future__ import annotations
import os
import socket
import struct
import time
from typing import Optional


# ── ESC/POS byte constants ────────────────────────────────────────────────────

ESC = b'\x1b'
GS  = b'\x1d'

INIT          = ESC + b'@'           # Initialise printer
ALIGN_LEFT    = ESC + b'a\x00'
ALIGN_CENTER  = ESC + b'a\x01'
ALIGN_RIGHT   = ESC + b'a\x02'
BOLD_ON       = ESC + b'E\x01'
BOLD_OFF      = ESC + b'E\x00'
DOUBLE_ON     = GS  + b'!\x11'      # double width + double height
DOUBLE_OFF    = GS  + b'!\x00'
FEED_LINE     = b'\n'
FEED_4        = ESC + b'd\x04'      # feed 4 lines
CUT_FULL      = GS  + b'V\x00'     # full cut
CUT_PARTIAL   = GS  + b'V\x01'     # partial cut (safer for most generics)

# Default USB vendor/product IDs for common generic 80mm printers
_USB_DEFAULTS = [
    (0x0416, 0x5011),   # Winbond / generic
    (0x04b8, 0x0e03),   # Epson TM-T88
    (0x0519, 0x0003),   # Star TSP100
    (0x067b, 0x2305),   # Prolific generic
]

DEFAULT_TCP_PORT   = 9100
DEFAULT_BAUD_RATE  = 9600
PRINT_WIDTH_CHARS  = 42   # characters per line on 80mm at 12cpi


# ── Connection helpers ────────────────────────────────────────────────────────

def _detect_type(printer_name: str) -> str:
    """Return 'network', 'serial', or 'usb' based on the printer name."""
    n = printer_name.strip().lower()
    if not n:
        return "usb"
    if n.startswith("/dev/") or n.lower().startswith("com"):
        return "serial"
    # IPv4 or hostname with optional port
    parts = n.split(":")
    if len(parts) <= 2 and (parts[0].replace(".", "").isdigit() or "." in parts[0]):
        return "network"
    return "usb"


# ── ThermalPrinter ────────────────────────────────────────────────────────────

class ThermalPrinter:
    """
    Context-manager wrapper around a generic 80mm ESC/POS printer.

        with ThermalPrinter.from_config() as p:
            p.print_text(text)
            p.cut()

    All methods return self for chaining.
    Raises PrinterError on connection failure.
    """

    def __init__(self, printer_name: str = "", copies: int = 1):
        self._name   = printer_name.strip()
        self._copies = max(1, copies)
        self._conn   = None        # underlying connection object
        self._type   = _detect_type(self._name)

    # ── Factory ───────────────────────────────────────────────────────

    @classmethod
    def from_config(cls) -> "ThermalPrinter":
        """Build a ThermalPrinter from the settings DB."""
        from core.db_config import get as cfg_get
        name   = cfg_get("thermal_printer_name", "")
        copies = int(cfg_get("receipt_copies", "1") or "1")
        return cls(name, copies)

    # ── Context manager ───────────────────────────────────────────────

    def __enter__(self) -> "ThermalPrinter":
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    # ── Connection ────────────────────────────────────────────────────

    def open(self):
        """Open the printer connection."""
        if self._type == "network":
            self._open_network()
        elif self._type == "serial":
            self._open_serial()
        else:
            self._open_usb()
        self._write(INIT)

    def close(self):
        if self._conn is None:
            return
        try:
            if self._type == "network":
                self._conn.close()
            elif self._type == "serial":
                self._conn.close()
            else:
                # python-escpos or raw USB file
                if hasattr(self._conn, "close"):
                    self._conn.close()
        except Exception:
            pass
        self._conn = None

    def _open_network(self):
        parts = self._name.split(":")
        host  = parts[0]
        port  = int(parts[1]) if len(parts) > 1 else DEFAULT_TCP_PORT
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((host, port))
        self._conn = s

    def _open_serial(self):
        try:
            import serial
            self._conn = serial.Serial(
                self._name, baudrate=DEFAULT_BAUD_RATE,
                timeout=2, write_timeout=5
            )
        except ImportError:
            raise PrinterError(
                "pyserial is not installed.\n"
                "Run: pip install pyserial"
            )

    def _open_usb(self):
        # Try python-escpos first
        try:
            import escpos.printer as ep
            # Try each known vendor/product pair
            for vid, pid in _USB_DEFAULTS:
                try:
                    p = ep.Usb(vid, pid)
                    self._conn = p
                    self._use_escpos = True
                    return
                except Exception:
                    continue
            raise PrinterError(
                "Could not find a USB thermal printer.\n"
                "Check the USB cable and that the printer is on.\n"
                "You may need to specify the printer name in Manager → Settings."
            )
        except ImportError:
            pass

        # Raw USB fallback via /dev/usb/lp0 on Linux
        usb_nodes = ["/dev/usb/lp0", "/dev/usb/lp1", "/dev/lp0"]
        if self._name.lower().startswith("usb"):
            # Try to use the number suffix e.g. USB001 → lp0
            suffix = self._name.lower().replace("usb", "").lstrip("0") or "0"
            usb_nodes = [f"/dev/usb/lp{suffix}", f"/dev/lp{suffix}"] + usb_nodes

        for node in usb_nodes:
            if os.path.exists(node):
                try:
                    self._conn = open(node, "wb")
                    return
                except PermissionError:
                    raise PrinterError(
                        f"Permission denied: {node}\n"
                        f"Run: sudo usermod -aG lp {os.environ.get('USER','$USER')}\n"
                        f"Then log out and back in."
                    )

        raise PrinterError(
            "No USB printer device found.\n"
            "Install python-escpos for full USB support:\n"
            "  pip install python-escpos"
        )

    # ── Low-level write ───────────────────────────────────────────────

    def _write(self, data: bytes):
        if self._conn is None:
            raise PrinterError("Printer not connected.")
        if self._type == "network":
            self._conn.sendall(data)
        elif hasattr(self._conn, "write"):
            self._conn.write(data)
            if hasattr(self._conn, "flush"):
                self._conn.flush()

    # ── High-level print methods ──────────────────────────────────────

    def print_text(self, text: str, encoding: str = "cp437") -> "ThermalPrinter":
        """Print a pre-formatted text string, repeating for copies."""
        for copy in range(self._copies):
            encoded = text.encode(encoding, errors="replace")
            self._write(encoded)
            if copy < self._copies - 1:
                self.cut()
                time.sleep(0.5)
        return self

    def bold(self, on: bool = True) -> "ThermalPrinter":
        self._write(BOLD_ON if on else BOLD_OFF)
        return self

    def align(self, alignment: str = "left") -> "ThermalPrinter":
        mapping = {"left": ALIGN_LEFT, "center": ALIGN_CENTER, "right": ALIGN_RIGHT}
        self._write(mapping.get(alignment, ALIGN_LEFT))
        return self

    def feed(self, lines: int = 1) -> "ThermalPrinter":
        self._write(ESC + b'd' + bytes([min(lines, 255)]))
        return self

    def cut(self, full: bool = False) -> "ThermalPrinter":
        self.feed(4)
        self._write(CUT_FULL if full else CUT_PARTIAL)
        return self

    @property
    def copies(self) -> int:
        return self._copies

    @property
    def connection_type(self) -> str:
        return self._type

    @property
    def is_configured(self) -> bool:
        """True if a printer name is set in config."""
        return bool(self._name)


# ── Exception ─────────────────────────────────────────────────────────────────

class PrinterError(Exception):
    """Raised when the printer cannot be opened or written to."""
    pass
