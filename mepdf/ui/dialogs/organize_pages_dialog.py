"""Multi-column 'Organize Pages' Grid Dialog, Split PDF Dialog, and range parser powered by pikepdf."""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mepdf.core.document_controller import PDFDocumentController
from mepdf.core.mupdf_engine import MuPDFEngine
from mepdf.core.pikepdf_engine import PikePDFEngine


def parse_page_ranges(range_text: str, total_pages: int) -> list[tuple[int, int]]:
    """
    Parse a human-friendly 1-based page range string like '1-3, 5, 7-9' into
    0-based inclusive `(start_idx, end_idx)` tuples.
    """
    ranges: list[tuple[int, int]] = []
    if total_pages <= 0:
        return ranges
    for part in range_text.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            pieces = token.split("-", 1)
            start_1 = int(pieces[0].strip())
            end_1 = int(pieces[1].strip())
        else:
            start_1 = int(token)
            end_1 = start_1
        s0 = max(0, min(start_1 - 1, total_pages - 1))
        e0 = max(s0, min(end_1 - 1, total_pages - 1))
        ranges.append((s0, e0))
    return ranges


class SplitPDFDialog(QDialog):
    """Dialog for splitting a PDF into multiple files by page ranges or every N pages."""

    def __init__(
        self,
        controller: PDFDocumentController,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Split / Extract PDF Pages")
        self.resize(460, 280)
        self.controller = controller
        self._created_files: list[str] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        total = self.controller.page_count

        info = QLabel(f"Document has <b>{total}</b> page(s). Choose how to split:")
        root.addWidget(info)

        self.radio_ranges = QRadioButton("Split by Page Ranges (e.g. 1-2, 3-5, 6):")
        self.radio_ranges.setChecked(True)
        root.addWidget(self.radio_ranges)

        self.range_input = QLineEdit(f"1-{max(1, total // 2)}, {max(1, total // 2) + 1}-{total}" if total > 1 else "1")
        root.addWidget(self.range_input)

        self.radio_every_n = QRadioButton("Split every N pages:")
        root.addWidget(self.radio_every_n)

        n_row = QHBoxLayout()
        n_row.addWidget(QLabel("Pages per output file:"))
        self.spin_every_n = QSpinBox()
        self.spin_every_n.setRange(1, max(1, total))
        self.spin_every_n.setValue(1)
        n_row.addWidget(self.spin_every_n)
        n_row.addStretch()
        root.addLayout(n_row)

        form = QFormLayout()
        self.prefix_input = QLineEdit(Path(self.controller.raw_title).stem)
        form.addRow("Output Filename Prefix:", self.prefix_input)
        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Choose Output Folder & Split...")
        ok_btn.setProperty("primary", True)
        buttons.accepted.connect(self._on_split)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_split(self) -> None:
        total = self.controller.page_count
        if self.radio_ranges.isChecked():
            try:
                ranges = parse_page_ranges(self.range_input.text(), total)
            except ValueError:
                QMessageBox.warning(
                    self,
                    "Invalid Range",
                    "Please enter valid page numbers or ranges separated by commas (e.g. 1-3, 4-6).",
                )
                return
        else:
            step = self.spin_every_n.value()
            ranges = [
                (i, min(i + step - 1, total - 1)) for i in range(0, total, step)
            ]

        if not ranges:
            QMessageBox.warning(self, "No Pages", "Please specify at least one valid page range.")
            return

        out_dir = QFileDialog.getExistingDirectory(self, "Select Output Folder for Split PDFs")
        if not out_dir:
            return

        prefix = self.prefix_input.text().strip() or "split"
        self._created_files = PikePDFEngine.split_pdf(
            self.controller.pdf_bytes,
            ranges,
            out_dir,
            prefix=prefix,
        )
        QMessageBox.information(
            self,
            "Split Complete",
            f"Successfully created {len(self._created_files)} PDF file(s) in:\n{out_dir}",
        )
        self.accept()

    @property
    def created_files(self) -> list[str]:
        return self._created_files


class OrganizePagesDialog(QDialog):
    """
    Adobe Acrobat-style multi-column 'Organize Pages' modal grid view.
    Supports drag-and-drop page reordering, batch rotation, deletion, blank page insertion,
    merging external PDFs, extracting selected pages, and splitting.
    """

    PAGE_INDEX_ROLE = Qt.ItemDataRole.UserRole + 1

    def __init__(
        self,
        controller: PDFDocumentController,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Organize Pages — {controller.raw_title}")
        self.resize(920, 620)
        self.controller = controller
        self._syncing = False
        self._build_ui()
        self._populate_grid()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Action Toolbar
        action_bar = QHBoxLayout()

        btn_rot_ccw = QPushButton("↺ Rotate Left")
        btn_rot_ccw.clicked.connect(lambda: self._rotate_selected(-90))
        action_bar.addWidget(btn_rot_ccw)

        btn_rot_cw = QPushButton("↻ Rotate Right")
        btn_rot_cw.clicked.connect(lambda: self._rotate_selected(90))
        action_bar.addWidget(btn_rot_cw)

        btn_delete = QPushButton("🗑 Delete Selected")
        btn_delete.setProperty("danger", True)
        btn_delete.clicked.connect(self._delete_selected)
        action_bar.addWidget(btn_delete)

        btn_blank = QPushButton("📄+ Insert Blank Page")
        btn_blank.clicked.connect(self._insert_blank)
        action_bar.addWidget(btn_blank)

        btn_merge = QPushButton("📑 Merge / Insert PDF...")
        btn_merge.clicked.connect(self._merge_external_pdf)
        action_bar.addWidget(btn_merge)

        btn_extract = QPushButton("📤 Extract Selected...")
        btn_extract.clicked.connect(self._extract_selected)
        action_bar.addWidget(btn_extract)

        btn_split = QPushButton("✂ Split PDF...")
        btn_split.clicked.connect(self._open_split_dialog)
        action_bar.addWidget(btn_split)

        action_bar.addStretch()
        root.addLayout(action_bar)

        # Quick Selection Bar
        sel_bar = QHBoxLayout()
        sel_bar.addWidget(QLabel("Quick Select:"))
        for label, mode in [
            ("All", "all"),
            ("Even Pages", "even"),
            ("Odd Pages", "odd"),
            ("Clear Selection", "none"),
        ]:
            b = QPushButton(label)
            b.clicked.connect(lambda _checked=False, m=mode: self._quick_select(m))
            sel_bar.addWidget(b)
        sel_bar.addStretch()
        sel_bar.addWidget(
            QLabel("Tip: Drag and drop thumbnails to reorder pages. Use Ctrl/Shift+Click for multi-select.")
        )
        root.addLayout(sel_bar)

        # Multi-column Thumbnail Grid
        self.grid = QListWidget()
        self.grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid.setIconSize(QSize(150, 200))
        self.grid.setGridSize(QSize(185, 240))
        self.grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.grid.setMovement(QListWidget.Movement.Snap)
        self.grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.grid.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.grid.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.grid.model().rowsMoved.connect(self._on_rows_moved)
        root.addWidget(self.grid, stretch=1)

        # Footer Close Button
        footer = QHBoxLayout()
        self.status_label = QLabel()
        footer.addWidget(self.status_label)
        footer.addStretch()
        close_btn = QPushButton("Done")
        close_btn.setProperty("primary", True)
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        root.addLayout(footer)

    def _populate_grid(self) -> None:
        self._syncing = True
        self.grid.clear()
        total = self.controller.page_count
        pdf_bytes = self.controller.pdf_bytes
        dpr = max(1.0, self.devicePixelRatioF())

        for idx in range(total):
            qimg = MuPDFEngine.render_page(pdf_bytes, idx, zoom=0.28, dpr=dpr)
            pix = QPixmap.fromImage(qimg)
            item = QListWidgetItem(QIcon(pix), f"Page {idx + 1}")
            item.setData(self.PAGE_INDEX_ROLE, idx)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            self.grid.addItem(item)

        if 0 <= self.controller.current_page < self.grid.count():
            self.grid.setCurrentRow(self.controller.current_page)

        self.status_label.setText(f"Total Pages: {total}")
        self._syncing = False

    def _selected_indices(self) -> list[int]:
        indices = []
        for item in self.grid.selectedItems():
            idx = item.data(self.PAGE_INDEX_ROLE)
            if isinstance(idx, int):
                indices.append(idx)
        return sorted(set(indices))

    def _on_rows_moved(self, *_args) -> None:
        if self._syncing:
            return
        new_order: list[int] = []
        for row in range(self.grid.count()):
            item = self.grid.item(row)
            idx = item.data(self.PAGE_INDEX_ROLE)
            if isinstance(idx, int):
                new_order.append(idx)
        if len(new_order) == self.controller.page_count and new_order != list(
            range(self.controller.page_count)
        ):
            self.controller.reorder_pages(new_order)
            self._populate_grid()

    def _quick_select(self, mode: str) -> None:
        self.grid.clearSelection()
        for row in range(self.grid.count()):
            page_num = row + 1
            if mode == "all":
                self.grid.item(row).setSelected(True)
            elif mode == "even" and page_num % 2 == 0:
                self.grid.item(row).setSelected(True)
            elif mode == "odd" and page_num % 2 == 1:
                self.grid.item(row).setSelected(True)

    def _rotate_selected(self, angle_delta: int) -> None:
        sel = self._selected_indices()
        if not sel:
            QMessageBox.information(self, "Select Pages", "Please select at least one page to rotate.")
            return
        self.controller.rotate_pages(sel, angle_delta)
        self._populate_grid()
        for idx in sel:
            if 0 <= idx < self.grid.count():
                self.grid.item(idx).setSelected(True)

    def _delete_selected(self) -> None:
        sel = self._selected_indices()
        if not sel:
            QMessageBox.information(self, "Select Pages", "Please select at least one page to delete.")
            return
        if len(sel) >= self.controller.page_count:
            QMessageBox.warning(
                self,
                "Cannot Delete All Pages",
                "A PDF document must contain at least one page.",
            )
            return
        self.controller.delete_pages(sel)
        self._populate_grid()

    def _insert_blank(self) -> None:
        sel = self._selected_indices()
        insert_idx = (sel[-1] + 1) if sel else self.controller.page_count
        self.controller.insert_blank_page(index=insert_idx)
        self._populate_grid()

    def _merge_external_pdf(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select PDF Files to Merge / Insert",
            "",
            "PDF Documents (*.pdf)",
        )
        if not files:
            return
        sel = self._selected_indices()
        insert_at = (sel[-1] + 1) if sel else self.controller.page_count
        try:
            self.controller.merge_pdfs(files, insert_at=insert_at)
            self._populate_grid()
        except Exception as exc:
            QMessageBox.critical(self, "Merge Failed", f"Failed to merge PDF files:\n{exc}")

    def _extract_selected(self) -> None:
        sel = self._selected_indices()
        if not sel:
            QMessageBox.information(self, "Select Pages", "Please select the pages you want to extract.")
            return
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Extracted Pages As",
            f"{Path(self.controller.raw_title).stem}_extracted.pdf",
            "PDF Documents (*.pdf)",
        )
        if not out_path:
            return
        extracted_bytes = PikePDFEngine.extract_pages_to_bytes(self.controller.pdf_bytes, sel)
        Path(out_path).write_bytes(extracted_bytes)
        QMessageBox.information(
            self,
            "Extraction Complete",
            f"Extracted {len(sel)} page(s) to:\n{out_path}",
        )

    def _open_split_dialog(self) -> None:
        dlg = SplitPDFDialog(self.controller, self)
        dlg.exec()
