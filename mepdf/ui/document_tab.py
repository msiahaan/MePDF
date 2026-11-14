"""Per-document tab widget combining Left Navigation Sidebar, Center PDFCanvasView, and Right InspectorPanel."""

from __future__ import annotations

from typing import Callable, Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QSplitter, QTabWidget, QVBoxLayout, QWidget

from mepdf.core.document_controller import PDFDocumentController
from mepdf.core.signature_store import SignatureStore
from mepdf.ui.dialogs.encryption_dialog import EncryptionDialog
from mepdf.ui.dialogs.organize_pages_dialog import OrganizePagesDialog, SplitPDFDialog
from mepdf.ui.dialogs.signature_dialog import SignatureDialog
from mepdf.ui.panels.annotation_panel import AnnotationListPanel
from mepdf.ui.panels.inspector_panel import InspectorPanel
from mepdf.ui.panels.search_redact_panel import SearchRedactPanel
from mepdf.ui.panels.thumbnail_panel import ThumbnailPanel
from mepdf.ui.pdf_canvas import PDFCanvasView


class DocumentTabWidget(QWidget):
    """Self-contained workspace for a single open PDF document tab."""

    def __init__(
        self,
        controller: PDFDocumentController,
        signature_store: SignatureStore,
        on_signatures_changed: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.signature_store = signature_store
        self._on_signatures_changed = on_signatures_changed

        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(self.splitter)

        # 1. Left Navigation Dock (Pages | Annotations | Search & Redact)
        self.left_tabs = QTabWidget()
        self.left_tabs.setMinimumWidth(210)
        self.left_tabs.setMaximumWidth(340)

        self.canvas = PDFCanvasView(self.controller)

        self.thumbnail_panel = ThumbnailPanel(
            self.controller,
            on_open_organize_dialog=self.open_organize_pages_dialog,
        )
        self.annotation_panel = AnnotationListPanel(
            self.controller,
            on_focus_rect=self.canvas.flash_pdf_rect,
        )
        self.search_panel = SearchRedactPanel(
            self.controller,
            on_focus_rect=self.canvas.flash_pdf_rect,
        )

        self.left_tabs.addTab(self.thumbnail_panel, "📄 Pages")
        self.left_tabs.addTab(self.annotation_panel, "📝 Notes")
        self.left_tabs.addTab(self.search_panel, "🔍 Search")
        self.splitter.addWidget(self.left_tabs)

        # 2. Center Interactive PDF Canvas
        self.splitter.addWidget(self.canvas)

        # 3. Right Contextual Inspector
        self.inspector_panel = InspectorPanel(
            self.controller,
            self.signature_store,
            on_open_signature_dialog=self.open_signature_dialog,
            on_open_encryption_dialog=self.open_encryption_dialog,
        )
        self.inspector_panel.setMinimumWidth(250)
        self.inspector_panel.setMaximumWidth(350)
        self.splitter.addWidget(self.inspector_panel)

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([235, 820, 280])

    def set_canvas_background(self, color: QColor) -> None:
        self.canvas.set_canvas_background(color)

    def focus_search_tab(self) -> None:
        self.left_tabs.setCurrentWidget(self.search_panel)
        self.search_panel.query_input.setFocus()
        self.search_panel.query_input.selectAll()

    def open_signature_dialog(self) -> None:
        dlg = SignatureDialog(self.signature_store, self)
        if dlg.exec():
            if self._on_signatures_changed is not None:
                self._on_signatures_changed()
            else:
                self.inspector_panel.refresh_signature_library()
            png_bytes = dlg.result_png_bytes()
            if png_bytes:
                self.controller.request_signature_placement(png_bytes)
        else:
            self.controller.set_tool_mode(self.controller.tool_mode)

    def open_organize_pages_dialog(self) -> None:
        if self.controller.page_count == 0:
            return
        dlg = OrganizePagesDialog(self.controller, self)
        dlg.exec()

    def open_split_dialog(self) -> None:
        if self.controller.page_count == 0:
            return
        dlg = SplitPDFDialog(self.controller, self)
        dlg.exec()

    def open_encryption_dialog(self) -> None:
        dlg = EncryptionDialog(self.controller.encryption_config, self)
        if dlg.exec():
            self.controller.set_encryption_config(dlg.result_config())
