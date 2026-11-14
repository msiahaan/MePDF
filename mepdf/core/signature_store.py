"""Local signature store and image processing for visual E-Signatures (Draw, Type, Upload)."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import uuid
from typing import Optional
from PySide6.QtCore import QBuffer, QIODevice, QPointF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath, QPen


@dataclass(frozen=True)
class SavedSignature:
    """Represents a locally saved reusable visual E-Signature."""

    sig_id: str
    name: str
    png_path: str

    def load_image(self) -> QImage:
        return QImage(self.png_path)

    def load_png_bytes(self) -> bytes:
        p = Path(self.png_path)
        return p.read_bytes() if p.exists() else b""


class SignatureStore:
    """Manages creating, rendering, background-cleaning, and persisting E-Signatures."""

    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        self.storage_dir = storage_dir or (Path.home() / ".mepdf" / "signatures")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.storage_dir / "signatures.json"

    @staticmethod
    def qimage_to_png_bytes(image: QImage) -> bytes:
        """Encode a QImage as PNG bytes in memory."""
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buf, "PNG")
        return bytes(buf.data())

    @staticmethod
    def remove_white_background(image: QImage, threshold: int = 235) -> QImage:
        """
        Convert near-white background pixels to transparent alpha while preserving
        smooth anti-aliased signature ink edges.
        """
        if image.isNull():
            return QImage()
        rgba = image.convertToFormat(QImage.Format.Format_ARGB32)
        width = rgba.width()
        height = rgba.height()

        for y in range(height):
            for x in range(width):
                c = rgba.pixelColor(x, y)
                if c.alpha() == 0:
                    continue
                lum = (c.red() * 299 + c.green() * 587 + c.blue() * 114) // 1000
                if lum >= threshold:
                    rgba.setPixelColor(x, y, QColor(255, 255, 255, 0))
                elif lum >= threshold - 35:
                    # Smooth feather transition for anti-aliased edges
                    alpha_scale = (threshold - lum) / 35.0
                    new_alpha = int(max(0, min(255, c.alpha() * alpha_scale)))
                    rgba.setPixelColor(x, y, QColor(c.red(), c.green(), c.blue(), new_alpha))
        return SignatureStore.crop_to_non_transparent(rgba)

    @staticmethod
    def crop_to_non_transparent(image: QImage, padding: int = 10) -> QImage:
        """Tightly crop a transparent QImage around non-transparent ink pixels."""
        if image.isNull():
            return image
        rgba = image.convertToFormat(QImage.Format.Format_ARGB32)
        w, h = rgba.width(), rgba.height()
        min_x, min_y = w, h
        max_x, max_y = -1, -1

        for y in range(h):
            for x in range(w):
                if rgba.pixelColor(x, y).alpha() > 12:
                    if x < min_x:
                        min_x = x
                    if y < min_y:
                        min_y = y
                    if x > max_x:
                        max_x = x
                    if y > max_y:
                        max_y = y

        if max_x < min_x or max_y < min_y:
            return rgba

        x0 = max(0, min_x - padding)
        y0 = max(0, min_y - padding)
        x1 = min(w - 1, max_x + padding)
        y1 = min(h - 1, max_y + padding)
        return rgba.copy(x0, y0, x1 - x0 + 1, y1 - y0 + 1)

    @staticmethod
    def render_typed_signature(
        text: str,
        font_family: str = "Segoe Script",
        ink_color: QColor = QColor("#0f296b"),
        font_size: int = 44,
    ) -> QImage:
        """Render a stylized typed signature string into a transparent QImage."""
        clean_text = text.strip() or "Signature"
        font = QFont(font_family, font_size)
        font.setItalic(True)
        metrics = QFontMetrics(font)
        rect = metrics.boundingRect(clean_text)
        width = max(260, rect.width() + 60)
        height = max(100, rect.height() + 40)

        img = QImage(width, height, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)

        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(font)
        painter.setPen(QPen(ink_color, 2))
        painter.drawText(img.rect(), Qt.AlignmentFlag.AlignCenter, clean_text)
        painter.end()

        return SignatureStore.crop_to_non_transparent(img, padding=12)

    @staticmethod
    def render_strokes_signature(
        strokes: list[list[tuple[float, float]]],
        canvas_size: tuple[int, int] = (520, 200),
        ink_color: QColor = QColor("#0f296b"),
        pen_width: float = 3.2,
    ) -> QImage:
        """Render freehand drawn strokes into a cropped transparent QImage."""
        w, h = canvas_size
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)

        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(ink_color, pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        for stroke in strokes:
            if not stroke:
                continue
            if len(stroke) == 1:
                pt = stroke[0]
                painter.drawPoint(QPointF(pt[0], pt[1]))
                continue
            path = QPainterPath(QPointF(stroke[0][0], stroke[0][1]))
            for i in range(1, len(stroke)):
                prev = QPointF(stroke[i - 1][0], stroke[i - 1][1])
                curr = QPointF(stroke[i][0], stroke[i][1])
                mid = QPointF((prev.x() + curr.x()) / 2.0, (prev.y() + curr.y()) / 2.0)
                path.quadTo(prev, mid)
            path.lineTo(QPointF(stroke[-1][0], stroke[-1][1]))
            painter.drawPath(path)

        painter.end()
        return SignatureStore.crop_to_non_transparent(img, padding=10)

    def list_signatures(self) -> list[SavedSignature]:
        """Return all saved signatures from the local signature library."""
        if not self.index_path.exists():
            return []
        try:
            items = json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        results: list[SavedSignature] = []
        for entry in items:
            png_path = Path(entry.get("png_path", ""))
            if png_path.exists():
                results.append(
                    SavedSignature(
                        sig_id=entry["sig_id"],
                        name=entry.get("name", "Signature"),
                        png_path=str(png_path),
                    )
                )
        return results

    def save_signature(self, name: str, image: QImage) -> SavedSignature:
        """Save a transparent QImage signature to the local signature library."""
        sig_id = uuid.uuid4().hex[:10]
        png_path = self.storage_dir / f"sig_{sig_id}.png"
        cropped = self.crop_to_non_transparent(image, padding=10)
        cropped.save(str(png_path), "PNG")

        existing = [
            {"sig_id": s.sig_id, "name": s.name, "png_path": s.png_path}
            for s in self.list_signatures()
        ]
        new_entry = SavedSignature(
            sig_id=sig_id,
            name=name.strip() or "My Signature",
            png_path=str(png_path),
        )
        existing.append(
            {
                "sig_id": new_entry.sig_id,
                "name": new_entry.name,
                "png_path": new_entry.png_path,
            }
        )
        self.index_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        return new_entry

    def delete_signature(self, sig_id: str) -> None:
        """Delete a saved signature by ID."""
        remaining = []
        for s in self.list_signatures():
            if s.sig_id == sig_id:
                try:
                    Path(s.png_path).unlink(missing_ok=True)
                except OSError:
                    pass
            else:
                remaining.append(
                    {"sig_id": s.sig_id, "name": s.name, "png_path": s.png_path}
                )
        self.index_path.write_text(json.dumps(remaining, indent=2), encoding="utf-8")
