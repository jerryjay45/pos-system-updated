"""
ui/supervisor/supervisor_window.py
Supervisor dashboard — Products, Reports, Transactions, Void/Refund, Quick Keys.
Adapted from prototype layout and functions with amber/dark theme.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QComboBox, QCheckBox, QAbstractItemView,
    QMessageBox, QScrollArea, QSplitter, QSpinBox,
)
from PyQt6.QtCore  import Qt, QTimer, QDateTime, pyqtSignal
from PyQt6.QtGui   import QColor, QDoubleValidator

from ui.base_window  import BaseWindow
from ui.shared.theme import (
    AMBER, AMBER_DARK, AMBER_LIGHTEST, AMBER_BG,
    DARK, DARK_2, DARK_4, DARK_CARD,
    WARM_WHITE, WHITE, BORDER, BORDER_LIGHT, MUTED, LABEL_TEXT,
    RED, RED_LIGHT, GREEN, GREEN_LIGHT, BLUE,
)
from core.db_products import (
    get_products, get_product_by_id, add_product, update_product,
    delete_product, get_groups, add_group, get_aliases, set_aliases,
)
from core.db_users    import get_users, get_sessions, open_session, close_session, get_user_by_id
from core.db_checkout import (
    get_receipts, get_receipt_by_id, void_receipt, refund_receipt, session_totals,
)
from core.db_config   import get_quick_keys, save_quick_keys, gct_rate


class SupervisorWindow(BaseWindow):
    logout_requested = pyqtSignal()

    def __init__(self, user: dict, parent=None):
        super().__init__(parent)
        self.user = user
        self._editing_product_id = None
        self.setWindowTitle("POS System — Supervisor")
        self.setMinimumSize(1280, 720)
        self._build_ui()
        self._start_clock()

    # ================================================================
    # UI BUILD
    # ================================================================

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
        self.tabs.addTab(self._build_void_tab(),         "↩  Void / Refund")
        self.tabs.addTab(self._build_quickkeys_tab(),    "⌨  Quick Keys")
        self.tabs.setCurrentIndex(0)
        return self.tabs

    # ================================================================
    # PRODUCTS TAB
    # ================================================================

    def _build_products_tab(self):
        w = QWidget(); w.setStyleSheet(f"background:{WARM_WHITE};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8); lay.setSpacing(8)
        lay.addWidget(self._build_product_list(), stretch=1)
        lay.addWidget(self._build_product_form())
        return w

    def _build_product_list(self):
        panel = QFrame()
        panel.setStyleSheet(f"background:{WHITE};border-radius:10px;border:1px solid {BORDER};")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 10, 10, 10); lay.setSpacing(8)

        tb = QHBoxLayout(); tb.setSpacing(8)
        self.product_search = QLineEdit()
        self.product_search.setPlaceholderText("🔍  Search by name, barcode, brand, alias or group…")
        self.product_search.setFixedHeight(34)
        self.product_search.setStyleSheet(self._input_style())
        self.product_search.returnPressed.connect(self._search_products)

        refresh_btn = self._icon_btn("↻", "Refresh")
        refresh_btn.clicked.connect(lambda: self._load_products(self.product_search.text()))

        add_btn = QPushButton("+ Add Product"); add_btn.setFixedHeight(34)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(self._accent_btn())
        add_btn.clicked.connect(self._new_product_form)

        tb.addWidget(self.product_search, stretch=1)
        tb.addWidget(refresh_btn); tb.addWidget(add_btn)
        lay.addLayout(tb)

        self.product_table = QTableWidget()
        self.product_table.setColumnCount(8)
        self.product_table.setHorizontalHeaderLabels(
            ["Name","Barcode","Brand","Price","Group","GCT","Type","Actions"])
        hh = self.product_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, w_ in enumerate([120,100,80,90,60,60,80], start=1):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.product_table.setColumnWidth(col, w_)
        self.product_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.product_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.product_table.verticalHeader().setVisible(False)
        self.product_table.setShowGrid(False)
        self.product_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.product_table.setStyleSheet(self._table_style())
        self.product_table.doubleClicked.connect(self._on_product_dbl_click)
        lay.addWidget(self.product_table, stretch=1)
        self._load_products()
        return panel

    def _build_product_form(self):
        scroll = QScrollArea(); scroll.setFixedWidth(280); scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea{{background:{WHITE};border:1px solid {BORDER};border-radius:10px;}}")
        fw = QWidget(); fw.setStyleSheet(f"background:{WHITE};")
        lay = QVBoxLayout(fw); lay.setContentsMargins(14,14,14,14); lay.setSpacing(10)

        self.form_title = QLabel("➕  Add Product")
        self.form_title.setStyleSheet(f"color:{DARK_CARD};font-size:13px;font-weight:700;")
        lay.addWidget(self.form_title)

        self.f_barcode = self._field("Barcode", "Scan or type barcode")
        self.f_brand   = self._field("Brand",   "e.g. Coca Cola")
        self.f_name    = self._field("Name",     "e.g. Coca Cola 330ml")
        self.f_alias   = self._field("Alias",    "e.g. coca-cola (comma-separated)")
        self.f_cost    = self._field("Cost",     "0.00")
        self.f_cost[1].setValidator(QDoubleValidator(0, 999999, 2))
        self.f_cost[1].textChanged.connect(self._calc_selling_price)
        for lbl, inp in [self.f_barcode, self.f_brand, self.f_name, self.f_alias, self.f_cost]:
            lay.addWidget(lbl); lay.addWidget(inp)

        lay.addWidget(self._flabel("Selling Price"))
        self.f_price = QLineEdit(); self.f_price.setReadOnly(True); self.f_price.setFixedHeight(34)
        self.f_price.setStyleSheet(f"QLineEdit{{background:#0d1a10;color:{GREEN};border:1px solid #1a3a20;border-radius:6px;padding:0 10px;font-size:13px;font-weight:700;}}")
        self.f_price_hint = QLabel(""); self.f_price_hint.setStyleSheet(f"color:{MUTED};font-size:10px;")
        lay.addWidget(self.f_price); lay.addWidget(self.f_price_hint)

        lay.addWidget(self._flabel("Group"))
        self.f_group = QComboBox(); self.f_group.setStyleSheet(self._combo_style())
        self.f_group.currentIndexChanged.connect(self._calc_selling_price)
        self._populate_groups(); lay.addWidget(self.f_group)

        lay.addWidget(self._flabel("Discount Level 1"))
        self.f_disc1 = QComboBox(); self.f_disc1.setStyleSheet(self._combo_style())
        self._populate_discount_levels(self.f_disc1); lay.addWidget(self.f_disc1)

        lay.addWidget(self._flabel("Discount Level 2  (higher qty)"))
        self.f_disc2 = QComboBox(); self.f_disc2.setStyleSheet(self._combo_style())
        self._populate_discount_levels(self.f_disc2); lay.addWidget(self.f_disc2)

        div = QFrame(); div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"background:{BORDER};max-height:1px;border:none;")
        lay.addWidget(div)

        self.t_gct  = self._toggle("GCT Applicable", True)
        self.t_case = self._toggle("Case Item")
        self.t_case.stateChanged.connect(self._on_case_toggled)
        lay.addWidget(self.t_gct); lay.addWidget(self.t_case)

        self.case_box = QFrame(); self.case_box.setVisible(False)
        self.case_box.setStyleSheet(f"background:{AMBER_LIGHTEST};border:1px solid {AMBER};border-radius:6px;")
        cb_lay = QVBoxLayout(self.case_box); cb_lay.setContentsMargins(10,10,10,10); cb_lay.setSpacing(6)
        cb_lay.addWidget(self._flabel("Units per Case"))
        self.f_case_qty = QSpinBox(); self.f_case_qty.setMinimum(1); self.f_case_qty.setMaximum(9999)
        self.f_case_qty.setStyleSheet(self._input_style())
        cb_lay.addWidget(self.f_case_qty)
        lay.addWidget(self.case_box)

        lay.addStretch()

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        self.cancel_btn = QPushButton("Cancel"); self.cancel_btn.setFixedHeight(34)
        self.cancel_btn.setStyleSheet(f"QPushButton{{background:{DARK_CARD};color:white;border:none;border-radius:7px;font-size:12px;}}QPushButton:hover{{background:#444;}}")
        self.cancel_btn.clicked.connect(self._new_product_form)
        self.save_btn = QPushButton("Save Product"); self.save_btn.setFixedHeight(34)
        self.save_btn.setStyleSheet(self._accent_btn()); self.save_btn.clicked.connect(self._save_product)
        btn_row.addWidget(self.cancel_btn); btn_row.addWidget(self.save_btn, stretch=1)
        lay.addLayout(btn_row)

        scroll.setWidget(fw)
        return scroll

    # ── Products: data ────────────────────────────────────────────────

    def _load_products(self, search=""):
        products = get_products(search=search, limit=500)
        self.product_table.setRowCount(0)
        R = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        C = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter
        for row, p in enumerate(products):
            self.product_table.insertRow(row)
            self.product_table.setRowHeight(row, 36)
            def cell(t, color=DARK_CARD, align=None):
                c = QTableWidgetItem(str(t)); c.setForeground(QColor(color))
                if align: c.setTextAlignment(align)
                return c
            gct_c = AMBER_DARK if p["gct_applicable"] else MUTED
            typ_c = BLUE if p["is_case"] else LABEL_TEXT
            self.product_table.setItem(row, 0, cell(p["name"]))
            self.product_table.setItem(row, 1, cell(p["barcode"], MUTED))
            self.product_table.setItem(row, 2, cell(p["brand"] or "—"))
            self.product_table.setItem(row, 3, cell(f"${p['selling_price']:.2f}", AMBER_DARK, R))
            self.product_table.setItem(row, 4, cell(p.get("group_name") or "—", LABEL_TEXT, C))
            self.product_table.setItem(row, 5, cell("GCT" if p["gct_applicable"] else "No GCT", gct_c, C))
            self.product_table.setItem(row, 6, cell("Case" if p["is_case"] else "Single", typ_c, C))
            act = QWidget(); al = QHBoxLayout(act)
            al.setContentsMargins(4,2,4,2); al.setSpacing(4)
            for icon, color, cb in [
                ("✎", AMBER, lambda _, pid=p["id"]: self._edit_product(pid)),
                ("✕", RED,   lambda _, pid=p["id"]: self._delete_product(pid)),
            ]:
                b = QPushButton(icon); b.setFixedSize(26,26)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setStyleSheet(f"QPushButton{{background:transparent;color:{color};border:1px solid {color};border-radius:5px;font-size:13px;}}QPushButton:hover{{background:{color};color:white;}}")
                b.clicked.connect(cb); al.addWidget(b)
            al.addStretch()
            self.product_table.setCellWidget(row, 7, act)

    def _search_products(self):
        self._load_products(self.product_search.text().strip())

    def _on_product_dbl_click(self, index):
        barcode_item = self.product_table.item(index.row(), 1)
        if not barcode_item: return
        from core.db_products import get_product_by_barcode
        p = get_product_by_barcode(barcode_item.text())
        if p: self._edit_product(p["id"])

    def _new_product_form(self):
        self._editing_product_id = None
        self.form_title.setText("➕  Add Product")
        for _, inp in [self.f_barcode, self.f_brand, self.f_name, self.f_alias, self.f_cost]:
            inp.clear()
        self.f_group.setCurrentIndex(0); self.f_disc1.setCurrentIndex(0); self.f_disc2.setCurrentIndex(0)
        self.t_gct.setChecked(True); self.t_case.setChecked(False)
        self.f_price.clear(); self.f_price_hint.clear()

    def _edit_product(self, pid: int):
        p = get_product_by_id(pid)
        if not p: return
        self._editing_product_id = pid
        self.form_title.setText("✎  Edit Product")
        self.f_barcode[1].setText(p["barcode"]); self.f_brand[1].setText(p["brand"] or "")
        self.f_name[1].setText(p["name"])
        self.f_alias[1].setText(", ".join(get_aliases(pid)))
        self.f_cost[1].setText(str(p["cost"]))
        self.f_price.setText(f"${p['selling_price']:.2f}")
        self.t_gct.setChecked(bool(p["gct_applicable"]))
        self.t_case.setChecked(bool(p["is_case"]))
        if p["is_case"] and p.get("case_qty"): self.f_case_qty.setValue(p["case_qty"])
        for i in range(self.f_group.count()):
            if self.f_group.itemData(i) == p.get("group_id"):
                self.f_group.setCurrentIndex(i); break

    def _save_product(self):
        barcode = self.f_barcode[1].text().strip()
        name    = self.f_name[1].text().strip()
        if not barcode or not name:
            QMessageBox.warning(self, "Missing Fields", "Barcode and Name are required."); return
        try:    cost = float(self.f_cost[1].text() or 0)
        except: QMessageBox.warning(self, "Invalid Cost", "Enter a valid cost."); return
        group_id = self.f_group.currentData()
        selling_price = self._get_selling_price(cost, group_id)
        kwargs = dict(barcode=barcode, brand=self.f_brand[1].text().strip(), name=name,
                      cost=cost, selling_price=selling_price, group_id=group_id,
                      discount_level1=self.f_disc1.currentData(),
                      discount_level2=self.f_disc2.currentData(),
                      gct_applicable=int(self.t_gct.isChecked()),
                      is_case=int(self.t_case.isChecked()),
                      case_qty=self.f_case_qty.value() if self.t_case.isChecked() else None)
        aliases = [a.strip() for a in self.f_alias[1].text().split(",") if a.strip()]
        try:
            if self._editing_product_id:
                update_product(self._editing_product_id, **kwargs)
                set_aliases(self._editing_product_id, aliases)
                QMessageBox.information(self, "Saved", f"'{name}' updated.")
            else:
                pid = add_product(**kwargs)
                if aliases: set_aliases(pid, aliases)
                QMessageBox.information(self, "Added", f"'{name}' added.")
                self._new_product_form()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
        self._load_products(self.product_search.text())

    def _delete_product(self, pid: int):
        p = get_product_by_id(pid)
        if not p: return
        reply = QMessageBox.question(self, "Delete", f"Delete '{p['name']}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            delete_product(pid); self._load_products(self.product_search.text())

    def _calc_selling_price(self):
        try:    cost = float(self.f_cost[1].text() or 0)
        except: return
        gid = self.f_group.currentData()
        price = self._get_selling_price(cost, gid)
        self.f_price.setText(f"${price:.2f}")
        m = self._group_markup(gid)
        self.f_price_hint.setText(f"= ${cost:.2f} × (1 + {m*100:.0f}%) = ${price:.2f}" if m and cost else "")

    def _get_selling_price(self, cost, group_id):
        m = self._group_markup(group_id)
        return round(cost * (1 + m), 2) if m and cost else cost

    def _group_markup(self, group_id) -> float:
        if not group_id: return 0.0
        try:
            import sqlite3; from config import DB_PRODUCTS
            con = sqlite3.connect(DB_PRODUCTS)
            row = con.execute("SELECT profit_margin FROM groups WHERE id=?", (group_id,)).fetchone()
            con.close(); return float(row[0]) if row and row[0] else 0.0
        except: return 0.0

    def _on_case_toggled(self, state): self.case_box.setVisible(bool(state))

    def _populate_groups(self):
        self.f_group.clear(); self.f_group.addItem("— No Group —", None)
        for g in get_groups(): self.f_group.addItem(g["name"], g["id"])

    def _populate_discount_levels(self, combo):
        combo.clear(); combo.addItem("— None —", None)
        try:
            import sqlite3; from config import DB_PRODUCTS
            con = sqlite3.connect(DB_PRODUCTS)
            for r in con.execute("SELECT id,name,discount_percent,min_quantity FROM discount_levels ORDER BY min_quantity").fetchall():
                combo.addItem(f"{r[1]}  ({r[2]}% off, min qty {r[3]})", r[0])
            con.close()
        except: pass


    # ================================================================
    # REPORTS TAB
    # ================================================================

    def _build_reports_tab(self):
        w = QWidget(); w.setStyleSheet(f"background:{WARM_WHITE};")
        lay = QHBoxLayout(w); lay.setContentsMargins(8,8,8,8); lay.setSpacing(8)

        # Left: cashier list
        left = QFrame(); left.setFixedWidth(220)
        left.setStyleSheet(f"background:{WHITE};border-radius:10px;border:1px solid {BORDER};")
        ll = QVBoxLayout(left); ll.setContentsMargins(10,10,10,10); ll.setSpacing(8)
        ll.addWidget(self._section_lbl("Cashiers"))
        self.rpt_cashier_search = QLineEdit()
        self.rpt_cashier_search.setPlaceholderText("🔍  Search cashier…")
        self.rpt_cashier_search.setFixedHeight(30)
        self.rpt_cashier_search.setStyleSheet(self._input_style())
        self.rpt_cashier_search.textChanged.connect(self._rpt_filter_cashiers)
        ll.addWidget(self.rpt_cashier_search)
        self.rpt_cashier_list = QTableWidget(); self.rpt_cashier_list.setColumnCount(1)
        self.rpt_cashier_list.setHorizontalHeaderLabels(["Name"])
        self.rpt_cashier_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.rpt_cashier_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.rpt_cashier_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.rpt_cashier_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.rpt_cashier_list.verticalHeader().setVisible(False)
        self.rpt_cashier_list.setShowGrid(False)
        self.rpt_cashier_list.setStyleSheet(self._table_style())
        self.rpt_cashier_list.selectionModel().selectionChanged.connect(self._rpt_on_cashier_selected)
        ll.addWidget(self.rpt_cashier_list, stretch=1)

        # Right panel
        right = QFrame()
        right.setStyleSheet(f"background:{WHITE};border-radius:10px;border:1px solid {BORDER};")
        rl = QVBoxLayout(right); rl.setContentsMargins(12,12,12,12); rl.setSpacing(10)

        # Summary cards
        cards = QHBoxLayout(); cards.setSpacing(8)
        self.rpt_cards = {}
        for key, label, color in [
            ("total_sales","TOTAL SALES",AMBER),("total_gct","TOTAL GCT",AMBER_DARK),
            ("transactions","TRANSACTIONS",BLUE),("discounts","DISCOUNTS",GREEN),
        ]:
            card = QFrame()
            card.setStyleSheet(f"background:{WARM_WHITE};border-radius:8px;border:1px solid {BORDER};")
            cl = QVBoxLayout(card); cl.setContentsMargins(12,8,12,8); cl.setSpacing(2)
            t = QLabel(label); t.setStyleSheet(f"color:{LABEL_TEXT};font-size:10px;font-weight:700;")
            v = QLabel("—"); v.setStyleSheet(f"color:{color};font-size:20px;font-weight:700;")
            cl.addWidget(t); cl.addWidget(v); self.rpt_cards[key] = v; cards.addWidget(card)
        rl.addLayout(cards)

        # Action bar
        sb = QHBoxLayout(); sb.setSpacing(8)
        self.rpt_session_header = QLabel("Select a cashier")
        self.rpt_session_header.setStyleSheet(f"color:{LABEL_TEXT};font-size:12px;font-weight:600;")
        self.rpt_search_bar = QLineEdit()
        self.rpt_search_bar.setPlaceholderText("🔍  Date or session #…")
        self.rpt_search_bar.setFixedHeight(28); self.rpt_search_bar.setFixedWidth(160)
        self.rpt_search_bar.setStyleSheet(self._input_style())
        self.rpt_search_bar.textChanged.connect(self._rpt_filter_sessions)
        self.rpt_refresh_btn = self._outline_btn("↻  Refresh"); self.rpt_refresh_btn.clicked.connect(self._rpt_refresh)
        self.rpt_close_btn   = self._danger_btn("Close Session"); self.rpt_close_btn.setEnabled(False); self.rpt_close_btn.clicked.connect(self._rpt_close_session)
        self.rpt_open_btn    = self._success_btn("Open New Session"); self.rpt_open_btn.setEnabled(False); self.rpt_open_btn.clicked.connect(self._rpt_open_session)
        self.rpt_print_btn   = self._outline_btn("🖨  Print Summary"); self.rpt_print_btn.setEnabled(False); self.rpt_print_btn.clicked.connect(self._rpt_print_session)
        sb.addWidget(self.rpt_session_header); sb.addStretch()
        for w_ in [self.rpt_search_bar,self.rpt_refresh_btn,self.rpt_close_btn,self.rpt_open_btn,self.rpt_print_btn]:
            sb.addWidget(w_)
        rl.addLayout(sb)

        self.rpt_session_list = QTableWidget(); self.rpt_session_list.setColumnCount(5)
        self.rpt_session_list.setHorizontalHeaderLabels(["Session","Status","Opened","Closed","Sales"])
        hh = self.rpt_session_list.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.rpt_session_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.rpt_session_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.rpt_session_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.rpt_session_list.verticalHeader().setVisible(False)
        self.rpt_session_list.setShowGrid(False)
        self.rpt_session_list.setStyleSheet(self._table_style())
        self.rpt_session_list.selectionModel().selectionChanged.connect(self._rpt_on_session_selected)
        rl.addWidget(self.rpt_session_list, stretch=1)

        lay.addWidget(left); lay.addWidget(right, stretch=1)
        self._rpt_all_cashiers=[]; self._rpt_all_sessions=[]; self._rpt_selected_cashier_id=None; self._rpt_selected_session_id=None
        self._rpt_load_cashiers()
        return w

    def _rpt_load_cashiers(self):
        self._rpt_all_cashiers = get_users(role="cashier")
        self._rpt_fill_cashier_list(self._rpt_all_cashiers)

    def _rpt_fill_cashier_list(self, cashiers):
        self.rpt_cashier_list.setRowCount(0)
        for i, c in enumerate(cashiers):
            self.rpt_cashier_list.insertRow(i); self.rpt_cashier_list.setRowHeight(i, 34)
            item = QTableWidgetItem(c["full_name"]); item.setData(Qt.ItemDataRole.UserRole, c["id"])
            item.setForeground(QColor(DARK_CARD)); self.rpt_cashier_list.setItem(i, 0, item)

    def _rpt_filter_cashiers(self, text):
        f = [c for c in self._rpt_all_cashiers if text.lower() in c["full_name"].lower()] if text else self._rpt_all_cashiers
        self._rpt_fill_cashier_list(f)

    def _rpt_on_cashier_selected(self):
        row = self.rpt_cashier_list.currentRow()
        if row < 0: return
        item = self.rpt_cashier_list.item(row, 0)
        if not item: return
        self._rpt_selected_cashier_id = item.data(Qt.ItemDataRole.UserRole)
        self.rpt_session_header.setText(f"Sessions — {item.text()}")
        self.rpt_open_btn.setEnabled(True)
        self._rpt_load_sessions(self._rpt_selected_cashier_id)

    def _rpt_load_sessions(self, user_id):
        sessions = get_sessions(user_id=user_id)
        # Enrich each session with live totals from receipts DB
        for s in sessions:
            st = session_totals(s["id"])
            s["_sales"]   = st.get("total_sales", 0) or 0
            s["_gct"]     = st.get("total_gct", 0) or 0
            s["_txns"]    = st.get("transaction_count", 0) or 0
            s["_disc"]    = st.get("total_discount", 0) or 0
        self._rpt_all_sessions = sessions
        self._rpt_fill_session_list(sessions)
        # Summary cards — totals across ALL sessions for this cashier
        total_sales  = sum(s["_sales"] for s in sessions)
        total_gct    = sum(s["_gct"]   for s in sessions)
        total_txns   = sum(s["_txns"]  for s in sessions)
        total_disc   = sum(s["_disc"]  for s in sessions)
        self.rpt_cards["total_sales"].setText(f"${total_sales:.2f}")
        self.rpt_cards["total_gct"].setText(f"${total_gct:.2f}")
        self.rpt_cards["transactions"].setText(str(total_txns))
        self.rpt_cards["discounts"].setText(f"${total_disc:.2f}")

    def _rpt_fill_session_list(self, sessions):
        self.rpt_session_list.setRowCount(0)
        R = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        for i, s in enumerate(sessions):
            self.rpt_session_list.insertRow(i); self.rpt_session_list.setRowHeight(i, 34)
            num = QTableWidgetItem(f"#{s['id']:04d}"); num.setData(Qt.ItemDataRole.UserRole, s["id"])
            num.setForeground(QColor(DARK_CARD))
            stat = QTableWidgetItem(s["status"].capitalize())
            stat.setForeground(QColor(GREEN if s["status"]=="open" else MUTED))
            opened = QTableWidgetItem(str(s["opened_at"])[:16])
            opened.setForeground(QColor(DARK_CARD))
            closed = QTableWidgetItem(str(s["closed_at"])[:16] if s["closed_at"] else "—")
            closed.setForeground(QColor(DARK_CARD))
            # Use live sales from enriched key, fallback to stored value
            live_sales = s.get("_sales", s.get("total_sales", 0))
            txns = s.get("_txns", 0)
            sales = QTableWidgetItem(f"${live_sales:.2f}  ({txns} txns)")
            sales.setForeground(QColor(AMBER)); sales.setTextAlignment(R)
            for col, it in enumerate([num, stat, opened, closed, sales]):
                self.rpt_session_list.setItem(i, col, it)

    def _rpt_filter_sessions(self, text):
        f = [s for s in self._rpt_all_sessions if text.lower() in str(s["id"]) or text in str(s.get("opened_at",""))] if text else self._rpt_all_sessions
        self._rpt_fill_session_list(f)

    def _rpt_on_session_selected(self):
        row = self.rpt_session_list.currentRow()
        if row < 0: return
        item = self.rpt_session_list.item(row, 0)
        if not item: return
        self._rpt_selected_session_id = item.data(Qt.ItemDataRole.UserRole)
        stat = self.rpt_session_list.item(row, 1)
        self.rpt_close_btn.setEnabled(bool(stat and stat.text().lower()=="open"))
        self.rpt_print_btn.setEnabled(True)

    def _rpt_refresh(self):
        if self._rpt_selected_cashier_id: self._rpt_load_sessions(self._rpt_selected_cashier_id)

    def _rpt_close_session(self):
        if not self._rpt_selected_session_id: return
        reply = QMessageBox.question(self, "Close Session", "Close this cashier session?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            # Pass real sales total from receipts
            st = session_totals(self._rpt_selected_session_id)
            close_session(self._rpt_selected_session_id, st.get("total_sales", 0))
            self._rpt_refresh()

    def _rpt_open_session(self):
        if not self._rpt_selected_cashier_id: return
        open_session(self._rpt_selected_cashier_id); self._rpt_refresh()

    def _rpt_print_session(self):
        QMessageBox.information(self, "Print", "Print session summary — printer integration coming.")

    # ================================================================
    # TRANSACTIONS TAB
    # ================================================================

    def _build_transactions_tab(self):
        w = QWidget(); w.setStyleSheet(f"background:{WARM_WHITE};")
        lay = QVBoxLayout(w); lay.setContentsMargins(8,8,8,8); lay.setSpacing(8)
        sr = QHBoxLayout(); sr.setSpacing(8)
        self.tx_search = QLineEdit()
        self.tx_search.setPlaceholderText("🔍  Search by receipt #, cashier, date (YYYY-MM-DD)…")
        self.tx_search.setFixedHeight(34); self.tx_search.setStyleSheet(self._input_style())
        self.tx_search.returnPressed.connect(self._tx_search_fn)
        self.tx_status_filter = QComboBox()
        self.tx_status_filter.addItems(["All Statuses","Completed","Voided","Refunded"])
        self.tx_status_filter.setFixedHeight(34); self.tx_status_filter.setStyleSheet(self._combo_style())
        search_btn = QPushButton("Search"); search_btn.setFixedHeight(34)
        search_btn.setStyleSheet(self._accent_btn()); search_btn.clicked.connect(self._tx_search_fn)
        refresh_btn = self._outline_btn("↻  Refresh"); refresh_btn.clicked.connect(self._tx_search_fn)
        self.tx_reprint_btn = self._outline_btn("🖨  Reprint")
        self.tx_reprint_btn.setEnabled(False); self.tx_reprint_btn.clicked.connect(self._tx_reprint)
        sr.addWidget(self.tx_search, stretch=1)
        sr.addWidget(self.tx_status_filter); sr.addWidget(search_btn)
        sr.addWidget(refresh_btn); sr.addWidget(self.tx_reprint_btn)
        lay.addLayout(sr)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(f"QSplitter::handle{{background:{BORDER};width:1px;}}")
        left = QFrame(); left.setStyleSheet(f"background:{WHITE};border-radius:8px;border:1px solid {BORDER};")
        ll = QVBoxLayout(left); ll.setContentsMargins(0,0,0,0)
        self.tx_table = QTableWidget(); self.tx_table.setColumnCount(6)
        self.tx_table.setHorizontalHeaderLabels(["Receipt #","Cashier","Date","Time","Total","Status"])
        hh = self.tx_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in [2,3,4,5]: hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.tx_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tx_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tx_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tx_table.verticalHeader().setVisible(False); self.tx_table.setShowGrid(False)
        self.tx_table.setStyleSheet(self._table_style())
        self.tx_table.itemClicked.connect(self._tx_on_row_selected_by_item)
        ll.addWidget(self.tx_table)
        right = QFrame(); right.setFixedWidth(280)
        right.setStyleSheet(f"background:{WHITE};border-radius:8px;border:1px solid {BORDER};")
        rl = QVBoxLayout(right); rl.setContentsMargins(12,12,12,12); rl.setSpacing(8)
        self.tx_detail_title = QLabel("Select a transaction")
        self.tx_detail_title.setStyleSheet(f"color:{DARK_CARD};font-size:12px;font-weight:700;")
        self.tx_detail_meta = QLabel(""); self.tx_detail_meta.setStyleSheet(f"color:{LABEL_TEXT};font-size:11px;"); self.tx_detail_meta.setWordWrap(True)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine); sep.setStyleSheet(f"color:{BORDER};")
        self.tx_items_table = QTableWidget(); self.tx_items_table.setColumnCount(4)
        self.tx_items_table.setHorizontalHeaderLabels(["Item","Qty","Price","Total"])
        hh2 = self.tx_items_table.horizontalHeader(); hh2.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in [1,2,3]: hh2.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.tx_items_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tx_items_table.verticalHeader().setVisible(False); self.tx_items_table.setShowGrid(False)
        self.tx_items_table.setStyleSheet(self._table_style())
        self.tx_footer = QLabel(""); self.tx_footer.setStyleSheet(f"color:{LABEL_TEXT};font-size:11px;")
        self.tx_footer.setAlignment(Qt.AlignmentFlag.AlignRight); self.tx_footer.setWordWrap(True)
        rl.addWidget(self.tx_detail_title); rl.addWidget(self.tx_detail_meta)
        rl.addWidget(sep); rl.addWidget(self.tx_items_table, stretch=1); rl.addWidget(self.tx_footer)
        splitter.addWidget(left); splitter.addWidget(right); splitter.setStretchFactor(0,1)
        lay.addWidget(splitter, stretch=1)
        self._tx_load(); return w

    def _tx_load(self, search="", status_filter=""):
        sf = status_filter.lower() if status_filter and status_filter != "All Statuses" else None
        receipts = get_receipts(search=search, status=sf, limit=200)
        self.tx_table.setRowCount(0)
        R = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        C = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter
        sc_map = {"completed":GREEN,"voided":RED,"refunded":AMBER_DARK}
        for i, r in enumerate(receipts):
            self.tx_table.insertRow(i); self.tx_table.setRowHeight(i, 34)
            num = QTableWidgetItem(r["receipt_number"]); num.setData(Qt.ItemDataRole.UserRole, r["id"])
            u = get_user_by_id(r["user_id"]); cname = u["full_name"] if u else f"#{r['user_id']}"
            dt = str(r["created_at"])
            self.tx_table.setItem(i, 0, num)
            self.tx_table.setItem(i, 1, QTableWidgetItem(cname))
            self.tx_table.setItem(i, 2, QTableWidgetItem(dt[:10]))
            self.tx_table.setItem(i, 3, QTableWidgetItem(dt[11:19]))
            tot = QTableWidgetItem(f"${r['total']:.2f}"); tot.setForeground(QColor(AMBER)); tot.setTextAlignment(R)
            self.tx_table.setItem(i, 4, tot)
            sc = sc_map.get(r["status"], MUTED)
            stat = QTableWidgetItem(r["status"].capitalize()); stat.setForeground(QColor(sc)); stat.setTextAlignment(C)
            self.tx_table.setItem(i, 5, stat)

    def _tx_search_fn(self):
        self._tx_load(search=self.tx_search.text().strip(), status_filter=self.tx_status_filter.currentText())

    def _tx_on_row_selected_by_item(self, clicked_item):
        """Called when user clicks any cell — route to main handler."""
        self._tx_on_row_selected()

    def _tx_on_row_selected(self):
        row = self.tx_table.currentRow(); item = self.tx_table.item(row, 0)
        if not item: return
        receipt = get_receipt_by_id(item.data(Qt.ItemDataRole.UserRole))
        if not receipt: return
        u = get_user_by_id(receipt["user_id"]); cname = u["full_name"] if u else "—"
        self.tx_detail_title.setText(f"Receipt {receipt['receipt_number']}")
        self.tx_detail_meta.setText(f"Cashier: {cname}\nDate: {str(receipt['created_at'])[:16]}\nStatus: {receipt['status'].capitalize()}")
        items = receipt.get("items", [])
        self.tx_items_table.setRowCount(len(items))
        R = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        for r, it in enumerate(items):
            self.tx_items_table.setItem(r, 0, QTableWidgetItem(it["product_name"]))
            qi = QTableWidgetItem(str(it["quantity"])); qi.setTextAlignment(Qt.AlignmentFlag.AlignCenter); self.tx_items_table.setItem(r, 1, qi)
            pi = QTableWidgetItem(f"${it['unit_price']:.2f}"); pi.setTextAlignment(R); self.tx_items_table.setItem(r, 2, pi)
            ti = QTableWidgetItem(f"${it['line_total']:.2f}"); ti.setForeground(QColor(GREEN)); ti.setTextAlignment(R); self.tx_items_table.setItem(r, 3, ti)
        self.tx_footer.setText(f"Subtotal: ${receipt['subtotal']:.2f}  |  GCT: ${receipt['gct_amount']:.2f}  |  <b>Total: ${receipt['total']:.2f}</b>")
        self.tx_footer.setTextFormat(Qt.TextFormat.RichText)
        self.tx_reprint_btn.setEnabled(True)

    def _tx_reprint(self):
        row = self.tx_table.currentRow(); item = self.tx_table.item(row, 0)
        if not item: return
        QMessageBox.information(self, "Reprint", f"Reprinting {item.text()}…\n(Printer integration coming)")

    # ================================================================
    # VOID / REFUND TAB
    # ================================================================

    def _build_void_tab(self):
        w = QWidget(); w.setStyleSheet(f"background:{WARM_WHITE};")
        lay = QVBoxLayout(w); lay.setContentsMargins(8,8,8,8); lay.setSpacing(8)
        sr = QHBoxLayout(); sr.setSpacing(8)
        self.vr_search = QLineEdit()
        self.vr_search.setPlaceholderText("🔍  Search by receipt #, cashier, or date (YYYY-MM-DD)…")
        self.vr_search.setFixedHeight(34); self.vr_search.setStyleSheet(self._input_style())
        self.vr_search.returnPressed.connect(self._vr_search_fn)
        self.vr_status_filter = QComboBox()
        self.vr_status_filter.addItems(["Completed Only","All Statuses"])
        self.vr_status_filter.setFixedHeight(34); self.vr_status_filter.setStyleSheet(self._combo_style())
        search_btn = QPushButton("Search"); search_btn.setFixedHeight(34)
        search_btn.setStyleSheet(self._accent_btn()); search_btn.clicked.connect(self._vr_search_fn)
        refresh_btn = self._outline_btn("↻  Refresh"); refresh_btn.clicked.connect(self._vr_search_fn)
        sr.addWidget(self.vr_search, stretch=1); sr.addWidget(self.vr_status_filter)
        sr.addWidget(search_btn); sr.addWidget(refresh_btn)
        lay.addLayout(sr)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(f"QSplitter::handle{{background:{BORDER};width:1px;}}")
        left = QFrame(); left.setStyleSheet(f"background:{WHITE};border-radius:8px;border:1px solid {BORDER};")
        ll = QVBoxLayout(left); ll.setContentsMargins(0,0,0,0)
        self.vr_table = QTableWidget(); self.vr_table.setColumnCount(6)
        self.vr_table.setHorizontalHeaderLabels(["Receipt #","Cashier","Date","Time","Total","Status"])
        hh = self.vr_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in [2,3,4,5]: hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.vr_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.vr_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.vr_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.vr_table.verticalHeader().setVisible(False); self.vr_table.setShowGrid(False)
        self.vr_table.setStyleSheet(self._table_style())
        self.vr_table.itemClicked.connect(lambda _: self._vr_on_row_selected())
        ll.addWidget(self.vr_table)
        right = QFrame(); right.setFixedWidth(300)
        right.setStyleSheet(f"background:{WHITE};border-radius:8px;border:1px solid {BORDER};")
        rl = QVBoxLayout(right); rl.setContentsMargins(14,14,14,14); rl.setSpacing(10)
        self.vr_receipt_title = QLabel("Select a receipt")
        self.vr_receipt_title.setStyleSheet(f"color:{DARK_CARD};font-size:13px;font-weight:700;")
        self.vr_receipt_meta = QLabel(""); self.vr_receipt_meta.setStyleSheet(f"color:{LABEL_TEXT};font-size:11px;"); self.vr_receipt_meta.setWordWrap(True)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine); sep.setStyleSheet(f"color:{BORDER};")
        self.vr_items_table = QTableWidget(); self.vr_items_table.setColumnCount(5)
        self.vr_items_table.setHorizontalHeaderLabels(["✓","Item","Qty","Price","Total"])
        hh2 = self.vr_items_table.horizontalHeader()
        hh2.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh2.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in [2,3,4]: hh2.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.vr_items_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.vr_items_table.verticalHeader().setVisible(False); self.vr_items_table.setShowGrid(False)
        self.vr_items_table.setStyleSheet(self._table_style())
        self.vr_totals = QLabel(""); self.vr_totals.setStyleSheet(f"color:{LABEL_TEXT};font-size:11px;")
        self.vr_totals.setAlignment(Qt.AlignmentFlag.AlignRight); self.vr_totals.setWordWrap(True)
        rl.addWidget(self.vr_receipt_title); rl.addWidget(self.vr_receipt_meta)
        rl.addWidget(sep); rl.addWidget(self.vr_items_table, stretch=1); rl.addWidget(self.vr_totals)
        rl.addWidget(self._flabel("Refund Mode"))
        self.vr_refund_mode = QComboBox(); self.vr_refund_mode.addItems(["Full Refund","Partial Refund"])
        self.vr_refund_mode.setStyleSheet(self._combo_style())
        self.vr_refund_mode.currentIndexChanged.connect(self._vr_on_mode_changed); rl.addWidget(self.vr_refund_mode)
        rl.addWidget(self._flabel("Reason (required)"))
        self.vr_reason = QLineEdit(); self.vr_reason.setPlaceholderText("Enter reason…")
        self.vr_reason.setFixedHeight(32); self.vr_reason.setStyleSheet(self._input_style())
        self.vr_reason.textChanged.connect(self._vr_update_buttons); rl.addWidget(self.vr_reason)
        self.vr_selected_amount = QLabel(""); self.vr_selected_amount.setStyleSheet(f"color:{AMBER};font-size:11px;font-weight:600;"); rl.addWidget(self.vr_selected_amount)
        self.vr_status_banner = QLabel(""); self.vr_status_banner.setVisible(False); self.vr_status_banner.setWordWrap(True); rl.addWidget(self.vr_status_banner)
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        self.vr_void_btn = self._danger_btn("↩  Void Transaction"); self.vr_void_btn.setEnabled(False); self.vr_void_btn.clicked.connect(self._vr_do_void)
        self.vr_refund_btn = QPushButton("↩  Issue Refund"); self.vr_refund_btn.setFixedHeight(32)
        self.vr_refund_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.vr_refund_btn.setStyleSheet(f"QPushButton{{background:{AMBER};color:white;border:none;border-radius:16px;font-size:11px;font-weight:600;padding:0 14px;}}QPushButton:hover{{background:{AMBER_DARK};}}QPushButton:disabled{{background:{MUTED};}}")
        self.vr_refund_btn.setEnabled(False); self.vr_refund_btn.clicked.connect(self._vr_do_refund)
        btn_row.addWidget(self.vr_void_btn); btn_row.addWidget(self.vr_refund_btn); rl.addLayout(btn_row)
        splitter.addWidget(left); splitter.addWidget(right); splitter.setStretchFactor(0,1)
        lay.addWidget(splitter, stretch=1)
        self._vr_selected_tx_id=None; self._vr_selected_tx_status=None; self._vr_items_data=[]
        self._vr_load(); return w

    def _vr_load(self, search="", status_filter="completed"):
        sf = None if status_filter == "" else status_filter
        receipts = get_receipts(search=search, status=sf, limit=200)
        self.vr_table.setRowCount(0)
        R = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        C = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter
        sc_map = {"completed":GREEN,"voided":RED,"refunded":AMBER_DARK}
        for i, r in enumerate(receipts):
            self.vr_table.insertRow(i); self.vr_table.setRowHeight(i, 34)
            num = QTableWidgetItem(r["receipt_number"]); num.setData(Qt.ItemDataRole.UserRole, r["id"])
            u = get_user_by_id(r["user_id"]); cname = u["full_name"] if u else "—"
            dt = str(r["created_at"])
            self.vr_table.setItem(i, 0, num); self.vr_table.setItem(i, 1, QTableWidgetItem(cname))
            self.vr_table.setItem(i, 2, QTableWidgetItem(dt[:10])); self.vr_table.setItem(i, 3, QTableWidgetItem(dt[11:19]))
            tot = QTableWidgetItem(f"${r['total']:.2f}"); tot.setForeground(QColor(AMBER)); tot.setTextAlignment(R); self.vr_table.setItem(i, 4, tot)
            sc = sc_map.get(r["status"], MUTED); stat = QTableWidgetItem(r["status"].capitalize()); stat.setForeground(QColor(sc)); stat.setTextAlignment(C); self.vr_table.setItem(i, 5, stat)

    def _vr_search_fn(self):
        sf = "completed" if self.vr_status_filter.currentIndex()==0 else ""
        self._vr_load(search=self.vr_search.text().strip(), status_filter=sf)

    def _vr_on_row_selected(self):
        row = self.vr_table.currentRow(); item = self.vr_table.item(row, 0)
        if not item: return
        receipt = get_receipt_by_id(item.data(Qt.ItemDataRole.UserRole))
        if not receipt: return
        self._vr_selected_tx_id=receipt["id"]; self._vr_selected_tx_status=receipt["status"]; self._vr_items_data=receipt.get("items",[])
        u = get_user_by_id(receipt["user_id"]); cname = u["full_name"] if u else "—"
        self.vr_receipt_title.setText(f"Receipt {receipt['receipt_number']}")
        self.vr_receipt_meta.setText(f"Cashier: {cname}\nDate: {str(receipt['created_at'])[:16]}\nStatus: {receipt['status'].capitalize()}")
        is_partial = self.vr_refund_mode.currentIndex()==1
        self.vr_items_table.setRowCount(len(self._vr_items_data))
        R = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        for r, it in enumerate(self._vr_items_data):
            chk_w = QWidget(); chk_l = QHBoxLayout(chk_w); chk_l.setContentsMargins(4,0,4,0); chk_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk = QCheckBox(); chk.setChecked(True); chk.setEnabled(is_partial); chk.stateChanged.connect(self._vr_update_selected_amount)
            chk_l.addWidget(chk); self.vr_items_table.setCellWidget(r, 0, chk_w)
            self.vr_items_table.setItem(r, 1, QTableWidgetItem(it["product_name"]))
            qi = QTableWidgetItem(str(it["quantity"])); qi.setTextAlignment(Qt.AlignmentFlag.AlignCenter); self.vr_items_table.setItem(r, 2, qi)
            pi = QTableWidgetItem(f"${it['unit_price']:.2f}"); pi.setTextAlignment(R); self.vr_items_table.setItem(r, 3, pi)
            ti = QTableWidgetItem(f"${it['line_total']:.2f}"); ti.setForeground(QColor(GREEN)); ti.setTextAlignment(R); self.vr_items_table.setItem(r, 4, ti)
        self.vr_totals.setText(f"Subtotal: ${receipt['subtotal']:.2f}  |  GCT: ${receipt['gct_amount']:.2f}  |  <b>Total: ${receipt['total']:.2f}</b>")
        self.vr_totals.setTextFormat(Qt.TextFormat.RichText)
        self.vr_status_banner.setVisible(False); self.vr_reason.clear(); self._vr_update_buttons()

    def _vr_on_mode_changed(self):
        is_partial = self.vr_refund_mode.currentIndex()==1
        for r in range(self.vr_items_table.rowCount()):
            w = self.vr_items_table.cellWidget(r, 0)
            if w:
                chk = w.findChild(QCheckBox)
                if chk: chk.setEnabled(is_partial)
        self._vr_update_selected_amount()

    def _vr_update_selected_amount(self):
        if not self._vr_items_data or self.vr_refund_mode.currentIndex()==0:
            self.vr_selected_amount.setText(""); return
        total = sum(it["line_total"] for r, it in enumerate(self._vr_items_data) if (lambda w: w and w.findChild(QCheckBox) and w.findChild(QCheckBox).isChecked())(self.vr_items_table.cellWidget(r, 0)))
        self.vr_selected_amount.setText(f"Selected refund: ${total:.2f}")

    def _vr_update_buttons(self):
        ok = self._vr_selected_tx_id is not None and self._vr_selected_tx_status=="completed" and bool(self.vr_reason.text().strip())
        self.vr_void_btn.setEnabled(ok); self.vr_refund_btn.setEnabled(ok)

    def _vr_do_void(self):
        reason = self.vr_reason.text().strip()
        if not reason: QMessageBox.warning(self, "Reason Required", "Please enter a reason."); return
        reply = QMessageBox.question(self, "Confirm Void", f"Void receipt #{self._vr_selected_tx_id}?\nReason: {reason}\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes: return
        if void_receipt(self._vr_selected_tx_id, self.user["id"], reason):
            self._vr_selected_tx_status="voided"; self.vr_void_btn.setEnabled(False); self.vr_refund_btn.setEnabled(False)
            self.vr_status_banner.setText(f"✓  Receipt #{self._vr_selected_tx_id} voided."); self.vr_status_banner.setStyleSheet(f"color:{RED};font-size:12px;font-weight:600;"); self.vr_status_banner.setVisible(True)
            self._vr_search_fn()
        else: QMessageBox.critical(self, "Failed", "Could not void this receipt.")

    def _vr_do_refund(self):
        reason = self.vr_reason.text().strip()
        if not reason: QMessageBox.warning(self, "Reason Required", "Please enter a reason."); return
        is_partial = self.vr_refund_mode.currentIndex()==1
        items = []
        for r, it in enumerate(self._vr_items_data):
            w = self.vr_items_table.cellWidget(r, 0)
            chk = w.findChild(QCheckBox) if w else None
            if not is_partial or (chk and chk.isChecked()): items.append(it)
        if not items: QMessageBox.warning(self, "No Items", "Select at least one item."); return
        amount = sum(it["line_total"] for it in items)
        mode = "Partial" if is_partial else "Full"
        reply = QMessageBox.question(self, f"Confirm {mode} Refund", f"{mode} refund — ${amount:.2f}\nReason: {reason}\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes: return
        rtype = "partial" if is_partial else "full"
        if refund_receipt(self._vr_selected_tx_id, self.user["id"], reason, amount, rtype):
            self.vr_void_btn.setEnabled(False); self.vr_refund_btn.setEnabled(False)
            self.vr_status_banner.setText(f"✓  {mode} refund of ${amount:.2f} issued."); self.vr_status_banner.setStyleSheet(f"color:{AMBER};font-size:12px;font-weight:600;"); self.vr_status_banner.setVisible(True)
            self._vr_search_fn()
        else: QMessageBox.critical(self, "Failed", "Could not process refund.")

    # ================================================================
    # QUICK KEYS TAB
    # ================================================================

    def _build_quickkeys_tab(self):
        w = QWidget(); w.setStyleSheet(f"background:{WARM_WHITE};")
        lay = QVBoxLayout(w); lay.setContentsMargins(20,20,20,20); lay.setSpacing(10)
        hint = QLabel("Assign a product to each F-key (F1–F8). Start typing a product name to search.")
        hint.setStyleSheet(f"color:{LABEL_TEXT};font-size:12px;"); lay.addWidget(hint)
        self._qk_inputs = []
        for k in get_quick_keys():
            row = QHBoxLayout(); row.setSpacing(10)
            badge = QLabel(f"F{k['slot']}"); badge.setFixedSize(40,32); badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(f"background:{DARK_CARD};color:{AMBER};border-radius:6px;font-size:11px;font-weight:700;")
            inp = QLineEdit(); inp.setFixedHeight(34)
            inp.setPlaceholderText("Search products…")
            inp.setText(f"{k['product_name']} (${k['product_price']:.2f})" if k.get("product_name") else "")
            inp.setStyleSheet(self._input_style(accent=bool(k.get("product_name"))))
            inp.setProperty("slot", k["slot"]); inp.setProperty("product_id", k.get("product_id"))
            row.addWidget(badge); row.addWidget(inp, stretch=1)
            lay.addLayout(row); self._qk_inputs.append(inp)
        lay.addStretch()
        save_btn = QPushButton("💾  Save Quick Keys"); save_btn.setFixedHeight(42)
        save_btn.setStyleSheet(self._accent_btn()); save_btn.clicked.connect(self._qk_save); lay.addWidget(save_btn)
        return w

    def _qk_save(self):
        assignments = []
        for inp in self._qk_inputs:
            slot = inp.property("slot"); pid = inp.property("product_id"); text = inp.text().strip()
            if not pid and text:
                results = get_products(search=text, limit=1)
                if results: pid = results[0]["id"]; inp.setProperty("product_id", pid)
            if pid:
                p = get_product_by_id(pid)
                assignments.append({"slot":slot,"product_id":pid,"product_name":p["name"] if p else text,"product_price":p["selling_price"] if p else 0})
            else:
                assignments.append({"slot":slot,"product_id":None,"product_name":None,"product_price":None})
        save_quick_keys(assignments)
        QMessageBox.information(self, "Saved", "Quick keys saved successfully.")

    # ================================================================
    # CLOCK + LOGOUT
    # ================================================================

    def _start_clock(self):
        t = QTimer(self); t.timeout.connect(self._tick); t.start(1000); self._tick()

    def _tick(self):
        n = QDateTime.currentDateTime()
        self._clock.setText(n.toString("dd MMM yyyy") + "   " + n.toString("hh:mm:ss AP"))

    def _handle_logout(self):
        reply = QMessageBox.question(self, "Logout", "Are you sure you want to logout?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.logout_requested.emit(); self.force_close()

    # ================================================================
    # STYLE HELPERS
    # ================================================================

    def _table_style(self):
        return f"""
            QTableWidget{{background:{WHITE};border:none;font-size:12px;color:{DARK_CARD};}}
            QTableWidget::item{{padding:6px 8px;border-bottom:1px solid {BORDER_LIGHT};}}
            QTableWidget::item:selected{{background:{AMBER_BG};color:{DARK_CARD};}}
            QHeaderView::section{{background:{DARK};color:{AMBER};font-size:11px;
            font-weight:700;padding:6px 8px;border:none;border-right:1px solid {DARK_4};}}
            QScrollBar:vertical{{background:{WARM_WHITE};width:6px;border-radius:3px;}}
            QScrollBar::handle:vertical{{background:{BORDER};border-radius:3px;}}
        """

    def _input_style(self, accent=False):
        b = AMBER if accent else BORDER
        return (
            f"QLineEdit{{background:{WHITE};color:{DARK_CARD};border:1px solid {b};"
            f"border-radius:7px;padding:0 10px;font-size:12px;font-weight:400;}}"
            f"QLineEdit:focus{{border-color:{AMBER};background:#fffef9;}}"
            f"QLineEdit::placeholder{{color:{MUTED};}}"
            f"QSpinBox{{background:{WHITE};color:{DARK_CARD};border:1px solid {b};"
            f"border-radius:7px;padding:0 8px;font-size:12px;}}"
            f"QSpinBox:focus{{border-color:{AMBER};}}"
        )

    def _combo_style(self):
        return (
            f"QComboBox{{background:{WHITE};color:{DARK_CARD};border:1px solid {BORDER};"
            f"border-radius:7px;padding:0 10px;font-size:12px;font-weight:400;}}"
            f"QComboBox:focus{{border-color:{AMBER};}}"
            f"QComboBox::drop-down{{border:none;width:20px;}}"
            f"QComboBox::down-arrow{{width:10px;height:10px;}}"
            f"QComboBox QAbstractItemView{{background:{WHITE};color:{DARK_CARD};"
            f"border:1px solid {BORDER};outline:none;"
            f"selection-background-color:{AMBER};selection-color:white;}}"
        )

    def _accent_btn(self):
        return f"QPushButton{{background:{AMBER};color:white;border:none;border-radius:17px;font-size:12px;font-weight:600;padding:0 16px;}}QPushButton:hover{{background:{AMBER_DARK};}}"

    def _outline_btn(self, text):
        b = QPushButton(text); b.setFixedHeight(32); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QPushButton{{background:transparent;color:{LABEL_TEXT};border:1.5px solid {BORDER};border-radius:16px;font-size:11px;font-weight:600;padding:0 14px;}}QPushButton:hover{{background:{WARM_WHITE};color:{DARK_CARD};}}QPushButton:disabled{{color:{MUTED};border-color:{BORDER_LIGHT};}}")
        return b

    def _danger_btn(self, text):
        b = QPushButton(text); b.setFixedHeight(32); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QPushButton{{background:{RED_LIGHT};color:{RED};border:none;border-radius:16px;font-size:11px;font-weight:600;padding:0 14px;}}QPushButton:hover{{background:{RED};color:white;}}QPushButton:disabled{{background:{WARM_WHITE};color:{MUTED};}}")
        return b

    def _success_btn(self, text):
        b = QPushButton(text); b.setFixedHeight(32); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QPushButton{{background:{GREEN_LIGHT};color:{GREEN};border:none;border-radius:16px;font-size:11px;font-weight:600;padding:0 14px;}}QPushButton:hover{{background:{GREEN};color:white;}}QPushButton:disabled{{background:{WARM_WHITE};color:{MUTED};}}")
        return b

    def _icon_btn(self, icon, tooltip=""):
        b = QPushButton(icon); b.setFixedSize(34,34); b.setToolTip(tooltip); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QPushButton{{background:{WARM_WHITE};color:{LABEL_TEXT};border:1px solid {BORDER};border-radius:17px;font-size:16px;font-weight:700;}}QPushButton:hover{{border-color:{AMBER};color:{AMBER};}}")
        return b

    def _field(self, label, placeholder):
        lbl = self._flabel(label)
        inp = QLineEdit(); inp.setPlaceholderText(placeholder); inp.setFixedHeight(34)
        inp.setStyleSheet(self._input_style()); return lbl, inp

    def _flabel(self, text):
        l = QLabel(text); l.setStyleSheet(f"color:{LABEL_TEXT};font-size:11px;font-weight:600;"); return l

    def _section_lbl(self, text):
        l = QLabel(text.upper()); l.setStyleSheet(f"color:{MUTED};font-size:10px;font-weight:700;letter-spacing:1px;"); return l

    def _toggle(self, label, checked=False):
        cb = QCheckBox(label); cb.setChecked(checked)
        cb.setStyleSheet(f"QCheckBox{{color:{DARK_CARD};font-size:12px;font-weight:500;}}QCheckBox::indicator{{width:16px;height:16px;border:1px solid {BORDER};border-radius:3px;background:{WHITE};}}QCheckBox::indicator:checked{{background:{AMBER};border-color:{AMBER};}}")
        return cb
