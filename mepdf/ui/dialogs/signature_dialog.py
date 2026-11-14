"""3-Mode Visual E-Signature Creation Dialog (Draw, Type, Upload Image with transparent background)."""

from __future__ import annotations

from typing import Optional
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mepdf.core.signature_store import SavedSignature, SignatureStore


def draw_checkerboard(painter: QPainter, width: int, height: int, tile: int = 10) -> None:
    """Draw a subtle alpha-transparency checkerboard background."""
    c1 = QColor("#f8fafc")
    c2 = QColor("#e2e8f0")
    for y in range(0, height, tile):
        for x in range(0, width, tile):
            painter.fillRect(
                x,
                y,
                tile,
                tile,
                c1 if ((x // tile + y // tile) % 2 == 0) else c2,
            )


class SignatureDrawingPad(QWidget):
    """Interactive freehand signature drawing canvas."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(480, 180)
        self.strokes: list[list[tuple[float, float]]] = []
        self._current_stroke: list[tuple[float, float]] = []
        self.ink_color = QColor("#0f296b")
        self.pen_width = 3.2

    def clear_pad(self) -> None:
        self.strokes.clear()
        self._current_stroke.clear()
        self.update()

    def has_ink(self) -> bool:
        return any(len(s) > 0 for s in self.strokes)

    def to_qimage(self) -> QImage:
        return SignatureStore.render_strokes_signature(
            self.strokes,
            canvas_size=(max(300, self.width()), max(140, self.height())),
            ink_color=self.ink_color,
            pen_width=self.pen_width,
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            self._current_stroke = [(pos.x(), pos.y())]
            self.strokes.append(self._current_stroke)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton and self._current_stroke:
            pos = event.position()
            self._current_stroke.append((pos.x(), pos.y()))
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._current_stroke = []
            self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        draw_checkerboard(painter, self.width(), self.height(), tile=12)

        # Baseline guide
        guide_y = int(self.height() * 0.76)
        painter.setPen(QPen(QColor("#94a3b8"), 1, Qt.PenStyle.DashLine))
        painter.drawLine(30, guide_y, self.width() - 30, guide_y)
        painter.drawText(34, guide_y - 6, "Sign Here")

        # Draw strokes
        pen = QPen(
            self.ink_color,
            self.pen_width,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        painter.setPen(pen)
        for stroke in self.strokes:
            if not stroke:
                continue
            if len(stroke) == 1:
                painter.drawPoint(QPointF(stroke[0][0], stroke[0][1]))
                continue
            path = QPainterPath(QPointF(stroke[0][0], stroke[0][1]))
            for i in range(1, len(stroke)):
                prev = QPointF(stroke[i - 1][0], stroke[i - 1][1])
                curr = QPointF(stroke[i][0], stroke[i][1])
                mid = QPointF((prev.x() + curr.x()) / 2.0, (prev.y() + curr.y()) / 2.0)
                path.quadTo(prev, mid)
            path.lineTo(QPointF(stroke[-1][0], stroke[-1][1]))
            painter.drawPath(path)

        # Border
        painter.setPen(QPen(QColor("#64748b"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)


class SignatureDialog(QDialog):
    """Modal dialog for creating an E-Signature via Draw, Type, or Image Upload."""

    INK_COLORS = [
        ("Classic Navy Blue", QColor("#0f296b")),
        ("Jet Black", QColor("#111827")),
        ("Deep Crimson", QColor("#991b1b")),
        ("Emerald Ink", QColor("#065f46")),
    ]

    SCRIPT_FONTS = [
        "Segoe Script",
        "Lucida Handwriting",
        "Gabriola",
        "Brush Script MT",
        "Monotype Corsiva",
        "Georgia",
    ]

    def __init__(
        self,
        signature_store: SignatureStore,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create E-Signature")
        self.resize(580, 440)
        self.signature_store = signature_store

        self._uploaded_raw_image: Optional[QImage] = None
        self._result_image: Optional[QImage] = None
        self._saved_signature: Optional[SavedSignature] = None

        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Ink color bar shared across Draw & Type tabs
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Ink Color:"))
        self.color_combo = QComboBox()
        for label, color in self.INK_COLORS:
            self.color_combo.addItem(label, color)
        self.color_combo.currentIndexChanged.connect(self._on_ink_color_changed)
        top_bar.addWidget(self.color_combo)
        top_bar.addStretch()
        root.addLayout(top_bar)

        # 3-Mode Tab Widget
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, stretch=1)

        # --- Tab 1: Draw ---
        draw_tab = QWidget()
        draw_layout = QVBoxLayout(draw_tab)
        self.drawing_pad = SignatureDrawingPad()
        draw_layout.addWidget(self.drawing_pad, stretch=1)

        draw_controls = QHBoxLayout()
        draw_controls.addWidget(QLabel("Stroke Width:"))
        self.width_slider = QSlider(Qt.Orientation.Horizontal)
        self.width_slider.setRange(15, 70)
        self.width_slider.setValue(32)
        self.width_slider.valueChanged.connect(self._on_stroke_width_changed)
        draw_controls.addWidget(self.width_slider)
        clear_btn = QPushButton("Clear Pad")
        clear_btn.clicked.connect(self.drawing_pad.clear_pad)
        draw_controls.addWidget(clear_btn)
        draw_layout.addLayout(draw_controls)
        self.tabs.addTab(draw_tab, "✒ Draw Signature")

        # --- Tab 2: Type ---
        type_tab = QWidget()
        type_layout = QVBoxLayout(type_tab)
        form = QFormLayout()
        self.type_input = QLineEdit("Alex Rivera")
        self.type_input.setPlaceholderText("Type your full name or initials...")
        self.type_input.textChanged.connect(self._update_typed_preview)
        form.addRow("Your Name:", self.type_input)

        self.font_combo = QComboBox()
        for f in self.SCRIPT_FONTS:
            self.font_combo.addItem(f)
        self.font_combo.currentIndexChanged.connect(self._update_typed_preview)
        form.addRow("Signature Style:", self.font_combo)
        type_layout.addLayout(form)

        self.type_preview_label = QLabel()
        self.type_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.type_preview_label.setMinimumHeight(140)
        self.type_preview_label.setStyleSheet(
            "background-color: #f8fafc; border: 1px solid #94a3b8; border-radius: 6px;"
        )
        type_layout.addWidget(self.type_preview_label, stretch=1)
        self.tabs.addTab(type_tab, "⌨ Type Signature")

        # --- Tab 3: Upload Image ---
        upload_tab = QWidget()
        upload_layout = QVBoxLayout(upload_tab)
        upload_top = QHBoxLayout()
        browse_btn = QPushButton("Browse Signature Image (.png / .jpg)...")
        browse_btn.setProperty("primary", True)
        browse_btn.clicked.connect(self._on_browse_image)
        upload_top.addWidget(browse_btn)

        self.remove_bg_check = QCheckBox("Remove white background (make transparent)")
        self.remove_bg_check.setChecked(True)
        self.remove_bg_check.toggled.connect(self._update_upload_preview)
        upload_top.addWidget(self.remove_bg_check)
        upload_layout.addLayout(upload_top)

        self.upload_preview_label = QLabel("No signature image uploaded yet.")
        self.upload_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.upload_preview_label.setMinimumHeight(150)
        self.upload_preview_label.setStyleSheet(
            "background-color: #f8fafc; color: #334155; border: 1px dashed #94a3b8; border-radius: 6px;"
        )
        upload_layout.addWidget(self.upload_preview_label, stretch=1)
        self.tabs.addTab(upload_tab, "🖼 Upload Image")

        # --- Save to Library Option ---
        save_row = QHBoxLayout()
        self.save_to_lib_check = QCheckBox(
            "Save to My Signatures library for 1-click reuse"
        )
        self.save_to_lib_check.setChecked(True)
        save_row.addWidget(self.save_to_lib_check)

        save_row.addWidget(QLabel("Label:"))
        self.sig_label_input = QLineEdit("Primary Signature")
        self.sig_label_input.setMaximumWidth(200)
        save_row.addWidget(self.sig_label_input)
        root.addLayout(save_row)

        # Dialog Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Use Signature")
        ok_btn.setProperty("primary", True)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._update_typed_preview()

    def _current_ink_color(self) -> QColor:
        color = self.color_combo.currentData()
        return color if isinstance(color, QColor) else QColor("#0f296b")

    def _on_ink_color_changed(self) -> None:
        self.drawing_pad.ink_color = self._current_ink_color()
        self.drawing_pad.update()
        self._update_typed_preview()

    def _on_stroke_width_changed(self, value: int) -> None:
        self.drawing_pad.pen_width = value / 10.0
        self.drawing_pad.update()

    def _update_typed_preview(self) -> None:
        img = SignatureStore.render_typed_signature(
            self.type_input.text(),
            font_family=self.font_combo.currentText(),
            ink_color=self._current_ink_color(),
        )
        self.type_preview_label.setPixmap(QPixmap.fromImage(img))

    def _on_browse_image(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Signature Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp)",
        )
        if not file_path:
            return
        loaded = QImage(file_path)
        if loaded.isNull():
            QMessageBox.warning(self, "Invalid Image", "Could not load the selected image file.")
            return
        self._uploaded_raw_image = loaded
        self._update_upload_preview()

    def _get_processed_upload_image(self) -> QImage:
        if self._uploaded_raw_image is None or self._uploaded_raw_image.isNull():
            return QImage()
        if self.remove_bg_check.isChecked():
            return SignatureStore.remove_white_background(self._uploaded_raw_image)
        return self._uploaded_raw_image.convertToFormat(QImage.Format.Format_ARGB32)

    def _update_upload_preview(self) -> None:
        img = self._get_processed_upload_image()
        if img.isNull():
            return
        scaled = img.scaled(
            420,
            130,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.upload_preview_label.setPixmap(QPixmap.fromImage(scaled))

    def _build_active_signature_image(self) -> QImage:
        idx = self.tabs.currentIndex()
        if idx == 0:
            if not self.drawing_pad.has_ink():
                return QImage()
            return self.drawing_pad.to_qimage()
        if idx == 1:
            if not self.type_input.text().strip():
                return QImage()
            return SignatureStore.render_typed_signature(
                self.type_input.text(),
                font_family=self.font_combo.currentText(),
                ink_color=self._current_ink_color(),
            )
        return self._get_processed_upload_image()

    def _on_accept(self) -> None:
        img = self._build_active_signature_image()
        if img.isNull():
            QMessageBox.information(
                self,
                "Signature Empty",
                "Please draw, type, or upload a signature before continuing.",
            )
            return
        self._result_image = img
        if self.save_to_lib_check.isChecked():
            label = self.sig_label_input.text().strip() or "My Signature"
            self._saved_signature = self.signature_store.save_signature(label, img)
        self.accept()

    def result_png_bytes(self) -> bytes:
        if self._result_image is None or self._result_image.isNull():
            return b""
        return SignatureStore.qimage_to_png_bytes(self._result_image)

    @property
    def saved_signature(self) -> Optional[SavedSignature]:
        return self._saved_signature
