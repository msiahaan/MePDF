"""Central per-tab PDF document controller coordinating PyMuPDF, pikepdf, and QUndoStack."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QUndoCommand, QUndoStack

from mepdf.core.mupdf_engine import AnnotationInfo, MuPDFEngine, SearchMatch
from mepdf.core.pikepdf_engine import EncryptionConfig, PikePDFEngine


class ToolMode(str, Enum):
    """Interactive canvas tool modes."""

    PAN = "pan"
    HIGHLIGHT = "highlight"
    STICKY_NOTE = "sticky_note"
    SIGNATURE = "signature"
    REDACT = "redact"


class ViewMode(str, Enum):
    """PDF page display layout modes."""

    CONTINUOUS = "continuous"
    SINGLE_PAGE = "single_page"


class _PDFStateCommand(QUndoCommand):
    """Undo/Redo command storing before/after in-memory PDF byte snapshots."""

    def __init__(
        self,
        controller: "PDFDocumentController",
        description: str,
        old_bytes: bytes,
        new_bytes: bytes,
        old_redacted_flag: bool,
        new_redacted_flag: bool,
        structural_change: bool = False,
        target_page: int = -1,
    ) -> None:
        super().__init__(description)
        self._controller = controller
        self._old_bytes = old_bytes
        self._new_bytes = new_bytes
        self._old_redacted = old_redacted_flag
        self._new_redacted = new_redacted_flag
        self._structural = structural_change
        self._target_page = target_page

    def undo(self) -> None:
        self._controller._apply_snapshot(
            self._old_bytes,
            self._old_redacted,
            structural=self._structural,
            target_page=self._target_page,
        )

    def redo(self) -> None:
        self._controller._apply_snapshot(
            self._new_bytes,
            self._new_redacted,
            structural=self._structural,
            target_page=self._target_page,
        )


class PDFDocumentController(QObject):
    """Manages state, dual-engine operations, and undo/redo for a single open PDF tab."""

    documentLoaded = Signal()
    documentModified = Signal(bool)
    pageChanged = Signal(int)
    pagesStructureChanged = Signal()
    pageContentChanged = Signal(int)
    annotationsUpdated = Signal()
    redactionsUpdated = Signal(int)
    zoomChanged = Signal(float)
    viewModeChanged = Signal(str)
    toolModeChanged = Signal(str)
    encryptionChanged = Signal(bool)
    signaturePlacementRequested = Signal(bytes)  # PNG bytes to place interactively

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._pdf_bytes: bytes = b""
        self._file_path: Optional[str] = None
        self._display_title: str = "Untitled.pdf"
        self._is_modified: bool = False
        self._has_applied_redactions: bool = False
        self._current_page: int = 0
        self._zoom: float = 1.25
        self._view_mode: ViewMode = ViewMode.CONTINUOUS
        self._tool_mode: ToolMode = ToolMode.PAN

        # Active tool settings
        self.highlight_color: tuple[float, float, float] = (1.0, 0.92, 0.23)  # Yellow
        self.sticky_note_color: tuple[float, float, float] = (1.0, 0.84, 0.15)
        self.redact_fill_color: tuple[float, float, float] = (0.0, 0.0, 0.0)  # Black
        self.redact_overlay_text: str = "REDACTED"
        self.scrub_metadata_on_redact: bool = True

        # Security / Encryption state
        self.encryption_config: EncryptionConfig = EncryptionConfig()

        # Undo/Redo stack
        self.undo_stack = QUndoStack(self)
        self.undo_stack.cleanChanged.connect(self._on_clean_changed)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def pdf_bytes(self) -> bytes:
        return self._pdf_bytes

    @property
    def file_path(self) -> Optional[str]:
        return self._file_path

    @property
    def display_title(self) -> str:
        prefix = "* " if self._is_modified else ""
        return f"{prefix}{self._display_title}"

    @property
    def raw_title(self) -> str:
        return self._display_title

    @property
    def is_modified(self) -> bool:
        return self._is_modified

    @property
    def has_applied_redactions(self) -> bool:
        return self._has_applied_redactions

    @property
    def page_count(self) -> int:
        return MuPDFEngine.get_page_count(self._pdf_bytes)

    @property
    def current_page(self) -> int:
        return self._current_page

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def view_mode(self) -> ViewMode:
        return self._view_mode

    @property
    def tool_mode(self) -> ToolMode:
        return self._tool_mode

    # ------------------------------------------------------------------
    # Loading & Saving
    # ------------------------------------------------------------------
    def load_from_file(self, file_path: str, password: str = "") -> None:
        """Open a PDF file via pikepdf and initialize the working buffer."""
        raw_bytes, was_encrypted = PikePDFEngine.open_pdf_file(file_path, password=password)
        self._pdf_bytes = raw_bytes
        self._file_path = str(Path(file_path).resolve())
        self._display_title = Path(file_path).name
        self._current_page = 0
        self._has_applied_redactions = False
        self.encryption_config = EncryptionConfig(
            enabled=was_encrypted,
            user_password=password if was_encrypted else "",
            owner_password=password if was_encrypted else "",
        )
        self.undo_stack.clear()
        self.undo_stack.setClean()
        self._set_modified(False)
        self.documentLoaded.emit()
        self.encryptionChanged.emit(self.encryption_config.enabled)
        self.annotationsUpdated.emit()
        self.redactionsUpdated.emit(self.pending_redactions_count())

    def load_from_bytes(self, pdf_bytes: bytes, title: str = "Untitled.pdf") -> None:
        """Initialize the controller from an in-memory PDF byte stream."""
        self._pdf_bytes = pdf_bytes
        self._file_path = None
        self._display_title = title
        self._current_page = 0
        self._has_applied_redactions = False
        self.encryption_config = EncryptionConfig()
        self.undo_stack.clear()
        self.undo_stack.setClean()
        self._set_modified(False)
        self.documentLoaded.emit()
        self.encryptionChanged.emit(False)
        self.annotationsUpdated.emit()
        self.redactionsUpdated.emit(self.pending_redactions_count())

    def should_force_save_as(self) -> bool:
        """
        Return True if saving should prompt 'Save As' (either no file path exists yet,
        or permanent redactions were applied so the original unredacted file is protected).
        """
        return self._file_path is None or self._has_applied_redactions

    def suggested_save_as_path(self) -> str:
        """Return recommended output path (appending `_redacted.pdf` if redactions were applied)."""
        if self._file_path:
            p = Path(self._file_path)
            if self._has_applied_redactions and not p.stem.endswith("_redacted"):
                return str(p.with_name(f"{p.stem}_redacted{p.suffix}"))
            return str(p)
        stem = Path(self._display_title).stem
        if self._has_applied_redactions and not stem.endswith("_redacted"):
            return f"{stem}_redacted.pdf"
        return f"{stem}.pdf"

    def save_to_file(self, target_path: Optional[str] = None) -> str:
        """Save the current PDF buffer (with any configured pikepdf encryption) to disk."""
        out_path = target_path or self._file_path
        if not out_path:
            raise ValueError("A target file path is required to save the document.")
        PikePDFEngine.save_pdf_file(
            self._pdf_bytes,
            out_path,
            encryption=self.encryption_config,
        )
        self._file_path = str(Path(out_path).resolve())
        self._display_title = Path(out_path).name
        self._has_applied_redactions = False
        self.undo_stack.setClean()
        self._set_modified(False)
        return self._file_path

    # ------------------------------------------------------------------
    # Navigation, Zoom, View & Tool Modes
    # ------------------------------------------------------------------
    def set_current_page(self, index: int) -> None:
        total = self.page_count
        if total == 0:
            return
        clamped = max(0, min(index, total - 1))
        if clamped != self._current_page:
            self._current_page = clamped
            self.pageChanged.emit(clamped)

    def set_zoom(self, zoom_factor: float) -> None:
        clamped = max(0.25, min(zoom_factor, 4.0))
        if abs(clamped - self._zoom) > 1e-3:
            self._zoom = clamped
            self.zoomChanged.emit(self._zoom)

    def set_view_mode(self, mode: ViewMode) -> None:
        if mode != self._view_mode:
            self._view_mode = mode
            self.viewModeChanged.emit(mode.value)

    def toggle_view_mode(self) -> ViewMode:
        new_mode = (
            ViewMode.SINGLE_PAGE
            if self._view_mode == ViewMode.CONTINUOUS
            else ViewMode.CONTINUOUS
        )
        self.set_view_mode(new_mode)
        return new_mode

    def set_tool_mode(self, mode: ToolMode) -> None:
        self._tool_mode = mode
        self.toolModeChanged.emit(mode.value)

    def request_signature_placement(self, png_bytes: bytes) -> None:
        """Switch to SIGNATURE tool mode and notify the canvas to spawn an interactive placement item."""
        self.set_tool_mode(ToolMode.SIGNATURE)
        self.signaturePlacementRequested.emit(png_bytes)

    # ------------------------------------------------------------------
    # Rendering & Queries
    # ------------------------------------------------------------------
    def render_page_image(
        self,
        page_index: int,
        zoom: Optional[float] = None,
        dpr: float = 1.0,
    ) -> QImage:
        z = zoom if zoom is not None else self._zoom
        return MuPDFEngine.render_page(self._pdf_bytes, page_index, zoom=z, dpr=dpr)

    def get_page_dimensions(self) -> list[tuple[float, float]]:
        return MuPDFEngine.get_page_dimensions(self._pdf_bytes)

    def search_text(self, query: str) -> list[SearchMatch]:
        return MuPDFEngine.search_text(self._pdf_bytes, query)

    def list_annotations(self, page_index: Optional[int] = None) -> list[AnnotationInfo]:
        return MuPDFEngine.list_annotations(self._pdf_bytes, page_index=page_index)

    def pending_redactions_count(self) -> int:
        return MuPDFEngine.count_pending_redactions(self._pdf_bytes)

    # ------------------------------------------------------------------
    # PyMuPDF Markup, E-Signature & Redaction Mutations
    # ------------------------------------------------------------------
    def add_highlight(
        self,
        page_index: int,
        rect: tuple[float, float, float, float],
        color: Optional[tuple[float, float, float]] = None,
        smart_snap: bool = True,
    ) -> bool:
        """Add a smart text-snap or rectangular highlight annotation."""
        use_color = color or self.highlight_color
        new_bytes, snapped = MuPDFEngine.add_smart_highlight(
            self._pdf_bytes,
            page_index,
            rect,
            color=use_color,
            smart_snap=smart_snap,
        )
        if new_bytes != self._pdf_bytes:
            self._push_state(
                "Add Highlight",
                new_bytes,
                structural=False,
                target_page=page_index,
            )
        return snapped

    def add_sticky_note(
        self,
        page_index: int,
        point: tuple[float, float],
        content: str,
        title: str = "Note",
        color: Optional[tuple[float, float, float]] = None,
    ) -> None:
        """Add a sticky note annotation on `page_index`."""
        use_color = color or self.sticky_note_color
        new_bytes = MuPDFEngine.add_sticky_note(
            self._pdf_bytes,
            page_index,
            point,
            content=content,
            title=title,
            color=use_color,
        )
        self._push_state(
            "Add Sticky Note",
            new_bytes,
            structural=False,
            target_page=page_index,
        )

    def update_annotation_text(self, page_index: int, xref: int, new_text: str) -> None:
        new_bytes = MuPDFEngine.update_annotation_text(
            self._pdf_bytes, page_index, xref, new_text
        )
        self._push_state(
            "Edit Annotation Note",
            new_bytes,
            structural=False,
            target_page=page_index,
        )

    def delete_annotation(self, page_index: int, xref: int) -> None:
        new_bytes = MuPDFEngine.delete_annotation(self._pdf_bytes, page_index, xref)
        self._push_state(
            "Delete Annotation",
            new_bytes,
            structural=False,
            target_page=page_index,
        )

    def stamp_signature(
        self,
        page_index: int,
        rect: tuple[float, float, float, float],
        png_bytes: bytes,
    ) -> None:
        """Embed a visual E-Signature onto `page_index` at `rect`."""
        new_bytes = MuPDFEngine.stamp_signature(
            self._pdf_bytes, page_index, rect, png_bytes
        )
        self._push_state(
            "Stamp E-Signature",
            new_bytes,
            structural=False,
            target_page=page_index,
        )

    def add_redaction(
        self,
        page_index: int,
        rect: tuple[float, float, float, float],
        fill_color: Optional[tuple[float, float, float]] = None,
        overlay_text: Optional[str] = None,
    ) -> None:
        """Mark a rectangular region for redaction (Step 1)."""
        fill = fill_color if fill_color is not None else self.redact_fill_color
        text = overlay_text if overlay_text is not None else self.redact_overlay_text
        new_bytes = MuPDFEngine.add_redaction_annot(
            self._pdf_bytes,
            page_index,
            rect,
            fill_color=fill,
            overlay_text=text,
        )
        if new_bytes != self._pdf_bytes:
            self._push_state(
                "Mark for Redaction",
                new_bytes,
                structural=False,
                target_page=page_index,
            )

    def add_batch_redactions(
        self,
        matches: list[SearchMatch],
        fill_color: Optional[tuple[float, float, float]] = None,
        overlay_text: Optional[str] = None,
    ) -> int:
        """Mark multiple search matches for redaction in a single undoable operation."""
        if not matches:
            return 0
        fill = fill_color if fill_color is not None else self.redact_fill_color
        text = overlay_text if overlay_text is not None else self.redact_overlay_text
        working = self._pdf_bytes
        for m in matches:
            working = MuPDFEngine.add_redaction_annot(
                working,
                m.page_index,
                m.rect,
                fill_color=fill,
                overlay_text=text,
            )
        if working != self._pdf_bytes:
            self._push_state(
                f"Mark {len(matches)} Matches for Redaction",
                working,
                structural=False,
            )
        return len(matches)

    def apply_all_redactions(self, sanitize_metadata: Optional[bool] = None) -> int:
        """
        Permanently apply all pending redactions (Step 2) and optionally scrub
        document metadata via pikepdf. Marks `has_applied_redactions = True` so
        saving defaults to 'Save As' (`_redacted.pdf`).
        """
        scrub = (
            sanitize_metadata
            if sanitize_metadata is not None
            else self.scrub_metadata_on_redact
        )
        new_bytes, applied_count = MuPDFEngine.apply_redactions(self._pdf_bytes)
        if applied_count == 0:
            return 0
        if scrub:
            new_bytes = PikePDFEngine.sanitize_metadata(new_bytes)
        self._push_state(
            "Apply Redactions Permanently",
            new_bytes,
            structural=False,
            redacted_applied=True,
        )
        return applied_count

    # ------------------------------------------------------------------
    # pikepdf Page Management & Security Mutations
    # ------------------------------------------------------------------
    def reorder_pages(self, new_order: list[int]) -> None:
        if new_order == list(range(self.page_count)):
            return
        new_bytes = PikePDFEngine.reorder_pages(self._pdf_bytes, new_order)
        self._push_state("Reorder Pages", new_bytes, structural=True)

    def rotate_pages(self, page_indices: list[int], angle_delta: int) -> None:
        if not page_indices:
            return
        new_bytes = PikePDFEngine.rotate_pages(self._pdf_bytes, page_indices, angle_delta)
        self._push_state(f"Rotate Pages ({angle_delta}°)", new_bytes, structural=True)

    def delete_pages(self, page_indices: list[int]) -> None:
        if not page_indices:
            return
        new_bytes = PikePDFEngine.delete_pages(self._pdf_bytes, page_indices)
        self._push_state("Delete Pages", new_bytes, structural=True)

    def insert_blank_page(
        self,
        index: Optional[int] = None,
        width: float = 595.0,
        height: float = 842.0,
    ) -> None:
        insert_idx = (self._current_page + 1) if index is None else index
        new_bytes = PikePDFEngine.insert_blank_page(
            self._pdf_bytes, index=insert_idx, width=width, height=height
        )
        self._push_state("Insert Blank Page", new_bytes, structural=True)

    def merge_pdfs(
        self,
        external_paths: list[str],
        insert_at: Optional[int] = None,
    ) -> None:
        if not external_paths:
            return
        new_bytes = PikePDFEngine.merge_pdfs(
            self._pdf_bytes,
            external_paths,
            insert_at=insert_at,
        )
        self._push_state("Merge PDFs", new_bytes, structural=True)

    def update_metadata(self, metadata: dict[str, str]) -> None:
        new_bytes = PikePDFEngine.set_metadata(self._pdf_bytes, metadata)
        self._push_state("Update Document Metadata", new_bytes, structural=False)

    def set_encryption_config(self, config: EncryptionConfig) -> None:
        self.encryption_config = config
        self._set_modified(True)
        self.encryptionChanged.emit(config.enabled)

    # ------------------------------------------------------------------
    # Internal Undo/Redo Snapshot Helpers
    # ------------------------------------------------------------------
    def _push_state(
        self,
        description: str,
        new_bytes: bytes,
        structural: bool = False,
        redacted_applied: bool = False,
        target_page: int = -1,
    ) -> None:
        old_bytes = self._pdf_bytes
        old_redacted = self._has_applied_redactions
        new_redacted = old_redacted or redacted_applied
        cmd = _PDFStateCommand(
            self,
            description=description,
            old_bytes=old_bytes,
            new_bytes=new_bytes,
            old_redacted_flag=old_redacted,
            new_redacted_flag=new_redacted,
            structural_change=structural,
            target_page=target_page,
        )
        self.undo_stack.push(cmd)

    def _apply_snapshot(
        self,
        snapshot_bytes: bytes,
        redacted_flag: bool,
        structural: bool = False,
        target_page: int = -1,
    ) -> None:
        self._pdf_bytes = snapshot_bytes
        self._has_applied_redactions = redacted_flag
        total = self.page_count
        if 0 <= target_page < total:
            self._current_page = target_page
        elif self._current_page >= total and total > 0:
            self._current_page = total - 1

        self._set_modified(not self.undo_stack.isClean())
        if structural:
            self.pagesStructureChanged.emit()
        else:
            self.pageContentChanged.emit(target_page)
        self.annotationsUpdated.emit()
        self.redactionsUpdated.emit(self.pending_redactions_count())

    def _on_clean_changed(self, is_clean: bool) -> None:
        self._set_modified(not is_clean)

    def _set_modified(self, modified: bool) -> None:
        if self._is_modified != modified:
            self._is_modified = modified
            self.documentModified.emit(modified)
