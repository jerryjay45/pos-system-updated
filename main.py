"""
main.py — Merchant POS Systems entry point.
Run with:  python main.py
"""
import sys
import os

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Create required directories
from config import DATA_DIR, RECEIPT_DIR, LABEL_DIR
os.makedirs(DATA_DIR,    exist_ok=True)
os.makedirs(RECEIPT_DIR, exist_ok=True)
os.makedirs(LABEL_DIR,   exist_ok=True)

# Initialise all databases
from core import init_all_databases
init_all_databases()

# High-DPI policy MUST be set before QApplication is created
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore    import Qt
QApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Merchant POS Systems")
    app.setApplicationVersion("1.0.0")

    # Apply theme stylesheet
    from ui.shared.theme import get_stylesheet
    app.setStyleSheet(get_stylesheet())

    # Load Inter font if bundled in assets/fonts/
    from PyQt6.QtGui import QFontDatabase
    font_dir = os.path.join(os.path.dirname(__file__), "assets", "fonts")
    if os.path.isdir(font_dir):
        for f in os.listdir(font_dir):
            if f.endswith((".ttf", ".otf")):
                QFontDatabase.addApplicationFont(os.path.join(font_dir, f))

    # Show login window
    from ui.login_window import LoginWindow
    window = LoginWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
