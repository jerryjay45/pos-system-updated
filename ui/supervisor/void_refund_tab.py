"""
ui/supervisor/void_refund_tab.py
Supervisor void/refund transaction management tab.

Features:
  - Search/filter transactions by receipt number or date range
  - View transaction details (items, amounts)
  - Void completed transactions (full void)
  - Partial refund processing
  - Password confirmation dialog
  - Print void/refund notices
  - Refund history display
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QDateEdit, QComboBox, QLabel, QTextEdit,
    QDialog, QSpinBox, QDoubleSpinBox, QMessageBox, QDialogButtonBox,
    QFrame, QHeaderView, QSizePolicy,
)
from PyQt6.QtCore import Qt, QDate, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from ui.shared.theme import (
    AMBER, AMBER_DARK, DARK_CARD, WHITE, BORDER, MUTED, RED, GREEN,
    RED_LIGHT, RED_BORDER, LABEL_TEXT, MAIN_FONT,
)
from core.db_checkout import (
    get_receipts, get_receipt_by_id, void_receipt, refund_receipt,
    get_refunds_for_receipt,
)
from core.db_users import get_user_by_id, authenticate
from utils.print_manager import print_void, print_refund


# ── Password verification dialog ────────────────────────────────────────────────

class PasswordDialog(QDialog):
    """Modal password entry dialog for supervisor authorization."""
    
    def __init__(self, supervisor: dict, parent=None):
        super().__init__(parent)
        self.supervisor = supervisor
        self.setWindowTitle("Confirm Identity")
        self.setModal(True)
        self.setFixedWidth(340)
        self.password_input = None
        self._verified = False
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 20)
        
        # Title
        title = QLabel("Supervisor Authorization Required")
        title_font = QFont(MAIN_FONT, 13, QFont.Weight.Bold)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {DARK_CARD};")
        layout.addWidget(title)
        
        # Message
        msg = QLabel(
            f"Please enter your password to confirm this action.\n\n"
            f"Supervisor: {self.supervisor.get('full_name', 'Unknown')}"
        )
        msg.setStyleSheet(f"color: {LABEL_TEXT}; font-size: 12px;")
        msg.setWordWrap(True)
        layout.addWidget(msg)
        
        # Password field
        layout.addSpacing(8)
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter your password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setFixedHeight(40)
        self.password_input.setStyleSheet(f"""
            QLineEdit {{
                background: #FAFAF8;
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 0 12px;
                font-size: 13px;
                color: {DARK_CARD};
            }}
            QLineEdit:focus {{ border-color: {AMBER}; background: {WHITE}; }}
        """)
        self.password_input.returnPressed.connect(self.accept)
        layout.addWidget(self.password_input)
        
        # Buttons
        layout.addSpacing(12)
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(40)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {WHITE};
                border: 1px solid {BORDER};
                border-radius: 8px;
                color: {DARK_CARD};
                font-weight: 600;
            }}
            QPushButton:hover {{ background: #F5F5F3; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        verify_btn = QPushButton("Verify & Proceed")
        verify_btn.setFixedHeight(40)
        verify_btn.setStyleSheet(f"""
            QPushButton {{
                background: {AMBER};
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {AMBER_DARK}; }}
        """)
        verify_btn.clicked.connect(self._verify)
        button_layout.addWidget(verify_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def _verify(self):
        """Verify password against supervisor account."""
        password = self.password_input.text()
        if not password:
            QMessageBox.warning(self, "Missing Password", "Please enter your password.")
            return
        
        # Authenticate
        user = authenticate(self.supervisor["username"], password)
        if user is None:
            QMessageBox.warning(self, "Invalid Password", "Password incorrect.")
            self.password_input.clear()
            self.password_input.setFocus()
            return
        
        self._verified = True
        self.accept()
    
    def is_verified(self) -> bool:
        return self._verified


# ── Refund dialog (partial refunds) ─────────────────────────────────────────────

class RefundDialog(QDialog):
    """Dialog to process a partial refund for a transaction."""
    
    def __init__(self, receipt: dict, parent=None):
        super().__init__(parent)
        self.receipt = receipt
        self.refund_amount = 0.0
        self.refund_type = "full"
        self.reason_text = ""
        self.setWindowTitle("Process Refund")
        self.setModal(True)
        self.setFixedWidth(400)
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 20)
        
        # Title
        title = QLabel("Process Refund")
        title_font = QFont(MAIN_FONT, 13, QFont.Weight.Bold)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {DARK_CARD};")
        layout.addWidget(title)
        
        # Receipt info
        info_layout = QHBoxLayout()
        info_layout.setSpacing(20)
        info_layout.addWidget(QLabel(f"Receipt: {self.receipt['receipt_number']}"))
        info_layout.addWidget(QLabel(f"Total: ${self.receipt['total']:.2f}"))
        info_layout.addStretch()
        layout.addLayout(info_layout)
        
        layout.addSpacing(8)
        
        # Refund type
        layout.addWidget(QLabel("Refund Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Full Refund", "Partial Refund"])
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        layout.addWidget(self.type_combo)
        
        layout.addSpacing(8)
        
        # Refund amount (only for partial)
        self.amount_label = QLabel("Refund Amount:")
        layout.addWidget(self.amount_label)
        self.amount_input = QDoubleSpinBox()
        self.amount_input.setMinimum(0.01)
        self.amount_input.setMaximum(self.receipt["total"])
        self.amount_input.setValue(self.receipt["total"])
        self.amount_input.setDecimals(2)
        self.amount_input.setSuffix(" $")
        self.amount_input.setFixedHeight(40)
        self.amount_input.setVisible(False)
        layout.addWidget(self.amount_input)
        
        layout.addSpacing(8)
        
        # Reason
        layout.addWidget(QLabel("Reason:"))
        self.reason_input = QTextEdit()
        self.reason_input.setPlaceholderText("Enter reason for refund...")
        self.reason_input.setFixedHeight(80)
        layout.addWidget(self.reason_input)
        
        # Buttons
        layout.addSpacing(12)
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Ok
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        self.setLayout(layout)
    
    def _on_type_changed(self, text: str):
        """Toggle refund amount input based on type."""
        is_partial = text == "Partial Refund"
        self.amount_input.setVisible(is_partial)
        self.amount_label.setVisible(is_partial)
    
    def _on_accept(self):
        """Validate and accept."""
        self.refund_type = "partial" if self.type_combo.currentText() == "Partial Refund" else "full"
        self.refund_amount = self.amount_input.value() if self.refund_type == "partial" else self.receipt["total"]
        self.reason_text = self.reason_input.toPlainText().strip()
        
        if not self.reason_text:
            QMessageBox.warning(self, "Missing Reason", "Please enter a reason for the refund.")
            return
        
        self.accept()


# ── Main void/refund tab ────────────────────────────────────────────────────────

class VoidRefundTab(QWidget):
    """Supervisor tab for managing void/refund transactions."""
    
    def __init__(self, user: dict, parent=None):
        super().__init__(parent)
        self.user = user  # supervisor/manager
        self._build_ui()
        self._refresh_table()
    
    def _build_ui(self):
        """Build the tab layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        # ── Search & filter bar ─────────────────────────────────────────────────
        search_layout = QHBoxLayout()
        search_layout.setSpacing(12)
        
        search_label = QLabel("Receipt #:")
        search_label.setStyleSheet(f"color: {LABEL_TEXT}; font-weight: 600;")
        search_layout.addWidget(search_label)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("e.g. #0042")
        self.search_input.setFixedWidth(120)
        self.search_input.textChanged.connect(self._on_search)
        search_layout.addWidget(self.search_input)
        
        search_layout.addSpacing(12)
        
        date_label = QLabel("From:")
        date_label.setStyleSheet(f"color: {LABEL_TEXT}; font-weight: 600;")
        search_layout.addWidget(date_label)
        
        self.date_from = QDateEdit()
        self.date_from.setDate(QDate.currentDate().addDays(-30))
        self.date_from.dateChanged.connect(self._on_search)
        search_layout.addWidget(self.date_from)
        
        to_label = QLabel("To:")
        to_label.setStyleSheet(f"color: {LABEL_TEXT}; font-weight: 600;")
        search_layout.addWidget(to_label)
        
        self.date_to = QDateEdit()
        self.date_to.setDate(QDate.currentDate())
        self.date_to.dateChanged.connect(self._on_search)
        search_layout.addWidget(self.date_to)
        
        search_layout.addStretch()
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(100)
        refresh_btn.clicked.connect(self._refresh_table)
        search_layout.addWidget(refresh_btn)
        
        layout.addLayout(search_layout)
        
        # ── Transactions table ──────────────────────────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Receipt #", "Date", "Cashier", "Total", "Status", "Action", "Print", "History"
        ])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {WHITE};
                gridline-color: #E2DDD3;
                border: none;
            }}
            QTableWidget::item {{
                padding: 12px;
                border-bottom: 1px solid #E2DDD3;
                color: {DARK_CARD};
            }}
            QTableWidget::item:selected {{
                background-color: #FAEEDA;
                color: {DARK_CARD};
            }}
            QHeaderView::section {{
                background-color: {DARK_CARD};
                color: {AMBER};
                font-weight: 700;
                padding: 10px;
                border: none;
                border-right: 1px solid #333;
                font-size: 12px;
            }}
        """)
        layout.addWidget(self.table, 1)
        
        # ── Info panel (transaction details) ────────────────────────────────────
        info_layout = QHBoxLayout()
        info_layout.setSpacing(16)
        
        details_frame = QFrame()
        details_frame.setStyleSheet(f"""
            QFrame {{
                background: {WHITE};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 12px;
            }}
        """)
        details_layout = QVBoxLayout(details_frame)
        details_layout.setSpacing(8)
        
        details_title = QLabel("Transaction Details")
        details_title.setStyleSheet(f"color: {DARK_CARD}; font-weight: 700;")
        details_layout.addWidget(details_title)
        
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setFixedHeight(120)
        details_layout.addWidget(self.details_text)
        
        info_layout.addWidget(details_frame, 1)
        layout.addLayout(info_layout)
    
    def _on_search(self):
        """Filter table by search/date."""
        self._refresh_table()
    
    def _refresh_table(self):
        """Load and display transactions."""
        date_from = self.date_from.date().toString("yyyy-MM-dd")
        date_to = self.date_to.date().toString("yyyy-MM-dd")
        search = self.search_input.text().strip()
        
        # Get completed transactions only (available for void/refund)
        receipts = get_receipts(
            status="completed",
            search=search,
            date_from=date_from,
            date_to=date_to,
            limit=200,
        )
        
        self.table.setRowCount(len(receipts))
        
        for idx, receipt in enumerate(receipts):
            # Receipt #
            num_item = QTableWidgetItem(receipt["receipt_number"])
            num_item.setData(Qt.ItemDataRole.UserRole, receipt["id"])
            self.table.setItem(idx, 0, num_item)
            
            # Date
            date_item = QTableWidgetItem(receipt["created_at"][:10])
            self.table.setItem(idx, 1, date_item)
            
            # Cashier
            cashier = get_user_by_id(receipt["user_id"])
            cashier_name = cashier["full_name"] if cashier else "Unknown"
            self.table.setItem(idx, 2, QTableWidgetItem(cashier_name))
            
            # Total
            total_item = QTableWidgetItem(f"${receipt['total']:.2f}")
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(idx, 3, total_item)
            
            # Status (always "Completed" for this list)
            status_item = QTableWidgetItem("Completed")
            status_item.setForeground(QColor(GREEN))
            self.table.setItem(idx, 4, status_item)
            
            # Action buttons
            action_layout = QHBoxLayout()
            void_btn = QPushButton("Void")
            void_btn.setFixedWidth(70)
            void_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {RED};
                    color: white;
                    border: none;
                    border-radius: 5px;
                    font-size: 11px;
                    font-weight: 600;
                }}
                QPushButton:hover {{ background: #7A1E1E; }}
            """)
            void_btn.clicked.connect(lambda checked, r=receipt: self._void_receipt(r))
            action_layout.addWidget(void_btn)
            
            refund_btn = QPushButton("Refund")
            refund_btn.setFixedWidth(70)
            refund_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {AMBER};
                    color: white;
                    border: none;
                    border-radius: 5px;
                    font-size: 11px;
                    font-weight: 600;
                }}
                QPushButton:hover {{ background: {AMBER_DARK}; }}
            """)
            refund_btn.clicked.connect(lambda checked, r=receipt: self._refund_receipt(r))
            action_layout.addWidget(refund_btn)
            
            action_cell = QWidget()
            action_cell.setLayout(action_layout)
            self.table.setCellWidget(idx, 5, action_cell)
            
            # Print button
            print_btn = QPushButton("Print")
            print_btn.setFixedWidth(60)
            print_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {MUTED};
                    color: white;
                    border: none;
                    border-radius: 5px;
                    font-size: 11px;
                    font-weight: 600;
                }}
                QPushButton:hover {{ background: #4A4845; }}
            """)
            print_btn.clicked.connect(lambda checked, r=receipt: self._print_receipt(r))
            self.table.setCellWidget(idx, 6, print_btn)
            
            # History button
            history_btn = QPushButton("History")
            history_btn.setFixedWidth(60)
            history_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {MUTED};
                    color: white;
                    border: none;
                    border-radius: 5px;
                    font-size: 11px;
                    font-weight: 600;
                }}
                QPushButton:hover {{ background: #4A4845; }}
            """)
            history_btn.clicked.connect(lambda checked, r=receipt: self._show_history(r))
            self.table.setCellWidget(idx, 7, history_btn)
            
            # Connect row selection to details panel
            self.table.item(idx, 0).setData(Qt.ItemDataRole.UserRole, receipt)
        
        self.table.resizeRowsToContents()
        self.table.itemSelectionChanged.connect(self._on_row_selected)
    
    def _on_row_selected(self):
        """Update details panel when a row is selected."""
        selected = self.table.selectedItems()
        if not selected:
            self.details_text.clear()
            return
        
        receipt_data = selected[0].data(Qt.ItemDataRole.UserRole)
        if not receipt_data:
            return
        
        # Full receipt with items
        receipt = get_receipt_by_id(receipt_data.get("id") or receipt_data.get("receipt_id"))
        if not receipt:
            return
        
        # Format details
        details = f"""Receipt: {receipt['receipt_number']}
Date: {receipt['created_at']}
Cashier: {get_user_by_id(receipt['user_id']).get('full_name', 'Unknown') if get_user_by_id(receipt['user_id']) else 'Unknown'}
Payment: {receipt['payment_method'].capitalize()}

Items:
"""
        for item in receipt.get("items", []):
            details += f"  • {item['product_name']} x{item['quantity']} @ ${item['unit_price']:.2f} = ${item['line_total']:.2f}\n"
        
        details += f"\nSubtotal: ${receipt['subtotal']:.2f}"
        details += f"\nGCT: ${receipt['gct_amount']:.2f}"
        if receipt.get("discount_amount", 0) > 0:
            details += f"\nDiscount: -${receipt['discount_amount']:.2f}"
        details += f"\n\nTOTAL: ${receipt['total']:.2f}"
        
        self.details_text.setText(details)
    
    def _void_receipt(self, receipt: dict):
        """Initiate void process."""
        # Verify supervisor identity
        dlg = PasswordDialog(self.user, self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.is_verified():
            return
        
        # Get reason
        reason_dlg = QDialog(self)
        reason_dlg.setWindowTitle("Void Reason")
        reason_dlg.setModal(True)
        reason_dlg.setFixedWidth(400)
        
        layout = QVBoxLayout(reason_dlg)
        layout.addWidget(QLabel("Reason for void:"))
        reason_input = QTextEdit()
        reason_input.setFixedHeight(80)
        layout.addWidget(reason_input)
        
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Ok
        )
        btn_box.accepted.connect(reason_dlg.accept)
        btn_box.rejected.connect(reason_dlg.reject)
        layout.addWidget(btn_box)
        
        if reason_dlg.exec() != QDialog.DialogCode.Accepted:
            return
        
        reason = reason_input.toPlainText().strip()
        if not reason:
            QMessageBox.warning(self, "Missing Reason", "Please enter a reason.")
            return
        
        # Execute void
        success = void_receipt(receipt["id"], self.user["id"], reason)
        if not success:
            QMessageBox.critical(self, "Void Failed", "Could not void this receipt. It may already be voided or refunded.")
            return
        
        # Fetch updated receipt
        voided_receipt = get_receipt_by_id(receipt["id"])
        refund = get_refunds_for_receipt(receipt["id"])[0] if get_refunds_for_receipt(receipt["id"]) else {}
        
        # Print void notice
        print_void(voided_receipt, refund, self.user, self)
        
        QMessageBox.information(self, "Success", f"Receipt {receipt['receipt_number']} has been voided.")
        self._refresh_table()
    
    def _refund_receipt(self, receipt: dict):
        """Initiate refund process."""
        # Verify supervisor identity
        dlg = PasswordDialog(self.user, self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.is_verified():
            return
        
        # Open refund dialog
        refund_dlg = RefundDialog(receipt, self)
        if refund_dlg.exec() != QDialog.DialogCode.Accepted:
            return
        
        # Execute refund
        success = refund_receipt(
            receipt["id"],
            self.user["id"],
            refund_dlg.reason_text,
            refund_dlg.refund_amount,
            refund_dlg.refund_type,
        )
        if not success:
            QMessageBox.critical(self, "Refund Failed", "Could not process this refund.")
            return
        
        # Fetch updated receipt
        refunded_receipt = get_receipt_by_id(receipt["id"])
        refund = get_refunds_for_receipt(receipt["id"])[0] if get_refunds_for_receipt(receipt["id"]) else {}
        
        # Print refund receipt
        print_refund(refunded_receipt, refund, self.user, self)
        
        QMessageBox.information(
            self, "Success",
            f"Refund of ${refund_dlg.refund_amount:.2f} has been processed for receipt {receipt['receipt_number']}."
        )
        self._refresh_table()
    
    def _print_receipt(self, receipt: dict):
        """Print original receipt."""
        full_receipt = get_receipt_by_id(receipt["id"])
        if not full_receipt:
            QMessageBox.warning(self, "Not Found", "Could not load receipt.")
            return
        
        from utils.print_manager import print_receipt
        print_receipt(full_receipt, self)
    
    def _show_history(self, receipt: dict):
        """Show refund history dialog."""
        refunds = get_refunds_for_receipt(receipt["id"])
        
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Refund History — {receipt['receipt_number']}")
        dlg.setFixedSize(500, 300)
        
        layout = QVBoxLayout(dlg)
        
        if not refunds:
            layout.addWidget(QLabel("No refunds or voids for this receipt."))
        else:
            text = "Refund History:\n\n"
            for rf in refunds:
                text += f"Type: {rf['refund_type'].upper()}\n"
                text += f"Amount: ${rf['amount']:.2f}\n"
                text += f"Reason: {rf['reason']}\n"
                text += f"By User ID: {rf['user_id']}\n"
                text += f"Date: {rf['created_at']}\n"
                text += "─" * 40 + "\n"
            
            text_display = QTextEdit()
            text_display.setPlainText(text)
            text_display.setReadOnly(True)
            layout.addWidget(text_display)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)
        
        dlg.exec()
