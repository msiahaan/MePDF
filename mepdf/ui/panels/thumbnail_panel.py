"""Left sidebar Page Thumbnail panel with drag-and-drop reordering and pikepdf context menu."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional
from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mepdf.core.document_controller import PDFDocumentController
from mepdf.core.mupdf_engine import MuPDFEngine
from mepdf.core.pikepdf_engine import PikePDFEngine


class ThumbnailPanel(QWidget):
    """Displays page thumbnails with drag-and-drop reordering and quick pikepdf actions."""

    PAGE_INDEX_ROLE = Qt.ItemDataRole.UserRole + 1

    def __init__(
        self,
        controller: PDFDocumentController,
        on_open_organize_dialog: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self._on_open_organize_dialog = on_open_organize_dialog
        self._syncing = False

        self._build_ui()
        self.controller.documentLoaded.connect(self.refresh_thumbnails)
        self.controller.pagesStructureChanged.connect(self.refresh_thumbnails)
        self.controller.pageContentChanged.connect(self._on_single_page_updated)
        self.controller.pageChanged.connect(self._on_current_page_changed)
        if self.controller.page_count > 0:
            self.refresh_thumbnails()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # Mini action bar
        top_row = QHBoxLayout()
        top_row.setSpacing(4)

        btn_rot_l = QPushButton("↺")
        btn_rot_l.setToolTip("Rotate Current Page Left (-90°)")
        btn_rot_l.clicked.connect(lambda: self._rotate_current(-90))
        top_row.addWidget(btn_rot_l)

        btn_rot_r = QPushButton("↻")
        btn_rot_r.setToolTip("Rotate Current Page Right (+90°)")
        btn_rot_r.clicked.connect(lambda: self._rotate_current(90))
        top_row.addWidget(btn_rot_r)

        btn_del = QPushButton("🗑")
        btn_del.setToolTip("Delete Current Page")
        btn_del.clicked.connect(self._delete_current)
        top_row.addWidget(btn_del)

        btn_org = QPushButton("⊞ Grid")
        btn_org.setToolTip("Open Full 'Organize Pages' Multi-Column Grid")
        btn_org.clicked.connect(self._trigger_organize_dialog)
        top_row.addWidget(btn_org)

        root.addLayout(top_row)

        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setIconSize(QSize(115, 155))
        self.list_widget.setGridSize(QSize(145, 185))
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setMovement(QListWidget.Movement.Snap)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self.list_widget.currentRowChanged.connect(self._on_row_selected)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.model().rowsMoved.connect(self._on_rows_moved)

        root.addWidget(self.list_widget, stretch=1)

    def refresh_thumbnails(self) -> None:
        self._syncing = True
        self.list_widget.clear()
        total = self.controller.page_count
        pdf_bytes = self.controller.pdf_bytes
        dpr = max(1.0, self.devicePixelRatioF())

        for idx in range(total):
            qimg = MuPDFEngine.render_page(pdf_bytes, idx, zoom=0.22, dpr=dpr)
            pix = QPixmap.fromImage(qimg)
            item = QListWidgetItem(QIcon(pix), f"Page {idx + 1}")
            item.setData(self.PAGE_INDEX_ROLE, idx)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            self.list_widget.addItem(item)

        if 0 <= self.controller.current_page < self.list_widget.count():
            self.list_widget.setCurrentRow(self.controller.current_page)
        self._syncing = False

    def _on_single_page_updated(self, page_index: int) -> None:
        if 0 <= page_index < self.list_widget.count():
            dpr = max(1.0, self.devicePixelRatioF())
            qimg = MuPDFEngine.render_page(
                self.controller.pdf_bytes, page_index, zoom=0.22, dpr=dpr
            )
            item = self.list_widget.item(page_index)
            if item is not None and not qimg.isNull():
                item.setIcon(QIcon(QPixmap.fromImage(qimg)))
        else:
            self.refresh_thumbnails()

    def _on_current_page_changed(self, page_index: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        if 0 <= page_index < self.list_widget.count():
            self.list_widget.setCurrentRow(page_index)
        self._syncing = False

    def _on_row_selected(self, row: int) -> None:
        if self._syncing or row < 0:
            return
        self.controller.set_current_page(row)

    def _on_rows_moved(self, *_args) -> None:
        if self._syncing:
            return
        new_order: list[int] = []
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            idx = item.data(self.PAGE_INDEX_ROLE)
            if isinstance(idx, int):
                new_order.append(idx)
        if len(new_order) == self.controller.page_count and new_order != list(
            range(self.controller.page_count)
        ):
            self.controller.reorder_pages(new_order)

    def _rotate_current(self, delta: int) -> None:
        if self.controller.page_count > 0:
            self.controller.rotate_pages([self.controller.current_page], delta)

    def _delete_current(self) -> None:
        if self.controller.page_count <= 1:
            QMessageBox.warning(
                self,
                "Cannot Delete Page",
                "Cannot delete the only remaining page in the document.",
            )
            return
        self.controller.delete_pages([self.controller.current_page])

    def _trigger_organize_dialog(self) -> None:
        if self._on_open_organize_dialog is not None:
            self._on_open_organize_dialog()

    def _show_context_menu(self, pos: QPoint) -> None:
        item = self.list_widget.itemAt(pos)
        page_idx = (
            item.data(self.PAGE_INDEX_ROLE)
            if item is not None
            else self.controller.current_page
        )
        if not isinstance(page_idx, int) or self.controller.page_count == 0:
            return

        menu = QMenu(self)
        act_rot_cw = menu.addAction(f"↻ Rotate Page {page_idx + 1} Right (+90°)")
        act_rot_ccw = menu.addAction(f"↺ Rotate Page {page_idx + 1} Left (-90°)")
        menu.addSeparator()
        act_ins_before = menu.addAction(f"📄+ Insert Blank Page Before Page {page_idx + 1}")
        act_ins_after = menu.addAction(f"📄+ Insert Blank Page After Page {page_idx + 1}")
        act_extract = menu.addAction(f"📤 Extract Page {page_idx + 1} to New PDF...")
        menu.addSeparator()
        act_del = menu.addAction(f"🗑 Delete Page {page_idx + 1}")
        menu.addSeparator()
        act_grid = menu.addAction("⊞ Open Organize Pages Grid...")

        chosen = menu.exec(self.list_widget.mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == act_rot_cw:
            self.controller.rotate_pages([page_idx], 90)
        elif chosen == act_rot_ccw:
            self.controller.rotate_pages([page_idx], -90)
        elif chosen == act_ins_before:
            self.controller.insert_blank_page(index=page_idx)
        elif chosen == act_ins_after:
            self.controller.insert_blank_page(index=page_idx + 1)
        elif chosen == act_extract:
            out_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Extracted Page As",
                f"{Path(self.controller.raw_title).stem}_page{page_idx + 1}.pdf",
                "PDF Documents (*.pdf)",
            )
            if out_path:
                data = PikePDFEngine.extract_pages_to_bytes(
                    self.controller.pdf_bytes, [page_idx]
                )
                Path(out_path).write_bytes(data)
        elif chosen == act_del:
            if self.controller.page_count <= 1:
                QMessageBox.warning(
                    self,
                    "Cannot Delete",
                    "Cannot delete the only page in the document.",
                )
            else:
                self.controller.delete_pages([page_idx])
        elif chosen == act_grid:
            self._trigger_organize_dialog()
