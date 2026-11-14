"""Entry point for the MePDF desktop application."""

from __future__ import annotations

import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from mepdf.ui.main_window import MainWindow
from mepdf.ui.theme import ThemeManager


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("MePDF")
    app.setOrganizationName("MePDF")

    theme_manager = ThemeManager()
    theme_manager.apply_to_app()

    window = MainWindow(theme_manager=theme_manager)
    window.show()

    # If a PDF file path was passed on the command line, open it automatically
    for arg in sys.argv[1:]:
        if arg.lower().endswith(".pdf"):
            window.action_open_pdf(arg)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
