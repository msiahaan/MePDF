"""AES-256 Encryption and Permissions Dialog powered by pikepdf."""

from __future__ import annotations

from copy import deepcopy
from typing import Optional
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from mepdf.core.pikepdf_engine import EncryptionConfig, EncryptionPermissions


class EncryptionDialog(QDialog):
    """Modal dialog for configuring PDF password security and granular permissions."""

    def __init__(
        self,
        current_config: EncryptionConfig,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Document Security & AES-256 Encryption")
        self.resize(480, 440)
        self._config = deepcopy(current_config)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        banner = QLabel(
            "Protect this PDF with 256-bit AES encryption (pikepdf R=6) when saving."
        )
        banner.setWordWrap(True)
        root.addWidget(banner)

        self.enable_check = QCheckBox("Enable Password Encryption & Permission Controls")
        self.enable_check.setChecked(self._config.enabled)
        self.enable_check.toggled.connect(self._update_enabled_state)
        root.addWidget(self.enable_check)

        # Password group
        self.pw_group = QGroupBox("Passwords")
        pw_form = QFormLayout(self.pw_group)

        self.user_pw_input = QLineEdit(self._config.user_password)
        self.user_pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.user_pw_input.setPlaceholderText("Required to open the document")
        pw_form.addRow("Document Open Password:", self.user_pw_input)

        self.owner_pw_input = QLineEdit(self._config.owner_password)
        self.owner_pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.owner_pw_input.setPlaceholderText("Required to change permissions (optional)")
        pw_form.addRow("Permissions / Owner Password:", self.owner_pw_input)

        show_pw_row = QHBoxLayout()
        self.show_pw_check = QCheckBox("Show passwords")
        self.show_pw_check.toggled.connect(self._on_toggle_show_passwords)
        show_pw_row.addWidget(self.show_pw_check)
        show_pw_row.addStretch()
        pw_form.addRow("", show_pw_row)
        root.addWidget(self.pw_group)

        # Permissions group
        self.perm_group = QGroupBox("Allowed Document Permissions")
        perm_layout = QVBoxLayout(self.perm_group)
        p = self._config.permissions

        self.chk_print_high = QCheckBox("Allow High-Resolution Printing")
        self.chk_print_high.setChecked(p.allow_print_highres)
        perm_layout.addWidget(self.chk_print_high)

        self.chk_print_low = QCheckBox("Allow Low-Resolution Printing")
        self.chk_print_low.setChecked(p.allow_print_lowres)
        perm_layout.addWidget(self.chk_print_low)

        self.chk_extract = QCheckBox("Allow Copying Text, Images, and Content")
        self.chk_extract.setChecked(p.allow_extract)
        perm_layout.addWidget(self.chk_extract)

        self.chk_annot = QCheckBox("Allow Adding/Editing Highlights & Sticky Notes")
        self.chk_annot.setChecked(p.allow_modify_annotation)
        perm_layout.addWidget(self.chk_annot)

        self.chk_form = QCheckBox("Allow Filling Form Fields & Signing")
        self.chk_form.setChecked(p.allow_modify_form)
        perm_layout.addWidget(self.chk_form)

        self.chk_assembly = QCheckBox("Allow Page Assembly (Insert, Rotate, Delete Pages)")
        self.chk_assembly.setChecked(p.allow_modify_assembly)
        perm_layout.addWidget(self.chk_assembly)

        self.chk_other = QCheckBox("Allow Other Content Modifications")
        self.chk_other.setChecked(p.allow_modify_other)
        perm_layout.addWidget(self.chk_other)

        self.chk_access = QCheckBox("Allow Screen Reader Text Access (Accessibility)")
        self.chk_access.setChecked(p.allow_accessibility)
        perm_layout.addWidget(self.chk_access)

        root.addWidget(self.perm_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Apply Security Settings")
        ok_btn.setProperty("primary", True)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._update_enabled_state(self.enable_check.isChecked())

    def _update_enabled_state(self, enabled: bool) -> None:
        self.pw_group.setEnabled(enabled)
        self.perm_group.setEnabled(enabled)

    def _on_toggle_show_passwords(self, checked: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self.user_pw_input.setEchoMode(mode)
        self.owner_pw_input.setEchoMode(mode)

    def _on_accept(self) -> None:
        enabled = self.enable_check.isChecked()
        user_pw = self.user_pw_input.text()
        owner_pw = self.owner_pw_input.text()
        if enabled and not user_pw and not owner_pw:
            QMessageBox.warning(
                self,
                "Password Required",
                "Please enter a Document Open Password or Owner Password to enable encryption.",
            )
            return

        self._config = EncryptionConfig(
            enabled=enabled,
            user_password=user_pw,
            owner_password=owner_pw or user_pw,
            permissions=EncryptionPermissions(
                allow_print_highres=self.chk_print_high.isChecked(),
                allow_print_lowres=self.chk_print_low.isChecked(),
                allow_extract=self.chk_extract.isChecked(),
                allow_modify_annotation=self.chk_annot.isChecked(),
                allow_modify_form=self.chk_form.isChecked(),
                allow_modify_assembly=self.chk_assembly.isChecked(),
                allow_modify_other=self.chk_other.isChecked(),
                allow_accessibility=self.chk_access.isChecked(),
            ),
        )
        self.accept()

    def result_config(self) -> EncryptionConfig:
        return self._config
