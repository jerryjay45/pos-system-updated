"""
ui/supervisor/supervisor_window.py
Supervisor dashboard — Products, Reports, Transactions, Void/Refund, Quick Keys.
Adapted from prototype layout and functions with amber/dark theme.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QComboBox, QCheckBox, QAbstractItemView,
    QMessageBox, QScrollArea, QSpinBox, QDoubleSpinBox, QDialog, QDialogButtonBox,
)
from PyQt6.QtCore import Qt, QTimer, QDateTime, pyqtSignal
from PyQt6.QtGui import QColor, QDoubleValidator

from ui.base_window  import BaseWindow
from ui.shared.theme import (
    AMBER, AMBER_DARK, AMBER_LIGHTEST, AMBER_BG,
    DARK, DARK_2, DARK_4, DARK_CARD,
    WARM_WHITE, WHITE, BORDER, BORDER_LIGHT, MUTED, LABEL_TEXT,
    RED, RED_LIGHT, GREEN, GREEN_LIGHT, BLUE,
)
from ui.supervisor.void_refund_tab import VoidRefundTab
from core.db_products import (
    get_products, get_product_by_id, add_product, update_product,
    delete_product, get_groups, add_group,
    get_price_groups, add_price_group, update_price_group,
    count_products, cascade_single_cost_to_cases, recalculate_all_cases,
    adjust_stock,
)
from core.db_users    import get_users, get_sessions, open_session, close_session, get_user_by_id, has_open_session
from core.db_checkout import (
    get_receipts, get_receipt_by_id, void_receipt, refund_receipt,
    session_totals, count_receipts,
)
from core.db_config   import get_quick_keys, save_quick_keys, gct_rate


class SupervisorWindow(BaseWindow):
    logout_requested = pyqtSignal()

    def __init__(self, user: dict, parent=None):
        super().__init__(parent)
        self.user = user
        self._editing_product_id = None
        self.setWindowTitle("POS System – Supervisor")
        self.setMinimumSize(1280, 720)
        self._build_ui()
        self._start_clock()

    # =================================================================
    # UI BUILD
    # =================================================================

    def _build_ui(self):
        root = QWidget(); root.setStyleSheet(f"background:{WARM_WHITE};")
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        lay.addWidget(self._build_topbar())
        lay.addWidget(self._build_tabs(), stretch=1)

    def _build_topbar(self):
        bar = QFrame(); bar.setFixedHeight(44)
        bar.setStyleSheet(f"background:{DARK};border-bottom:1px solid {DARK_4};")
        lay = QHBoxLayout(bar); lay.setContentsMargins(16, 0, 16, 0)
        left = QLabel(f"POS System  |  Supervisor:  {self.user['full_name']}")
        left.setStyleSheet("color:white;font-size:13px;font-weight:600;")
        self._clock = QLabel()
        self._clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._clock.setStyleSheet(f"color:{MUTED};font-size:11px;font-family:'DM Mono',monospace;")
        logout = QPushButton("Logout  ↗"); logout.setFixedHeight(30)
        logout.setCursor(Qt.CursorShape.PointingHandCursor)
        logout.setStyleSheet(f"""
            QPushButton{{background:{AMBER};color:white;border:none;
            border-radius:15px;font-size:11px;font-weight:700;padding:0 16px;}}
            QPushButton:hover{{background:{AMBER_DARK};}}
        """)
        logout.clicked.connect(self._handle_logout)
        lay.addWidget(left); lay.addStretch()
        lay.addWidget(self._clock); lay.addStretch()
        lay.addWidget(logout)
        return bar

    def _build_tabs(self):
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane{{background:{WARM_WHITE};border:none;}}
            QTabBar::tab{{background:{WHITE};color:{LABEL_TEXT};border:none;
            border-bottom:2px solid transparent;padding:10px 18px;
            font-size:12px;font-weight:500;margin-right:2px;}}
            QTabBar::tab:selected{{color:{DARK_CARD};border-bottom:2px solid {AMBER};font-weight:700;}}
            QTabBar::tab:hover{{color:{DARK_CARD};}}
        """)
        self.tabs.addTab(self._build_products_tab(),     "📦  Products")
        self.tabs.addTab(self._build_reports_tab(),      "📊  Reports")
        self.tabs.addTab(self._build_transactions_tab(), "🧾  Transactions")
        self.tabs.addTab(VoidRefundTab(self.user),       "↩  Void / Refund")
        self.tabs.addTab(self._build_quickkeys_tab(),    "⌨  Quick Keys")
        self.tabs.setCurrentIndex(0)
        return self.tabs

    # ================================================================
    # PRODUCTS TAB
    # ================================================================

    def _build_products_tab(self):
        w = QWidget(); w.setStyleSheet(f"background:{WARM_WHITE};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10); lay.setSpacing(10)
        lay.addWidget(self._build_product_list(), stretch=3)
        lay.addWidget(self._build_product_form(), stretch=2)
        return w

    def _build_product_list(self):
        panel = QFrame()
        panel.setStyleSheet(f"background:{WHITE};border-radius:10px;border:1px solid {BORDER};")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 10, 10, 10); lay.setSpacing(8)

        tb = QHBoxLayout(); tb.setSpacing(6)
        self.product_search = QLineEdit()
        self.product_search.setPlaceholderText("🔍  Search by name, barcode, alias or group…")
        self.product_search.setFixedHeight(36)
        self.product_search.setStyleSheet(self._input_style())
        self.product_search.returnPressed.connect(self._search_products)

        refresh_btn = self._outline_btn("↻  Refresh")
        refresh_btn.setFixedHeight(36)
        refresh_btn.clicked.connect(lambda: (setattr(self, '_pg_page', 0), self._load_products(self.product_search.text())))

        recalc_btn = QPushButton("⟳ Recalc Cases")
        recalc_btn.setFixedHeight(36)
        recalc_btn.setStyleSheet(self._accent_btn())
        recalc_btn.clicked.connect(self._recalc_cases)

        tb.addWidget(self.product_search, stretch=1); tb.addWidget(refresh_btn)
        tb.addWidget(recalc_btn)
        lay.addLayout(tb)

        self.product_table = QTableWidget(); self.product_table.setColumnCount(7)
        self.product_table.setHorizontalHeaderLabels(
            ["ID", "Barcode", "Name", "Group", "Unit $", "Case", "Stock"]
        )
        hh = self.product_table.horizontalHeader()
        for c in [0,1,3,6]: hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        for c in [2,4,5]:    hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        self.product_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.product_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.product_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.product_table.verticalHeader().setVisible(False); self.product_table.setShowGrid(False)
        self.product_table.setStyleSheet(self._table_style())
        self.product_table.itemClicked.connect(lambda _: self._on_product_selected())
        lay.addWidget(self.product_table, stretch=1)

        # Pagination
        pg_row = QHBoxLayout(); pg_row.setSpacing(8)
        self._pg_prev = self._outline_btn("← Prev"); self._pg_prev.setFixedWidth(80)
        self._pg_prev.clicked.connect(self._prev_page)
        self._pg_label = QLabel("Page 1 of 1")
        self._pg_label.setStyleSheet(f"color:{MUTED};font-size:11px;")
        self._pg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pg_next = self._outline_btn("Next →"); self._pg_next.setFixedWidth(80)
        self._pg_next.clicked.connect(self._next_page)
        pg_row.addStretch(); pg_row.addWidget(self._pg_prev); pg_row.addWidget(self._pg_label)
        pg_row.addWidget(self._pg_next); pg_row.addStretch()
        lay.addLayout(pg_row)

        self._pg_page = 0; self._pg_limit = 20
        self._load_products("")
        return panel

    def _build_product_form(self):
        panel = QFrame()
        panel.setStyleSheet(f"background:{WHITE};border-radius:10px;border:1px solid {BORDER};")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 12, 12, 12); lay.setSpacing(10)

        def _divider():
            f = QFrame(); f.setFrameShape(QFrame.Shape.HLine); f.setStyleSheet(f"background:{BORDER_LIGHT};")
            return f

        def _section(title):
            lbl = QLabel(title)
            lbl.setStyleSheet(f"color:{LABEL_TEXT};font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;")
            return lbl

        def _input(ph="", validator=None):
            field = QLineEdit(); field.setPlaceholderText(ph); field.setFixedHeight(32)
            if validator: field.setValidator(validator)
            field.setStyleSheet(self._input_style())
            return field

        def _spin(minv=0, maxv=999999, suf=""):
            sp = QSpinBox(); sp.setMinimum(minv); sp.setMaximum(maxv)
            sp.setSuffix(suf); sp.setFixedHeight(32); sp.setStyleSheet(self._input_style())
            return sp

        def _dspin(minv=0, maxv=999999, dec=2, suf=""):
            sp = QDoubleSpinBox(); sp.setMinimum(minv); sp.setMaximum(maxv)
            sp.setDecimals(dec); sp.setSuffix(suf); sp.setFixedHeight(32)
            sp.setStyleSheet(self._input_style())
            return sp

        def _combo(items):
            cb = QComboBox(); cb.addItems(items); cb.setFixedHeight(32)
            cb.setStyleSheet(self._combo_style())
            return cb

        def cell(t, color=DARK_CARD, align=None):
            lbl = QLabel(t)
            lbl.setStyleSheet(f"color:{color};font-size:11px;font-weight:600;")
            if align: lbl.setAlignment(align)
            return lbl

        # Header
        hdr = QLabel("Product Details")
        hdr.setStyleSheet(f"color:{DARK_CARD};font-size:12px;font-weight:700;")
        lay.addWidget(hdr)
        lay.addWidget(_divider())

        # ID
        lay.addWidget(cell("ID", MUTED))
        self.prod_id = QLineEdit(); self.prod_id.setReadOnly(True); self.prod_id.setFixedHeight(28)
        self.prod_id.setStyleSheet(f"background:{BORDER_LIGHT};color:{MUTED};font-size:10px;")
        lay.addWidget(self.prod_id)

        # Barcode
        lay.addWidget(cell("Barcode"))
        self.prod_barcode = _input("e.g. 5901234123457")
        lay.addWidget(self.prod_barcode)

        # Name
        lay.addWidget(cell("Name"))
        self.prod_name = _input("Product name")
        lay.addWidget(self.prod_name)

        # Group
        lay.addWidget(cell("Group"))
        self.prod_group = _combo(["Select Group..."])
        lay.addWidget(self.prod_group)

        # Unit price
        lay.addWidget(cell("Unit Price $"))
        self.prod_unit_price = _dspin(0, 9999, 2, " $")
        lay.addWidget(self.prod_unit_price)

        # Cost
        lay.addWidget(cell("Cost $"))
        self.prod_cost = _dspin(0, 9999, 2, " $")
        lay.addWidget(self.prod_cost)

        # Markup
        lay.addWidget(cell("Markup %"))
        self.prod_markup = _dspin(0, 500, 1, " %")
        lay.addWidget(self.prod_markup)

        lay.addSpacing(4)
        lay.addWidget(_divider())

        # Case qty
        lay.addWidget(cell("Case Qty"))
        self.prod_case_qty = _spin(1, 999, " units")
        lay.addWidget(self.prod_case_qty)

        # Case cost
        lay.addWidget(cell("Case Cost $"))
        self.prod_case_cost = _dspin(0, 99999, 2, " $")
        lay.addWidget(self.prod_case_cost)

        # Stock
        lay.addWidget(cell("Current Stock"))
        self.prod_stock = _spin(0, 999999, " units")
        lay.addWidget(self.prod_stock)

        lay.addSpacing(4)
        lay.addWidget(_divider())

        # Buttons
        btn_row = QHBoxLayout(); btn_row.setSpacing(6)
        save_btn = QPushButton("💾 Save")
        save_btn.setStyleSheet(self._accent_btn()); save_btn.clicked.connect(self._save_product)
        delete_btn = QPushButton("🗑  Delete")
        delete_btn.setStyleSheet(f"""QPushButton{{background:{RED};color:white;border:none;border-radius:6px;
        font-weight:600;}} QPushButton:hover{{background:#7A1E1E;}}""")
        delete_btn.clicked.connect(self._delete_product)
        new_btn = QPushButton("+ New")
        new_btn.setStyleSheet(self._outline_btn()); new_btn.clicked.connect(self._new_product)

        btn_row.addWidget(new_btn); btn_row.addWidget(save_btn); btn_row.addWidget(delete_btn)
        lay.addLayout(btn_row)

        lay.addStretch()
        return panel

    # Products helpers
    def _load_products(self, search=""):
        offset = self._pg_page * self._pg_limit
        total = count_products(search=search)
        prods = get_products(search=search, limit=self._pg_limit, offset=offset)
        self.product_table.setRowCount(len(prods))
        for i, p in enumerate(prods):
            self.product_table.setItem(i, 0, QTableWidgetItem(str(p.get("id", ""))))
            self.product_table.setItem(i, 1, QTableWidgetItem(p.get("barcode", "")))
            self.product_table.setItem(i, 2, QTableWidgetItem(p.get("name", "")))
            self.product_table.setItem(i, 3, QTableWidgetItem(p.get("group_name", "Ungrouped")))
            self.product_table.setItem(i, 4, QTableWidgetItem(f"${p.get('unit_price', 0):.2f}"))
            self.product_table.setItem(i, 5, QTableWidgetItem(f"${p.get('case_cost', 0):.2f}"))
            self.product_table.setItem(i, 6, QTableWidgetItem(str(p.get("stock_count", 0))))
        pages = (total + self._pg_limit - 1) // self._pg_limit
        self._pg_label.setText(f"Page {self._pg_page + 1} of {pages}")
        self._pg_prev.setEnabled(self._pg_page > 0)
        self._pg_next.setEnabled(self._pg_page + 1 < pages)

    def _on_product_selected(self):
        rows = self.product_table.selectedItems()
        if not rows: return
        pid = int(rows[0].text())
        p = get_product_by_id(pid)
        if not p: return
        self._editing_product_id = pid
        self.prod_id.setText(str(p.get("id", "")))
        self.prod_barcode.setText(p.get("barcode", ""))
        self.prod_name.setText(p.get("name", ""))
        self.prod_unit_price.setValue(float(p.get("unit_price", 0)))
        self.prod_cost.setValue(float(p.get("cost", 0)))
        self.prod_markup.setValue(float(p.get("markup_pct", 0)))
        self.prod_case_qty.setValue(int(p.get("case_qty", 1)))
        self.prod_case_cost.setValue(float(p.get("case_cost", 0)))
        self.prod_stock.setValue(int(p.get("stock_count", 0)))

    def _new_product(self):
        self._editing_product_id = None
        self.prod_id.setText("")
        self.prod_barcode.clear()
        self.prod_name.clear()
        self.prod_unit_price.setValue(0)
        self.prod_cost.setValue(0)
        self.prod_markup.setValue(0)
        self.prod_case_qty.setValue(1)
        self.prod_case_cost.setValue(0)
        self.prod_stock.setValue(0)

    def _save_product(self):
        if not self.prod_barcode.text() or not self.prod_name.text():
            QMessageBox.warning(self, "Required", "Barcode and name are required.")
            return
        try:
            if self._editing_product_id:
                update_product(self._editing_product_id, name=self.prod_name.text(),
                    barcode=self.prod_barcode.text(), unit_price=self.prod_unit_price.value(),
                    cost=self.prod_cost.value(), markup_pct=self.prod_markup.value(),
                    case_qty=self.prod_case_qty.value(), case_cost=self.prod_case_cost.value())
            else:
                add_product(self.prod_barcode.text(), self.prod_name.text(), self.prod_unit_price.value(),
                    cost=self.prod_cost.value(), markup_pct=self.prod_markup.value(),
                    case_qty=self.prod_case_qty.value(), case_cost=self.prod_case_cost.value())
            QMessageBox.information(self, "Success", "Product saved.")
            self._load_products(self.product_search.text())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save: {e}")

    def _delete_product(self):
        if not self._editing_product_id:
            QMessageBox.warning(self, "Not Selected", "Select a product first.")
            return
        if QMessageBox.question(self, "Confirm", "Delete this product?") == QMessageBox.StandardButton.Yes:
            delete_product(self._editing_product_id)
            QMessageBox.information(self, "Deleted", "Product removed.")
            self._new_product()
            self._load_products(self.product_search.text())

    def _search_products(self):
        self._pg_page = 0; self._load_products(self.product_search.text())

    def _prev_page(self):
        if self._pg_page > 0: self._pg_page -= 1
        self._load_products(self.product_search.text())

    def _next_page(self):
        self._pg_page += 1; self._load_products(self.product_search.text())

    def _recalc_cases(self):
        if QMessageBox.question(self, "Confirm", "Recalculate all case costs? This may take a moment.") == QMessageBox.StandardButton.Yes:
            recalculate_all_cases()
            QMessageBox.information(self, "Done", "Case costs recalculated.")
            self._load_products()

    # ================================================================
    # REPORTS TAB (stub)
    # ================================================================

    def _build_reports_tab(self):
        w = QWidget(); w.setStyleSheet(f"background:{WARM_WHITE};")
        lay = QVBoxLayout(w); lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel("📊  Reports\n(Session summaries, trends, etc. — coming soon)")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color:{MUTED};font-size:14px;")
        lay.addWidget(lbl)
        return w

    # ================================================================
    # TRANSACTIONS TAB (stub)
    # ================================================================

    def _build_transactions_tab(self):
        w = QWidget(); w.setStyleSheet(f"background:{WARM_WHITE};")
        lay = QVBoxLayout(w); lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel("🧾  Transactions\n(View/audit completed sales — coming soon)")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color:{MUTED};font-size:14px;")
        lay.addWidget(lbl)
        return w

    # ================================================================
    # QUICK KEYS TAB
    # ================================================================

    def _build_quickkeys_tab(self):
        w = QWidget(); w.setStyleSheet(f"background:{WARM_WHITE};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16); lay.setSpacing(12)

        lbl = QLabel("Quick Keys — Assign products to F1-F12 for rapid checkout")
        lbl.setStyleSheet(f"color:{DARK_CARD};font-size:13px;font-weight:600;")
        lay.addWidget(lbl)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        container = QWidget()
        grid = QVBoxLayout(container)
        grid.setSpacing(10)

        self.qk_fields = {}
        for i in range(1, 13):
            row = QHBoxLayout(); row.setSpacing(12)
            lbl = QLabel(f"F{i}"); lbl.setFixedWidth(30); lbl.setStyleSheet(f"font-weight:700;color:{LABEL_TEXT};")
            inp = QLineEdit(); inp.setPlaceholderText("Barcode or product ID"); inp.setStyleSheet(self._input_style())
            self.qk_fields[i] = inp
            row.addWidget(lbl); row.addWidget(inp)
            grid.addLayout(row)

        grid.addStretch()
        scroll.setWidget(container)
        lay.addWidget(scroll, stretch=1)

        save_btn = QPushButton("💾 Save Quick Keys")
        save_btn.setFixedHeight(40); save_btn.setStyleSheet(self._accent_btn())
        save_btn.clicked.connect(self._save_quickkeys)
        lay.addWidget(save_btn)

        self._load_quickkeys()
        return w

    def _load_quickkeys(self):
        try:
            qks = get_quick_keys()
            for i in range(1, 13):
                self.qk_fields[i].setText(qks.get(str(i), ""))
        except:
            pass

    def _save_quickkeys(self):
        try:
            qks = {str(i): self.qk_fields[i].text() for i in range(1, 13)}
            save_quick_keys(qks)
            QMessageBox.information(self, "Saved", "Quick keys updated.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save: {e}")

    # ================================================================
    # Helpers & Clock
    # ================================================================

    def _start_clock(self):
        self.clock_timer = QTimer()
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(1000)

    def _update_clock(self):
        self._clock.setText(QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss"))

    def _handle_logout(self):
        self.logout_requested.emit()

    def _input_style(self):
        return f"""QLineEdit{{background:{WHITE};border:1px solid {BORDER};border-radius:6px;
        padding:0 10px;font-size:12px;color:{DARK_CARD};}}
        QLineEdit:focus{{border:1px solid {AMBER};background:{WHITE};}}"""

    def _combo_style(self):
        return f"""QComboBox{{background:{WHITE};border:1px solid {BORDER};border-radius:6px;
        padding:0 10px;font-size:12px;color:{DARK_CARD};}}
        QComboBox:focus{{border:1px solid {AMBER};}}
        QComboBox::drop-down{{border:none;width:20px;}}
        QComboBox QAbstractItemView{{background:{WHITE};border:1px solid {BORDER};
        selection-background-color:{AMBER_BG};selection-color:{DARK_CARD};}}"""

    def _table_style(self):
        return f"""QTableWidget{{background:{WHITE};gridline-color:{BORDER_LIGHT};border:none;}}
        QTableWidget::item{{padding:8px 6px;border-bottom:1px solid {BORDER_LIGHT};color:{DARK_CARD};}}
        QTableWidget::item:selected{{background-color:{AMBER_BG};color:{DARK_CARD};}}
        QHeaderView::section{{background-color:{DARK_CARD};color:{AMBER};font-size:11px;
        font-weight:700;padding:8px 6px;border:none;border-right:1px solid {DARK_4};}}"""

    def _accent_btn(self):
        return f"""QPushButton{{background:{AMBER};color:white;border:none;border-radius:6px;
        font-weight:600;}} QPushButton:hover{{background:{AMBER_DARK};}}"""

    def _outline_btn(self, text):
        btn = QPushButton(text)
        btn.setStyleSheet(f"""QPushButton{{background:{WHITE};border:1px solid {BORDER};
        border-radius:6px;color:{DARK_CARD};font-weight:600;}}
        QPushButton:hover{{border-color:{AMBER};color:{AMBER};background:{AMBER_LIGHTEST};}}""")
        return btn
