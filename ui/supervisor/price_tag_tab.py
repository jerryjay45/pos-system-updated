"""
ui/supervisor/price_tag_tab.py
Price tag / shelf label designer and printer.

Renders labels with QPainter (not HTML) for reliable print output.
Includes a live preview widget and "Show on label" toggles.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QLineEdit, QComboBox, QSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSplitter, QCheckBox, QMessageBox,
    QFileDialog,
)
from PyQt6.QtCore import Qt, QRectF, QSizeF, QMarginsF
from PyQt6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush,
    QPageSize, QPageLayout,
)

from ui.shared.theme import (
    AMBER, AMBER_DARK, AMBER_BG, AMBER_LIGHTEST,
    DARK, DARK_4, DARK_CARD,
    WHITE, WARM_WHITE, BORDER, BORDER_LIGHT,
    MUTED, LABEL_TEXT, GREEN, GREEN_LIGHT,
)
from core.db_products import get_products, count_products, get_discount_levels
from core.db_config import get as cfg_get, gct_rate


# ── Label / page size catalogue ───────────────────────────────────────────────
#  (w_val, h_val, display_name, is_page_layout)
#  is_page_layout=True  → standard paper, multiple labels per page
#  is_page_layout=False → individual label stock, one label per page
_LABEL_SIZES = [
    (38,  21,  "38 × 21 mm  (small price tag)", False),
    (50,  30,  "50 × 30 mm  (standard shelf)",  False),
    (70,  40,  "70 × 40 mm  (large shelf)",     False),
    (100, 50,  "100 × 50 mm  (case label)",     False),
    ("A4",     None, "A4  (210 × 297 mm)",     True),
    ("Letter", None, "Letter  (216 × 279 mm)", True),
    ("Legal",  None, "Legal  (216 × 356 mm)",  True),
    ("POS57",  None, "POS Roll  57 mm wide",   True),
    ("POS76",  None, "POS Roll  76 mm wide",   True),
    ("POS80",  None, "POS Roll  80 mm wide",   True),
]

_PAGE_COLS = {
    "A4": 3, "Letter": 3, "Legal": 3,
    "POS57": 1, "POS76": 1, "POS80": 1,
}
_POS_WIDTHS = {"POS57": 57, "POS76": 76, "POS80": 80}


# ── Shared QPainter label drawing ─────────────────────────────────────────────

def _draw_label(painter: QPainter, rect: QRectF,
                product: dict, options: dict, preview: bool = False):
    """
    Draw a price tag label into `rect`.

    Font sizes are derived from the physical label dimensions in mm
    (passed via options) so they scale correctly at any print DPI.
    """
    show_name    = options.get("show_name",    True)
    show_price   = options.get("show_price",   True)
    show_barcode = options.get("show_barcode", True)

    name      = product.get("name", "")
    price     = product.get("price", 0.0)
    barcode   = product.get("barcode", "")
    gct_ok    = product.get("gct_applicable", False)
    disc_rows = product.get("disc_rows", [])

    x = rect.x();  y = rect.y()
    w = rect.width(); h = rect.height()

    # Physical dimensions in mm — used for font sizing
    w_mm = options.get("label_w_mm", 50)
    h_mm = options.get("label_h_mm", 30)

    # px per mm for this render target
    px_per_mm = w / max(w_mm, 1)

    # Font sizes in points — proportional to label height in mm
    name_pt  = max(h_mm * 0.38, 7.0)
    price_pt = max(h_mm * 0.55, 10.0)
    gct_pt   = max(h_mm * 0.28, 5.5)
    disc_pt  = max(h_mm * 0.52, 9.0)

    pad = max(2.0 * px_per_mm, 2.0)

    painter.save()
    painter.setClipRect(rect)

    # Rounded border
    pen_w = max(0.35 * px_per_mm, 0.8)
    painter.setPen(QPen(QColor("#000000"), pen_w))
    painter.setBrush(QBrush(QColor("#ffffff")))
    radius = max(1.5 * px_per_mm, 3.0)
    painter.drawRoundedRect(rect.adjusted(pen_w, pen_w, -pen_w, -pen_w), radius, radius)

    # Row heights — barcode removed; all space goes to name/price/discounts
    shown_disc   = disc_rows[:2]
    disc_h_each  = h * 0.22   # larger rows for the bigger discount font
    disc_h       = disc_h_each * len(shown_disc) if (show_price and shown_disc) else 0
    name_avail_w = w - pad * 2

    # Measure name at its font size so it gets exactly the height it needs
    name_font = QFont("Arial"); name_font.setPointSizeF(name_pt); name_font.setBold(True)
    painter.setFont(name_font)

    if show_name and name:
        needed_name_h = painter.boundingRect(
            QRectF(0, 0, name_avail_w, h * 2),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop |
            Qt.TextFlag.TextWordWrap,
            name
        ).height() + pad * 0.5
    else:
        needed_name_h = 0

    remaining = h - disc_h - pad * 2
    name_h    = min(needed_name_h, remaining * 0.45) if show_name else 0
    price_h   = remaining - name_h if show_price else 0

    cur_y = y + pad

    # Product name — word wrap allowed
    if show_name and name:
        painter.setPen(QColor("#000000"))
        tr = QRectF(x + pad, cur_y, name_avail_w, name_h)
        painter.drawText(tr,
            Qt.AlignmentFlag.AlignLeft |
            Qt.AlignmentFlag.AlignTop |
            Qt.TextFlag.TextWordWrap,
            name)
        cur_y += name_h

    # Price row: large price + "+GCT" inline
    if show_price:
        price_str = f"${price:.2f}"
        font = QFont("Arial"); font.setPointSizeF(price_pt); font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#000000"))
        # Use painter.fontMetrics() — bound to the actual paint device DPI
        pfm      = painter.fontMetrics()
        price_px = pfm.horizontalAdvance(price_str)
        # Draw price left-aligned in full available width
        painter.drawText(
            QRectF(x + pad, cur_y, w - pad * 2, price_h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            price_str
        )
        if gct_ok:
            gct_font = QFont("Arial"); gct_font.setPointSizeF(gct_pt); gct_font.setBold(True)
            painter.setFont(gct_font)
            painter.setPen(QColor("#555555"))
            painter.drawText(
                QRectF(x + pad + price_px + pad * 0.4,
                       cur_y + price_h * 0.20,
                       w - pad * 2 - price_px - pad,
                       price_h * 0.65),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "+GCT"
            )
        cur_y += price_h

        # Discount rows
        for (min_qty, disc_price, pct_str) in shown_disc:
            font = QFont("Arial"); font.setPointSizeF(disc_pt); font.setBold(True)
            painter.setFont(font)
            tr = QRectF(x + pad, cur_y, w - pad * 2, disc_h_each)
            painter.setPen(QColor("#222222"))
            painter.drawText(tr,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"{min_qty} \u2192 ${disc_price:.2f}")
            painter.setPen(QColor("#444444"))
            painter.drawText(tr,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"Discount {pct_str}")
            cur_y += disc_h_each

    painter.restore()


def _draw_barcode_bars(painter: QPainter, rect: QRectF,
                       barcode_text: str, preview: bool = False,
                       num_pt: float = 5.0):
    """
    Draw barcode as filled black rectangles derived from barcode digits.
    Each digit maps to a sequence of narrow/wide bar and space units.
    Works at any DPI — pure geometry, no external libraries.
    """
    painter.save()
    painter.setClipRect(rect)

    bar_h = rect.height() * 0.76
    num_y = rect.y() + bar_h + rect.height() * 0.03
    num_h = rect.height() - bar_h - rect.height() * 0.03

    # Each digit → list of (is_bar, width_units)
    _DIGIT_BARS = {
        "0": [1,3, 0,2, 1,1, 0,1, 1,1],
        "1": [1,2, 0,2, 1,2, 0,1, 1,1],
        "2": [1,2, 0,2, 1,1, 0,1, 1,2],
        "3": [1,1, 0,4, 1,1, 0,1, 1,1],
        "4": [1,1, 0,1, 1,3, 0,2, 1,1],
        "5": [1,1, 0,2, 1,2, 0,2, 1,1],
        "6": [1,1, 0,1, 1,1, 0,4, 1,1],
        "7": [1,1, 0,3, 1,1, 0,1, 1,2],
        "8": [1,1, 0,2, 1,1, 0,3, 1,1],
        "9": [1,3, 0,1, 1,1, 0,1, 1,2],
    }
    # Guard bars
    guard = [1,1, 0,1, 1,1]
    bars = guard[:]
    for ch in barcode_text:
        for i, (is_b, w) in enumerate(
            zip(_DIGIT_BARS.get(ch, [1,1,0,1,1,1,0,1,1,1])[::2],
                _DIGIT_BARS.get(ch, [1,1,0,1,1,1,0,1,1,1])[1::2])
        ):
            bars.append(is_b); bars.append(w)
    bars += guard

    # Convert to (is_bar, units) pairs
    pairs = list(zip(bars[::2], bars[1::2]))
    total_units = sum(w for _, w in pairs)
    unit_w = rect.width() / max(total_units, 1)

    painter.setPen(Qt.PenStyle.NoPen)
    cur_x = rect.x()
    for is_bar, units in pairs:
        bw = units * unit_w
        if is_bar:
            painter.setBrush(QBrush(QColor("#000000")))
            painter.drawRect(QRectF(cur_x, rect.y(), max(bw - 0.3, 0.5), bar_h))
        cur_x += bw

    # Digits below
    num_font = QFont("Courier New"); num_font.setPointSizeF(num_pt)
    painter.setFont(num_font)
    painter.setPen(QColor("#000000"))
    painter.drawText(
        QRectF(rect.x(), num_y, rect.width(), num_h),
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
        barcode_text
    )

    painter.restore()


# ── Live preview widget ───────────────────────────────────────────────────────

class _LabelPreviewWidget(QWidget):
    """Draws a scaled live preview of the label using the same _draw_label function."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._product = None
        self._options = {
            "show_name": True, "show_price": True, "show_barcode": True,
            "label_w_mm": 50, "label_h_mm": 30,
        }
        self.setStyleSheet(f"background:{WARM_WHITE};border:1px solid {BORDER};border-radius:8px;")
        self.setMinimumHeight(160)

    def set_product(self, data: dict):
        self._product = data
        self.update()

    def set_options(self, options: dict):
        self._options = options
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self._product:
            painter.setPen(QColor(MUTED))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Select a product to preview")
            return

        w_mm  = self._options.get("label_w_mm", 50)
        h_mm  = self._options.get("label_h_mm", 30)
        aspect = w_mm / max(h_mm, 1)

        margin  = 16
        avail_w = self.width()  - margin * 2
        avail_h = self.height() - margin * 2

        if avail_w / aspect <= avail_h:
            lw = avail_w; lh = avail_w / aspect
        else:
            lh = avail_h; lw = avail_h * aspect

        lx = (self.width()  - lw) / 2
        ly = (self.height() - lh) / 2
        rect = QRectF(lx, ly, lw, lh)

        # Label background + amber border
        painter.setBrush(QBrush(QColor(WHITE)))
        painter.setPen(QPen(QColor(AMBER), 1.5))
        painter.drawRoundedRect(rect, 6, 6)

        _draw_label(painter, rect, self._product, self._options, preview=True)


# ── Main tab widget ───────────────────────────────────────────────────────────

class PriceTagTab(QWidget):

    def __init__(self, user: dict, parent=None):
        super().__init__(parent)
        self.user         = user
        self._selected    = set()
        self._all_prods   = []
        self._prod_data   = {}     # pid -> enriched dict for drawing
        self._pg_page     = 0
        self._pg_per_page = 50
        self._pg_search   = ""
        self.setStyleSheet(f"background:{WARM_WHITE};")
        self._build_ui()
        self._load_table()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8); root.setSpacing(8)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setHandleWidth(4)
        split.setStyleSheet(f"QSplitter::handle{{background:{BORDER};}}")

        split.addWidget(self._build_left())
        split.addWidget(self._build_right())
        split.setSizes([700, 320])
        root.addWidget(split, stretch=1)

    # ── Left: product list ────────────────────────────────────────────

    def _build_left(self):
        card = QFrame()
        card.setStyleSheet(
            f"background:{WHITE};border-radius:10px;border:1px solid {BORDER};"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 12, 12, 12); lay.setSpacing(8)

        # Toolbar
        tb = QHBoxLayout(); tb.setSpacing(6)
        self.search_inp = QLineEdit()
        self.search_inp.setPlaceholderText("🔍  Search products…")
        self.search_inp.setFixedHeight(34)
        self.search_inp.setStyleSheet(self._input_style())
        self.search_inp.returnPressed.connect(self._search)
        self.search_inp.textChanged.connect(self._search)
        tb.addWidget(self.search_inp, stretch=1)
        refresh = self._outline_btn("↻"); refresh.setFixedWidth(36)
        refresh.clicked.connect(self._load_table)
        tb.addWidget(refresh)
        lay.addLayout(tb)

        # Select all / clear
        sel_row = QHBoxLayout(); sel_row.setSpacing(6)
        sel_all = self._outline_btn("☑  Select All")
        sel_all.clicked.connect(self._select_all)
        clr     = self._outline_btn("☐  Clear")
        clr.clicked.connect(self._clear_selection)
        self.sel_lbl = QLabel("0 selected")
        self.sel_lbl.setStyleSheet(f"color:{AMBER_DARK};font-size:12px;font-weight:600;")
        sel_row.addWidget(sel_all); sel_row.addWidget(clr)
        sel_row.addStretch(); sel_row.addWidget(self.sel_lbl)
        lay.addLayout(sel_row)

        # Product table
        self.prod_table = QTableWidget(); self.prod_table.setColumnCount(4)
        self.prod_table.setHorizontalHeaderLabels(["", "Product", "Price", "Group"])
        hh = self.prod_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.prod_table.setColumnWidth(0, 32)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.prod_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.prod_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.prod_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.prod_table.verticalHeader().setVisible(False)
        self.prod_table.setShowGrid(False)
        self.prod_table.setStyleSheet(self._table_style())
        self.prod_table.currentItemChanged.connect(self._on_row_changed)
        self.prod_table.itemChanged.connect(self._on_item_changed)
        lay.addWidget(self.prod_table, stretch=1)

        # Pagination
        pg = QHBoxLayout(); pg.setSpacing(8)
        self._pg_prev = self._outline_btn("← Prev"); self._pg_prev.setFixedWidth(80)
        self._pg_prev.clicked.connect(self._prev_page)
        self._pg_label = QLabel("Page 1")
        self._pg_label.setStyleSheet(f"color:{MUTED};font-size:11px;")
        self._pg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pg_next = self._outline_btn("Next →"); self._pg_next.setFixedWidth(80)
        self._pg_next.clicked.connect(self._next_page)
        pg.addStretch(); pg.addWidget(self._pg_prev)
        pg.addWidget(self._pg_label); pg.addWidget(self._pg_next); pg.addStretch()
        lay.addLayout(pg)
        return card

    # ── Right: settings + preview + print ────────────────────────────

    def _build_right(self):
        card = QFrame()
        card.setFixedWidth(320)
        card.setStyleSheet(
            f"background:{WHITE};border-radius:10px;border:1px solid {BORDER};"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 14, 14, 14); lay.setSpacing(10)

        # Preview
        lay.addWidget(self._section_lbl("Label Preview"))
        self.preview = _LabelPreviewWidget()
        self.preview.setFixedHeight(170)
        lay.addWidget(self.preview)

        lay.addWidget(self._div())

        # Label size
        lay.addWidget(self._section_lbl("Label / Page Size"))
        self.size_combo = QComboBox()
        self.size_combo.setFixedHeight(34)
        self.size_combo.setStyleSheet(self._combo_style())
        for entry in _LABEL_SIZES:
            self.size_combo.addItem(entry[2], entry)
        self.size_combo.setCurrentIndex(1)   # default: 50×30mm
        self.size_combo.currentIndexChanged.connect(self._update_preview)
        lay.addWidget(self.size_combo)

        # Columns (page layouts only) — hidden until a page layout is selected
        self.cols_row_w = QWidget()
        self.cols_row_w.setVisible(False)
        cr = QHBoxLayout(self.cols_row_w); cr.setContentsMargins(0,0,0,0); cr.setSpacing(8)
        cr.addWidget(self._field_lbl("Labels per Row:"))
        self.cols_spin = QSpinBox()
        self.cols_spin.setMinimum(1); self.cols_spin.setMaximum(6); self.cols_spin.setValue(3)
        self.cols_spin.setFixedHeight(32); self.cols_spin.setFixedWidth(60)
        self.cols_spin.setStyleSheet(self._spinbox_style())
        cr.addWidget(self.cols_spin); cr.addStretch()
        lay.addWidget(self.cols_row_w)

        lay.addWidget(self._div())

        # Show on label
        lay.addWidget(self._section_lbl("Show on Label"))
        self.chk_name    = self._toggle("Product Name", True)
        self.chk_price   = self._toggle("Price",        True)
        self.chk_barcode = self._toggle("Barcode",      True)
        for c in (self.chk_name, self.chk_price, self.chk_barcode):
            c.stateChanged.connect(self._update_preview)
            lay.addWidget(c)
        gct_note = QLabel("  GCT and discount tiers shown automatically when applicable.")
        gct_note.setStyleSheet(f"color:{MUTED};font-size:10px;")
        gct_note.setWordWrap(True)
        lay.addWidget(gct_note)

        lay.addWidget(self._div())

        # Copies
        copies_row = QHBoxLayout(); copies_row.setSpacing(8)
        copies_row.addWidget(self._field_lbl("Copies per product:"))
        self.copies_spin = QSpinBox()
        self.copies_spin.setMinimum(1); self.copies_spin.setMaximum(999)
        self.copies_spin.setValue(1); self.copies_spin.setFixedHeight(32)
        self.copies_spin.setFixedWidth(70)
        self.copies_spin.setStyleSheet(self._spinbox_style())
        copies_row.addWidget(self.copies_spin); copies_row.addStretch()
        lay.addLayout(copies_row)

        lay.addStretch()

        # Status
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet(f"color:{GREEN};font-size:11px;")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.status_lbl)

        # Buttons
        self.print_btn = QPushButton("🖨  Preview && Print")
        self.print_btn.setFixedHeight(42)
        self.print_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.print_btn.setStyleSheet(
            f"QPushButton{{background:{AMBER};color:white;border:none;"
            f"border-radius:8px;font-size:14px;font-weight:700;}}"
            f"QPushButton:hover{{background:{AMBER_DARK};}}"
            f"QPushButton:disabled{{background:{MUTED};color:white;}}"
        )
        self.print_btn.setEnabled(False)
        self.print_btn.clicked.connect(lambda: self._do_print(save_pdf=False))
        lay.addWidget(self.print_btn)

        self.pdf_btn = QPushButton("💾  Save as PDF")
        self.pdf_btn.setFixedHeight(34)
        self.pdf_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pdf_btn.setEnabled(False)
        self.pdf_btn.setStyleSheet(
            f"QPushButton{{background:{GREEN_LIGHT};color:{GREEN};border:none;"
            f"border-radius:7px;font-size:12px;font-weight:600;}}"
            f"QPushButton:hover{{background:{GREEN};color:white;}}"
            f"QPushButton:disabled{{background:{WARM_WHITE};color:{MUTED};}}"
        )
        self.pdf_btn.clicked.connect(lambda: self._do_print(save_pdf=True))
        lay.addWidget(self.pdf_btn)

        return card

    # ── Data ──────────────────────────────────────────────────────────────────

    def _search(self):
        self._pg_page   = 0
        self._pg_search = self.search_inp.text().strip()
        self._load_table()

    def _load_table(self):
        search  = self._pg_search
        total   = count_products(search=search, exclude_cases=True)
        pages   = max(1, (total + self._pg_per_page - 1) // self._pg_per_page)
        self._pg_page = min(self._pg_page, pages - 1)

        products = get_products(
            search=search, exclude_cases=True,
            limit=self._pg_per_page,
            offset=self._pg_page * self._pg_per_page,
        )
        self._all_prods = products

        # Build discount tier lookup
        disc_levels = {d["id"]: d for d in get_discount_levels()}  # {id: row_dict}
        currency    = cfg_get("currency_symbol", "$")
        gct_r       = gct_rate()

        tbl = self.prod_table
        tbl.blockSignals(True)
        tbl.setRowCount(0)

        for row, p in enumerate(products):
            tbl.insertRow(row)
            tbl.setRowHeight(row, 34)

            # Checkbox column (native Qt checkable item)
            chk = QTableWidgetItem()
            chk.setData(Qt.ItemDataRole.UserRole, p["id"])
            chk.setFlags(
                Qt.ItemFlag.ItemIsEnabled |
                Qt.ItemFlag.ItemIsSelectable |
                Qt.ItemFlag.ItemIsUserCheckable
            )
            chk.setCheckState(
                Qt.CheckState.Checked if p["id"] in self._selected
                else Qt.CheckState.Unchecked
            )
            chk.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            tbl.setItem(row, 0, chk)

            name_it = QTableWidgetItem(p["name"])
            name_it.setData(Qt.ItemDataRole.UserRole + 1, p["id"])
            tbl.setItem(row, 1, name_it)

            price_it = QTableWidgetItem(
                f"{currency}{p['selling_price']:.2f}"
                + (" +GCT" if p.get("gct_applicable") else "")
            )
            price_it.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            price_it.setForeground(QColor(AMBER_DARK))
            tbl.setItem(row, 2, price_it)

            grp_it = QTableWidgetItem(p.get("group_name") or "—")
            grp_it.setForeground(QColor(MUTED))
            grp_it.setTextAlignment(
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
            )
            tbl.setItem(row, 3, grp_it)

            # Build disc_rows: (min_qty, disc_price, pct_str)
            # Source 1: named global discount levels (FK)
            # Source 2: inline fields from DBF import (no FK, not shown in edit form)
            disc_rows = []
            for lvl_key, qty_key, pct_key in [
                ("discount_level1", None,              None),
                ("discount_level2", None,              None),
                (None,              "inline_disc1_qty", "inline_disc1_pct"),
                (None,              "inline_disc2_qty", "inline_disc2_pct"),
            ]:
                if lvl_key:
                    lid = p.get(lvl_key)
                    if lid and lid in disc_levels:
                        dl  = disc_levels[lid]
                        qty = dl.get("min_quantity") or 0
                        pct = dl.get("discount_percent") or 0.0
                        if qty and pct:
                            disc_price = round(p["selling_price"] * (1 - pct / 100), 2)
                            disc_rows.append((qty, disc_price, f"{pct:.0f}%"))
                else:
                    qty = p.get(qty_key)
                    pct = p.get(pct_key)
                    if qty and pct:
                        disc_price = round(p["selling_price"] * (1 - pct / 100), 2)
                        disc_rows.append((qty, disc_price, f"{pct:.0f}%"))
            # Deduplicate and sort by min_qty
            seen = set()
            deduped = []
            for row in sorted(disc_rows, key=lambda r: r[0]):
                if row[0] not in seen:
                    seen.add(row[0]); deduped.append(row)
            disc_rows = deduped

            self._prod_data[p["id"]] = {
                "name":           p["name"],
                "barcode":        p.get("barcode", ""),
                "price":          p["selling_price"],
                "gct_applicable": bool(p.get("gct_applicable")),
                "disc_rows":      disc_rows,
            }

        tbl.blockSignals(False)
        self._pg_label.setText(f"Page {self._pg_page+1} of {pages}  ({total})")
        self._pg_prev.setEnabled(self._pg_page > 0)
        self._pg_next.setEnabled(self._pg_page < pages - 1)
        self._update_sel_label()

    def _on_item_changed(self, item: QTableWidgetItem):
        if item.column() != 0:
            return
        pid = item.data(Qt.ItemDataRole.UserRole)
        if pid is None:
            return
        if item.checkState() == Qt.CheckState.Checked:
            self._selected.add(pid)
        else:
            self._selected.discard(pid)
        self._update_sel_label()

    def _on_row_changed(self, current, _prev):
        if not current:
            return
        chk = self.prod_table.item(current.row(), 0)
        if not chk:
            return
        pid  = chk.data(Qt.ItemDataRole.UserRole)
        data = self._prod_data.get(pid)
        if data:
            self.preview.set_product(data)
            self._update_preview()

    def _select_all(self):
        tbl = self.prod_table
        tbl.blockSignals(True)
        for row in range(tbl.rowCount()):
            it = tbl.item(row, 0)
            if it:
                self._selected.add(it.data(Qt.ItemDataRole.UserRole))
                it.setCheckState(Qt.CheckState.Checked)
        tbl.blockSignals(False)
        self._update_sel_label()

    def _clear_selection(self):
        tbl = self.prod_table
        tbl.blockSignals(True)
        self._selected.clear()
        for row in range(tbl.rowCount()):
            it = tbl.item(row, 0)
            if it:
                it.setCheckState(Qt.CheckState.Unchecked)
        tbl.blockSignals(False)
        self._update_sel_label()

    def _update_sel_label(self):
        n = len(self._selected)
        self.sel_lbl.setText(f"{n} selected")
        enabled = n > 0
        self.print_btn.setEnabled(enabled)
        self.pdf_btn.setEnabled(enabled)

    def _prev_page(self):
        if self._pg_page > 0:
            self._pg_page -= 1; self._load_table()

    def _next_page(self):
        self._pg_page += 1; self._load_table()

    # ── Preview ───────────────────────────────────────────────────────────────

    def _update_preview(self):
        entry = self.size_combo.currentData()
        if not entry:
            return
        w_val, h_val, _, is_page = entry
        w_mm = 50 if is_page else w_val
        h_mm = 30 if is_page else h_val
        self.preview.set_options({
            "show_name":    self.chk_name.isChecked(),
            "show_price":   self.chk_price.isChecked(),
            "show_barcode": self.chk_barcode.isChecked(),
            "label_w_mm":   w_mm,
            "label_h_mm":   h_mm,
        })
        # Show/hide cols spinner based on whether it's a page layout
        self.cols_row_w.setVisible(is_page)

    # ── Print ─────────────────────────────────────────────────────────────────

    def _do_print(self, save_pdf: bool = False):
        if not self._selected:
            QMessageBox.information(self, "No Products",
                "Select at least one product to print.")
            return

        from core.db_products import get_product_by_id
        job = []
        for pid in self._selected:
            data = self._prod_data.get(pid)
            if not data:
                p = get_product_by_id(pid)
                if p:
                    data = self._prod_data.get(pid, {})
            if data:
                for _ in range(self.copies_spin.value()):
                    job.append(data)

        if not job:
            return

        entry = self.size_combo.currentData()
        if not entry:
            return
        w_val, h_val, _, is_page = entry

        options = {
            "show_name":    self.chk_name.isChecked(),
            "show_price":   self.chk_price.isChecked(),
            "show_barcode": self.chk_barcode.isChecked(),
        }

        try:
            from PyQt6.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog

            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setColorMode(QPrinter.ColorMode.GrayScale)

            # Set up page size
            if is_page:
                pos_w = _POS_WIDTHS.get(str(w_val))
                if pos_w:
                    ps = QPageSize(QSizeF(pos_w, 297),
                                   QPageSize.Unit.Millimeter)
                    layout = QPageLayout(ps, QPageLayout.Orientation.Portrait,
                                        QMarginsF(2, 2, 2, 2),
                                        QPageLayout.Unit.Millimeter)
                    printer.setPageLayout(layout)
                    label_w_mm = pos_w - 4
                    label_h_mm = 30
                    cols = 1
                else:
                    size_map = {
                        "A4":     QPageSize.PageSizeId.A4,
                        "Letter": QPageSize.PageSizeId.Letter,
                        "Legal":  QPageSize.PageSizeId.Legal,
                    }
                    ps = QPageSize(size_map.get(str(w_val), QPageSize.PageSizeId.A4))
                    layout = QPageLayout(ps, QPageLayout.Orientation.Portrait,
                                        QMarginsF(8, 8, 8, 8),
                                        QPageLayout.Unit.Millimeter)
                    printer.setPageLayout(layout)
                    label_w_mm = 62
                    label_h_mm = 35
                    cols = self.cols_spin.value()
            else:
                label_w_mm = float(w_val)
                label_h_mm = float(h_val)
                ps = QPageSize(QSizeF(label_w_mm, label_h_mm),
                               QPageSize.Unit.Millimeter)
                layout = QPageLayout(ps, QPageLayout.Orientation.Portrait,
                                    QMarginsF(0, 0, 0, 0),
                                    QPageLayout.Unit.Millimeter)
                printer.setPageLayout(layout)
                cols = 1

            if save_pdf:
                pdf_path, _ = QFileDialog.getSaveFileName(
                    self, "Save Labels as PDF", "labels.pdf", "PDF Files (*.pdf)"
                )
                if not pdf_path:
                    return
                printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                printer.setOutputFileName(pdf_path)
            else:
                dlg = QPrintPreviewDialog(printer, self)
                dlg.setWindowTitle("Price Tag Preview")

                def _paint(p):
                    self._render_job(p, job, label_w_mm, label_h_mm, cols,
                                     is_page, dict(options,
                                                   label_w_mm=label_w_mm,
                                                   label_h_mm=label_h_mm))

                dlg.paintRequested.connect(_paint)
                dlg.resize(1000, 700)
                dlg.exec()
                self.status_lbl.setText(f"✅  Sent {len(job)} label(s) to printer.")
                return

            # PDF path
            painter = QPainter()
            if not painter.begin(printer):
                self.status_lbl.setText("❌  Could not open PDF output.")
                return
            self._render_job(printer, job, label_w_mm, label_h_mm, cols,
                             is_page, options, painter=painter)
            painter.end()
            self.status_lbl.setText(f"✅  Saved {len(job)} label(s) to PDF.")

        except Exception as e:
            self.status_lbl.setText(f"❌  {e}")
            import traceback; traceback.print_exc()

    def _render_job(self, printer, job, label_w_mm, label_h_mm,
                    cols, is_page, options, painter=None):
        """Paint all labels onto the printer device."""
        from PyQt6.QtPrintSupport import QPrinter
        owns_painter = (painter is None)
        if owns_painter:
            painter = QPainter()
            if not painter.begin(printer):
                return

        # Inject physical dimensions so _draw_label can size fonts correctly
        draw_opts = dict(options, label_w_mm=label_w_mm, label_h_mm=label_h_mm)

        page_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
        dpi       = printer.resolution()
        px_per_mm = dpi / 25.4
        lw_px     = label_w_mm * px_per_mm
        lh_px     = label_h_mm * px_per_mm
        gap_px    = 3 * px_per_mm if is_page else 0

        if is_page:
            x0    = page_rect.left()
            y0    = page_rect.top()
            col   = 0
            row_y = y0
            for i, data in enumerate(job):
                x = x0 + col * (lw_px + gap_px)
                rect = QRectF(x, row_y, lw_px, lh_px)
                _draw_label(painter, rect, data, draw_opts)
                col += 1
                if col >= cols:
                    col   = 0
                    row_y += lh_px + gap_px
                    if row_y + lh_px > page_rect.bottom() and i < len(job) - 1:
                        printer.newPage()
                        row_y = y0
        else:
            for i, data in enumerate(job):
                if i > 0:
                    printer.newPage()
                rect = QRectF(page_rect.left(), page_rect.top(), lw_px, lh_px)
                _draw_label(painter, rect, data, draw_opts)

        if owns_painter:
            painter.end()

    # ── Style helpers ─────────────────────────────────────────────────────────

    def _outline_btn(self, text: str) -> QPushButton:
        b = QPushButton(text); b.setFixedHeight(32)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            f"QPushButton{{background:transparent;color:{LABEL_TEXT};"
            f"border:1.5px solid {BORDER};border-radius:16px;"
            f"font-size:11px;font-weight:600;padding:0 12px;}}"
            f"QPushButton:hover{{border-color:{AMBER};color:{AMBER};}}"
            f"QPushButton:disabled{{color:{MUTED};border-color:{BORDER_LIGHT};}}"
        )
        return b

    def _section_lbl(self, text: str) -> QLabel:
        l = QLabel(text.upper())
        l.setStyleSheet(
            f"color:{MUTED};font-size:10px;font-weight:700;letter-spacing:1px;"
        )
        return l

    def _field_lbl(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(f"color:{LABEL_TEXT};font-size:11px;font-weight:600;")
        return l

    def _toggle(self, label: str, checked: bool = True) -> QCheckBox:
        cb = QCheckBox(label); cb.setChecked(checked)
        cb.setStyleSheet(
            f"QCheckBox{{color:{DARK_CARD};font-size:12px;}}"
            f"QCheckBox::indicator{{width:15px;height:15px;"
            f"border:1px solid {BORDER};border-radius:3px;background:{WHITE};}}"
            f"QCheckBox::indicator:checked{{background:{AMBER};border-color:{AMBER};}}"
        )
        return cb

    def _div(self) -> QFrame:
        d = QFrame(); d.setFrameShape(QFrame.Shape.HLine)
        d.setStyleSheet(f"background:{BORDER_LIGHT};max-height:1px;border:none;")
        return d

    def _input_style(self) -> str:
        return (
            f"QLineEdit{{background:{WHITE};color:{DARK_CARD};border:1px solid {BORDER};"
            f"border-radius:7px;padding:0 10px;font-size:12px;}}"
            f"QLineEdit:focus{{border-color:{AMBER};}}"
        )

    def _combo_style(self) -> str:
        return (
            f"QComboBox{{background:{WHITE};color:{DARK_CARD};border:1px solid {BORDER};"
            f"border-radius:7px;padding:0 10px;font-size:12px;}}"
            f"QComboBox:focus{{border-color:{AMBER};}}"
            f"QComboBox::drop-down{{border:none;width:20px;}}"
        )

    def _spinbox_style(self) -> str:
        return (
            f"QSpinBox{{background:{WHITE};color:{DARK_CARD};border:1px solid {BORDER};"
            f"border-radius:7px;padding:0 8px;font-size:12px;}}"
            f"QSpinBox:focus{{border-color:{AMBER};}}"
        )

    def _table_style(self) -> str:
        return (
            f"QTableWidget{{background:{WHITE};border:none;font-size:12px;color:{DARK_CARD};}}"
            f"QTableWidget::item{{padding:6px 8px;border-bottom:1px solid {BORDER_LIGHT};}}"
            f"QTableWidget::item:selected{{background:{AMBER_BG};color:{DARK_CARD};}}"
            f"QHeaderView::section{{background:{DARK};color:{AMBER};font-size:11px;"
            f"font-weight:700;padding:6px 8px;border:none;"
            f"border-right:1px solid {DARK_4};}}"
        )
