# MePDF — Modern PDF Editor (PySide6 + PyMuPDF + pikepdf)

**MePDF** is a clean, Adobe Acrobat-inspired desktop PDF editor built with Python and **PySide6**.

## Features

- **Multi-Tab Document Workspace**: Open and edit multiple PDF documents simultaneously in tabs, each with independent Undo/Redo history (`Ctrl+Z` / `Ctrl+Y`).
- **Continuous & Single-Page Views**: Switch effortlessly between Continuous Vertical Scroll and Single-Page View.
- **Live Dark & Light Theme Toggle**: Switch between a sleek Dark Theme and a crisp Light Theme (`Ctrl+T` or the toolbar toggle button).
- **Smart Text-Snap Highlighter & Sticky Notes (`PyMuPDF`)**:
  - **Smart Highlight**: Automatically snaps to PDF word/line quads when dragging across text, or falls back to an area highlight on scanned images.
  - **Sticky Notes**: Click anywhere on a page to place a comment icon; view, edit, or delete notes from the canvas or the left **Notes** sidebar.
- **Visual E-Signatures + Local Signature Library (`PyMuPDF`)**:
  - Create signatures via **Draw** (freehand pad), **Type** (script fonts), or **Upload Image** (with automatic white-background removal).
  - Save signatures to your local library (`~/.mepdf/signatures/`) for 1-click reuse.
  - Drag and resize the signature box interactively on any PDF page before stamping.
- **Two-Step Permanent Redaction & Metadata Sanitization (`PyMuPDF` + `pikepdf`)**:
  - Mark areas or search matches (`Search & Redact`) for redaction with customizable fill color and overlay text.
  - Click **Apply Redactions Permanently** to scrub underlying text, vector paths, and image pixels, with an option to sanitize document `/Info` and XMP metadata.
  - Automatically prompts **Save As (`<name>_redacted.pdf`)** after applying redactions to protect your original source file.
- **Page Management & AES-256 Encryption (`pikepdf`)**:
  - Reorder pages via drag-and-drop in the left **Pages** sidebar or the multi-column **Organize Pages Grid** dialog.
  - Rotate (`±90°`), delete, insert blank pages, **Merge** multiple PDFs, and **Split / Extract** pages by range or every $N$ pages.
  - Protect PDFs with **256-bit AES encryption (`R=6`)**, user/owner passwords, and granular permissions.

## Setup & Running

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python main.py
```

## Running Automated Tests

```powershell
.\.venv\Scripts\pytest -v
```
