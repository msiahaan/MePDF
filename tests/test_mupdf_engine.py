"""Unit tests for MuPDFEngine (rendering, search, smart highlights, sticky notes, e-signature, and 2-step redaction)."""

from __future__ import annotations

import pymupdf as fitz
from PySide6.QtGui import QColor

from mepdf.core.mupdf_engine import MuPDFEngine
from mepdf.core.signature_store import SignatureStore


def test_sample_pdf_and_rendering(qapp) -> None:
    pdf_bytes = MuPDFEngine.create_sample_pdf(num_pages=3)
    assert MuPDFEngine.get_page_count(pdf_bytes) == 3

    dims = MuPDFEngine.get_page_dimensions(pdf_bytes)
    assert len(dims) == 3
    assert dims[0] == (595.0, 842.0)

    img = MuPDFEngine.render_page(pdf_bytes, 0, zoom=1.5)
    assert not img.isNull()
    assert img.width() > 800
    assert img.height() > 1200

    # Verify High-DPI rendering scales physical pixels and sets QImage devicePixelRatio
    img_hidpi = MuPDFEngine.render_page(pdf_bytes, 0, zoom=1.5, dpr=2.0)
    assert not img_hidpi.isNull()
    assert abs(img_hidpi.devicePixelRatio() - 2.0) < 1e-3
    assert abs(img_hidpi.width() - img.width() * 2) <= 1
    assert abs(img_hidpi.height() - img.height() * 2) <= 1


def test_smart_highlight_snaps_to_text_and_area_fallback(qapp) -> None:
    pdf_bytes = MuPDFEngine.create_sample_pdf(num_pages=1)

    # 1. Highlight over text region -> should snap to text quads
    updated_bytes, snapped = MuPDFEngine.add_smart_highlight(
        pdf_bytes,
        page_index=0,
        rect=(50, 120, 450, 180),
        color=(1.0, 0.92, 0.23),
        smart_snap=True,
    )
    assert snapped is True
    annots = MuPDFEngine.list_annotations(updated_bytes, page_index=0)
    assert len(annots) == 1
    assert annots[0].annot_type == "Highlight"

    # 2. Highlight over blank region -> should fall back to rectangular highlight
    updated_bytes_2, snapped_blank = MuPDFEngine.add_smart_highlight(
        updated_bytes,
        page_index=0,
        rect=(400, 780, 540, 825),
        color=(0.3, 0.88, 0.45),
        smart_snap=True,
    )
    assert snapped_blank is False
    annots_2 = MuPDFEngine.list_annotations(updated_bytes_2, page_index=0)
    assert len(annots_2) == 2


def test_sticky_notes_crud(qapp) -> None:
    pdf_bytes = MuPDFEngine.create_sample_pdf(num_pages=1)

    with_note = MuPDFEngine.add_sticky_note(
        pdf_bytes,
        page_index=0,
        point=(120.0, 200.0),
        content="Initial review comment",
        title="Reviewer",
    )
    annots = MuPDFEngine.list_annotations(with_note)
    assert len(annots) == 1
    note = annots[0]
    assert note.annot_type == "StickyNote"
    assert note.content == "Initial review comment"

    # Update sticky note text
    edited = MuPDFEngine.update_annotation_text(
        with_note,
        page_index=0,
        xref=note.xref,
        new_content="Updated clause comment",
    )
    annots_after_edit = MuPDFEngine.list_annotations(edited)
    assert annots_after_edit[0].content == "Updated clause comment"

    # Delete sticky note
    deleted = MuPDFEngine.delete_annotation(edited, page_index=0, xref=note.xref)
    assert len(MuPDFEngine.list_annotations(deleted)) == 0


def test_e_signature_stamping(qapp) -> None:
    pdf_bytes = MuPDFEngine.create_sample_pdf(num_pages=1)
    sig_img = SignatureStore.render_typed_signature(
        "Alex Rivera",
        font_family="Segoe Script",
        ink_color=QColor("#0f296b"),
    )
    png_bytes = SignatureStore.qimage_to_png_bytes(sig_img)
    assert len(png_bytes) > 100

    stamped_bytes = MuPDFEngine.stamp_signature(
        pdf_bytes,
        page_index=0,
        rect=(65.0, 690.0, 260.0, 750.0),
        png_bytes=png_bytes,
    )
    with fitz.open(stream=stamped_bytes, filetype="pdf") as doc:
        images = doc[0].get_images()
        assert len(images) >= 1


def test_two_step_search_and_permanent_redaction(qapp) -> None:
    pdf_bytes = MuPDFEngine.create_sample_pdf(num_pages=2)
    secret = "SECRET-TOKEN-9942-ALPHA"
    assert secret in MuPDFEngine.extract_page_text(pdf_bytes, 0)

    matches = MuPDFEngine.search_text(pdf_bytes, secret)
    assert len(matches) == 2

    # Step 1: Mark first page match for redaction
    marked = MuPDFEngine.add_redaction_annot(
        pdf_bytes,
        page_index=0,
        rect=matches[0].rect,
        fill_color=(0.0, 0.0, 0.0),
        overlay_text="REDACTED",
    )
    assert MuPDFEngine.count_pending_redactions(marked) == 1
    # Before applying, text still exists in stream
    assert secret in MuPDFEngine.extract_page_text(marked, 0)

    # Step 2: Apply redactions permanently
    scrubbed, count = MuPDFEngine.apply_redactions(marked)
    assert count == 1
    assert MuPDFEngine.count_pending_redactions(scrubbed) == 0
    assert secret not in MuPDFEngine.extract_page_text(scrubbed, 0)
    # Page 2 wasn't redacted, so it still has its copy
    assert secret in MuPDFEngine.extract_page_text(scrubbed, 1)
