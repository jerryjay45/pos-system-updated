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


def _parse_vid_pid(s: str) -> tuple[int, int] | None:
    """Parse 'VID:PID' hex string to (int, int), or None on failure."""
    try:
        parts = s.strip().split(":")
        if len(parts) == 2:
            return int(parts[0], 16), int(parts[1], 16)
    except (ValueError, AttributeError):
        pass
    return None


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

    def __init__(self, printer_name: str = "", copies: int = 1,
                 baud_rate: int = None, usb_vid_pid: str = ""):
        self._name      = printer_name.strip()
        self._copies    = max(1, copies)
        self._conn      = None        # underlying connection object
        self._type      = _detect_type(self._name)
        self._baud_rate = baud_rate or DEFAULT_BAUD_RATE
        self._vid_pid   = _parse_vid_pid(usb_vid_pid)   # (vid, pid) or None
        self._use_escpos = False

    # ── Factory ───────────────────────────────────────────────────────

    @classmethod
    def from_config(cls) -> "ThermalPrinter":
        """Build a ThermalPrinter from the settings DB."""
        from core.db_config import get as cfg_get
        name      = cfg_get("thermal_printer_name", "")
        copies    = int(cfg_get("receipt_copies", "1") or "1")
        baud_rate = int(cfg_get("thermal_baud_rate", str(DEFAULT_BAUD_RATE)) or DEFAULT_BAUD_RATE)
        vid_pid   = cfg_get("thermal_usb_vid_pid", "")
        return cls(name, copies, baud_rate=baud_rate, usb_vid_pid=vid_pid)

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
            if self._type == "_win32":
                import win32print
                win32print.ClosePrinter(self._conn)
            elif self._type in ("network", "serial"):
                self._conn.close()
            else:
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
                self._name, baudrate=self._baud_rate,
                timeout=2, write_timeout=5
            )
        except ImportError:
            raise PrinterError(
                "pyserial is not installed.\n"
                "Run: pip install pyserial"
            )

    def _open_usb(self):
        # Build list of VID/PID pairs to try — user-configured first
        pairs_to_try = []
        if self._vid_pid:
            pairs_to_try.append(self._vid_pid)
        pairs_to_try.extend(_USB_DEFAULTS)

        # Try python-escpos first (works on Windows and Linux)
        try:
            import escpos.printer as ep
            for vid, pid in pairs_to_try:
                try:
                    p = ep.Usb(vid, pid)
                    self._conn = p
                    self._use_escpos = True
                    return
                except Exception:
                    continue
        except ImportError:
            pass

        # Windows fallback — try win32print if available
        import sys
        if sys.platform == "win32":
            self._open_usb_windows()
            return

        # Linux fallback — raw /dev/usb/lp* nodes
        usb_nodes = ["/dev/usb/lp0", "/dev/usb/lp1", "/dev/lp0"]
        if self._name.lower().startswith("usb"):
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
            "  pip install python-escpos\n"
            "Or specify the USB VID:PID in Manager → Settings → Printers."
        )

    def _open_usb_windows(self):
        """Windows USB fallback using win32print raw spooler API."""
        try:
            import win32print
            # Use the printer name directly if given (e.g. 'POS-80 Printer')
            # otherwise use the default printer
            printer_name = self._name if self._name.lower() not in ("usb", "") else None
            if not printer_name:
                printer_name = win32print.GetDefaultPrinter()
            if not printer_name:
                raise PrinterError(
                    "No default printer found on Windows.\n"
                    "Set the thermal printer as default or enter its exact name\n"
                    "in Manager → Settings → Printers."
                )
            self._conn = win32print.OpenPrinter(printer_name)
            self._win32_printer_name = printer_name
            self._type = "_win32"   # flag for _write / close
        except ImportError:
            raise PrinterError(
                "Could not find a USB thermal printer on Windows.\n\n"
                "To fix this, do one of the following:\n"
                "  1. Install python-escpos:  pip install python-escpos\n"
                "     Then enter the USB VID:PID in Manager → Settings → Printers\n"
                "     (e.g.  0416:5011  for a generic 80mm printer)\n\n"
                "  2. Install the printer driver in Windows, set it as default,\n"
                "     and enter its exact Windows printer name in Settings.\n\n"
                "  3. Use a network connection instead:\n"
                "     Enter the printer's IP address (e.g. 192.168.1.100)"
            )

    # ── Low-level write ───────────────────────────────────────────────

    def _write(self, data: bytes):
        if self._conn is None:
            raise PrinterError("Printer not connected.")
        if self._type == "network":
            self._conn.sendall(data)
        elif self._type == "_win32":
            import win32print
            win32print.StartDocPrinter(self._conn, 1, ("Receipt", None, "RAW"))
            win32print.StartPagePrinter(self._conn)
            win32print.WritePrinter(self._conn, data)
            win32print.EndPagePrinter(self._conn)
            win32print.EndDocPrinter(self._conn)
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
