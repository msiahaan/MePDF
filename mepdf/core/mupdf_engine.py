"""PyMuPDF (fitz) engine for rendering, text search, smart highlights, sticky notes, e-signatures, and redaction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import pymupdf as fitz  # PyMuPDF
from PySide6.QtGui import QImage


@dataclass(frozen=True)
class SearchMatch:
    """Represents a text search hit on a specific PDF page."""

    page_index: int
    rect: tuple[float, float, float, float]
    snippet: str


@dataclass(frozen=True)
class AnnotationInfo:
    """Metadata describing an annotation on a PDF page."""

    xref: int
    page_index: int
    annot_type: str  # "Highlight", "StickyNote", "Redact", or other PDF subtype
    rect: tuple[float, float, float, float]
    content: str
    title: str
    color: tuple[float, float, float]


class MuPDFEngine:
    """Stateless/in-memory helper wrapping PyMuPDF (`fitz`) operations."""

    @staticmethod
    def get_page_count(pdf_bytes: bytes) -> int:
        if not pdf_bytes:
            return 0
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            return len(doc)

    @staticmethod
    def get_page_dimensions(pdf_bytes: bytes) -> list[tuple[float, float]]:
        """Return list of (width_pt, height_pt) for all pages."""
        if not pdf_bytes:
            return []
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            return [(page.rect.width, page.rect.height) for page in doc]

    @staticmethod
    def render_page(
        pdf_bytes: bytes,
        page_index: int,
        zoom: float = 1.0,
        draw_annots: bool = True,
        dpr: float = 1.0,
    ) -> QImage:
        """Render a PDF page at the given logical zoom and device pixel ratio into a crisp High-DPI QImage."""
        if not pdf_bytes:
            return QImage()
        effective_dpr = max(1.0, float(dpr))
        scale = max(0.05, float(zoom) * effective_dpr)
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            if page_index < 0 or page_index >= len(doc):
                return QImage()
            page = doc[page_index]
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat, alpha=False, annots=draw_annots)
            img = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format.Format_RGB888,
            ).copy()
            img.setDevicePixelRatio(effective_dpr)
            return img

    @staticmethod
    def extract_page_text(pdf_bytes: bytes, page_index: int) -> str:
        """Extract plain text from a given page."""
        if not pdf_bytes:
            return ""
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            if 0 <= page_index < len(doc):
                return doc[page_index].get_text("text")
            return ""

    @staticmethod
    def search_text(
        pdf_bytes: bytes,
        query: str,
        page_index: Optional[int] = None,
    ) -> list[SearchMatch]:
        """Search for query text across one or all pages and return bounding boxes + context snippets."""
        query_clean = query.strip()
        if not pdf_bytes or not query_clean:
            return []

        matches: list[SearchMatch] = []
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            pages = [page_index] if page_index is not None else range(len(doc))
            for idx in pages:
                if idx < 0 or idx >= len(doc):
                    continue
                page = doc[idx]
                rects = page.search_for(query_clean)
                if not rects:
                    continue
                full_text = " ".join(page.get_text("text").split())
                snippet = full_text[:120] + ("..." if len(full_text) > 120 else "")
                for r in rects:
                    # Extract local text around the match rect for a richer snippet
                    expanded = fitz.Rect(
                        max(0, r.x0 - 40),
                        max(0, r.y0 - 6),
                        min(page.rect.width, r.x1 + 80),
                        min(page.rect.height, r.y1 + 6),
                    )
                    local_text = " ".join(page.get_text("text", clip=expanded).split())
                    matches.append(
                        SearchMatch(
                            page_index=idx,
                            rect=(r.x0, r.y0, r.x1, r.y1),
                            snippet=local_text or snippet or query_clean,
                        )
                    )
        return matches

    @staticmethod
    def add_smart_highlight(
        pdf_bytes: bytes,
        page_index: int,
        rect: tuple[float, float, float, float],
        color: tuple[float, float, float] = (1.0, 0.92, 0.23),
        smart_snap: bool = True,
    ) -> tuple[bytes, bool]:
        """
        Add a highlight annotation to `page_index`.
        Returns (updated_pdf_bytes, snapped_to_text).
        If `smart_snap` is True and words intersect `rect`, snaps to line quads;
        otherwise falls back to highlighting the rectangular area.
        """
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            page = doc[page_index]
            raw_rect = fitz.Rect(*rect).normalize()
            # Expand very thin horizontal drag strokes so they still hit text lines
            if raw_rect.height < 6.0:
                mid_y = (raw_rect.y0 + raw_rect.y1) / 2.0
                raw_rect.y0 = mid_y - 5.0
                raw_rect.y1 = mid_y + 5.0
            if raw_rect.width < 4.0:
                mid_x = (raw_rect.x0 + raw_rect.x1) / 2.0
                raw_rect.x0 = mid_x - 4.0
                raw_rect.x1 = mid_x + 4.0

            target_rect = raw_rect & page.rect
            if target_rect.is_empty:
                return pdf_bytes, False

            snapped = False
            if smart_snap:
                # Find all words whose bounding boxes intersect target_rect
                all_words = page.get_text("words")
                words = [
                    w
                    for w in all_words
                    if fitz.Rect(w[0], w[1], w[2], w[3]).intersects(target_rect)
                ]
                if words:
                    # Group words by (block_no, line_no) so each line gets a clean quad
                    line_bounds: dict[tuple[int, int], fitz.Rect] = {}
                    for w in words:
                        x0, y0, x1, y1, _word_str, block_no, line_no, _word_no = w[:8]
                        w_rect = fitz.Rect(x0, y0, x1, y1)
                        key = (int(block_no), int(line_no))
                        if key in line_bounds:
                            line_bounds[key] |= w_rect
                        else:
                            line_bounds[key] = w_rect

                    quads = [r.quad for r in line_bounds.values() if not r.is_empty]
                    if quads:
                        annot = page.add_highlight_annot(quads)
                        annot.set_colors(stroke=color)
                        annot.set_opacity(0.45)
                        annot.set_info(title="MePDF", content="Highlighted Text")
                        annot.update()
                        snapped = True

            if not snapped:
                annot = page.add_highlight_annot(target_rect)
                annot.set_colors(stroke=color)
                annot.set_opacity(0.42)
                annot.set_info(title="MePDF", content="Highlighted Area")
                annot.update()

            return doc.tobytes(garbage=2, deflate=True), snapped

    @staticmethod
    def add_sticky_note(
        pdf_bytes: bytes,
        page_index: int,
        point: tuple[float, float],
        content: str,
        title: str = "Note",
        color: tuple[float, float, float] = (1.0, 0.84, 0.15),
    ) -> bytes:
        """Add a sticky note (PDF text annotation) at `(x, y)` on `page_index`."""
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            page = doc[page_index]
            pt = fitz.Point(
                max(8.0, min(point[0], page.rect.width - 24.0)),
                max(8.0, min(point[1], page.rect.height - 24.0)),
            )
            annot = page.add_text_annot(pt, content, icon="Note")
            annot.set_info(title=title, content=content)
            annot.set_colors(stroke=color)
            annot.update()
            return doc.tobytes(garbage=2, deflate=True)

    @staticmethod
    def list_annotations(
        pdf_bytes: bytes,
        page_index: Optional[int] = None,
    ) -> list[AnnotationInfo]:
        """List all annotations across the PDF (or for a single page)."""
        if not pdf_bytes:
            return []
        results: list[AnnotationInfo] = []
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            pages = [page_index] if page_index is not None else range(len(doc))
            for idx in pages:
                if idx < 0 or idx >= len(doc):
                    continue
                page = doc[idx]
                annots = page.annots()
                if not annots:
                    continue
                for annot in annots:
                    type_code, type_name = annot.type
                    if type_code == fitz.PDF_ANNOT_HIGHLIGHT:
                        friendly_type = "Highlight"
                    elif type_code == fitz.PDF_ANNOT_TEXT:
                        friendly_type = "StickyNote"
                    elif type_code == fitz.PDF_ANNOT_REDACT:
                        friendly_type = "Redact"
                    else:
                        friendly_type = type_name or "Annotation"

                    info = annot.info or {}
                    colors = annot.colors or {}
                    stroke = colors.get("stroke") or colors.get("fill") or (1.0, 0.85, 0.2)
                    if len(stroke) >= 3:
                        rgb = (float(stroke[0]), float(stroke[1]), float(stroke[2]))
                    else:
                        rgb = (1.0, 0.85, 0.2)

                    r = annot.rect
                    results.append(
                        AnnotationInfo(
                            xref=int(annot.xref),
                            page_index=idx,
                            annot_type=friendly_type,
                            rect=(r.x0, r.y0, r.x1, r.y1),
                            content=info.get("content", "") or "",
                            title=info.get("title", "") or "",
                            color=rgb,
                        )
                    )
        return results

    @staticmethod
    def update_annotation_text(
        pdf_bytes: bytes,
        page_index: int,
        xref: int,
        new_content: str,
    ) -> bytes:
        """Update the text content of an existing annotation identified by `xref`."""
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            page = doc[page_index]
            for annot in page.annots() or []:
                if int(annot.xref) == int(xref):
                    info = annot.info or {}
                    annot.set_info(
                        title=info.get("title", "Note") or "Note",
                        content=new_content,
                    )
                    annot.update()
                    break
            return doc.tobytes(garbage=2, deflate=True)

    @staticmethod
    def delete_annotation(
        pdf_bytes: bytes,
        page_index: int,
        xref: int,
    ) -> bytes:
        """Delete an annotation by its PDF `xref` on `page_index`."""
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            page = doc[page_index]
            for annot in page.annots() or []:
                if int(annot.xref) == int(xref):
                    page.delete_annot(annot)
                    break
            return doc.tobytes(garbage=2, deflate=True)

    @staticmethod
    def stamp_signature(
        pdf_bytes: bytes,
        page_index: int,
        rect: tuple[float, float, float, float],
        png_bytes: bytes,
    ) -> bytes:
        """Embed a transparent PNG signature image onto `page_index` inside `rect`."""
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            page = doc[page_index]
            target_rect = fitz.Rect(*rect) & page.rect
            if target_rect.is_empty:
                return pdf_bytes
            page.insert_image(
                target_rect,
                stream=png_bytes,
                keep_proportion=True,
                overlay=True,
            )
            return doc.tobytes(garbage=2, deflate=True)

    @staticmethod
    def add_redaction_annot(
        pdf_bytes: bytes,
        page_index: int,
        rect: tuple[float, float, float, float],
        fill_color: tuple[float, float, float] = (0.0, 0.0, 0.0),
        overlay_text: str = "",
    ) -> bytes:
        """Mark a rectangular region on `page_index` for redaction (Step 1 of 2-step redaction)."""
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            page = doc[page_index]
            raw_rect = fitz.Rect(*rect).normalize()
            if raw_rect.height < 6.0:
                mid_y = (raw_rect.y0 + raw_rect.y1) / 2.0
                raw_rect.y0 = mid_y - 5.0
                raw_rect.y1 = mid_y + 5.0
            if raw_rect.width < 4.0:
                mid_x = (raw_rect.x0 + raw_rect.x1) / 2.0
                raw_rect.x0 = mid_x - 4.0
                raw_rect.x1 = mid_x + 4.0
            target_rect = raw_rect & page.rect
            if target_rect.is_empty:
                return pdf_bytes

            text_color = (1.0, 1.0, 1.0) if sum(fill_color) < 1.5 else (0.0, 0.0, 0.0)
            annot = page.add_redact_annot(
                target_rect,
                text=overlay_text if overlay_text else None,
                fill=fill_color,
                text_color=text_color,
                align=fitz.TEXT_ALIGN_CENTER,
            )
            annot.set_info(
                title="Redaction",
                content=overlay_text or "Pending Redaction",
            )
            annot.update()
            return doc.tobytes(garbage=2, deflate=True)

    @staticmethod
    def count_pending_redactions(pdf_bytes: bytes) -> int:
        """Return total number of unapplied redaction annotations across all pages."""
        if not pdf_bytes:
            return 0
        count = 0
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for page in doc:
                for annot in page.annots() or []:
                    if annot.type[0] == fitz.PDF_ANNOT_REDACT:
                        count += 1
        return count

    @staticmethod
    def apply_redactions(pdf_bytes: bytes) -> tuple[bytes, int]:
        """
        Permanently apply all pending redaction annotations across the document (Step 2).
        Scrubs underlying text, vector graphics, and image pixels.
        Returns (scrubbed_pdf_bytes, applied_count).
        """
        applied = 0
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for page in doc:
                page_redacts = [
                    a for a in (page.annots() or []) if a.type[0] == fitz.PDF_ANNOT_REDACT
                ]
                if page_redacts:
                    applied += len(page_redacts)
                    page.apply_redactions(
                        images=fitz.PDF_REDACT_IMAGE_PIXELS,
                        graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                    )
            return doc.tobytes(garbage=4, clean=True, deflate=True), applied

    @staticmethod
    def create_sample_pdf(num_pages: int = 3) -> bytes:
        """Create a multi-page sample PDF document for testing or quick demo."""
        with fitz.open() as doc:
            for idx in range(num_pages):
                page = doc.new_page(width=595.0, height=842.0)  # A4
                # Header banner
                header_rect = fitz.Rect(45, 40, 550, 95)
                page.draw_rect(header_rect, color=(0.15, 0.38, 0.92), fill=(0.15, 0.38, 0.92))
                page.insert_text(
                    fitz.Point(60, 72),
                    f"MePDF Sample Document — Page {idx + 1} of {num_pages}",
                    fontsize=16,
                    color=(1, 1, 1),
                )

                # Body paragraphs
                body_lines = [
                    f"Section {idx + 1}.1: Executive Overview",
                    "This sample PDF demonstrates high-DPI rendering, smart text-snap highlighting,",
                    "sticky note annotations, visual E-Signature stamping, and permanent redaction.",
                    "",
                    f"Section {idx + 1}.2: Sensitive & Confidential Information",
                    f"Account Holder: Alex Rivera   |   Reference ID: CONF-2026-00{idx + 1}",
                    "Secret Token: SECRET-TOKEN-9942-ALPHA (Try Redact or Search & Redact on this line!)",
                    "",
                    f"Section {idx + 1}.3: Terms & Conditions",
                    "1. Use the Highlight tool to drag across these text lines—it snaps cleanly to words.",
                    "2. Use the Sticky Note tool to drop a review comment anywhere on the page.",
                    "3. Click E-Sign in the toolbar to draw, type, or upload a transparent signature.",
                    "4. Use Organize Pages or the Left Sidebar to reorder, rotate, split, or merge.",
                ]
                y = 135
                for line in body_lines:
                    is_heading = line.startswith("Section")
                    page.insert_text(
                        fitz.Point(55, y),
                        line,
                        fontsize=12 if is_heading else 10.5,
                        color=(0.1, 0.18, 0.35) if is_heading else (0.15, 0.15, 0.18),
                    )
                    y += 22 if is_heading else 18

                # Signature box placeholder at the bottom
                sig_rect = fitz.Rect(55, 680, 290, 760)
                page.draw_rect(sig_rect, color=(0.6, 0.65, 0.72), dashes="[3 3] 0")
                page.insert_text(
                    fitz.Point(68, 700),
                    "Authorized E-Signature Box:",
                    fontsize=9.5,
                    color=(0.45, 0.48, 0.55),
                )
                page.insert_text(
                    fitz.Point(68, 748),
                    "X _______________________________",
                    fontsize=10,
                    color=(0.35, 0.38, 0.45),
                )

            return doc.tobytes(garbage=2, deflate=True)
