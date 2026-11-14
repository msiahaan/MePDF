"""Entry point for the MePDF desktop application."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Optional
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFileOpenEvent, QIcon
from PySide6.QtWidgets import QApplication

from mepdf import __version__
from mepdf.ui.main_window import MainWindow
from mepdf.ui.theme import ThemeManager


def _resolve_asset_path(rel_path: str) -> Path:
    """Resolve an asset path whether running from source or a PyInstaller bundle."""
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_dir / rel_path


class MePDFApplication(QApplication):
    """QApplication subclass that routes macOS Finder QFileOpenEvent (.pdf) to MainWindow."""

    def __init__(self, argv: list[str]) -> None:
        super().__init__(argv)
        self.main_window: Optional[MainWindow] = None
        self._pending_files: list[str] = []

    def set_main_window(self, window: MainWindow) -> None:
        self.main_window = window
        for file_path in self._pending_files:
            self.main_window.action_open_pdf(file_path)
        self._pending_files.clear()

    def event(self, ev: QEvent) -> bool:
        if ev.type() == QEvent.Type.FileOpen and isinstance(ev, QFileOpenEvent):
            local_file = ev.file()
            if local_file and local_file.lower().endswith(".pdf"):
                if self.main_window is not None:
                    self.main_window.action_open_pdf(local_file)
                else:
                    self._pending_files.append(local_file)
                return True
        return super().event(ev)


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = MePDFApplication(sys.argv)
    app.setApplicationName("MePDF")
    app.setOrganizationName("MePDF")
    app.setApplicationVersion(__version__)

    icon_candidate = (
        _resolve_asset_path("assets/mepdf.ico")
        if sys.platform == "win32"
        else _resolve_asset_path("assets/mepdf.png")
    )
    if icon_candidate.exists():
        app.setWindowIcon(QIcon(str(icon_candidate)))

    theme_manager = ThemeManager()
    theme_manager.apply_to_app()

    window = MainWindow(theme_manager=theme_manager)
    if icon_candidate.exists():
        window.setWindowIcon(QIcon(str(icon_candidate)))
    app.set_main_window(window)
    window.show()

    # If a PDF file path was passed on the command line, open it automatically
    for arg in sys.argv[1:]:
        if arg.lower().endswith(".pdf") and Path(arg).exists():
            window.action_open_pdf(arg)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
