"""pikepdf engine for structural page management, metadata sanitization, and AES-256 encryption."""

from __future__ import annotations

from dataclasses import dataclass, field
import io
import os
from pathlib import Path
from typing import Optional
import pikepdf


@dataclass
class EncryptionPermissions:
    """Granular PDF permission flags for pikepdf encryption."""

    allow_print_highres: bool = True
    allow_print_lowres: bool = True
    allow_extract: bool = True
    allow_modify_annotation: bool = True
    allow_modify_form: bool = True
    allow_modify_assembly: bool = False
    allow_modify_other: bool = False
    allow_accessibility: bool = True

    def to_pikepdf_permissions(self) -> pikepdf.Permissions:
        return pikepdf.Permissions(
            accessibility=self.allow_accessibility,
            extract=self.allow_extract,
            modify_annotation=self.allow_modify_annotation,
            modify_assembly=self.allow_modify_assembly,
            modify_form=self.allow_modify_form,
            modify_other=self.allow_modify_other,
            print_lowres=self.allow_print_lowres,
            print_highres=self.allow_print_highres,
        )


@dataclass
class EncryptionConfig:
    """Active encryption configuration for saving a PDF via pikepdf."""

    enabled: bool = False
    user_password: str = ""
    owner_password: str = ""
    permissions: EncryptionPermissions = field(default_factory=EncryptionPermissions)


class PasswordRequiredError(Exception):
    """Raised when opening a password-protected PDF without a valid password."""


class PikePDFEngine:
    """Stateless helper wrapping `pikepdf` page management, metadata scrubbing, and encryption."""

    @staticmethod
    def open_pdf_file(file_path: str, password: str = "") -> tuple[bytes, bool]:
        """
        Open a PDF from disk using pikepdf, decrypting into an unencrypted working
        memory stream so PyMuPDF and pikepdf can freely edit it in memory.
        Returns (working_pdf_bytes, was_encrypted).
        Raises PasswordRequiredError if a password is required or incorrect.
        """
        try:
            with pikepdf.open(file_path, password=password) as pdf:
                was_encrypted = bool(pdf.is_encrypted)
                buf = io.BytesIO()
                pdf.save(buf)
                return buf.getvalue(), was_encrypted
        except pikepdf.PasswordError as exc:
            raise PasswordRequiredError("This PDF is protected by a password.") from exc

    @staticmethod
    def save_pdf_file(
        pdf_bytes: bytes,
        output_path: str,
        encryption: Optional[EncryptionConfig] = None,
    ) -> None:
        """Save working PDF bytes to disk, optionally applying AES-256 encryption via pikepdf."""
        src_buf = io.BytesIO(pdf_bytes)
        with pikepdf.open(src_buf) as pdf:
            enc_obj = None
            if encryption and encryption.enabled and (
                encryption.user_password or encryption.owner_password
            ):
                owner_pw = encryption.owner_password or encryption.user_password
                enc_obj = pikepdf.Encryption(
                    user=encryption.user_password,
                    owner=owner_pw,
                    R=6,  # AES-256 encryption
                    allow=encryption.permissions.to_pikepdf_permissions(),
                )
            pdf.save(output_path, encryption=enc_obj)

    @staticmethod
    def encrypt_pdf_bytes(
        pdf_bytes: bytes,
        user_password: str,
        owner_password: str = "",
        permissions: Optional[EncryptionPermissions] = None,
    ) -> bytes:
        """Return AES-256 encrypted PDF bytes in memory."""
        perms = permissions or EncryptionPermissions()
        owner_pw = owner_password or user_password
        src_buf = io.BytesIO(pdf_bytes)
        out_buf = io.BytesIO()
        with pikepdf.open(src_buf) as pdf:
            enc = pikepdf.Encryption(
                user=user_password,
                owner=owner_pw,
                R=6,
                allow=perms.to_pikepdf_permissions(),
            )
            pdf.save(out_buf, encryption=enc)
        return out_buf.getvalue()

    @staticmethod
    def reorder_pages(pdf_bytes: bytes, new_order: list[int]) -> bytes:
        """Reorder pages according to 0-based `new_order` indices."""
        src_buf = io.BytesIO(pdf_bytes)
        out_buf = io.BytesIO()
        with pikepdf.open(src_buf) as src_pdf:
            total = len(src_pdf.pages)
            if sorted(new_order) != list(range(total)):
                raise ValueError(
                    f"new_order {new_order} must be a permutation of 0..{total - 1}"
                )
            with pikepdf.Pdf.new() as dst_pdf:
                for idx in new_order:
                    dst_pdf.pages.append(src_pdf.pages[idx])
                # Preserve document info dictionary if present
                if "/Info" in src_pdf.trailer:
                    dst_pdf.docinfo = dst_pdf.copy_foreign(src_pdf.docinfo)
                dst_pdf.save(out_buf)
        return out_buf.getvalue()

    @staticmethod
    def rotate_pages(
        pdf_bytes: bytes,
        page_indices: list[int],
        angle_delta: int,
    ) -> bytes:
        """Rotate specified 0-based pages relatively by `angle_delta` (multiple of 90 degrees)."""
        if angle_delta % 90 != 0:
            raise ValueError("Rotation angle must be a multiple of 90 degrees.")
        src_buf = io.BytesIO(pdf_bytes)
        out_buf = io.BytesIO()
        with pikepdf.open(src_buf) as pdf:
            for idx in page_indices:
                if 0 <= idx < len(pdf.pages):
                    pdf.pages[idx].rotate(angle_delta, relative=True)
            pdf.save(out_buf)
        return out_buf.getvalue()

    @staticmethod
    def delete_pages(pdf_bytes: bytes, page_indices: list[int]) -> bytes:
        """Delete the specified 0-based pages. Prevents deleting every page in the PDF."""
        src_buf = io.BytesIO(pdf_bytes)
        out_buf = io.BytesIO()
        with pikepdf.open(src_buf) as pdf:
            unique_sorted = sorted(
                {i for i in page_indices if 0 <= i < len(pdf.pages)},
                reverse=True,
            )
            if len(unique_sorted) >= len(pdf.pages):
                raise ValueError("Cannot delete all pages from a PDF document.")
            for idx in unique_sorted:
                del pdf.pages[idx]
            pdf.save(out_buf)
        return out_buf.getvalue()

    @staticmethod
    def insert_blank_page(
        pdf_bytes: Optional[bytes] = None,
        index: int = 0,
        width: float = 595.0,
        height: float = 842.0,
    ) -> bytes:
        """Insert a blank page at `index` (or create a new 1-page PDF if `pdf_bytes` is empty)."""
        out_buf = io.BytesIO()
        if not pdf_bytes:
            with pikepdf.Pdf.new() as pdf:
                pdf.add_blank_page(page_size=(width, height))
                pdf.save(out_buf)
            return out_buf.getvalue()

        src_buf = io.BytesIO(pdf_bytes)
        with pikepdf.open(src_buf) as src_pdf:
            total = len(src_pdf.pages)
            insert_pos = max(0, min(index, total))
            with pikepdf.Pdf.new() as dst_pdf:
                for i in range(insert_pos):
                    dst_pdf.pages.append(src_pdf.pages[i])
                dst_pdf.add_blank_page(page_size=(width, height))
                for i in range(insert_pos, total):
                    dst_pdf.pages.append(src_pdf.pages[i])
                if "/Info" in src_pdf.trailer:
                    dst_pdf.docinfo = dst_pdf.copy_foreign(src_pdf.docinfo)
                dst_pdf.save(out_buf)
        return out_buf.getvalue()

    @staticmethod
    def merge_pdfs(
        base_bytes: Optional[bytes],
        external_paths_or_bytes: list[str | bytes],
        insert_at: Optional[int] = None,
    ) -> bytes:
        """
        Merge external PDF files (or raw PDF byte buffers) into `base_bytes` at `insert_at`
        (defaults to appending at the end).
        """
        out_buf = io.BytesIO()
        with pikepdf.Pdf.new() as dst_pdf:
            base_pdf = pikepdf.open(io.BytesIO(base_bytes)) if base_bytes else None
            try:
                base_total = len(base_pdf.pages) if base_pdf else 0
                pos = base_total if insert_at is None else max(0, min(insert_at, base_total))

                if base_pdf:
                    for i in range(pos):
                        dst_pdf.pages.append(base_pdf.pages[i])

                opened_ext: list[pikepdf.Pdf] = []
                try:
                    for item in external_paths_or_bytes:
                        ext_pdf = (
                            pikepdf.open(item)
                            if isinstance(item, (str, os.PathLike))
                            else pikepdf.open(io.BytesIO(item))
                        )
                        opened_ext.append(ext_pdf)
                        for p in ext_pdf.pages:
                            dst_pdf.pages.append(p)

                    if base_pdf:
                        for i in range(pos, base_total):
                            dst_pdf.pages.append(base_pdf.pages[i])
                        if "/Info" in base_pdf.trailer:
                            dst_pdf.docinfo = dst_pdf.copy_foreign(base_pdf.docinfo)

                    dst_pdf.save(out_buf)
                finally:
                    for ext in opened_ext:
                        ext.close()
            finally:
                if base_pdf:
                    base_pdf.close()

        return out_buf.getvalue()

    @staticmethod
    def extract_pages_to_bytes(pdf_bytes: bytes, page_indices: list[int]) -> bytes:
        """Extract specific 0-based page indices into a new standalone PDF byte buffer."""
        src_buf = io.BytesIO(pdf_bytes)
        out_buf = io.BytesIO()
        with pikepdf.open(src_buf) as src_pdf:
            with pikepdf.Pdf.new() as dst_pdf:
                for idx in page_indices:
                    if 0 <= idx < len(src_pdf.pages):
                        dst_pdf.pages.append(src_pdf.pages[idx])
                if len(dst_pdf.pages) == 0:
                    raise ValueError("No valid pages selected for extraction.")
                dst_pdf.save(out_buf)
        return out_buf.getvalue()

    @staticmethod
    def split_pdf(
        pdf_bytes: bytes,
        page_ranges: list[tuple[int, int]],
        output_dir: str,
        prefix: str = "split",
    ) -> list[str]:
        """
        Split `pdf_bytes` by 0-based inclusive `(start_idx, end_idx)` ranges and save files
        into `output_dir`. Returns list of created file paths.
        """
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        created_files: list[str] = []

        src_buf = io.BytesIO(pdf_bytes)
        with pikepdf.open(src_buf) as src_pdf:
            total = len(src_pdf.pages)
            for part_num, (start_idx, end_idx) in enumerate(page_ranges, start=1):
                s = max(0, min(start_idx, total - 1))
                e = max(s, min(end_idx, total - 1))
                out_path = out_dir / f"{prefix}_part{part_num}_p{s + 1}-{e + 1}.pdf"
                with pikepdf.Pdf.new() as part_pdf:
                    for idx in range(s, e + 1):
                        part_pdf.pages.append(src_pdf.pages[idx])
                    part_pdf.save(str(out_path))
                created_files.append(str(out_path))
        return created_files

    @staticmethod
    def get_metadata(pdf_bytes: bytes) -> dict[str, str]:
        """Read standard PDF document info fields (`/Title`, `/Author`, `/Subject`, `/Keywords`, `/Creator`)."""
        if not pdf_bytes:
            return {}
        keys = ("Title", "Author", "Subject", "Keywords", "Creator", "Producer")
        result: dict[str, str] = {}
        with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
            info = pdf.docinfo
            for k in keys:
                slash_k = f"/{k}"
                if slash_k in info:
                    result[k] = str(info[slash_k])
                else:
                    result[k] = ""
        return result

    @staticmethod
    def set_metadata(pdf_bytes: bytes, metadata: dict[str, str]) -> bytes:
        """Update PDF `/Info` dictionary fields."""
        src_buf = io.BytesIO(pdf_bytes)
        out_buf = io.BytesIO()
        with pikepdf.open(src_buf) as pdf:
            for k, v in metadata.items():
                slash_k = k if k.startswith("/") else f"/{k}"
                if v:
                    pdf.docinfo[slash_k] = v
                elif slash_k in pdf.docinfo:
                    del pdf.docinfo[slash_k]
            pdf.save(out_buf)
        return out_buf.getvalue()

    @staticmethod
    def sanitize_metadata(pdf_bytes: bytes) -> bytes:
        """
        Scrub all document metadata (`/Info` dictionary entries and XMP `/Metadata` stream)
        for redaction privacy compliance.
        """
        src_buf = io.BytesIO(pdf_bytes)
        out_buf = io.BytesIO()
        with pikepdf.open(src_buf) as pdf:
            # Clear XMP metadata
            with pdf.open_metadata(set_pikepdf_as_editor=False) as xmp:
                xmp.clear()
            if "/Metadata" in pdf.Root:
                del pdf.Root["/Metadata"]

            # Clear /Info dictionary keys
            keys_to_remove = list(pdf.docinfo.keys())
            for k in keys_to_remove:
                del pdf.docinfo[k]
            if "/Info" in pdf.trailer:
                del pdf.trailer["/Info"]

            pdf.save(out_buf)
        return out_buf.getvalue()
