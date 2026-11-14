"""Left sidebar Annotations panel listing all Highlights, Sticky Notes, and Pending Redactions."""

from __future__ import annotations

from typing import Callable, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mepdf.core.document_controller import PDFDocumentController, ToolMode
from mepdf.core.mupdf_engine import AnnotationInfo


class AnnotationListPanel(QWidget):
    """Lists all annotations across the PDF with quick navigation, note editing, and deletion."""

    ANNOT_DATA_ROLE = Qt.ItemDataRole.UserRole + 1

    def __init__(
        self,
        controller: PDFDocumentController,
        on_focus_rect: Optional[Callable[[int, tuple[float, float, float, float]], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self._on_focus_rect = on_focus_rect
        self._build_ui()

        self.controller.documentLoaded.connect(self.refresh_list)
        self.controller.pagesStructureChanged.connect(self.refresh_list)
        self.controller.annotationsUpdated.connect(self.refresh_list)
        if self.controller.page_count > 0:
            self.refresh_list()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        btn_add_note = QPushButton("➕ Add Sticky Note on Page")
        btn_add_note.setProperty("primary", True)
        btn_add_note.clicked.connect(
            lambda: self.controller.set_tool_mode(ToolMode.STICKY_NOTE)
        )
        root.addWidget(btn_add_note)

        self.summary_label = QLabel("0 annotations")
        root.addWidget(self.summary_label)

        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        root.addWidget(self.list_widget, stretch=1)

        btn_row = QHBoxLayout()
        self.btn_edit = QPushButton("📝 Edit Note")
        self.btn_edit.clicked.connect(self._edit_selected)
        btn_row.addWidget(self.btn_edit)

        self.btn_delete = QPushButton("🗑 Delete")
        self.btn_delete.setProperty("danger", True)
        self.btn_delete.clicked.connect(self._delete_selected)
        btn_row.addWidget(self.btn_delete)
        root.addLayout(btn_row)

    def refresh_list(self) -> None:
        self.list_widget.clear()
        annots = self.controller.list_annotations()
        self.summary_label.setText(f"{len(annots)} annotation(s) in document")

        for a in annots:
            badge = (
                "🟨 Highlight"
                if a.annot_type == "Highlight"
                else ("📝 Sticky Note" if a.annot_type == "StickyNote" else "⬛ Pending Redact")
            )
            detail = a.content.strip() or a.title or a.annot_type
            text = f"[Page {a.page_index + 1}] {badge}\n{detail}"
            item = QListWidgetItem(text)
            item.setData(self.ANNOT_DATA_ROLE, a)
            self.list_widget.addItem(item)

    def _selected_annot(self) -> Optional[AnnotationInfo]:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        data = item.data(self.ANNOT_DATA_ROLE)
        return data if isinstance(data, AnnotationInfo) else None

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        annot = item.data(self.ANNOT_DATA_ROLE)
        if isinstance(annot, AnnotationInfo):
            self.controller.set_current_page(annot.page_index)
            if self._on_focus_rect is not None:
                self._on_focus_rect(annot.page_index, annot.rect)

    def _on_item_double_clicked(self, _item: QListWidgetItem) -> None:
        self._edit_selected()

    def _edit_selected(self) -> None:
        annot = self._selected_annot()
        if annot is None:
            return
        new_text, ok = QInputDialog.getMultiLineText(
            self,
            f"Edit {annot.annot_type} (Page {annot.page_index + 1})",
            "Note / Comment Text:",
            annot.content,
        )
        if ok:
            self.controller.update_annotation_text(annot.page_index, annot.xref, new_text)

    def _delete_selected(self) -> None:
        annot = self._selected_annot()
        if annot is None:
            return
        self.controller.delete_annotation(annot.page_index, annot.xref)
