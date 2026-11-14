"""Interactive QGraphicsView PDF canvas supporting Continuous & Single-Page views and all 5 tool modes."""

from __future__ import annotations

from typing import Optional
from PySide6.QtCore import QPointF, QRectF, Qt, QThreadPool, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSceneMouseEvent,
    QGraphicsView,
    QInputDialog,
    QMenu,
    QWidget,
)

from mepdf.core.document_controller import PDFDocumentController, ToolMode, ViewMode
from mepdf.core.render_worker import PageRenderWorker


class CrispPagePixmapItem(QGraphicsPixmapItem):
    """
    Page pixmap item that snaps its target device position to exact integer physical pixels
    and draws 1:1 without sub-pixel bilinear smearing on High-DPI displays (e.g. 125% / 150%).
    """

    def paint(self, painter: QPainter, option, widget=None) -> None:
        pix = self.pixmap()
        if pix.isNull():
            return
        wt = painter.worldTransform()
        if (
            abs(wt.m11() - 1.0) < 1e-4
            and abs(wt.m22() - 1.0) < 1e-4
            and abs(wt.m12()) < 1e-4
            and abs(wt.m21()) < 1e-4
        ):
            dev = painter.device()
            dpr = dev.devicePixelRatioF() if dev is not None else 1.0
            if dpr <= 0.0:
                dpr = 1.0
            tx = wt.dx()
            ty = wt.dy()
            corr_x = (round(tx * dpr) / dpr) - tx
            corr_y = (round(ty * dpr) / dpr) - ty
            prev_smooth = bool(
                painter.renderHints() & QPainter.RenderHint.SmoothPixmapTransform
            )
            if prev_smooth:
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            painter.drawPixmap(QPointF(corr_x, corr_y), pix)
            if prev_smooth:
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            return
        super().paint(painter, option, widget)


class SignatureOverlayItem(QGraphicsObject):
    """
    Interactive movable & resizable E-Signature placement overlay on the PDF canvas.
    Includes a bottom-right resize handle and clickable 'Stamp' / 'Cancel' action pills.
    """

    HANDLE_SIZE = 12.0
    BAR_HEIGHT = 26.0

    def __init__(
        self,
        png_bytes: bytes,
        initial_rect: QRectF,
        page_index: int,
        on_commit,
        on_cancel,
    ) -> None:
        super().__init__()
        self.png_bytes = png_bytes
        self.page_index = page_index
        self._on_commit = on_commit
        self._on_cancel = on_cancel

        img = QImage.fromData(png_bytes)
        self._pixmap = QPixmap.fromImage(img)
        self._box = QRectF(0, 0, initial_rect.width(), initial_rect.height())
        self.setPos(initial_rect.topLeft())
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setZValue(50)
        self._resizing = False
        self._resize_start_pos = QPointF()
        self._resize_start_box = QRectF()

    def boundingRect(self) -> QRectF:
        return QRectF(
            -4,
            -self.BAR_HEIGHT - 6,
            max(self._box.width() + 8, 170),
            self._box.height() + self.BAR_HEIGHT + 12,
        )

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def signature_scene_rect(self) -> QRectF:
        return QRectF(self.pos(), self._box.size())

    def _handle_rect(self) -> QRectF:
        return QRectF(
            self._box.width() - self.HANDLE_SIZE,
            self._box.height() - self.HANDLE_SIZE,
            self.HANDLE_SIZE,
            self.HANDLE_SIZE,
        )

    def _stamp_btn_rect(self) -> QRectF:
        return QRectF(0, -self.BAR_HEIGHT - 2, 92, self.BAR_HEIGHT)

    def _cancel_btn_rect(self) -> QRectF:
        return QRectF(96, -self.BAR_HEIGHT - 2, 68, self.BAR_HEIGHT)

    def paint(self, painter: QPainter, _option, _widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # Translucent highlight backdrop
        painter.setBrush(QColor(59, 130, 246, 28))
        painter.setPen(QPen(QColor("#2563eb"), 1.8, Qt.PenStyle.DashLine))
        painter.drawRect(self._box)

        # Draw signature pixmap keeping aspect ratio inside _box
        if not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self._box.size().toSize(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            dx = (self._box.width() - scaled.width()) / 2.0
            dy = (self._box.height() - scaled.height()) / 2.0
            painter.drawPixmap(int(dx), int(dy), scaled)

        # Resize corner handle
        painter.setBrush(QColor("#2563eb"))
        painter.setPen(QPen(QColor("#ffffff"), 1.2))
        painter.drawRect(self._handle_rect())

        # Floating Stamp / Cancel action pills
        font = QFont("Segoe UI", 9, QFont.Weight.DemiBold)
        painter.setFont(font)

        stamp_r = self._stamp_btn_rect()
        painter.setBrush(QColor("#16a34a"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(stamp_r, 5, 5)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(stamp_r, Qt.AlignmentFlag.AlignCenter, "✔ Stamp")

        cancel_r = self._cancel_btn_rect()
        painter.setBrush(QColor("#dc2626"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(cancel_r, 5, 5)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(cancel_r, Qt.AlignmentFlag.AlignCenter, "✖ Cancel")

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        pos = event.pos()
        if self._stamp_btn_rect().contains(pos):
            event.accept()
            QTimer.singleShot(0, lambda: self._on_commit(self))
            return
        if self._cancel_btn_rect().contains(pos):
            event.accept()
            QTimer.singleShot(0, self._on_cancel)
            return
        if self._handle_rect().adjusted(-4, -4, 4, 4).contains(pos):
            self._resizing = True
            self._resize_start_pos = event.scenePos()
            self._resize_start_box = QRectF(self._box)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._resizing:
            delta = event.scenePos() - self._resize_start_pos
            new_w = max(60.0, self._resize_start_box.width() + delta.x())
            new_h = max(30.0, self._resize_start_box.height() + delta.y())
            self.prepareGeometryChange()
            self._box.setWidth(new_w)
            self._box.setHeight(new_h)
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._resizing:
            self._resizing = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        event.accept()
        QTimer.singleShot(0, lambda: self._on_commit(self))


class PDFCanvasView(QGraphicsView):
    """
    Central interactive PDF viewer & editor canvas.
    Supports Continuous Vertical Scroll and Single-Page View, async rendering,
    Smart Highlights, Sticky Notes, E-Signature overlay placement, and Redaction drawing.
    """

    PAGE_GAP = 18.0

    def __init__(
        self,
        controller: PDFDocumentController,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

        self._thread_pool = QThreadPool.globalInstance()
        self._render_token: int = 0
        self._page_items: dict[int, QGraphicsPixmapItem] = {}
        self._page_scene_rects: dict[int, QRectF] = {}
        self._updating_scroll_page = False
        self._last_dpr: float = self._effective_dpr()

        # Rubber-band selection state for Highlight & Redact tools
        self._drag_start_scene: Optional[QPointF] = None
        self._drag_page_index: Optional[int] = None
        self._rubber_band_item: Optional[QGraphicsRectItem] = None

        # Active E-Signature placement overlay & interaction state
        self._signature_overlay: Optional[SignatureOverlayItem] = None
        self._last_signature_png: bytes = b""
        self._sig_moving: bool = False
        self._sig_resizing: bool = False
        self._sig_drag_start_scene: QPointF = QPointF()
        self._sig_start_pos: QPointF = QPointF()
        self._sig_start_box: QRectF = QRectF()

        # Search highlight flash item
        self._search_flash_item: Optional[QGraphicsRectItem] = None

        # Wire controller signals
        self.controller.documentLoaded.connect(self.rebuild_layout)
        self.controller.pagesStructureChanged.connect(self.rebuild_layout)
        self.controller.pageContentChanged.connect(self._on_page_content_changed)
        self.controller.zoomChanged.connect(self._on_zoom_changed)
        self.controller.viewModeChanged.connect(self._on_view_mode_changed)
        self.controller.pageChanged.connect(self._on_controller_page_changed)
        self.controller.toolModeChanged.connect(self._on_tool_mode_changed)
        self.controller.signaturePlacementRequested.connect(self.spawn_signature_overlay)

        self.verticalScrollBar().valueChanged.connect(self._on_vertical_scroll)
        self._on_tool_mode_changed(self.controller.tool_mode.value)
        if self.controller.page_count > 0:
            self.rebuild_layout()

    def _effective_dpr(self) -> float:
        dpr = self.devicePixelRatioF()
        if dpr <= 0.0:
            app = QApplication.instance()
            if isinstance(app, QApplication) and app.primaryScreen():
                dpr = app.primaryScreen().devicePixelRatio()
        return max(1.0, float(dpr))

    def paintEvent(self, event) -> None:
        cur_dpr = self._effective_dpr()
        if abs(cur_dpr - self._last_dpr) > 1e-3:
            self._last_dpr = cur_dpr
            QTimer.singleShot(0, lambda: self._on_page_content_changed(-1))
        super().paintEvent(event)

    def set_canvas_background(self, color: QColor) -> None:
        self.setBackgroundBrush(QBrush(color))

    # ------------------------------------------------------------------
    # Layout & Rendering
    # ------------------------------------------------------------------
    def rebuild_layout(self) -> None:
        """Rebuild the scene page items for either Continuous or Single-Page view."""
        self._render_token += 1
        self._clear_transient_items()
        self._scene.clear()
        self._page_items.clear()
        self._page_scene_rects.clear()

        dims = self.controller.get_page_dimensions()
        if not dims:
            self._scene.setSceneRect(QRectF(0, 0, 400, 400))
            return

        zoom = self.controller.zoom
        dpr = self._effective_dpr()
        self._last_dpr = dpr
        is_continuous = self.controller.view_mode == ViewMode.CONTINUOUS
        pages_to_show = (
            list(range(len(dims)))
            if is_continuous
            else [max(0, min(self.controller.current_page, len(dims) - 1))]
        )

        y_cursor = round(self.PAGE_GAP)
        max_width = 0.0

        for idx in pages_to_show:
            w_pt, h_pt = dims[idx]
            w_px = w_pt * zoom
            h_px = h_pt * zoom
            max_width = max(max_width, w_px)

        for idx in pages_to_show:
            w_pt, h_pt = dims[idx]
            w_px = w_pt * zoom
            h_px = h_pt * zoom
            x_offset = round((max_width - w_px) / 2.0 + self.PAGE_GAP)
            page_rect = QRectF(x_offset, round(y_cursor), w_px, h_px)
            self._page_scene_rects[idx] = page_rect

            # Drop shadow & white page placeholder
            shadow = self._scene.addRect(
                page_rect.translated(3, 4),
                QPen(Qt.PenStyle.NoPen),
                QBrush(QColor(0, 0, 0, 75)),
            )
            shadow.setZValue(0)

            bg = self._scene.addRect(
                page_rect,
                QPen(QColor("#64748b"), 0.8),
                QBrush(QColor("#ffffff")),
            )
            bg.setZValue(1)

            pix_item = CrispPagePixmapItem()
            pix_item.setPos(page_rect.topLeft())
            pix_item.setZValue(2)
            self._scene.addItem(pix_item)
            self._page_items[idx] = pix_item

            y_cursor = round(y_cursor + h_px + self.PAGE_GAP)

        self._scene.setSceneRect(
            QRectF(0, 0, round(max_width + self.PAGE_GAP * 2), y_cursor)
        )

        # Render current page synchronously for instant visual feedback, others async
        cur = self.controller.current_page
        if cur in self._page_items:
            qimg = self.controller.render_page_image(cur, zoom=zoom, dpr=dpr)
            if not qimg.isNull():
                self._page_items[cur].setPixmap(QPixmap.fromImage(qimg))

        for idx in pages_to_show:
            if idx != cur:
                self._schedule_page_render(idx, zoom, self._render_token, dpr=dpr)

    def _schedule_page_render(
        self,
        page_index: int,
        zoom: float,
        token: int,
        dpr: Optional[float] = None,
    ) -> None:
        use_dpr = dpr if dpr is not None else self._effective_dpr()
        worker = PageRenderWorker(
            self.controller.pdf_bytes,
            page_index,
            zoom,
            token=token,
            dpr=use_dpr,
        )
        worker.signals.rendered.connect(self._on_worker_rendered)
        self._thread_pool.start(worker)

    def _on_worker_rendered(
        self,
        page_index: int,
        _zoom: float,
        token: int,
        image: QImage,
    ) -> None:
        if token != self._render_token or image.isNull():
            return
        item = self._page_items.get(page_index)
        if item is not None:
            item.setPixmap(QPixmap.fromImage(image))

    def _on_page_content_changed(self, page_index: int) -> None:
        """Re-render modified page(s) in-place without losing scroll position."""
        self._render_token += 1
        zoom = self.controller.zoom
        dpr = self._effective_dpr()
        self._last_dpr = dpr
        for idx, item in self._page_items.items():
            if idx == page_index or page_index < 0 or idx == self.controller.current_page:
                qimg = self.controller.render_page_image(idx, zoom=zoom, dpr=dpr)
                if not qimg.isNull():
                    item.setPixmap(QPixmap.fromImage(qimg))
            else:
                self._schedule_page_render(idx, zoom, self._render_token, dpr=dpr)

    def _on_zoom_changed(self, _new_zoom: float) -> None:
        target_page = self.controller.current_page
        self.rebuild_layout()
        self.scroll_to_page(target_page)

    def _on_view_mode_changed(self, _mode: str) -> None:
        target_page = self.controller.current_page
        self.rebuild_layout()
        self.scroll_to_page(target_page)

    def _on_controller_page_changed(self, page_index: int) -> None:
        if self._updating_scroll_page:
            return
        if self.controller.view_mode == ViewMode.SINGLE_PAGE:
            self.rebuild_layout()
        else:
            self.scroll_to_page(page_index)

    def scroll_to_page(self, page_index: int) -> None:
        rect = self._page_scene_rects.get(page_index)
        if rect is not None:
            self._updating_scroll_page = True
            self.centerOn(rect.center().x(), rect.top() + self.viewport().height() / 3)
            self._updating_scroll_page = False

    def flash_pdf_rect(
        self,
        page_index: int,
        pdf_rect: tuple[float, float, float, float],
    ) -> None:
        """Scroll to `page_index` and highlight a search match rectangle on the canvas."""
        self.controller.set_current_page(page_index)
        page_scene_rect = self._page_scene_rects.get(page_index)
        if page_scene_rect is None:
            return
        zoom = self.controller.zoom
        x0, y0, x1, y1 = pdf_rect
        scene_r = QRectF(
            page_scene_rect.left() + x0 * zoom - 3,
            page_scene_rect.top() + y0 * zoom - 3,
            (x1 - x0) * zoom + 6,
            (y1 - y0) * zoom + 6,
        )
        if self._search_flash_item is not None:
            self._scene.removeItem(self._search_flash_item)
            self._search_flash_item = None

        pen = QPen(QColor("#2563eb"), 2.2)
        brush = QBrush(QColor(59, 130, 246, 70))
        self._search_flash_item = self._scene.addRect(scene_r, pen, brush)
        self._search_flash_item.setZValue(35)
        self.centerOn(scene_r.center())

    def fit_to_width(self) -> None:
        dims = self.controller.get_page_dimensions()
        if not dims:
            return
        w_pt, _ = dims[self.controller.current_page]
        avail_w = max(200.0, self.viewport().width() - self.PAGE_GAP * 3)
        self.controller.set_zoom(avail_w / w_pt)

    def fit_to_page(self) -> None:
        dims = self.controller.get_page_dimensions()
        if not dims:
            return
        w_pt, h_pt = dims[self.controller.current_page]
        avail_w = max(200.0, self.viewport().width() - self.PAGE_GAP * 3)
        avail_h = max(200.0, self.viewport().height() - self.PAGE_GAP * 3)
        self.controller.set_zoom(min(avail_w / w_pt, avail_h / h_pt))

    def _on_vertical_scroll(self, _value: int) -> None:
        if (
            self._updating_scroll_page
            or self.controller.view_mode != ViewMode.CONTINUOUS
            or not self._page_scene_rects
        ):
            return
        viewport_center = self.mapToScene(self.viewport().rect().center())
        best_page = self.controller.current_page
        best_dist = float("inf")
        for idx, rect in self._page_scene_rects.items():
            if rect.contains(viewport_center):
                best_page = idx
                break
            dist = abs(rect.center().y() - viewport_center.y())
            if dist < best_dist:
                best_dist = dist
                best_page = idx
        if best_page != self.controller.current_page:
            self._updating_scroll_page = True
            self.controller.set_current_page(best_page)
            self._updating_scroll_page = False

    # ------------------------------------------------------------------
    # Coordinate Mapping Helpers
    # ------------------------------------------------------------------
    def _page_at_scene_pos(self, scene_pos: QPointF) -> Optional[int]:
        for idx, rect in self._page_scene_rects.items():
            if rect.contains(scene_pos):
                return idx
        return None

    def _scene_rect_to_pdf_rect(
        self,
        page_index: int,
        scene_rect: QRectF,
    ) -> tuple[float, float, float, float]:
        page_rect = self._page_scene_rects[page_index]
        clipped = scene_rect.intersected(page_rect)
        zoom = self.controller.zoom
        x0 = (clipped.left() - page_rect.left()) / zoom
        y0 = (clipped.top() - page_rect.top()) / zoom
        x1 = (clipped.right() - page_rect.left()) / zoom
        y1 = (clipped.bottom() - page_rect.top()) / zoom
        return (x0, y0, x1, y1)

    def _scene_point_to_pdf_point(
        self,
        page_index: int,
        scene_pos: QPointF,
    ) -> tuple[float, float]:
        page_rect = self._page_scene_rects[page_index]
        zoom = self.controller.zoom
        x = (scene_pos.x() - page_rect.left()) / zoom
        y = (scene_pos.y() - page_rect.top()) / zoom
        return (x, y)

    # ------------------------------------------------------------------
    # Tool Modes & Interactive Handlers
    # ------------------------------------------------------------------
    def _on_tool_mode_changed(self, mode_str: str) -> None:
        self._clear_rubber_band()
        if mode_str != ToolMode.SIGNATURE.value:
            self._remove_signature_overlay()

        if mode_str == ToolMode.PAN.value:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)

    def spawn_signature_overlay(self, png_bytes: bytes) -> None:
        """Create a movable, resizable signature box on the current page."""
        if not png_bytes or not self._page_scene_rects:
            return
        self._last_signature_png = png_bytes
        self._remove_signature_overlay()

        cur_page = self.controller.current_page
        if cur_page not in self._page_scene_rects:
            cur_page = next(iter(self._page_scene_rects.keys()))
        page_rect = self._page_scene_rects[cur_page]

        img = QImage.fromData(png_bytes)
        aspect = (img.width() / max(1, img.height())) if not img.isNull() else 2.6
        box_w = min(220.0 * self.controller.zoom, page_rect.width() * 0.45)
        box_h = max(45.0, box_w / max(0.8, aspect))

        # Place near center of visible viewport on current page
        view_center_scene = self.mapToScene(self.viewport().rect().center())
        cx = max(page_rect.left() + 20, min(view_center_scene.x() - box_w / 2, page_rect.right() - box_w - 20))
        cy = max(page_rect.top() + 35, min(view_center_scene.y() - box_h / 2, page_rect.bottom() - box_h - 20))

        initial_rect = QRectF(cx, cy, box_w, box_h)
        self._signature_overlay = SignatureOverlayItem(
            png_bytes=png_bytes,
            initial_rect=initial_rect,
            page_index=cur_page,
            on_commit=self._commit_signature_overlay,
            on_cancel=self._cancel_signature_overlay,
        )
        self._scene.addItem(self._signature_overlay)

    def _commit_signature_overlay(self, overlay: SignatureOverlayItem) -> None:
        sig_scene_rect = overlay.signature_scene_rect()
        page_idx = self._page_at_scene_pos(sig_scene_rect.center())
        if page_idx is None:
            page_idx = overlay.page_index
        if page_idx in self._page_scene_rects:
            pdf_rect = self._scene_rect_to_pdf_rect(page_idx, sig_scene_rect)
            png_bytes = overlay.png_bytes
            self._remove_signature_overlay()
            self.controller.stamp_signature(page_idx, pdf_rect, png_bytes)
            self.controller.set_tool_mode(ToolMode.PAN)

    def _cancel_signature_overlay(self) -> None:
        self._remove_signature_overlay()
        self.controller.set_tool_mode(ToolMode.PAN)

    def _remove_signature_overlay(self) -> None:
        self._sig_moving = False
        self._sig_resizing = False
        if self._signature_overlay is not None:
            if self._signature_overlay.scene() is self._scene:
                self._scene.removeItem(self._signature_overlay)
            self._signature_overlay = None

    def _clear_rubber_band(self) -> None:
        if self._rubber_band_item is not None:
            if self._rubber_band_item.scene() is self._scene:
                self._scene.removeItem(self._rubber_band_item)
            self._rubber_band_item = None
        self._drag_start_scene = None
        self._drag_page_index = None

    def _clear_transient_items(self) -> None:
        self._clear_rubber_band()
        self._remove_signature_overlay()
        self._search_flash_item = None

    # ------------------------------------------------------------------
    # Mouse & Wheel Events
    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())
        mode = self.controller.tool_mode

        # Handle active E-Signature overlay interactions (Stamp, Cancel, Resize, Move) directly
        if self._signature_overlay is not None and event.button() == Qt.MouseButton.LeftButton:
            local_pt = self._signature_overlay.mapFromScene(scene_pos)
            if self._signature_overlay._stamp_btn_rect().contains(local_pt):
                self._commit_signature_overlay(self._signature_overlay)
                event.accept()
                return
            if self._signature_overlay._cancel_btn_rect().contains(local_pt):
                self._cancel_signature_overlay()
                event.accept()
                return
            if self._signature_overlay._handle_rect().adjusted(-6, -6, 6, 6).contains(local_pt):
                self._sig_resizing = True
                self._sig_drag_start_scene = scene_pos
                self._sig_start_box = QRectF(self._signature_overlay._box)
                event.accept()
                return
            if self._signature_overlay._box.contains(local_pt):
                self._sig_moving = True
                self._sig_drag_start_scene = scene_pos
                self._sig_start_pos = QPointF(self._signature_overlay.pos())
                event.accept()
                return

        page_idx = self._page_at_scene_pos(scene_pos)
        if page_idx is not None and page_idx != self.controller.current_page:
            self._updating_scroll_page = True
            self.controller.set_current_page(page_idx)
            self._updating_scroll_page = False

        if event.button() == Qt.MouseButton.RightButton and page_idx is not None:
            if self._try_context_menu_on_annotation(page_idx, scene_pos, event.globalPosition().toPoint()):
                return

        if event.button() == Qt.MouseButton.LeftButton and page_idx is not None:
            if mode == ToolMode.PAN:
                if self._try_click_annotation(page_idx, scene_pos):
                    return
            elif mode == ToolMode.STICKY_NOTE:
                pdf_pt = self._scene_point_to_pdf_point(page_idx, scene_pos)
                text, ok = QInputDialog.getMultiLineText(
                    self,
                    "Add Sticky Note",
                    f"Enter note text for Page {page_idx + 1}:",
                    "",
                )
                if ok and text.strip():
                    self.controller.add_sticky_note(page_idx, pdf_pt, text.strip())
                return
            elif mode in (ToolMode.HIGHLIGHT, ToolMode.REDACT):
                self._drag_start_scene = scene_pos
                self._drag_page_index = page_idx
                if mode == ToolMode.HIGHLIGHT:
                    r, g, b = self.controller.highlight_color
                    qc = QColor(int(r * 255), int(g * 255), int(b * 255))
                    pen = QPen(qc.darker(120), 1.8, Qt.PenStyle.SolidLine)
                    brush = QBrush(QColor(qc.red(), qc.green(), qc.blue(), 95))
                else:
                    pen = QPen(QColor("#ef4444"), 2.0, Qt.PenStyle.DashLine)
                    brush = QBrush(QColor(239, 68, 68, 75))
                self._rubber_band_item = self._scene.addRect(
                    QRectF(scene_pos, scene_pos), pen, brush
                )
                self._rubber_band_item.setZValue(40)
                event.accept()
                return
            elif mode == ToolMode.SIGNATURE and self._last_signature_png:
                # Move existing signature overlay (or spawn if missing) centered at click point
                if self._signature_overlay is None:
                    self.spawn_signature_overlay(self._last_signature_png)
                if self._signature_overlay is not None:
                    box = self._signature_overlay._box
                    self._signature_overlay.page_index = page_idx
                    new_pos = QPointF(
                        scene_pos.x() - box.width() / 2.0,
                        scene_pos.y() - box.height() / 2.0,
                    )
                    self._signature_overlay.setPos(new_pos)
                    self._sig_moving = True
                    self._sig_drag_start_scene = scene_pos
                    self._sig_start_pos = new_pos
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        curr_scene = self.mapToScene(event.position().toPoint())
        if self._signature_overlay is not None:
            if self._sig_resizing:
                delta = curr_scene - self._sig_drag_start_scene
                new_w = max(60.0, self._sig_start_box.width() + delta.x())
                new_h = max(30.0, self._sig_start_box.height() + delta.y())
                self._signature_overlay.prepareGeometryChange()
                self._signature_overlay._box.setWidth(new_w)
                self._signature_overlay._box.setHeight(new_h)
                self._signature_overlay.update()
                event.accept()
                return
            if self._sig_moving:
                delta = curr_scene - self._sig_drag_start_scene
                self._signature_overlay.setPos(self._sig_start_pos + delta)
                event.accept()
                return

        if (
            self._drag_start_scene is not None
            and self._rubber_band_item is not None
            and self._drag_page_index is not None
        ):
            page_rect = self._page_scene_rects[self._drag_page_index]
            raw_box = QRectF(self._drag_start_scene, curr_scene).normalized()
            if raw_box.height() < 8.0 and raw_box.width() >= 4.0:
                raw_box.adjust(0, -5.0, 0, 5.0)
            box = raw_box.intersected(page_rect)
            self._rubber_band_item.setRect(box)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and (
            self._sig_moving or self._sig_resizing
        ):
            self._sig_moving = False
            self._sig_resizing = False
            event.accept()
            return

        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._drag_start_scene is not None
            and self._rubber_band_item is not None
            and self._drag_page_index is not None
        ):
            box = self._rubber_band_item.rect()
            page_idx = self._drag_page_index
            self._clear_rubber_band()
            if box.width() >= 4.0 or box.height() >= 4.0:
                page_rect = self._page_scene_rects[page_idx]
                if box.height() < 8.0:
                    box = box.adjusted(0, -5.0, 0, 5.0).intersected(page_rect)
                if box.width() < 4.0:
                    box = box.adjusted(-4.0, 0, 4.0, 0).intersected(page_rect)
                pdf_rect = self._scene_rect_to_pdf_rect(page_idx, box)
                if self.controller.tool_mode == ToolMode.HIGHLIGHT:
                    self.controller.add_highlight(page_idx, pdf_rect)
                elif self.controller.tool_mode == ToolMode.REDACT:
                    self.controller.add_redaction(page_idx, pdf_rect)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            factor = 1.15 if delta > 0 else (1.0 / 1.15)
            self.controller.set_zoom(self.controller.zoom * factor)
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self._signature_overlay is not None:
                self._cancel_signature_overlay()
                return
            self.controller.set_tool_mode(ToolMode.PAN)
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._signature_overlay is not None:
                self._commit_signature_overlay(self._signature_overlay)
                return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Annotation Click & Context Menu Inspection
    # ------------------------------------------------------------------
    def _annotation_at_scene_pos(self, page_index: int, scene_pos: QPointF):
        pdf_pt = self._scene_point_to_pdf_point(page_index, scene_pos)
        px, py = pdf_pt
        for annot in self.controller.list_annotations(page_index=page_index):
            x0, y0, x1, y1 = annot.rect
            if (x0 - 6) <= px <= (x1 + 6) and (y0 - 6) <= py <= (y1 + 6):
                return annot
        return None

    def _try_click_annotation(self, page_index: int, scene_pos: QPointF) -> bool:
        annot = self._annotation_at_scene_pos(page_index, scene_pos)
        if annot is None or annot.annot_type != "StickyNote":
            return False
        new_text, ok = QInputDialog.getMultiLineText(
            self,
            f"Sticky Note (Page {page_index + 1})",
            "View or edit sticky note content:",
            annot.content,
        )
        if ok and new_text != annot.content:
            self.controller.update_annotation_text(page_index, annot.xref, new_text)
        return True

    def _try_context_menu_on_annotation(
        self,
        page_index: int,
        scene_pos: QPointF,
        global_pos,
    ) -> bool:
        annot = self._annotation_at_scene_pos(page_index, scene_pos)
        if annot is None:
            return False
        menu = QMenu(self)
        edit_act = None
        if annot.annot_type == "StickyNote":
            edit_act = menu.addAction("📝 Edit Sticky Note...")
        del_act = menu.addAction(f"🗑 Delete {annot.annot_type}")
        chosen = menu.exec(global_pos)
        if chosen is None:
            return True
        if edit_act is not None and chosen == edit_act:
            new_text, ok = QInputDialog.getMultiLineText(
                self,
                "Edit Sticky Note",
                "Note content:",
                annot.content,
            )
            if ok:
                self.controller.update_annotation_text(page_index, annot.xref, new_text)
        elif chosen == del_act:
            self.controller.delete_annotation(page_index, annot.xref)
        return True
