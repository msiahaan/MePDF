"""Right-hand contextual Inspector Panel for Highlights, Sticky Notes, E-Signatures, Redactions, and Security."""

from __future__ import annotations

from typing import Callable, Optional
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mepdf.core.document_controller import PDFDocumentController, ToolMode
from mepdf.core.pikepdf_engine import PikePDFEngine
from mepdf.core.signature_store import SavedSignature, SignatureStore


class InspectorPanel(QWidget):
    """Contextual right sidebar adapting to Markup, E-Signatures, Redaction, and Security."""

    SIG_ROLE = Qt.ItemDataRole.UserRole + 1

    HIGHLIGHT_PALETTE = [
        ("Yellow", (1.0, 0.92, 0.23), "#facc15"),
        ("Mint Green", (0.30, 0.88, 0.45), "#4ade80"),
        ("Sky Cyan", (0.22, 0.78, 0.96), "#38bdf8"),
        ("Coral Pink", (0.98, 0.45, 0.65), "#f472b6"),
        ("Sunset Orange", (0.98, 0.60, 0.20), "#fb923c"),
    ]

    REDACT_FILL_COLORS = [
        ("Solid Black", (0.0, 0.0, 0.0)),
        ("Pure White", (1.0, 1.0, 1.0)),
        ("Dark Slate", (0.20, 0.22, 0.26)),
    ]

    def __init__(
        self,
        controller: PDFDocumentController,
        signature_store: SignatureStore,
        on_open_signature_dialog: Callable[[], None],
        on_open_encryption_dialog: Callable[[], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.signature_store = signature_store
        self._on_open_signature_dialog = on_open_signature_dialog
        self._on_open_encryption_dialog = on_open_encryption_dialog

        self._build_ui()

        self.controller.documentLoaded.connect(self._refresh_all)
        self.controller.redactionsUpdated.connect(self._update_redaction_badge)
        self.controller.encryptionChanged.connect(self._update_security_badge)
        self.controller.toolModeChanged.connect(self._on_tool_mode_changed)
        if self.controller.page_count > 0:
            self._refresh_all()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        root = QVBoxLayout(container)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        # Active Tool Banner
        self.tool_hint_label = QLabel(
            "<b>Active Tool:</b> Pan / Select<br>"
            "<span style='font-size:11px;'>Scroll, zoom, or click any Sticky Note to view/edit it.</span>"
        )
        self.tool_hint_label.setWordWrap(True)
        root.addWidget(self.tool_hint_label)

        # --- Group 1: Highlight & Sticky Note Color Swatches ---
        markup_group = QGroupBox("Highlight && Sticky Note Color")
        markup_layout = QVBoxLayout(markup_group)

        tool_btn_row = QHBoxLayout()
        btn_hl_tool = QPushButton("🟨 Highlight Tool")
        btn_hl_tool.clicked.connect(
            lambda: self.controller.set_tool_mode(ToolMode.HIGHLIGHT)
        )
        tool_btn_row.addWidget(btn_hl_tool)

        btn_note_tool = QPushButton("📝 Sticky Note Tool")
        btn_note_tool.clicked.connect(
            lambda: self.controller.set_tool_mode(ToolMode.STICKY_NOTE)
        )
        tool_btn_row.addWidget(btn_note_tool)
        markup_layout.addLayout(tool_btn_row)

        swatch_row = QHBoxLayout()
        self._swatch_buttons: list[tuple[QPushButton, tuple[float, float, float], str]] = []
        for name, rgb_tuple, hex_code in self.HIGHLIGHT_PALETTE:
            btn = QPushButton()
            btn.setToolTip(f"Select {name} (activates Highlighter)")
            btn.setFixedSize(30, 30)
            btn.clicked.connect(
                lambda _checked=False, c=rgb_tuple: self._set_markup_color(c)
            )
            swatch_row.addWidget(btn)
            self._swatch_buttons.append((btn, rgb_tuple, hex_code))
        swatch_row.addStretch()
        markup_layout.addLayout(swatch_row)
        self._update_swatch_styles()
        root.addWidget(markup_group)

        # --- Group 2: E-Signature Library ---
        sig_group = QGroupBox("E-Signature Library")
        sig_layout = QVBoxLayout(sig_group)

        btn_new_sig = QPushButton("✒ + Create New E-Signature...")
        btn_new_sig.setProperty("primary", True)
        btn_new_sig.clicked.connect(self._on_open_signature_dialog)
        sig_layout.addWidget(btn_new_sig)

        sig_layout.addWidget(QLabel("Saved Signatures (Click to place on page):"))
        self.sig_list = QListWidget()
        self.sig_list.setIconSize(QSize(120, 44))
        self.sig_list.setMaximumHeight(135)
        self.sig_list.itemClicked.connect(self._on_saved_signature_clicked)
        sig_layout.addWidget(self.sig_list)

        sig_btn_row = QHBoxLayout()
        btn_place_sig = QPushButton("Place Selected")
        btn_place_sig.clicked.connect(self._place_selected_signature)
        sig_btn_row.addWidget(btn_place_sig)

        btn_del_sig = QPushButton("Delete")
        btn_del_sig.clicked.connect(self._delete_selected_signature)
        sig_btn_row.addWidget(btn_del_sig)
        sig_layout.addLayout(sig_btn_row)
        root.addWidget(sig_group)

        # --- Group 3: Two-Step Redaction & Metadata Scrubbing ---
        redact_group = QGroupBox("Redaction && Sanitization")
        redact_layout = QVBoxLayout(redact_group)

        btn_mark_redact = QPushButton("⬛ Mark Area for Redaction")
        btn_mark_redact.clicked.connect(
            lambda: self.controller.set_tool_mode(ToolMode.REDACT)
        )
        redact_layout.addWidget(btn_mark_redact)

        self.redact_count_label = QLabel("Pending Redactions: <b>0</b>")
        redact_layout.addWidget(self.redact_count_label)

        redact_form = QFormLayout()
        self.fill_combo = QComboBox()
        for label, rgb in self.REDACT_FILL_COLORS:
            self.fill_combo.addItem(label, rgb)
        self.fill_combo.currentIndexChanged.connect(self._on_redact_settings_changed)
        redact_form.addRow("Fill Color:", self.fill_combo)

        self.overlay_input = QLineEdit(self.controller.redact_overlay_text)
        self.overlay_input.setPlaceholderText("e.g. REDACTED or leave blank")
        self.overlay_input.textChanged.connect(self._on_redact_settings_changed)
        redact_form.addRow("Overlay Text:", self.overlay_input)
        redact_layout.addLayout(redact_form)

        self.scrub_meta_check = QCheckBox(
            "Also scrub document metadata && XMP"
        )
        self.scrub_meta_check.setChecked(self.controller.scrub_metadata_on_redact)
        self.scrub_meta_check.toggled.connect(self._on_redact_settings_changed)
        redact_layout.addWidget(self.scrub_meta_check)

        self.btn_apply_redactions = QPushButton("⬛ Apply Redactions Permanently")
        self.btn_apply_redactions.setProperty("danger", True)
        self.btn_apply_redactions.clicked.connect(self._on_apply_redactions_clicked)
        redact_layout.addWidget(self.btn_apply_redactions)
        root.addWidget(redact_group)

        # --- Group 4: Document Security & Metadata ---
        sec_group = QGroupBox("Document Security && Metadata")
        sec_layout = QVBoxLayout(sec_group)

        self.security_badge_label = QLabel("Status: 🔓 Unencrypted")
        sec_layout.addWidget(self.security_badge_label)

        btn_enc = QPushButton("🔒 Configure AES-256 Encryption...")
        btn_enc.clicked.connect(self._on_open_encryption_dialog)
        sec_layout.addWidget(btn_enc)

        meta_form = QFormLayout()
        self.meta_title_input = QLineEdit()
        self.meta_author_input = QLineEdit()
        meta_form.addRow("Title:", self.meta_title_input)
        meta_form.addRow("Author:", self.meta_author_input)
        sec_layout.addLayout(meta_form)

        btn_save_meta = QPushButton("Update Metadata")
        btn_save_meta.clicked.connect(self._on_save_metadata)
        sec_layout.addWidget(btn_save_meta)

        root.addWidget(sec_group)
        root.addStretch()

        self.refresh_signature_library()

    def _refresh_all(self) -> None:
        self._update_redaction_badge(self.controller.pending_redactions_count())
        self._update_security_badge(self.controller.encryption_config.enabled)
        meta = PikePDFEngine.get_metadata(self.controller.pdf_bytes)
        self.meta_title_input.setText(meta.get("Title", ""))
        self.meta_author_input.setText(meta.get("Author", ""))

    def refresh_signature_library(self) -> None:
        self.sig_list.clear()
        for sig in self.signature_store.list_signatures():
            img = sig.load_image()
            pix = QPixmap.fromImage(img)
            item = QListWidgetItem(QIcon(pix), sig.name)
            item.setData(self.SIG_ROLE, sig)
            self.sig_list.addItem(item)

    def _update_swatch_styles(self) -> None:
        active_rgb = self.controller.highlight_color
        for btn, rgb_tuple, hex_code in self._swatch_buttons:
            is_selected = rgb_tuple == active_rgb
            border = "3px solid #2563eb" if is_selected else "2px solid #475569"
            btn.setStyleSheet(
                f"background-color: {hex_code}; border: {border}; border-radius: 15px;"
            )

    def _set_markup_color(self, rgb: tuple[float, float, float]) -> None:
        self.controller.highlight_color = rgb
        self.controller.sticky_note_color = rgb
        self._update_swatch_styles()
        if self.controller.tool_mode not in (ToolMode.HIGHLIGHT, ToolMode.STICKY_NOTE):
            self.controller.set_tool_mode(ToolMode.HIGHLIGHT)

    def _on_saved_signature_clicked(self, item: QListWidgetItem) -> None:
        sig = item.data(self.SIG_ROLE)
        if isinstance(sig, SavedSignature):
            png_bytes = sig.load_png_bytes()
            if png_bytes:
                self.controller.request_signature_placement(png_bytes)

    def _place_selected_signature(self) -> None:
        item = self.sig_list.currentItem()
        if item is not None:
            self._on_saved_signature_clicked(item)
        else:
            self._on_open_signature_dialog()

    def _delete_selected_signature(self) -> None:
        item = self.sig_list.currentItem()
        if item is None:
            return
        sig = item.data(self.SIG_ROLE)
        if isinstance(sig, SavedSignature):
            self.signature_store.delete_signature(sig.sig_id)
            self.refresh_signature_library()

    def _on_redact_settings_changed(self) -> None:
        rgb = self.fill_combo.currentData()
        if isinstance(rgb, (tuple, list)) and len(rgb) == 3:
            self.controller.redact_fill_color = (
                float(rgb[0]),
                float(rgb[1]),
                float(rgb[2]),
            )
        self.controller.redact_overlay_text = self.overlay_input.text()
        self.controller.scrub_metadata_on_redact = self.scrub_meta_check.isChecked()

    def _update_redaction_badge(self, count: int) -> None:
        self.redact_count_label.setText(f"Pending Redactions: <b>{count}</b>")
        self.btn_apply_redactions.setEnabled(count > 0)
        self.btn_apply_redactions.setText(
            f"⬛ Apply Redactions Permanently ({count})"
            if count > 0
            else "⬛ Apply Redactions Permanently"
        )

    def _on_apply_redactions_clicked(self) -> None:
        pending = self.controller.pending_redactions_count()
        if pending <= 0:
            return
        scrub = self.scrub_meta_check.isChecked()
        meta_note = (
            "\n• Document metadata (/Info & XMP) WILL also be scrubbed."
            if scrub
            else "\n• Document metadata will be kept unchanged."
        )
        reply = QMessageBox.question(
            self,
            "Confirm Permanent Redaction",
            f"Are you sure you want to permanently apply {pending} redaction(s)?\n\n"
            "• Underlying text, vectors, and image pixels inside redaction boxes will be destroyed."
            f"{meta_note}\n"
            "• Saving this document will automatically prompt 'Save As' (_redacted.pdf) to protect your original file.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.controller.apply_all_redactions(sanitize_metadata=scrub)
            self._refresh_all()

    def _update_security_badge(self, encrypted: bool) -> None:
        if encrypted:
            self.security_badge_label.setText("Status: 🔒 <b>AES-256 Encrypted</b>")
        else:
            self.security_badge_label.setText("Status: 🔓 Unencrypted")

    def _on_save_metadata(self) -> None:
        self.controller.update_metadata(
            {
                "Title": self.meta_title_input.text().strip(),
                "Author": self.meta_author_input.text().strip(),
            }
        )

    def _on_tool_mode_changed(self, mode_str: str) -> None:
        hints = {
            ToolMode.PAN.value: (
                "<b>Active Tool:</b> Pan / Select<br>"
                "<span style='font-size:11px;'>Scroll, zoom (Ctrl+Wheel), or click Sticky Notes to edit.</span>"
            ),
            ToolMode.HIGHLIGHT.value: (
                "<b>Active Tool:</b> Smart Highlighter<br>"
                "<span style='font-size:11px;'>Drag across text lines (auto-snaps to words) or image regions.</span>"
            ),
            ToolMode.STICKY_NOTE.value: (
                "<b>Active Tool:</b> Sticky Note<br>"
                "<span style='font-size:11px;'>Click anywhere on a page to place a comment icon.</span>"
            ),
            ToolMode.SIGNATURE.value: (
                "<b>Active Tool:</b> E-Signature Placement<br>"
                "<span style='font-size:11px;'>Drag the signature box, resize its corner, and click ✔ Stamp.</span>"
            ),
            ToolMode.REDACT.value: (
                "<b>Active Tool:</b> Mark for Redaction<br>"
                "<span style='font-size:11px;'>Drag boxes over sensitive text/images, then click Apply Redactions.</span>"
            ),
        }
        self.tool_hint_label.setText(hints.get(mode_str, ""))
