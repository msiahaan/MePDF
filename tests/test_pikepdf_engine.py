"""Unit tests for PikePDFEngine (reorder, rotate, delete, insert, merge, split, metadata scrubbing, AES-256 encryption)."""

from __future__ import annotations

from pathlib import Path
import pytest

from mepdf.core.mupdf_engine import MuPDFEngine
from mepdf.core.pikepdf_engine import (
    EncryptionConfig,
    EncryptionPermissions,
    PasswordRequiredError,
    PikePDFEngine,
)


def test_page_reorder_rotate_delete_and_insert() -> None:
    base_bytes = MuPDFEngine.create_sample_pdf(num_pages=3)
    assert "Page 1 of 3" in MuPDFEngine.extract_page_text(base_bytes, 0)

    # Reorder [2, 0, 1]
    reordered = PikePDFEngine.reorder_pages(base_bytes, [2, 0, 1])
    assert "Page 3 of 3" in MuPDFEngine.extract_page_text(reordered, 0)
    assert "Page 1 of 3" in MuPDFEngine.extract_page_text(reordered, 1)

    # Rotate page 0 by 90 degrees -> width and height swap
    rotated = PikePDFEngine.rotate_pages(reordered, [0], 90)
    dims = MuPDFEngine.get_page_dimensions(rotated)
    assert dims[0] == (842.0, 595.0)

    # Insert blank page at index 1 -> total 4 pages
    with_blank = PikePDFEngine.insert_blank_page(rotated, index=1, width=500.0, height=700.0)
    assert MuPDFEngine.get_page_count(with_blank) == 4
    assert MuPDFEngine.get_page_dimensions(with_blank)[1] == (500.0, 700.0)

    # Delete pages 1 and 2 -> 2 pages remain
    after_del = PikePDFEngine.delete_pages(with_blank, [1, 2])
    assert MuPDFEngine.get_page_count(after_del) == 2


def test_merge_and_split_pdfs(tmp_path: Path) -> None:
    pdf_a = MuPDFEngine.create_sample_pdf(num_pages=2)
    pdf_b = MuPDFEngine.create_sample_pdf(num_pages=2)
    path_b = tmp_path / "b.pdf"
    path_b.write_bytes(pdf_b)

    merged = PikePDFEngine.merge_pdfs(pdf_a, [str(path_b)], insert_at=1)
    assert MuPDFEngine.get_page_count(merged) == 4

    split_dir = tmp_path / "splits"
    created = PikePDFEngine.split_pdf(merged, [(0, 1), (2, 3)], str(split_dir), prefix="doc")
    assert len(created) == 2
    for fpath in created:
        raw, _ = PikePDFEngine.open_pdf_file(fpath)
        assert MuPDFEngine.get_page_count(raw) == 2


def test_metadata_update_and_sanitization() -> None:
    base_bytes = MuPDFEngine.create_sample_pdf(num_pages=1)
    with_meta = PikePDFEngine.set_metadata(
        base_bytes,
        {"Title": "Top Secret Contract", "Author": "Jane Doe"},
    )
    meta = PikePDFEngine.get_metadata(with_meta)
    assert meta["Title"] == "Top Secret Contract"
    assert meta["Author"] == "Jane Doe"

    sanitized = PikePDFEngine.sanitize_metadata(with_meta)
    clean_meta = PikePDFEngine.get_metadata(sanitized)
    assert clean_meta["Title"] == ""
    assert clean_meta["Author"] == ""


def test_aes256_encryption_and_password_enforcement(tmp_path: Path) -> None:
    base_bytes = MuPDFEngine.create_sample_pdf(num_pages=1)
    enc_path = tmp_path / "encrypted.pdf"

    cfg = EncryptionConfig(
        enabled=True,
        user_password="user123",
        owner_password="owner456",
        permissions=EncryptionPermissions(
            allow_print_highres=False,
            allow_extract=False,
        ),
    )
    PikePDFEngine.save_pdf_file(base_bytes, str(enc_path), encryption=cfg)

    # Opening without password must raise PasswordRequiredError
    with pytest.raises(PasswordRequiredError):
        PikePDFEngine.open_pdf_file(str(enc_path), password="")

    # Opening with correct user password succeeds
    decrypted_bytes, was_encrypted = PikePDFEngine.open_pdf_file(
        str(enc_path), password="user123"
    )
    assert was_encrypted is True
    assert MuPDFEngine.get_page_count(decrypted_bytes) == 1
