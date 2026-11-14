"""Left sidebar Search & Redact panel for full-text search, highlight, and batch redaction."""

from __future__ import annotations

from typing import Callable, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mepdf.core.document_controller import PDFDocumentController
from mepdf.core.mupdf_engine import SearchMatch


class SearchRedactPanel(QWidget):
    """Full-text search panel with 1-click Highlight or Mark for Redaction."""

    MATCH_ROLE = Qt.ItemDataRole.UserRole + 1

    def __init__(
        self,
        controller: PDFDocumentController,
        on_focus_rect: Optional[Callable[[int, tuple[float, float, float, float]], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self._on_focus_rect = on_focus_rect
        self._matches: list[SearchMatch] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        search_row = QHBoxLayout()
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Find text or sensitive terms...")
        self.query_input.returnPressed.connect(self.run_search)
        search_row.addWidget(self.query_input, stretch=1)

        btn_find = QPushButton("Find")
        btn_find.setProperty("primary", True)
        btn_find.clicked.connect(self.run_search)
        search_row.addWidget(btn_find)
        root.addLayout(search_row)

        self.status_label = QLabel("Enter a search term above.")
        root.addWidget(self.status_label)

        self.results_list = QListWidget()
        self.results_list.itemClicked.connect(self._on_match_clicked)
        root.addWidget(self.results_list, stretch=1)

        # Quick markup actions on search matches
        btn_hl = QPushButton("🟨 Highlight Selected Match")
        btn_hl.clicked.connect(self._highlight_selected_match)
        root.addWidget(btn_hl)

        btn_red_sel = QPushButton("⬛ Mark Selected for Redaction")
        btn_red_sel.clicked.connect(self._redact_selected_match)
        root.addWidget(btn_red_sel)

        btn_red_all = QPushButton("⬛ Mark ALL Matches for Redaction")
        btn_red_all.setProperty("danger", True)
        btn_red_all.clicked.connect(self._redact_all_matches)
        root.addWidget(btn_red_all)

    def run_search(self) -> int:
        query = self.query_input.text().strip()
        self.results_list.clear()
        self._matches = self.controller.search_text(query)
        self.status_label.setText(f"Found {len(self._matches)} match(es)")

        for m in self._matches:
            item = QListWidgetItem(f"Page {m.page_index + 1}: {m.snippet}")
            item.setData(self.MATCH_ROLE, m)
            self.results_list.addItem(item)
        return len(self._matches)

    def _selected_match(self) -> Optional[SearchMatch]:
        item = self.results_list.currentItem()
        if item is None:
            return None
        m = item.data(self.MATCH_ROLE)
        return m if isinstance(m, SearchMatch) else None

    def _on_match_clicked(self, item: QListWidgetItem) -> None:
        m = item.data(self.MATCH_ROLE)
        if isinstance(m, SearchMatch) and self._on_focus_rect is not None:
            self._on_focus_rect(m.page_index, m.rect)

    def _highlight_selected_match(self) -> None:
        m = self._selected_match()
        if m is not None:
            self.controller.add_highlight(m.page_index, m.rect, smart_snap=False)

    def _redact_selected_match(self) -> None:
        m = self._selected_match()
        if m is not None:
            self.controller.add_redaction(m.page_index, m.rect)

    def _redact_all_matches(self) -> None:
        if self._matches:
            self.controller.add_batch_redactions(self._matches)
