"""
ui/shared/theme.py
Multi-theme system for Merchant POS Systems.

Adding a new theme:
  1. Add a dict entry to THEMES below — only override what changes.
  2. That's it. Call apply_theme("your_theme_name") at startup or from settings.

Available themes:  amber (default) | blue | green | high_contrast
"""

from __future__ import annotations

# ── Base palette (shared across all themes — functional colors) ───────────────
_BASE = {
    # Status colors — same in every theme
    "RED":          "#A32D2D",
    "RED_LIGHT":    "#FCEBEB",
    "RED_BORDER":   "#F09595",
    "GREEN":        "#1E7A3E",
    "GREEN_LIGHT":  "#E6F9EE",
    "GREEN_BORDER": "#A3D9B5",
    "PURPLE":       "#7A3B9A",
    "PURPLE_LIGHT": "#F3EAF8",
    "BLUE":         "#2A6DB5",
    "BLUE_LIGHT":   "#EAF3FF",
    "WHITE":        "#FFFFFF",
    "MAIN_FONT":    "Inter",
    "MONO_FONT":    "DM Mono",
}

# ── Theme definitions ─────────────────────────────────────────────────────────
# Each theme only needs to define what differs from _BASE.
# Required keys: ACCENT, ACCENT_DARK, ACCENT_DARKER, ACCENT_LIGHT,
#                ACCENT_LIGHTEST, ACCENT_BG,
#                DARK, DARK_2, DARK_3, DARK_4, DARK_CARD,
#                WARM_WHITE, BORDER, BORDER_LIGHT, MUTED, LABEL_TEXT

THEMES: dict[str, dict] = {

    # ── Amber (default) ───────────────────────────────────────────────
    "amber": {
        "ACCENT":          "#EF9F27",
        "ACCENT_DARK":     "#BA7517",
        "ACCENT_DARKER":   "#633806",
        "ACCENT_LIGHT":    "#FAC775",
        "ACCENT_LIGHTEST": "#FAEEDA",
        "ACCENT_BG":       "#FEF3DC",
        "DARK":            "#111111",
        "DARK_2":          "#1E1E1E",
        "DARK_3":          "#252525",
        "DARK_4":          "#2A2A2A",
        "DARK_CARD":       "#2C2C2A",
        "WARM_WHITE":      "#F8F6F1",
        "BORDER":          "#E2DDD3",
        "BORDER_LIGHT":    "#F1EFE8",
        "MUTED":           "#B4B2A9",
        "SUBTLE":          "#5F5E5A",
        "LABEL_TEXT":      "#888780",
    },

    # ── Dark blue ─────────────────────────────────────────────────────
    "blue": {
        "ACCENT":          "#3B82F6",
        "ACCENT_DARK":     "#1D4ED8",
        "ACCENT_DARKER":   "#1E3A8A",
        "ACCENT_LIGHT":    "#93C5FD",
        "ACCENT_LIGHTEST": "#DBEAFE",
        "ACCENT_BG":       "#EFF6FF",
        "DARK":            "#0F172A",
        "DARK_2":          "#1E293B",
        "DARK_3":          "#273549",
        "DARK_4":          "#334155",
        "DARK_CARD":       "#1E293B",
        "WARM_WHITE":      "#F8FAFC",
        "BORDER":          "#CBD5E1",
        "BORDER_LIGHT":    "#E2E8F0",
        "MUTED":           "#94A3B8",
        "SUBTLE":          "#64748B",
        "LABEL_TEXT":      "#64748B",
    },

    # ── Green ─────────────────────────────────────────────────────────
    "green": {
        "ACCENT":          "#16A34A",
        "ACCENT_DARK":     "#15803D",
        "ACCENT_DARKER":   "#14532D",
        "ACCENT_LIGHT":    "#86EFAC",
        "ACCENT_LIGHTEST": "#DCFCE7",
        "ACCENT_BG":       "#F0FDF4",
        "DARK":            "#052E16",
        "DARK_2":          "#14532D",
        "DARK_3":          "#166534",
        "DARK_4":          "#15803D",
        "DARK_CARD":       "#052E16",
        "WARM_WHITE":      "#F0FDF4",
        "BORDER":          "#BBF7D0",
        "BORDER_LIGHT":    "#D1FAE5",
        "MUTED":           "#6EE7B7",
        "SUBTLE":          "#34D399",
        "LABEL_TEXT":      "#059669",
    },

    # ── High contrast (accessibility) ─────────────────────────────────
    "high_contrast": {
        "ACCENT":          "#FFDD00",
        "ACCENT_DARK":     "#CCA800",
        "ACCENT_DARKER":   "#665400",
        "ACCENT_LIGHT":    "#FFE966",
        "ACCENT_LIGHTEST": "#FFFACC",
        "ACCENT_BG":       "#FFFEEE",
        "DARK":            "#000000",
        "DARK_2":          "#0A0A0A",
        "DARK_3":          "#111111",
        "DARK_4":          "#1A1A1A",
        "DARK_CARD":       "#000000",
        "WARM_WHITE":      "#FFFFFF",
        "BORDER":          "#000000",
        "BORDER_LIGHT":    "#333333",
        "MUTED":           "#444444",
        "SUBTLE":          "#222222",
        "LABEL_TEXT":      "#333333",
    },
}

# ── Fallback module-level names (overwritten by apply_theme) ─────────────────────
BLUE_LIGHT = "#EAF3FF"
BLUE       = "#2A6DB5"

# ── Active palette (module-level, updated by apply_theme) ─────────────────────
_active: dict = {}


def apply_theme(name: str = "amber") -> dict:
    """
    Merge base + theme into _active and expose as module-level names.
    Returns the full palette dict.
    Call once at startup: apply_theme(db_config.get("theme", "amber"))
    """
    global _active
    theme = THEMES.get(name, THEMES["amber"])
    _active = {**_BASE, **theme}

    # Expose as legacy module-level names so existing code doesn't break
    g = globals()
    # Accent aliases
    g["AMBER"]          = _active["ACCENT"]
    g["AMBER_DARK"]     = _active["ACCENT_DARK"]
    g["AMBER_DARKER"]   = _active["ACCENT_DARKER"]
    g["AMBER_LIGHT"]    = _active["ACCENT_LIGHT"]
    g["AMBER_LIGHTEST"] = _active["ACCENT_LIGHTEST"]
    g["AMBER_BG"]       = _active["ACCENT_BG"]
    # Neutral
    g["DARK"]           = _active["DARK"]
    g["DARK_2"]         = _active["DARK_2"]
    g["DARK_3"]         = _active["DARK_3"]
    g["DARK_4"]         = _active["DARK_4"]
    g["DARK_CARD"]      = _active["DARK_CARD"]
    g["WARM_WHITE"]     = _active["WARM_WHITE"]
    g["WHITE"]          = _active["WHITE"]
    g["BORDER"]         = _active["BORDER"]
    g["BORDER_LIGHT"]   = _active["BORDER_LIGHT"]
    g["MUTED"]          = _active["MUTED"]
    g["SUBTLE"]         = _active.get("SUBTLE", _active["MUTED"])
    g["LABEL_TEXT"]     = _active["LABEL_TEXT"]
    # Status (unchanged)
    g["RED"]            = _active["RED"]
    g["RED_LIGHT"]      = _active["RED_LIGHT"]
    g["RED_BORDER"]     = _active["RED_BORDER"]
    g["GREEN"]          = _active["GREEN"]
    g["GREEN_LIGHT"]    = _active["GREEN_LIGHT"]
    g["GREEN_BORDER"]   = _active["GREEN_BORDER"]
    g["PURPLE"]         = _active["PURPLE"]
    g["PURPLE_LIGHT"]   = _active["PURPLE_LIGHT"]
    g["BLUE"]           = _active["BLUE"]
    g["BLUE_LIGHT"]     = _active["BLUE_LIGHT"]
    g["BLUE_LIGHT"]     = _active["BLUE_LIGHT"]
    g["MAIN_FONT"]      = _active["MAIN_FONT"]

    return _active


def get_stylesheet() -> str:
    """
    Returns the full Qt stylesheet using the currently active theme.
    Call app.setStyleSheet(get_stylesheet()) at startup or after theme change.
    """
    A  = _active.get("ACCENT",       "#EF9F27")
    AD = _active.get("ACCENT_DARK",  "#BA7517")
    AL = _active.get("ACCENT_LIGHTEST", "#FAEEDA")
    AB = _active.get("ACCENT_BG",    "#FEF3DC")
    D  = _active.get("DARK",         "#111111")
    D2 = _active.get("DARK_2",       "#1E1E1E")
    D4 = _active.get("DARK_4",       "#2A2A2A")
    DC = _active.get("DARK_CARD",    "#2C2C2A")
    WW = _active.get("WARM_WHITE",   "#F8F6F1")
    W  = _active.get("WHITE",        "#FFFFFF")
    B  = _active.get("BORDER",       "#E2DDD3")
    BL = _active.get("BORDER_LIGHT", "#F1EFE8")
    M  = _active.get("MUTED",        "#B4B2A9")
    LT = _active.get("LABEL_TEXT",   "#888780")
    F  = _active.get("MAIN_FONT",    "Inter")

    return f"""
QWidget {{
    font-family: "{F}", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {DC};
    background-color: {WW};
}}
QMainWindow, QDialog {{ background-color: {WW}; }}

QPushButton {{
    background-color: {A}; color: white; border: none;
    border-radius: 8px; padding: 6px 16px; font-weight: 600;
}}
QPushButton:hover   {{ background-color: {AD}; }}
QPushButton:pressed {{ background-color: {_active.get("ACCENT_DARKER","#633806")}; }}
QPushButton:disabled {{ background-color: {M}; color: white; }}

QPushButton[flat="true"] {{
    background-color: transparent; color: {_active.get("SUBTLE",M)};
    border: 1px solid {B};
}}
QPushButton[flat="true"]:hover {{
    border-color: {A}; color: {A}; background-color: {AL};
}}
QPushButton[danger="true"] {{ background-color: {_active["RED"]}; }}
QPushButton[danger="true"]:hover {{ background-color: #7A1E1E; }}
QPushButton[dark="true"] {{ background-color: {DC}; }}
QPushButton[dark="true"]:hover {{ background-color: #444441; }}

QLineEdit {{
    background-color: {W}; border: 1px solid {B};
    border-radius: 7px; padding: 4px 10px;
    font-size: 13px; color: {DC};
}}
QLineEdit:focus {{ border-color: {A}; }}

QComboBox {{
    background-color: {W}; border: 1px solid {B};
    border-radius: 7px; padding: 4px 10px;
    font-size: 12px; color: {DC};
}}
QComboBox:focus {{ border-color: {A}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background-color: {W}; border: 1px solid {B};
    selection-background-color: {AL}; selection-color: {DC};
}}

QTableWidget {{
    background-color: {W}; gridline-color: {BL};
    border: none; font-size: 12px;
}}
QTableWidget::item {{ padding: 6px 10px; border-bottom: 1px solid {BL}; }}
QTableWidget::item:selected {{ background-color: {AB}; color: {DC}; }}
QHeaderView::section {{
    background-color: {D}; color: {A};
    font-size: 11px; font-weight: 600;
    padding: 6px 10px; border: none;
    border-right: 1px solid {D4};
}}

QScrollBar:vertical {{
    background: {WW}; width: 8px; border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {B}; border-radius: 4px; min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{ background: {M}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QLabel {{ background: transparent; }}

QTabBar::tab {{
    background: {W}; color: {LT};
    border: none; border-bottom: 2px solid transparent;
    padding: 10px 16px; font-size: 12px; font-weight: 500;
}}
QTabBar::tab:selected {{ color: {DC}; border-bottom: 2px solid {A}; }}
QTabBar::tab:hover {{ color: {DC}; }}
QTabWidget::pane {{ border: none; border-top: 1px solid {B}; }}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {B}; border-radius: 3px; background: {W};
}}
QCheckBox::indicator:checked {{
    background-color: {A}; border-color: {A};
}}

QFrame#topbar {{ background-color: {D}; border-bottom: 1px solid {D4}; }}
QFrame#sidebar {{ background-color: {D2}; border-right: 1px solid {D4}; }}
QFrame#totalsPanel {{ background-color: {D2}; border-left: 1px solid {D4}; }}
QFrame#bottombar {{ background-color: {D2}; border-top: 1px solid {D4}; }}
QStatusBar {{ background-color: {D}; color: {M}; font-size: 11px; }}
"""


def theme_names() -> list[str]:
    """Returns list of available theme names for the manager settings UI."""
    return list(THEMES.keys())


# ── Auto-apply on import (reads saved preference or defaults to amber) ─────────
def _init():
    try:
        from core.db_config import get as cfg_get
        name = cfg_get("theme", "amber")
    except Exception:
        name = "amber"
    apply_theme(name)


_init()
