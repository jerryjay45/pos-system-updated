"""
ui/supervisor/void_refund_tab.py
Supervisor void/refund/exchange transaction management tab.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QDateEdit, QComboBox, QLabel, QTextEdit,
    QDialog, QDoubleSpinBox, QMessageBox, QFrame, QHeaderView,
    QAbstractItemView, QSplitter,
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QFont, QColor

from ui.shared.theme import (
    AMBER, AMBER_DARK, AMBER_LIGHTEST, DARK_CARD, DARK_2, DARK_4,
    WHITE, WARM_WHITE, BORDER, MUTED, LABEL_TEXT, MAIN_FONT,
    RED, RED_LIGHT, GREEN, GREEN_LIGHT,
)
from core.db_checkout import (
    get_receipts_with_refund_summary, get_receipt_by_id,
    void_receipt, refund_receipt, exchange_receipt,
    get_refunds_for_receipt, count_receipts,
)
from core.db_users import get_user_by_id, authenticate
from utils.print_manager import print_void, print_refund


# ── Helpers ───────────────────────────────────────────────────────────────────

def _section_lbl(text: str) -> QLabel:
    l = QLabel(text.upper())
    l.setStyleSheet(
        f"color:{MUTED};font-size:10px;font-weight:700;"
        f"letter-spacing:1px;background:transparent;"
    )
    return l

def _divider() -> QFrame:
    d = QFrame(); d.setFrameShape(QFrame.Shape.HLine)
    d.setStyleSheet(f"background:{BORDER};max-height:1px;border:none;")
    return d

def _field_style():
    return (
        f"QLineEdit,QTextEdit{{background:{WARM_WHITE};color:{DARK_CARD};"
        f"border:1px solid {BORDER};border-radius:8px;"
        f"padding:0 12px;font-size:13px;}}"
        f"QLineEdit:focus,QTextEdit:focus{{border-color:{AMBER};"
        f"background:{WHITE};}}"
    )

def _accent_btn_style():
    return (
        f"QPushButton{{background:{AMBER};color:white;border:none;"
        f"border-radius:8px;font-size:12px;font-weight:600;}}"
        f"QPushButton:hover{{background:{AMBER_DARK};}}"
        f"QPushButton:pressed{{background:#633806;}}"
    )

def _cancel_btn_style():
    return (
        f"QPushButton{{background:{DARK_4};color:white;border:none;"
        f"border-radius:8px;font-size:12px;font-weight:600;}}"
        f"QPushButton:hover{{background:#444;}}"
    )


# ── PasswordDialog ────────────────────────────────────────────────────────────

class PasswordDialog(QDialog):
    """Supervisor password confirmation."""

    def __init__(self, supervisor: dict, parent=None):
        super().__init__(parent)
        self.supervisor = supervisor
        self._verified  = False
        self.setWindowTitle("Confirm Identity")
        self.setModal(True)
        self.setFixedWidth(360)
        self.setStyleSheet(f"background:{WHITE};")
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        lay.addWidget(_section_lbl("Supervisor Authorisation"))
        title = QLabel("Confirm Your Identity")
        title.setStyleSheet(
            f"color:{DARK_CARD};font-size:14px;font-weight:700;"
        )
        lay.addWidget(title)

        msg = QLabel(
            f"Enter your password to proceed.\n"
            f"Authorising as: {self.supervisor.get('full_name','Unknown')}"
        )
        msg.setStyleSheet(f"color:{MUTED};font-size:11px;")
        msg.setWordWrap(True)
        lay.addWidget(msg)
        lay.addWidget(_divider())

        self.pw_input = QLineEdit()
        self.pw_input.setPlaceholderText("Password")
        self.pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw_input.setFixedHeight(40)
        self.pw_input.setStyleSheet(_field_style())
        self.pw_input.returnPressed.connect(self._verify)
        lay.addWidget(self.pw_input)

        err_row = QHBoxLayout()
        self._err_lbl = QLabel("")
        self._err_lbl.setStyleSheet(f"color:{RED};font-size:11px;")
        err_row.addWidget(self._err_lbl)
        lay.addLayout(err_row)

        btn_row = QHBoxLayout(); btn_row.setSpacing(10)
        cancel = QPushButton("Cancel"); cancel.setFixedHeight(38)
        cancel.setStyleSheet(_cancel_btn_style())
        cancel.clicked.connect(self.reject)
        verify = QPushButton("Verify & Proceed"); verify.setFixedHeight(38)
        verify.setStyleSheet(_accent_btn_style())
        verify.clicked.connect(self._verify)
        btn_row.addWidget(cancel); btn_row.addWidget(verify, stretch=1)
        lay.addLayout(btn_row)

    def _verify(self):
        pw = self.pw_input.text()
        if not pw:
            self._err_lbl.setText("Please enter your password.")
            return
        user = authenticate(self.supervisor["username"], pw)
        if user is None:
            self._err_lbl.setText("Incorrect password. Try again.")
            self.pw_input.clear(); self.pw_input.setFocus()
            return
        self._verified = True
        self.accept()

    def is_verified(self) -> bool:
        return self._verified


# ── VoidReasonDialog ──────────────────────────────────────────────────────────

class VoidReasonDialog(QDialog):
    """Styled reason entry for void actions."""

    def __init__(self, receipt: dict, parent=None):
        super().__init__(parent)
        self.receipt = receipt
        self.reason  = ""
        self.setWindowTitle("Void Receipt")
        self.setModal(True)
        self.setFixedWidth(400)
        self.setStyleSheet(f"background:{WHITE};")
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        lay.addWidget(_section_lbl("Void Transaction"))
        title = QLabel(f"Void {self.receipt['receipt_number']}")
        title.setStyleSheet(
            f"color:{RED};font-size:14px;font-weight:700;"
        )
        lay.addWidget(title)

        info = QLabel(
            f"Sale total: ${self.receipt['total']:.2f}  ·  "
            f"Date: {self.receipt['created_at'][:10]}"
        )
        info.setStyleSheet(f"color:{MUTED};font-size:11px;")
        lay.addWidget(info)
        lay.addWidget(_divider())

        lay.addWidget(QLabel("Reason for void:").setStyleSheet(
            f"color:{LABEL_TEXT};font-size:11px;font-weight:600;"
        ) or QLabel("Reason for void:"))
        self.reason_input = QTextEdit()
        self.reason_input.setPlaceholderText("Enter reason…")
        self.reason_input.setFixedHeight(80)
        self.reason_input.setStyleSheet(
            f"QTextEdit{{background:{WARM_WHITE};color:{DARK_CARD};"
            f"border:1px solid {BORDER};border-radius:8px;padding:8px;}}"
            f"QTextEdit:focus{{border-color:{AMBER};}}"
        )
        lay.addWidget(self.reason_input)

        self._err = QLabel("")
        self._err.setStyleSheet(f"color:{RED};font-size:11px;")
        lay.addWidget(self._err)

        btn_row = QHBoxLayout(); btn_row.setSpacing(10)
        cancel = QPushButton("Cancel"); cancel.setFixedHeight(38)
        cancel.setStyleSheet(_cancel_btn_style())
        cancel.clicked.connect(self.reject)
        confirm = QPushButton("⊘  Confirm Void"); confirm.setFixedHeight(38)
        confirm.setStyleSheet(
            f"QPushButton{{background:{RED};color:white;border:none;"
            f"border-radius:8px;font-size:12px;font-weight:600;}}"
            f"QPushButton:hover{{background:#7A1E1E;}}"
        )
        confirm.clicked.connect(self._accept)
        btn_row.addWidget(cancel); btn_row.addWidget(confirm, stretch=1)
        lay.addLayout(btn_row)

    def _accept(self):
        self.reason = self.reason_input.toPlainText().strip()
        if not self.reason:
            self._err.setText("A reason is required.")
            return
        self.accept()


# ── RefundDialog ──────────────────────────────────────────────────────────────

class RefundDialog(QDialog):
    """Full or partial refund dialog."""

    def __init__(self, receipt: dict, parent=None):
        super().__init__(parent)
        self.receipt       = receipt
        self.refund_amount = receipt["total"]
        self.refund_type   = "full"
        self.reason_text   = ""
        self.setWindowTitle("Process Refund")
        self.setModal(True)
        self.setFixedWidth(420)
        self.setStyleSheet(f"background:{WHITE};")
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        lay.addWidget(_section_lbl("Refund Transaction"))
        title = QLabel(f"Refund {self.receipt['receipt_number']}")
        title.setStyleSheet(
            f"color:{AMBER};font-size:14px;font-weight:700;"
        )
        lay.addWidget(title)
        lay.addWidget(_divider())

        # Refund type
        lay.addWidget(self._lbl("Refund Type"))
        self.type_combo = QComboBox()
        self.type_combo.setFixedHeight(36)
        self.type_combo.setStyleSheet(
            f"QComboBox{{background:{WARM_WHITE};color:{DARK_CARD};"
            f"border:1px solid {BORDER};border-radius:8px;padding:0 12px;}}"
            f"QComboBox:focus{{border-color:{AMBER};}}"
        )
        self.type_combo.addItems(["Full Refund", "Partial Refund"])
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        lay.addWidget(self.type_combo)

        # Full refund info (read-only)
        self.full_info = QLabel(
            f"Full refund amount: ${self.receipt['total']:.2f}"
        )
        self.full_info.setStyleSheet(
            f"color:{DARK_CARD};font-size:13px;font-weight:600;"
            f"background:{GREEN_LIGHT};border:1px solid {GREEN};"
            f"border-radius:8px;padding:10px 14px;"
        )
        lay.addWidget(self.full_info)

        # Partial amount input (hidden by default)
        self.amount_lbl = QLabel("Refund Amount")
        self.amount_lbl.setStyleSheet(f"color:{LABEL_TEXT};font-size:11px;font-weight:600;")
        self.amount_lbl.setVisible(False)
        self.amount_input = QDoubleSpinBox()
        self.amount_input.setMinimum(0.01)
        self.amount_input.setMaximum(self.receipt["total"])
        self.amount_input.setValue(self.receipt["total"])
        self.amount_input.setDecimals(2)
        self.amount_input.setPrefix("$ ")
        self.amount_input.setFixedHeight(40)
        self.amount_input.setVisible(False)
        self.amount_input.setStyleSheet(
            f"QDoubleSpinBox{{background:{WARM_WHITE};color:{DARK_CARD};"
            f"border:1px solid {BORDER};border-radius:8px;padding:0 12px;"
            f"font-size:13px;font-weight:600;}}"
            f"QDoubleSpinBox:focus{{border-color:{AMBER};}}"
        )
        lay.addWidget(self.amount_lbl)
        lay.addWidget(self.amount_input)

        # Reason
        lay.addWidget(self._lbl("Reason"))
        self.reason_input = QTextEdit()
        self.reason_input.setPlaceholderText("Enter reason for refund…")
        self.reason_input.setFixedHeight(75)
        self.reason_input.setStyleSheet(
            f"QTextEdit{{background:{WARM_WHITE};color:{DARK_CARD};"
            f"border:1px solid {BORDER};border-radius:8px;padding:8px;}}"
            f"QTextEdit:focus{{border-color:{AMBER};}}"
        )
        lay.addWidget(self.reason_input)

        self._err = QLabel("")
        self._err.setStyleSheet(f"color:{RED};font-size:11px;")
        lay.addWidget(self._err)

        btn_row = QHBoxLayout(); btn_row.setSpacing(10)
        cancel = QPushButton("Cancel"); cancel.setFixedHeight(38)
        cancel.setStyleSheet(_cancel_btn_style())
        cancel.clicked.connect(self.reject)
        confirm = QPushButton("↩  Confirm Refund"); confirm.setFixedHeight(38)
        confirm.setStyleSheet(_accent_btn_style())
        confirm.clicked.connect(self._accept)
        btn_row.addWidget(cancel); btn_row.addWidget(confirm, stretch=1)
        lay.addLayout(btn_row)

    def _lbl(self, text):
        l = QLabel(text)
        l.setStyleSheet(f"color:{LABEL_TEXT};font-size:11px;font-weight:600;")
        return l

    def _on_type_changed(self, text):
        is_partial = (text == "Partial Refund")
        self.full_info.setVisible(not is_partial)
        self.amount_lbl.setVisible(is_partial)
        self.amount_input.setVisible(is_partial)

    def _accept(self):
        self.reason_text  = self.reason_input.toPlainText().strip()
        if not self.reason_text:
            self._err.setText("A reason is required.")
            return
        self.refund_type   = "partial" if self.type_combo.currentText() == "Partial Refund" else "full"
        self.refund_amount = self.amount_input.value() if self.refund_type == "partial" else self.receipt["total"]
        self.accept()


# ── ExchangeDialog ────────────────────────────────────────────────────────────

class ExchangeDialog(QDialog):
    """Record an exchange against a receipt."""

    def __init__(self, receipt: dict, parent=None):
        super().__init__(parent)
        self.receipt      = receipt
        self.reason_text  = ""
        self.exchange_note = ""
        self.setWindowTitle("Process Exchange")
        self.setModal(True)
        self.setFixedWidth(440)
        self.setStyleSheet(f"background:{WHITE};")
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        lay.addWidget(_section_lbl("Exchange Transaction"))
        title = QLabel(f"Exchange — {self.receipt['receipt_number']}")
        title.setStyleSheet(
            f"color:{DARK_CARD};font-size:14px;font-weight:700;"
        )
        lay.addWidget(title)

        info = QLabel(
            f"Original total: ${self.receipt['total']:.2f}  ·  "
            f"Date: {self.receipt['created_at'][:10]}\n"
            f"An exchange records the transaction for audit purposes.\n"
            f"The receipt status remains Completed."
        )
        info.setStyleSheet(f"color:{MUTED};font-size:11px;")
        info.setWordWrap(True)
        lay.addWidget(info)
        lay.addWidget(_divider())

        # Reason
        lay.addWidget(self._lbl("Reason for Exchange"))
        self.reason_input = QTextEdit()
        self.reason_input.setPlaceholderText("e.g. Wrong size, defective item…")
        self.reason_input.setFixedHeight(70)
        self.reason_input.setStyleSheet(
            f"QTextEdit{{background:{WARM_WHITE};color:{DARK_CARD};"
            f"border:1px solid {BORDER};border-radius:8px;padding:8px;}}"
            f"QTextEdit:focus{{border-color:{AMBER};}}"
        )
        lay.addWidget(self.reason_input)

        # Exchange note (what is being exchanged for)
        lay.addWidget(self._lbl("Exchanged For (optional)"))
        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("e.g. Same item size L, different colour…")
        self.note_input.setFixedHeight(38)
        self.note_input.setStyleSheet(_field_style())
        lay.addWidget(self.note_input)

        self._err = QLabel("")
        self._err.setStyleSheet(f"color:{RED};font-size:11px;")
        lay.addWidget(self._err)

        btn_row = QHBoxLayout(); btn_row.setSpacing(10)
        cancel = QPushButton("Cancel"); cancel.setFixedHeight(38)
        cancel.setStyleSheet(_cancel_btn_style())
        cancel.clicked.connect(self.reject)
        confirm = QPushButton("⇄  Confirm Exchange"); confirm.setFixedHeight(38)
        confirm.setStyleSheet(_accent_btn_style())
        confirm.clicked.connect(self._accept)
        btn_row.addWidget(cancel); btn_row.addWidget(confirm, stretch=1)
        lay.addLayout(btn_row)

    def _lbl(self, text):
        l = QLabel(text)
        l.setStyleSheet(f"color:{LABEL_TEXT};font-size:11px;font-weight:600;")
        return l

    def _accept(self):
        self.reason_text   = self.reason_input.toPlainText().strip()
        self.exchange_note = self.note_input.text().strip()
        if not self.reason_text:
            self._err.setText("A reason is required.")
            return
        self.accept()


# ── HistoryDialog ─────────────────────────────────────────────────────────────

class HistoryDialog(QDialog):
    """Shows full void/refund/exchange history for a receipt."""

    def __init__(self, receipt: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"History — {receipt['receipt_number']}")
        self.setModal(True)
        self.setFixedWidth(500)
        self.setFixedHeight(360)
        self.setStyleSheet(f"background:{WHITE};")
        self._build(receipt)

    def _build(self, receipt: dict):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        title = QLabel(f"Transaction History — {receipt['receipt_number']}")
        title.setStyleSheet(
            f"color:{DARK_CARD};font-size:13px;font-weight:700;"
        )
        lay.addWidget(title)
        lay.addWidget(_divider())

        refunds = get_refunds_for_receipt(receipt["id"])

        if not refunds:
            empty = QLabel("No voids, refunds or exchanges recorded for this receipt.")
            empty.setStyleSheet(f"color:{MUTED};font-size:12px;")
            empty.setWordWrap(True)
            lay.addWidget(empty)
        else:
            TYPE_COLORS = {
                "void":     RED,
                "full":     RED,
                "partial":  AMBER,
                "exchange": DARK_CARD,
            }
            TYPE_LABELS = {
                "void":     "VOID",
                "full":     "FULL REFUND",
                "partial":  "PARTIAL REFUND",
                "exchange": "EXCHANGE",
            }
            for rf in refunds:
                user    = get_user_by_id(rf["user_id"])
                by_name = user["full_name"] if user else f"User #{rf['user_id']}"
                rtype   = rf["refund_type"]
                color   = TYPE_COLORS.get(rtype, MUTED)
                label   = TYPE_LABELS.get(rtype, rtype.upper())

                card = QFrame()
                card.setStyleSheet(
                    f"background:{WARM_WHITE};border:1px solid {BORDER};"
                    f"border-left:4px solid {color};border-radius:6px;"
                )
                cl = QVBoxLayout(card)
                cl.setContentsMargins(12, 8, 12, 8)
                cl.setSpacing(3)

                header_row = QHBoxLayout()
                type_lbl = QLabel(label)
                type_lbl.setStyleSheet(
                    f"color:{color};font-size:11px;font-weight:700;background:transparent;"
                )
                amt_lbl = QLabel(f"${rf['amount']:.2f}")
                amt_lbl.setStyleSheet(
                    f"color:{color};font-size:13px;font-weight:800;background:transparent;"
                )
                header_row.addWidget(type_lbl); header_row.addStretch()
                header_row.addWidget(amt_lbl)
                cl.addLayout(header_row)

                meta = QLabel(
                    f"By: {by_name}  ·  {rf['created_at'][:16]}"
                )
                meta.setStyleSheet(f"color:{MUTED};font-size:10px;background:transparent;")
                cl.addWidget(meta)

                if rf.get("reason"):
                    reason_lbl = QLabel(rf["reason"])
                    reason_lbl.setStyleSheet(
                        f"color:{DARK_CARD};font-size:11px;background:transparent;"
                    )
                    reason_lbl.setWordWrap(True)
                    cl.addWidget(reason_lbl)

                lay.addWidget(card)

        lay.addStretch()
        close_btn = QPushButton("Close"); close_btn.setFixedHeight(36)
        close_btn.setStyleSheet(_cancel_btn_style())
        close_btn.clicked.connect(self.accept)
        lay.addWidget(close_btn)


# ── VoidRefundTab ─────────────────────────────────────────────────────────────

class VoidRefundTab(QWidget):

    def __init__(self, user: dict, parent=None):
        super().__init__(parent)
        self.user = user
        self._build_ui()
        self._refresh_table()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8); lay.setSpacing(8)

        # ── Search bar ────────────────────────────────────────────────
        bar = QHBoxLayout(); bar.setSpacing(6)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍  Receipt # or cashier name…")
        self.search_input.setFixedHeight(32)
        self.search_input.setStyleSheet(
            f"QLineEdit{{background:{WARM_WHITE};color:{DARK_CARD};"
            f"border:1.5px solid {BORDER};border-radius:7px;padding:0 10px;"
            f"font-size:12px;}}"
            f"QLineEdit:focus{{border-color:{AMBER};}}"
        )
        self.search_input.returnPressed.connect(self._refresh_table)
        bar.addWidget(self.search_input, stretch=1)

        from PyQt6.QtWidgets import QCheckBox
        self.date_filter_chk = QCheckBox("Date:")
        self.date_filter_chk.setChecked(False)
        self.date_filter_chk.toggled.connect(self._on_date_filter_toggled)
        bar.addWidget(self.date_filter_chk)

        self.date_from = QDateEdit()
        self.date_from.setDate(QDate.currentDate().addDays(-90))
        self.date_from.setCalendarPopup(True)
        self.date_from.setFixedHeight(32)
        self.date_from.setEnabled(False)
        bar.addWidget(self.date_from)

        bar.addWidget(QLabel("→"))

        self.date_to = QDateEdit()
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setCalendarPopup(True)
        self.date_to.setFixedHeight(32)
        self.date_to.setEnabled(False)
        bar.addWidget(self.date_to)

        self.status_filter = QComboBox()
        self.status_filter.setFixedHeight(32); self.status_filter.setFixedWidth(130)
        self.status_filter.addItems(["All Statuses","Completed","Voided","Refunded"])
        self.status_filter.setStyleSheet(
            f"QComboBox{{background:{WARM_WHITE};color:{DARK_CARD};"
            f"border:1.5px solid {BORDER};border-radius:7px;padding:0 10px;}}"
            f"QComboBox:focus{{border-color:{AMBER};}}"
            f"QComboBox::drop-down{{border:none;width:18px;}}"
        )
        bar.addWidget(self.status_filter)

        search_btn = QPushButton("Search"); search_btn.setFixedHeight(32)
        search_btn.setStyleSheet(
            f"QPushButton{{background:{AMBER};color:white;border:none;"
            f"border-radius:7px;font-size:12px;font-weight:600;padding:0 12px;}}"
            f"QPushButton:hover{{background:{AMBER_DARK};}}"
        )
        search_btn.clicked.connect(self._refresh_table)
        refresh_btn = QPushButton("↻  Refresh"); refresh_btn.setFixedHeight(32)
        refresh_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{LABEL_TEXT};"
            f"border:1.5px solid {BORDER};border-radius:7px;font-size:12px;"
            f"font-weight:600;padding:0 10px;}}"
            f"QPushButton:hover{{border-color:{AMBER};color:{AMBER};}}"
        )
        refresh_btn.clicked.connect(self._refresh_table)
        bar.addWidget(search_btn); bar.addWidget(refresh_btn)
        lay.addLayout(bar)

        # ── Splitter: left = list, right = detail + actions ───────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(f"QSplitter::handle{{background:{BORDER};width:1px;}}")

        # Left — transactions table
        left = QFrame()
        left.setStyleSheet(f"background:{WARM_WHITE};border-radius:8px;border:1px solid {BORDER};")
        ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(); self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Receipt #", "Date", "Cashier", "Total", "Status", "Actions"
        ])
        hh = self.table.horizontalHeader()
        for c in range(5): hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(5, 210)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False); self.table.setShowGrid(False)
        self.table.setStyleSheet(
            f"QTableWidget{{background:{WARM_WHITE};border:none;font-size:13px;font-weight:500;}}"
            f"QTableWidget::item{{padding:8px 12px;border-bottom:1px solid {BORDER};color:{DARK_CARD};}}"
            f"QTableWidget::item:selected{{background:#FEF3DC;color:{DARK_CARD};}}"
            f"QHeaderView::section{{background:{DARK_CARD};color:{AMBER};"
            f"font-size:12px;font-weight:700;padding:8px 12px;border:none;"
            f"border-right:1px solid #333;}}"
        )
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        ll.addWidget(self.table, stretch=1)

        # Pagination
        pg_row = QHBoxLayout(); pg_row.setContentsMargins(8, 6, 8, 6); pg_row.setSpacing(8)
        self._pg_prev = QPushButton("← Prev"); self._pg_prev.setFixedHeight(28); self._pg_prev.setFixedWidth(80)
        self._pg_prev.setStyleSheet(
            f"QPushButton{{background:transparent;color:{LABEL_TEXT};"
            f"border:1.5px solid {BORDER};border-radius:6px;font-size:11px;font-weight:600;}}"
            f"QPushButton:hover{{border-color:{AMBER};color:{AMBER};}}"
            f"QPushButton:disabled{{color:{MUTED};border-color:{BORDER};}}"
        )
        self._pg_prev.clicked.connect(self._prev_page)
        self._pg_label = QLabel("Page 1 of 1")
        self._pg_label.setStyleSheet(f"color:{MUTED};font-size:11px;")
        self._pg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pg_next = QPushButton("Next →"); self._pg_next.setFixedHeight(28); self._pg_next.setFixedWidth(80)
        self._pg_next.setStyleSheet(
            f"QPushButton{{background:transparent;color:{LABEL_TEXT};"
            f"border:1.5px solid {BORDER};border-radius:6px;font-size:11px;font-weight:600;}}"
            f"QPushButton:hover{{border-color:{AMBER};color:{AMBER};}}"
            f"QPushButton:disabled{{color:{MUTED};border-color:{BORDER};}}"
        )
        self._pg_next.clicked.connect(self._next_page)
        pg_row.addStretch()
        pg_row.addWidget(self._pg_prev); pg_row.addWidget(self._pg_label); pg_row.addWidget(self._pg_next)
        pg_row.addStretch()
        ll.addLayout(pg_row)

        # Right — detail panel
        right = QFrame()
        right.setStyleSheet(f"background:{WARM_WHITE};border-radius:8px;border:1px solid {BORDER};")
        rl = QVBoxLayout(right); rl.setContentsMargins(14, 14, 14, 14); rl.setSpacing(8)

        self.det_title = QLabel("Select a transaction")
        self.det_title.setStyleSheet(f"color:{DARK_CARD};font-size:14px;font-weight:700;")
        self.det_title.setWordWrap(True)
        rl.addWidget(self.det_title)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background:{BORDER};max-height:1px;border:none;")
        rl.addWidget(sep)

        self.det_meta = QLabel("")
        self.det_meta.setStyleSheet(f"color:{LABEL_TEXT};font-size:12px;font-weight:500;")
        self.det_meta.setWordWrap(True)
        rl.addWidget(self.det_meta)

        # Items table
        self.det_items = QTableWidget(); self.det_items.setColumnCount(4)
        self.det_items.setHorizontalHeaderLabels(["Item","Qty","Price","Total"])
        hh2 = self.det_items.horizontalHeader()
        for c in range(4): hh2.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        self.det_items.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.det_items.verticalHeader().setVisible(False); self.det_items.setShowGrid(False)
        self.det_items.setStyleSheet(
            f"QTableWidget{{background:{WARM_WHITE};border:1px solid {BORDER};"
            f"border-radius:6px;font-size:12px;}}"
            f"QTableWidget::item{{padding:6px 10px;border-bottom:1px solid {BORDER};color:{DARK_CARD};}}"
            f"QHeaderView::section{{background:{DARK_CARD};color:{AMBER};"
            f"font-size:11px;font-weight:700;padding:6px 10px;border:none;}}"
        )
        rl.addWidget(self.det_items, stretch=1)

        self.det_totals = QLabel("")
        self.det_totals.setStyleSheet(f"color:{DARK_CARD};font-size:12px;font-weight:600;")
        self.det_totals.setAlignment(Qt.AlignmentFlag.AlignRight)
        rl.addWidget(self.det_totals)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"background:{BORDER};max-height:1px;border:none;")
        rl.addWidget(sep2)

        # Action buttons
        act_lbl = QLabel("ACTIONS")
        act_lbl.setStyleSheet(f"color:{MUTED};font-size:10px;font-weight:700;letter-spacing:1px;")
        rl.addWidget(act_lbl)

        act_row = QHBoxLayout(); act_row.setSpacing(6)
        self.void_btn = QPushButton("⊘  Void"); self.void_btn.setFixedHeight(34)
        self.void_btn.setEnabled(False); self.void_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.void_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{RED};border:1.5px solid {RED};"
            f"border-radius:7px;font-size:12px;font-weight:700;}}"
            f"QPushButton:hover{{background:{RED};color:white;}}"
            f"QPushButton:disabled{{color:{MUTED};border-color:{BORDER};}}"
        )
        self.refund_btn = QPushButton("↩  Refund"); self.refund_btn.setFixedHeight(34)
        self.refund_btn.setEnabled(False); self.refund_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refund_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{AMBER};border:1.5px solid {AMBER};"
            f"border-radius:7px;font-size:12px;font-weight:700;}}"
            f"QPushButton:hover{{background:{AMBER};color:white;}}"
            f"QPushButton:disabled{{color:{MUTED};border-color:{BORDER};}}"
        )
        self.exchange_btn = QPushButton("⇄  Exchange"); self.exchange_btn.setFixedHeight(34)
        self.exchange_btn.setEnabled(False); self.exchange_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.exchange_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{DARK_CARD};border:1.5px solid {BORDER};"
            f"border-radius:7px;font-size:12px;font-weight:700;}}"
            f"QPushButton:hover{{background:{DARK_CARD};color:white;}}"
            f"QPushButton:disabled{{color:{MUTED};border-color:{BORDER};}}"
        )
        act_row.addWidget(self.void_btn, stretch=1)
        act_row.addWidget(self.refund_btn, stretch=1)
        act_row.addWidget(self.exchange_btn, stretch=1)
        rl.addLayout(act_row)

        # Print + History row
        pr_row = QHBoxLayout(); pr_row.setSpacing(6)
        self.print_btn = QPushButton("🖨  Print Receipt"); self.print_btn.setFixedHeight(32)
        self.print_btn.setEnabled(False); self.print_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.print_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{LABEL_TEXT};"
            f"border:1.5px solid {BORDER};border-radius:7px;font-size:11px;font-weight:600;}}"
            f"QPushButton:hover{{border-color:{AMBER};color:{AMBER};}}"
            f"QPushButton:disabled{{color:{MUTED};border-color:{BORDER};}}"
        )
        self.history_btn = QPushButton("📋  History"); self.history_btn.setFixedHeight(32)
        self.history_btn.setEnabled(False); self.history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.history_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{LABEL_TEXT};"
            f"border:1.5px solid {BORDER};border-radius:7px;font-size:11px;font-weight:600;}}"
            f"QPushButton:hover{{border-color:{AMBER};color:{AMBER};}}"
            f"QPushButton:disabled{{color:{MUTED};border-color:{BORDER};}}"
        )
        pr_row.addWidget(self.print_btn, stretch=1)
        pr_row.addWidget(self.history_btn, stretch=1)
        rl.addLayout(pr_row)

        splitter.addWidget(left); splitter.addWidget(right)
        splitter.setStretchFactor(0, 1); splitter.setStretchFactor(1, 1)
        lay.addWidget(splitter, stretch=1)

        # Pagination state
        self._pg_page     = 0
        self._pg_per_page = 50
        self._current_receipt = None

    def _on_date_filter_toggled(self, checked: bool):
        self.date_from.setEnabled(checked)
        self.date_to.setEnabled(checked)
        self._pg_page = 0
        self._refresh_table()

    def _refresh_table(self):
        try:
            self._do_refresh_table()
        except Exception as e:
            import traceback
            traceback.print_exc()

    def _do_refresh_table(self):
        search     = self.search_input.text().strip()
        status_txt = self.status_filter.currentText()
        status     = None if status_txt == "All Statuses" else status_txt.lower()

        # Only apply date filter if the checkbox is checked
        date_from = self.date_from.date().toString("yyyy-MM-dd") if self.date_filter_chk.isChecked() else ""
        date_to   = self.date_to.date().toString("yyyy-MM-dd")   if self.date_filter_chk.isChecked() else ""

        total = count_receipts(search=search, status=status,
                               date_from=date_from, date_to=date_to)
        pages = max(1, (total + self._pg_per_page - 1) // self._pg_per_page)
        self._pg_page = min(self._pg_page, pages - 1)

        receipts = get_receipts_with_refund_summary(
            status=status, search=search,
            date_from=date_from, date_to=date_to,
            limit=self._pg_per_page,
            offset=self._pg_page * self._pg_per_page,
        )

        STATUS_COLOR = {"completed": GREEN, "voided": RED, "refunded": AMBER}
        R = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        C = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter

        self.table.setRowCount(0)
        for idx, r in enumerate(receipts):
            self.table.insertRow(idx); self.table.setRowHeight(idx, 38)
            status_val = r.get("status", "completed")

            num_item = QTableWidgetItem(r["receipt_number"])
            num_item.setData(Qt.ItemDataRole.UserRole, r)
            self.table.setItem(idx, 0, num_item)
            self.table.setItem(idx, 1, QTableWidgetItem(str(r["created_at"])[:10]))
            cashier = get_user_by_id(r["user_id"])
            self.table.setItem(idx, 2, QTableWidgetItem(
                cashier["full_name"] if cashier else "Unknown"))
            tot = QTableWidgetItem(f"${r['total']:.2f}")
            tot.setTextAlignment(R); self.table.setItem(idx, 3, tot)
            status_parts = [status_val.capitalize()]
            if r.get("has_partial"): status_parts.append(f"(-${r['refunded_total']:.2f})")
            if r.get("has_exchange"): status_parts.append("(exc)")
            si = QTableWidgetItem(" ".join(status_parts))
            si.setForeground(QColor(STATUS_COLOR.get(status_val, MUTED)))
            si.setTextAlignment(C); self.table.setItem(idx, 4, si)

            # Action cell — outline buttons only for completed
            is_comp = (status_val == "completed")
            act = QWidget(); al = QHBoxLayout(act)
            al.setContentsMargins(4, 2, 4, 2); al.setSpacing(4)
            for label, color, cb in [
                ("Void",     RED,       lambda _, rec=r: self._void_receipt(rec)),
                ("Refund",   AMBER,     lambda _, rec=r: self._refund_receipt(rec)),
                ("Exchange", DARK_CARD, lambda _, rec=r: self._exchange_receipt(rec)),
            ]:
                b = QPushButton(label); b.setFixedHeight(26)
                b.setEnabled(is_comp)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setStyleSheet(
                    f"QPushButton{{background:transparent;color:{color};"
                    f"border:1px solid {color};border-radius:5px;"
                    f"font-size:11px;font-weight:600;padding:0 8px;}}"
                    f"QPushButton:hover{{background:{color};color:white;}}"
                    f"QPushButton:disabled{{color:{MUTED};border-color:{BORDER};}}"
                )
                b.clicked.connect(cb); al.addWidget(b)
            al.addStretch()
            self.table.setCellWidget(idx, 5, act)

        self._pg_label.setText(f"Page {self._pg_page+1} of {pages}  ({total})")
        self._pg_prev.setEnabled(self._pg_page > 0)
        self._pg_next.setEnabled(self._pg_page < pages - 1)

    def _prev_page(self):
        if self._pg_page > 0:
            self._pg_page -= 1
            self._refresh_table()

    def _next_page(self):
        self._pg_page += 1
        self._refresh_table()

    def _on_row_selected(self):
        selected = self.table.selectedItems()
        if not selected:
            self._clear_detail(); return
        r = selected[0].data(Qt.ItemDataRole.UserRole)
        if not r: return
        receipt = get_receipt_by_id(r["id"])
        if not receipt: return
        self._current_receipt = receipt

        cashier = get_user_by_id(receipt["user_id"])
        is_comp = receipt["status"] == "completed"

        # Title + meta
        self.det_title.setText(receipt["receipt_number"])
        self.det_meta.setText(
            f"Date: {receipt['created_at'][:16]}  ·  "
            f"Cashier: {cashier['full_name'] if cashier else 'Unknown'}  ·  "
            f"Payment: {receipt['payment_method'].capitalize()}  ·  "
            f"Status: {receipt['status'].capitalize()}"
        )

        # Items
        self.det_items.setRowCount(0)
        for i, item in enumerate(receipt.get("items", [])):
            self.det_items.insertRow(i)
            self.det_items.setRowHeight(i, 32)
            self.det_items.setItem(i, 0, QTableWidgetItem(item["product_name"]))
            qi = QTableWidgetItem(str(item["quantity"]))
            qi.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter)
            self.det_items.setItem(i, 1, qi)
            pi = QTableWidgetItem(f"${item['unit_price']:.2f}")
            pi.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
            self.det_items.setItem(i, 2, pi)
            ti = QTableWidgetItem(f"${item['line_total']:.2f}")
            ti.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
            self.det_items.setItem(i, 3, ti)

        self.det_totals.setText(
            f"Subtotal: ${receipt['subtotal']:.2f}   "
            f"GCT: ${receipt['gct_amount']:.2f}   "
            f"Total: ${receipt['total']:.2f}"
        )

        # Enable/disable action buttons
        self.void_btn.setEnabled(is_comp)
        self.refund_btn.setEnabled(is_comp)
        self.exchange_btn.setEnabled(is_comp)
        self.print_btn.setEnabled(True)
        self.history_btn.setEnabled(True)

        # Wire buttons to this receipt
        try: self.void_btn.clicked.disconnect()
        except: pass
        try: self.refund_btn.clicked.disconnect()
        except: pass
        try: self.exchange_btn.clicked.disconnect()
        except: pass
        try: self.print_btn.clicked.disconnect()
        except: pass
        try: self.history_btn.clicked.disconnect()
        except: pass

        self.void_btn.clicked.connect(lambda: self._void_receipt(receipt))
        self.refund_btn.clicked.connect(lambda: self._refund_receipt(receipt))
        self.exchange_btn.clicked.connect(lambda: self._exchange_receipt(receipt))
        self.print_btn.clicked.connect(lambda: self._print_receipt(receipt))
        self.history_btn.clicked.connect(lambda: self._show_history(receipt))

    def _clear_detail(self):
        self.det_title.setText("Select a transaction")
        self.det_meta.setText("")
        self.det_items.setRowCount(0)
        self.det_totals.setText("")
        for btn in [self.void_btn, self.refund_btn, self.exchange_btn,
                    self.print_btn, self.history_btn]:
            btn.setEnabled(False)
        self._current_receipt = None

    def _print_receipt(self, r: dict):
        from utils.print_manager import print_receipt
        print_receipt(r, parent=self)

    def _show_history(self, r: dict):
        dlg = HistoryDialog(r, parent=self)
        dlg.exec()

    # ── Actions ────────────────────────────────────────────────────────

    def _auth(self) -> bool:
        dlg = PasswordDialog(self.user, self)
        return dlg.exec() == QDialog.DialogCode.Accepted and dlg.is_verified()

    def _void_receipt(self, r: dict):
        if not self._auth(): return
        dlg = VoidReasonDialog(r, self)
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        if not void_receipt(r["id"], self.user["id"], dlg.reason):
            QMessageBox.critical(self, "Failed",
                "Could not void. Receipt may already be voided or refunded.")
            return
        rec    = get_receipt_by_id(r["id"])
        refund = (get_refunds_for_receipt(r["id"]) or [{}])[0]
        self._maybe_restock(rec, full=True)
        print_void(rec, refund, self.user, self)
        QMessageBox.information(self, "Voided",
            f"Receipt {r['receipt_number']} has been voided.")
        self._refresh_table()

    def _refund_receipt(self, r: dict):
        if not self._auth(): return
        dlg = RefundDialog(r, self)
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        if not refund_receipt(r["id"], self.user["id"],
                              dlg.reason_text, dlg.refund_amount, dlg.refund_type):
            QMessageBox.critical(self, "Failed", "Could not process refund.")
            return
        rec    = get_receipt_by_id(r["id"])
        refund = (get_refunds_for_receipt(r["id"]) or [{}])[0]
        if dlg.refund_type == "full":
            self._maybe_restock(rec, full=True)
        print_refund(rec, refund, self.user, self)
        QMessageBox.information(self, "Refunded",
            f"${dlg.refund_amount:.2f} refunded for {r['receipt_number']}.")
        self._refresh_table()

    def _exchange_receipt(self, r: dict):
        if not self._auth(): return
        dlg = ExchangeDialog(r, self)
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        if not exchange_receipt(r["id"], self.user["id"],
                                dlg.reason_text, dlg.exchange_note):
            QMessageBox.critical(self, "Failed", "Could not record exchange.")
            return
        QMessageBox.information(self, "Exchange Recorded",
            f"Exchange recorded for {r['receipt_number']}.")
        self._refresh_table()

    def _maybe_restock(self, receipt: dict, full: bool = False):
        from core.db_config import get_bool
        if not get_bool("stock_tracking", False): return
        from core.db_products import increment_stock
        for item in (receipt or {}).get("items", []):
            if item.get("product_id"):
                increment_stock(item["product_id"], item["quantity"])

    def _print_receipt(self, r: dict):
        full = get_receipt_by_id(r["id"])
        if not full:
            QMessageBox.warning(self, "Not Found", "Could not load receipt.")
            return
        from utils.print_manager import print_receipt
        print_receipt(full, self)

    def _show_history(self, r: dict):
        full = get_receipt_by_id(r["id"])
        if full:
            HistoryDialog(full, self).exec()
