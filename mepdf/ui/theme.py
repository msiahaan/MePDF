"""ThemeManager providing live Dark / Light QSS stylesheets and custom QPainter vector icons."""

from __future__ import annotations

from enum import Enum
from typing import Optional
from PySide6.QtCore import QObject, QPointF, QRectF, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication


class ThemeMode(str, Enum):
    """Supported UI themes."""

    DARK = "dark"
    LIGHT = "light"


DARK_QSS = """
QMainWindow, QDialog {
    background-color: #18181c;
    color: #f1f5f9;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}
QWidget {
    color: #f1f5f9;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}
QMenuBar {
    background-color: #1e1e24;
    border-bottom: 1px solid #2e2e38;
    padding: 2px 6px;
}
QMenuBar::item {
    background: transparent;
    padding: 5px 10px;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background-color: #2e2e3a;
}
QMenu {
    background-color: #23232b;
    border: 1px solid #383846;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #3b82f6;
    color: #ffffff;
}
QToolBar {
    background-color: #202027;
    border-bottom: 1px solid #2e2e38;
    spacing: 2px;
    padding: 4px 6px;
}
QToolBar::separator {
    background-color: #32323e;
    width: 1px;
    margin: 4px 4px;
}
QToolButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 6px;
    color: #e2e8f0;
    font-weight: 500;
}
QToolButton:hover {
    background-color: #2c2c37;
    border-color: #3a3a48;
}
QToolButton:checked, QToolButton:pressed {
    background-color: #2563eb;
    border-color: #3b82f6;
    color: #ffffff;
}
QPushButton {
    background-color: #2b2b36;
    border: 1px solid #3d3d4d;
    border-radius: 6px;
    padding: 6px 12px;
    color: #f1f5f9;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #353542;
    border-color: #4f4f63;
}
QPushButton:pressed {
    background-color: #1d4ed8;
}
QPushButton[primary="true"] {
    background-color: #2563eb;
    border-color: #3b82f6;
    color: #ffffff;
    font-weight: 600;
}
QPushButton[primary="true"]:hover {
    background-color: #3b82f6;
}
QPushButton[danger="true"] {
    background-color: #dc2626;
    border-color: #ef4444;
    color: #ffffff;
    font-weight: 600;
}
QPushButton[danger="true"]:hover {
    background-color: #ef4444;
}
QTabWidget::pane {
    border: 1px solid #2e2e38;
    background-color: #1e1e24;
    border-radius: 4px;
}
QTabBar::tab {
    background-color: #1b1b21;
    color: #94a3b8;
    border: 1px solid #2e2e38;
    border-bottom: none;
    padding: 7px 14px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 500;
}
QTabBar::tab:selected {
    background-color: #262630;
    color: #ffffff;
    border-bottom: 2px solid #3b82f6;
}
QTabBar::tab:hover:!selected {
    background-color: #22222a;
    color: #e2e8f0;
}
QListWidget, QTreeWidget, QTextEdit, QPlainTextEdit, QLineEdit, QSpinBox, QComboBox {
    background-color: #16161b;
    border: 1px solid #32323e;
    border-radius: 6px;
    padding: 5px 8px;
    color: #f1f5f9;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}
QListWidget::item {
    border-radius: 6px;
    padding: 4px;
}
QListWidget::item:selected {
    background-color: #2563eb;
    color: #ffffff;
}
QListWidget::item:hover:!selected {
    background-color: #24242e;
}
QScrollArea, QScrollArea > QWidget > QWidget {
    background-color: #1e1e24;
    border: none;
}
QGroupBox {
    background-color: #212129;
    border: 1px solid #30303c;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 14px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #93c5fd;
}
QStatusBar {
    background-color: #1c1c22;
    border-top: 1px solid #2e2e38;
    color: #cbd5e1;
}
QSplitter::handle {
    background-color: #2a2a34;
}
QScrollBar:vertical {
    background: #18181c;
    width: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #383846;
    min-height: 24px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: #4f4f63;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

LIGHT_QSS = """
QMainWindow, QDialog {
    background-color: #f1f5f9;
    color: #0f172a;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}
QWidget {
    color: #0f172a;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}
QMenuBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    padding: 2px 6px;
}
QMenuBar::item {
    background: transparent;
    padding: 5px 10px;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background-color: #e2e8f0;
}
QMenu {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #2563eb;
    color: #ffffff;
}
QToolBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    spacing: 2px;
    padding: 4px 6px;
}
QToolBar::separator {
    background-color: #cbd5e1;
    width: 1px;
    margin: 4px 4px;
}
QToolButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 6px;
    color: #1e293b;
    font-weight: 500;
}
QToolButton:hover {
    background-color: #f1f5f9;
    border-color: #cbd5e1;
}
QToolButton:checked, QToolButton:pressed {
    background-color: #2563eb;
    border-color: #1d4ed8;
    color: #ffffff;
}
QPushButton {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 6px 12px;
    color: #0f172a;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #f8fafc;
    border-color: #94a3b8;
}
QPushButton:pressed {
    background-color: #e2e8f0;
}
QPushButton[primary="true"] {
    background-color: #2563eb;
    border-color: #1d4ed8;
    color: #ffffff;
    font-weight: 600;
}
QPushButton[primary="true"]:hover {
    background-color: #1d4ed8;
}
QPushButton[danger="true"] {
    background-color: #dc2626;
    border-color: #b91c1c;
    color: #ffffff;
    font-weight: 600;
}
QPushButton[danger="true"]:hover {
    background-color: #b91c1c;
}
QTabWidget::pane {
    border: 1px solid #cbd5e1;
    background-color: #ffffff;
    border-radius: 4px;
}
QTabBar::tab {
    background-color: #e2e8f0;
    color: #475569;
    border: 1px solid #cbd5e1;
    border-bottom: none;
    padding: 7px 14px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 500;
}
QTabBar::tab:selected {
    background-color: #ffffff;
    color: #0f172a;
    border-bottom: 2px solid #2563eb;
}
QTabBar::tab:hover:!selected {
    background-color: #f1f5f9;
    color: #0f172a;
}
QListWidget, QTreeWidget, QTextEdit, QPlainTextEdit, QLineEdit, QSpinBox, QComboBox {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 5px 8px;
    color: #0f172a;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}
QListWidget::item {
    border-radius: 6px;
    padding: 4px;
}
QListWidget::item:selected {
    background-color: #2563eb;
    color: #ffffff;
}
QListWidget::item:hover:!selected {
    background-color: #f1f5f9;
}
QScrollArea, QScrollArea > QWidget > QWidget {
    background-color: #f8fafc;
    border: none;
}
QGroupBox {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 14px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #1d4ed8;
}
QStatusBar {
    background-color: #ffffff;
    border-top: 1px solid #e2e8f0;
    color: #475569;
}
QSplitter::handle {
    background-color: #e2e8f0;
}
QScrollBar:vertical {
    background: #f1f5f9;
    width: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #cbd5e1;
    min-height: 24px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""


class ThemeManager(QObject):
    """Manages application-wide Dark / Light theme switching and dynamic vector icons."""

    themeChanged = Signal(str)

    def __init__(
        self,
        initial_mode: Optional[ThemeMode] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._settings = QSettings("MePDF", "MePDFEditor")
        if initial_mode is not None:
            self._mode = initial_mode
        else:
            saved = str(self._settings.value("ui/theme", ThemeMode.DARK.value))
            self._mode = ThemeMode.LIGHT if saved == ThemeMode.LIGHT.value else ThemeMode.DARK

    @property
    def mode(self) -> ThemeMode:
        return self._mode

    @property
    def is_dark(self) -> bool:
        return self._mode == ThemeMode.DARK

    def canvas_background_color(self) -> QColor:
        return QColor("#121216") if self.is_dark else QColor("#dfe4ec")

    def set_theme(self, mode: ThemeMode) -> None:
        self._mode = mode
        self._settings.setValue("ui/theme", mode.value)
        self.apply_to_app()
        self.themeChanged.emit(mode.value)

    def toggle_theme(self) -> ThemeMode:
        new_mode = ThemeMode.LIGHT if self.is_dark else ThemeMode.DARK
        self.set_theme(new_mode)
        return new_mode

    def apply_to_app(self) -> None:
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setStyleSheet(DARK_QSS if self.is_dark else LIGHT_QSS)

    def icon(self, name: str, size: int = 20) -> QIcon:
        """Draw a crisp vector icon adapted to the active theme."""
        fg = QColor("#e2e8f0") if self.is_dark else QColor("#1e293b")
        accent = QColor("#60a5fa") if self.is_dark else QColor("#2563eb")
        return create_vector_icon(name, fg, accent, size=size)


def create_vector_icon(
    name: str,
    fg: QColor,
    accent: QColor,
    size: int = 20,
) -> QIcon:
    """Render clean vector toolbar icons using QPainter so no external asset files are needed."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(fg, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)

    s = float(size)
    if name == "open":
        p.drawRect(QRectF(2.5, 5.5, s - 5, s - 8))
        p.drawLine(QPointF(2.5, 5.5), QPointF(7.5, 3.5))
        p.drawLine(QPointF(7.5, 3.5), QPointF(10.0, 5.5))
    elif name == "save":
        p.drawRoundedRect(QRectF(3, 3, s - 6, s - 6), 2, 2)
        p.drawRect(QRectF(6, 3, s - 12, 5))
        p.setBrush(accent)
        p.drawRect(QRectF(5.5, s - 8.5, s - 11, 5.5))
    elif name == "undo":
        path = QPainterPath(QPointF(6, 7))
        path.lineTo(QPointF(3, 10))
        path.lineTo(QPointF(6, 13))
        p.drawPath(path)
        p.drawArc(QRectF(4, 7, 12, 9), 16 * 20, 16 * 150)
    elif name == "redo":
        path = QPainterPath(QPointF(s - 6, 7))
        path.lineTo(QPointF(s - 3, 10))
        path.lineTo(QPointF(s - 6, 13))
        p.drawPath(path)
        p.drawArc(QRectF(4, 7, 12, 9), 16 * 10, 16 * 150)
    elif name == "pan":
        p.drawEllipse(QPointF(s / 2, s / 2), 5.5, 5.5)
        p.drawLine(QPointF(s / 2, 2.5), QPointF(s / 2, s - 2.5))
        p.drawLine(QPointF(2.5, s / 2), QPointF(s - 2.5, s / 2))
    elif name == "highlight":
        p.setPen(QPen(QColor("#eab308"), 2.2))
        p.setBrush(QColor(250, 204, 21, 140))
        p.drawRoundedRect(QRectF(3, 5, s - 6, s - 10), 2, 2)
        p.setPen(pen)
        p.drawLine(QPointF(5, s / 2), QPointF(s - 5, s / 2))
    elif name == "sticky_note":
        p.setBrush(QColor("#facc15"))
        p.setPen(QPen(QColor("#ca8a04"), 1.6))
        p.drawRoundedRect(QRectF(3, 3, s - 6, s - 6), 2.5, 2.5)
        p.drawLine(QPointF(6, 8), QPointF(s - 6, 8))
        p.drawLine(QPointF(6, 12), QPointF(s - 8, 12))
    elif name == "signature":
        p.setPen(QPen(accent, 2.0))
        path = QPainterPath(QPointF(3, s - 6))
        path.cubicTo(QPointF(6, 5), QPointF(10, s - 3), QPointF(13, 8))
        path.quadTo(QPointF(15, 12), QPointF(s - 3, 9))
        p.drawPath(path)
        p.setPen(pen)
        p.drawLine(QPointF(3, s - 3.5), QPointF(s - 3, s - 3.5))
    elif name == "redact":
        p.setBrush(QColor("#111827"))
        p.setPen(QPen(QColor("#ef4444"), 1.8))
        p.drawRect(QRectF(3, 5, s - 6, s - 10))
        p.drawLine(QPointF(5, 7), QPointF(s - 5, s - 7))
    elif name == "organize":
        w = (s - 8) / 2
        p.drawRect(QRectF(3, 3, w, w))
        p.drawRect(QRectF(5 + w, 3, w, w))
        p.drawRect(QRectF(3, 5 + w, w, w))
        p.setBrush(accent)
        p.drawRect(QRectF(5 + w, 5 + w, w, w))
    elif name == "rotate_left":
        p.drawArc(QRectF(4, 4, s - 8, s - 8), 16 * 30, 16 * 250)
        p.drawLine(QPointF(4, 8), QPointF(8, 8))
        p.drawLine(QPointF(4, 8), QPointF(4, 4))
    elif name == "rotate_right":
        p.drawArc(QRectF(4, 4, s - 8, s - 8), 16 * 100, -16 * 250)
        p.drawLine(QPointF(s - 4, 8), QPointF(s - 8, 8))
        p.drawLine(QPointF(s - 4, 8), QPointF(s - 4, 4))
    elif name == "encrypt":
        p.drawRoundedRect(QRectF(4, 9, s - 8, s - 11), 2, 2)
        p.drawArc(QRectF(6, 3.5, s - 12, 10), 0, 16 * 180)
    elif name == "theme_dark":
        p.setBrush(QColor("#fbbf24"))
        p.setPen(QPen(QColor("#f59e0b"), 1.6))
        p.drawEllipse(QPointF(s / 2, s / 2), 5.5, 5.5)
    elif name == "theme_light":
        p.setBrush(QColor("#60a5fa"))
        p.setPen(QPen(QColor("#3b82f6"), 1.6))
        p.drawEllipse(QPointF(s / 2, s / 2), 5.5, 5.5)
    else:
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, name[:2].upper())

    p.end()
    return QIcon(pix)
