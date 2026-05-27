"""
ui/base_window.py
Base window for all protected POS windows.
Blocks accidental closing via the X button.
All dashboards inherit from this.
"""

from PyQt6.QtWidgets import QMainWindow, QMessageBox


class BaseWindow(QMainWindow):
    """
    QMainWindow that blocks the X button with a warning.
    Use force_close() from logout buttons/actions.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

    def closeEvent(self, event):
        msg = QMessageBox(self)
        msg.setWindowTitle("Cannot Close")
        msg.setText("You cannot close this window using the X button.")
        msg.setInformativeText("Please use the Logout button.")
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()
        event.ignore()

    def force_close(self):
        """Bypass closeEvent protection — call from logout."""
        self.closeEvent = lambda event: event.accept()
        self.close()
