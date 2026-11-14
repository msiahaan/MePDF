"""Main Window for MePDF with Multi-Tab Workspace, Acrobat-Style Toolbar, and Live Dark/Light Theme Toggle."""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QDragEnterEvent, QDropEvent, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mepdf.core.document_controller import PDFDocumentController, ToolMode, ViewMode
from mepdf.core.mupdf_engine import MuPDFEngine
from mepdf.core.pikepdf_engine import PasswordRequiredError, PikePDFEngine
from mepdf.core.signature_store import SignatureStore
from mepdf.ui.document_tab import DocumentTabWidget
from mepdf.ui.theme import ThemeManager, ThemeMode


class MainWindow(QMainWindow):
    """Primary desktop window for MePDF."""

    def __init__(
        self,
        theme_manager: Optional[ThemeManager] = None,
        signature_store: Optional[SignatureStore] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("MePDF — Professional PDF Editor")
        self.resize(1380, 860)
        self.setAcceptDrops(True)

        self.theme_manager = theme_manager or ThemeManager()
        self.signature_store = signature_store or SignatureStore()

        self._build_actions_and_menus()
        self._build_toolbar()
        self._build_central_workspace()
        self._build_status_bar()

        self.theme_manager.themeChanged.connect(self._on_theme_changed)
        self._on_theme_changed(self.theme_manager.mode.value)
        self._sync_ui_to_active_tab()

    # ------------------------------------------------------------------
    # Menus & Toolbar Construction
    # ------------------------------------------------------------------
    def _build_actions_and_menus(self) -> None:
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("&File")
        self.act_open = QAction("Open", self)
        self.act_open.setToolTip("Open PDF Document (Ctrl+O)")
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open.triggered.connect(self.action_open_pdf)
        file_menu.addAction(self.act_open)

        self.act_new_blank = QAction("New Blank PDF", self)
        self.act_new_blank.setShortcut(QKeySequence("Ctrl+N"))
        self.act_new_blank.triggered.connect(self.action_new_blank_pdf)
        file_menu.addAction(self.act_new_blank)

        self.act_new_sample = QAction("Open Sample Demo PDF", self)
        self.act_new_sample.triggered.connect(self.action_open_sample_pdf)
        file_menu.addAction(self.act_new_sample)

        file_menu.addSeparator()
        self.act_save = QAction("Save", self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.triggered.connect(self.action_save)
        file_menu.addAction(self.act_save)

        self.act_save_as = QAction("Save As...", self)
        self.act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.act_save_as.triggered.connect(self.action_save_as)
        file_menu.addAction(self.act_save_as)

        file_menu.addSeparator()
        self.act_close_tab = QAction("Close Tab", self)
        self.act_close_tab.setShortcut(QKeySequence.StandardKey.Close)
        self.act_close_tab.triggered.connect(self._close_current_tab)
        file_menu.addAction(self.act_close_tab)

        # Edit Menu
        edit_menu = menubar.addMenu("&Edit")
        self.act_undo = QAction("Undo", self)
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_undo.triggered.connect(self.action_undo)
        edit_menu.addAction(self.act_undo)

        self.act_redo = QAction("Redo", self)
        self.act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.act_redo.triggered.connect(self.action_redo)
        edit_menu.addAction(self.act_redo)

        edit_menu.addSeparator()
        self.act_find = QAction("Find / Search & Redact...", self)
        self.act_find.setShortcut(QKeySequence.StandardKey.Find)
        self.act_find.triggered.connect(self.action_focus_search)
        edit_menu.addAction(self.act_find)

        # View Menu
        view_menu = menubar.addMenu("&View")
        self.act_toggle_view_mode = QAction("Continuous Scroll View", self)
        self.act_toggle_view_mode.setCheckable(True)
        self.act_toggle_view_mode.setChecked(True)
        self.act_toggle_view_mode.triggered.connect(self.action_toggle_view_mode)
        view_menu.addAction(self.act_toggle_view_mode)

        view_menu.addSeparator()
        self.act_toggle_theme = QAction("Switch Dark / Light Theme", self)
        self.act_toggle_theme.setShortcut(QKeySequence("Ctrl+T"))
        self.act_toggle_theme.triggered.connect(self.action_toggle_theme)
        view_menu.addAction(self.act_toggle_theme)

        # Page Menu (pikepdf)
        page_menu = menubar.addMenu("&Page")
        self.act_organize = QAction("Organize", self)
        self.act_organize.setToolTip("Open Organize Pages Multi-Column Grid")
        self.act_organize.triggered.connect(self.action_organize_pages)
        page_menu.addAction(self.act_organize)

        self.act_rot_left = QAction("Rotate L", self)
        self.act_rot_left.setToolTip("Rotate Current Page Left (-90°)")
        self.act_rot_left.triggered.connect(lambda: self.action_rotate_current(-90))
        page_menu.addAction(self.act_rot_left)

        self.act_rot_right = QAction("Rotate R", self)
        self.act_rot_right.setToolTip("Rotate Current Page Right (+90°)")
        self.act_rot_right.triggered.connect(lambda: self.action_rotate_current(90))
        page_menu.addAction(self.act_rot_right)

        self.act_insert_blank = QAction("Insert Blank Page", self)
        self.act_insert_blank.triggered.connect(self.action_insert_blank_page)
        page_menu.addAction(self.act_insert_blank)

        self.act_merge = QAction("Merge", self)
        self.act_merge.setToolTip("Merge / Insert External PDF Files")
        self.act_merge.triggered.connect(self.action_merge_pdfs)
        page_menu.addAction(self.act_merge)

        self.act_split = QAction("Split", self)
        self.act_split.setToolTip("Split or Extract PDF Pages")
        self.act_split.triggered.connect(self.action_split_pdf)
        page_menu.addAction(self.act_split)

        # Annotate & Redact Menu (PyMuPDF)
        annot_menu = menubar.addMenu("&Annotate && Sign")
        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)

        self.act_tool_pan = QAction("Pan", self)
        self.act_tool_pan.setToolTip("Pan / Select Tool")
        self.act_tool_pan.setCheckable(True)
        self.act_tool_pan.setChecked(True)
        self.act_tool_pan.setData(ToolMode.PAN)

        self.act_tool_highlight = QAction("Highlight", self)
        self.act_tool_highlight.setToolTip("Smart Text-Snap Highlighter")
        self.act_tool_highlight.setCheckable(True)
        self.act_tool_highlight.setData(ToolMode.HIGHLIGHT)

        self.act_tool_note = QAction("Note", self)
        self.act_tool_note.setToolTip("Add Sticky Note")
        self.act_tool_note.setCheckable(True)
        self.act_tool_note.setData(ToolMode.STICKY_NOTE)

        self.act_tool_sign = QAction("E-Sign", self)
        self.act_tool_sign.setToolTip("Create or Place Visual E-Signature")
        self.act_tool_sign.setCheckable(True)
        self.act_tool_sign.setData(ToolMode.SIGNATURE)

        self.act_tool_redact = QAction("Redact", self)
        self.act_tool_redact.setToolTip("Mark Area for Permanent Redaction")
        self.act_tool_redact.setCheckable(True)
        self.act_tool_redact.setData(ToolMode.REDACT)

        for act in (
            self.act_tool_pan,
            self.act_tool_highlight,
            self.act_tool_note,
            self.act_tool_sign,
            self.act_tool_redact,
        ):
            self.tool_group.addAction(act)
            annot_menu.addAction(act)

        self.tool_group.triggered.connect(self._on_tool_action_triggered)

        # Security Menu (pikepdf)
        sec_menu = menubar.addMenu("&Security")
        self.act_encrypt = QAction("Encrypt", self)
        self.act_encrypt.setToolTip("Configure AES-256 Encryption & Permissions")
        self.act_encrypt.triggered.connect(self.action_configure_encryption)
        sec_menu.addAction(self.act_encrypt)

    def _build_toolbar(self) -> None:
        self.toolbar = QToolBar("Main Toolbar", self)
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(18, 18))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        self.toolbar.addAction(self.act_open)
        self.toolbar.addAction(self.act_save)
        self.toolbar.addSeparator()

        self.toolbar.addAction(self.act_undo)
        self.toolbar.addAction(self.act_redo)
        self.toolbar.addSeparator()

        # View Mode Toggle button
        self.btn_view_mode = QToolButton()
        self.btn_view_mode.setText("📜 Continuous")
        self.btn_view_mode.setToolTip("Toggle between Continuous Vertical Scroll and Single-Page View")
        self.btn_view_mode.setCheckable(True)
        self.btn_view_mode.setChecked(True)
        self.btn_view_mode.clicked.connect(self.action_toggle_view_mode)
        self.toolbar.addWidget(self.btn_view_mode)
        self.toolbar.addSeparator()

        # Markup & Redaction Tools
        self.toolbar.addAction(self.act_tool_pan)
        self.toolbar.addAction(self.act_tool_highlight)
        self.toolbar.addAction(self.act_tool_note)
        self.toolbar.addAction(self.act_tool_sign)
        self.toolbar.addAction(self.act_tool_redact)
        self.toolbar.addSeparator()

        # Page & Security Tools
        self.toolbar.addAction(self.act_organize)
        self.toolbar.addAction(self.act_merge)
        self.toolbar.addAction(self.act_split)
        self.toolbar.addAction(self.act_encrypt)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.act_toggle_theme)

        self.btn_theme_toggle = QToolButton()
        self.btn_theme_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_theme_toggle.setToolTip("Switch between Dark Theme and Light Theme (Ctrl+T)")
        self.btn_theme_toggle.clicked.connect(self.action_toggle_theme)
        self.menuBar().setCornerWidget(self.btn_theme_toggle, Qt.Corner.TopRightCorner)

    # ------------------------------------------------------------------
    # Central Multi-Tab Workspace & Welcome Screen
    # ------------------------------------------------------------------
    def _build_central_workspace(self) -> None:
        self.central_stack = QStackedWidget()
        self.setCentralWidget(self.central_stack)

        # Page 0: Empty-state Welcome Screen
        welcome = QWidget()
        w_layout = QVBoxLayout(welcome)
        w_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QWidget()
        card.setMaximumWidth(560)
        c_layout = QVBoxLayout(card)
        c_layout.setSpacing(14)

        title = QLabel("<h1 style='margin-bottom:4px;'>Welcome to MePDF</h1>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_layout.addWidget(title)

        subtitle = QLabel(
            "Clean, fast PDF editing powered by <b>PyMuPDF</b> & <b>pikepdf</b>.<br>"
            "Highlight, annotate with sticky notes, place visual E-Signatures, permanently redact,<br>"
            "reorganize/merge/split pages, and protect documents with AES-256 encryption."
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        c_layout.addWidget(subtitle)

        btn_row1 = QHBoxLayout()
        btn_open = QPushButton("📂 Open PDF File...")
        btn_open.setProperty("primary", True)
        btn_open.setMinimumHeight(40)
        btn_open.clicked.connect(self.action_open_pdf)
        btn_row1.addWidget(btn_open)

        btn_sample = QPushButton("✨ Open Sample Demo PDF")
        btn_sample.setMinimumHeight(40)
        btn_sample.clicked.connect(self.action_open_sample_pdf)
        btn_row1.addWidget(btn_sample)
        c_layout.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        btn_blank = QPushButton("📄 Create New Blank PDF")
        btn_blank.setMinimumHeight(36)
        btn_blank.clicked.connect(self.action_new_blank_pdf)
        btn_row2.addWidget(btn_blank)

        btn_merge_welcome = QPushButton("📑 Merge Multiple PDFs...")
        btn_merge_welcome.setMinimumHeight(36)
        btn_merge_welcome.clicked.connect(self.action_merge_pdfs)
        btn_row2.addWidget(btn_merge_welcome)
        c_layout.addLayout(btn_row2)

        w_layout.addWidget(card)
        self.central_stack.addWidget(welcome)

        # Page 1: Multi-Tab Document Container
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget. setDocumentMode(True)
        self.tab_widget.currentChanged.connect(self._on_active_tab_changed)
        self.tab_widget.tabCloseRequested.connect(self.close_tab_at)
        self.central_stack.addWidget(self.tab_widget)

    def _build_status_bar(self) -> None:
        status = QStatusBar(self)
        self.setStatusBar(status)

        self.lbl_security_status = QLabel("🔓 Unencrypted")
        status.addWidget(self.lbl_security_status)

        self.lbl_view_status = QLabel("View: Continuous")
        status.addWidget(self.lbl_view_status)

        # Page navigation controls
        nav_widget = QWidget()
        nav_layout = QHBoxLayout(nav_widget)
        nav_layout.setContentsMargins(6, 0, 6, 0)
        nav_layout.setSpacing(4)

        self.btn_prev_page = QPushButton("◀")
        self.btn_prev_page.setFixedWidth(28)
        self.btn_prev_page.clicked.connect(self._prev_page)
        nav_layout.addWidget(self.btn_prev_page)

        self.lbl_page_counter = QLabel("Page 0 of 0")
        nav_layout.addWidget(self.lbl_page_counter)

        self.btn_next_page = QPushButton("▶")
        self.btn_next_page.setFixedWidth(28)
        self.btn_next_page.clicked.connect(self._next_page)
        nav_layout.addWidget(self.btn_next_page)
        status.addPermanentWidget(nav_widget)

        # Zoom controls
        zoom_widget = QWidget()
        zoom_layout = QHBoxLayout(zoom_widget)
        zoom_layout.setContentsMargins(6, 0, 4, 0)
        zoom_layout.setSpacing(6)

        self.lbl_zoom_pct = QLabel("125%")
        self.lbl_zoom_pct.setMinimumWidth(44)
        zoom_layout.addWidget(self.lbl_zoom_pct)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(25, 400)
        self.zoom_slider.setValue(125)
        self.zoom_slider.setFixedWidth(130)
        self.zoom_slider.valueChanged.connect(self._on_zoom_slider_changed)
        zoom_layout.addWidget(self.zoom_slider)

        btn_fit_w = QPushButton("Fit Width")
        btn_fit_w.clicked.connect(self._fit_width)
        zoom_layout.addWidget(btn_fit_w)

        btn_fit_p = QPushButton("Fit Page")
        btn_fit_p.clicked.connect(self._fit_page)
        zoom_layout.addWidget(btn_fit_p)

        btn_100 = QPushButton("100%")
        btn_100.clicked.connect(lambda: self._set_zoom_pct(100))
        zoom_layout.addWidget(btn_100)

        status.addPermanentWidget(zoom_widget)

    # ------------------------------------------------------------------
    # Tab Management
    # ------------------------------------------------------------------
    def current_tab(self) -> Optional[DocumentTabWidget]:
        w = self.tab_widget.currentWidget()
        return w if isinstance(w, DocumentTabWidget) else None

    def current_controller(self) -> Optional[PDFDocumentController]:
        tab = self.current_tab()
        return tab.controller if tab is not None else None

    def add_document_tab(self, controller: PDFDocumentController) -> DocumentTabWidget:
        tab = DocumentTabWidget(
            controller=controller,
            signature_store=self.signature_store,
            on_signatures_changed=self._refresh_all_signature_libraries,
            parent=self,
        )
        tab.set_canvas_background(self.theme_manager.canvas_background_color())
        idx = self.tab_widget.addTab(tab, controller.display_title)
        self.tab_widget.setCurrentIndex(idx)
        self.central_stack.setCurrentWidget(self.tab_widget)

        controller.documentModified.connect(lambda _m, t=tab: self._update_tab_title(t))
        controller.pageChanged.connect(lambda _p: self._sync_status_bar())
        controller.pagesStructureChanged.connect(self._sync_status_bar)
        controller.zoomChanged.connect(lambda _z: self._sync_status_bar())
        controller.viewModeChanged.connect(lambda _v: self._sync_status_bar())
        controller.toolModeChanged.connect(lambda _tm: self._sync_tool_actions())
        controller.encryptionChanged.connect(lambda _e: self._sync_status_bar())

        self._sync_ui_to_active_tab()
        return tab

    def _update_tab_title(self, tab: DocumentTabWidget) -> None:
        idx = self.tab_widget.indexOf(tab)
        if idx >= 0:
            self.tab_widget.setTabText(idx, tab.controller.display_title)

    def _close_current_tab(self) -> None:
        idx = self.tab_widget.currentIndex()
        if idx >= 0:
            self.close_tab_at(idx)

    def close_tab_at(self, index: int) -> bool:
        w = self.tab_widget.widget(index)
        if isinstance(w, DocumentTabWidget) and w.controller.is_modified:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                f"Save changes to '{w.controller.raw_title}' before closing?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return False
            if reply == QMessageBox.StandardButton.Save:
                self.tab_widget.setCurrentIndex(index)
                if not self.action_save():
                    return False

        self.tab_widget.removeTab(index)
        if self.tab_widget.count() == 0:
            self.central_stack.setCurrentIndex(0)
        self._sync_ui_to_active_tab()
        return True

    def _on_active_tab_changed(self, _index: int) -> None:
        self._sync_ui_to_active_tab()

    def _refresh_all_signature_libraries(self) -> None:
        for i in range(self.tab_widget.count()):
            w = self.tab_widget.widget(i)
            if isinstance(w, DocumentTabWidget):
                w.inspector_panel.refresh_signature_library()

    # ------------------------------------------------------------------
    # File Operations (Open, New, Sample, Save, Save As with _redacted safety)
    # ------------------------------------------------------------------
    def action_open_pdf(self, file_path: Optional[str] = None) -> Optional[DocumentTabWidget]:
        if not file_path:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Open PDF Document",
                "",
                "PDF Documents (*.pdf)",
            )
        if not file_path:
            return None

        ctrl = PDFDocumentController(self)
        password = ""
        while True:
            try:
                ctrl.load_from_file(file_path, password=password)
                break
            except PasswordRequiredError:
                pw, ok = QInputDialog.getText(
                    self,
                    "Password Protected PDF",
                    f"'{Path(file_path).name}' is encrypted. Enter password:",
                    QLineEdit.EchoMode.Password,
                )
                if not ok:
                    return None
                password = pw
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Failed to Open PDF",
                    f"Could not open '{file_path}':\n{exc}",
                )
                return None

        return self.add_document_tab(ctrl)

    def action_new_blank_pdf(self) -> DocumentTabWidget:
        ctrl = PDFDocumentController(self)
        blank_bytes = PikePDFEngine.insert_blank_page(None, index=0)
        ctrl.load_from_bytes(blank_bytes, title="Untitled.pdf")
        return self.add_document_tab(ctrl)

    def action_open_sample_pdf(self) -> DocumentTabWidget:
        ctrl = PDFDocumentController(self)
        sample_bytes = MuPDFEngine.create_sample_pdf(num_pages=3)
        ctrl.load_from_bytes(sample_bytes, title="MePDF_Sample_Guide.pdf")
        return self.add_document_tab(ctrl)

    def action_save(self) -> bool:
        ctrl = self.current_controller()
        if ctrl is None:
            return False
        if ctrl.should_force_save_as():
            return self.action_save_as()
        try:
            ctrl.save_to_file()
            self._update_tab_title(self.current_tab())
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", f"Failed to save PDF:\n{exc}")
            return False

    def action_save_as(self) -> bool:
        ctrl = self.current_controller()
        if ctrl is None:
            return False
        suggested = ctrl.suggested_save_as_path()
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PDF As",
            suggested,
            "PDF Documents (*.pdf)",
        )
        if not out_path:
            return False
        try:
            ctrl.save_to_file(out_path)
            tab = self.current_tab()
            if tab is not None:
                self._update_tab_title(tab)
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Save As Error", f"Failed to save PDF:\n{exc}")
            return False

    # ------------------------------------------------------------------
    # Edit, View, Tool & Page Actions
    # ------------------------------------------------------------------
    def action_undo(self) -> None:
        ctrl = self.current_controller()
        if ctrl is not None and ctrl.undo_stack.canUndo():
            ctrl.undo_stack.undo()

    def action_redo(self) -> None:
        ctrl = self.current_controller()
        if ctrl is not None and ctrl.undo_stack.canRedo():
            ctrl.undo_stack.redo()

    def action_focus_search(self) -> None:
        tab = self.current_tab()
        if tab is not None:
            tab.focus_search_tab()

    def action_toggle_view_mode(self) -> None:
        ctrl = self.current_controller()
        if ctrl is None:
            return
        ctrl.toggle_view_mode()
        self._sync_status_bar()

    def action_toggle_theme(self) -> ThemeMode:
        return self.theme_manager.toggle_theme()

    def select_tool_mode(self, mode: ToolMode) -> None:
        tab = self.current_tab()
        if tab is None:
            return
        if mode == ToolMode.SIGNATURE:
            tab.open_signature_dialog()
            self._sync_tool_actions()
        else:
            tab.controller.set_tool_mode(mode)

    def _on_tool_action_triggered(self, action: QAction) -> None:
        raw_data = action.data()
        try:
            mode = (
                raw_data
                if isinstance(raw_data, ToolMode)
                else ToolMode(str(raw_data))
            )
        except ValueError:
            return
        self.select_tool_mode(mode)

    def action_organize_pages(self) -> None:
        tab = self.current_tab()
        if tab is not None:
            tab.open_organize_pages_dialog()

    def action_rotate_current(self, delta: int) -> None:
        ctrl = self.current_controller()
        if ctrl is not None and ctrl.page_count > 0:
            ctrl.rotate_pages([ctrl.current_page], delta)

    def action_insert_blank_page(self) -> None:
        ctrl = self.current_controller()
        if ctrl is not None:
            ctrl.insert_blank_page()

    def action_merge_pdfs(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select PDF Files to Merge",
            "",
            "PDF Documents (*.pdf)",
        )
        if not files:
            return
        ctrl = self.current_controller()
        if ctrl is None:
            # Create a new merged document tab from the selected files
            merged_bytes = PikePDFEngine.merge_pdfs(None, files)
            new_ctrl = PDFDocumentController(self)
            new_ctrl.load_from_bytes(merged_bytes, title="Merged_Document.pdf")
            self.add_document_tab(new_ctrl)
        else:
            ctrl.merge_pdfs(files)

    def action_split_pdf(self) -> None:
        tab = self.current_tab()
        if tab is not None:
            tab.open_split_dialog()

    def action_configure_encryption(self) -> None:
        tab = self.current_tab()
        if tab is not None:
            tab.open_encryption_dialog()

    # ------------------------------------------------------------------
    # Status Bar, Theme & Sync Helpers
    # ------------------------------------------------------------------
    def _prev_page(self) -> None:
        ctrl = self.current_controller()
        if ctrl is not None:
            ctrl.set_current_page(ctrl.current_page - 1)

    def _next_page(self) -> None:
        ctrl = self.current_controller()
        if ctrl is not None:
            ctrl.set_current_page(ctrl.current_page + 1)

    def _on_zoom_slider_changed(self, value: int) -> None:
        ctrl = self.current_controller()
        if ctrl is not None:
            ctrl.set_zoom(value / 100.0)

    def _set_zoom_pct(self, pct: int) -> None:
        ctrl = self.current_controller()
        if ctrl is not None:
            ctrl.set_zoom(pct / 100.0)

    def _fit_width(self) -> None:
        tab = self.current_tab()
        if tab is not None:
            tab.canvas.fit_to_width()

    def _fit_page(self) -> None:
        tab = self.current_tab()
        if tab is not None:
            tab.canvas.fit_to_page()

    def _sync_ui_to_active_tab(self) -> None:
        has_doc = self.current_controller() is not None
        for act in (
            self.act_save,
            self.act_save_as,
            self.act_close_tab,
            self.act_undo,
            self.act_redo,
            self.act_find,
            self.act_organize,
            self.act_rot_left,
            self.act_rot_right,
            self.act_insert_blank,
            self.act_split,
            self.act_encrypt,
            self.act_tool_pan,
            self.act_tool_highlight,
            self.act_tool_note,
            self.act_tool_sign,
            self.act_tool_redact,
        ):
            act.setEnabled(has_doc)
        self.btn_view_mode.setEnabled(has_doc)
        self._sync_tool_actions()
        self._sync_status_bar()

    def _sync_tool_actions(self) -> None:
        ctrl = self.current_controller()
        if ctrl is None:
            return
        mode = ctrl.tool_mode
        mapping = {
            ToolMode.PAN: self.act_tool_pan,
            ToolMode.HIGHLIGHT: self.act_tool_highlight,
            ToolMode.STICKY_NOTE: self.act_tool_note,
            ToolMode.SIGNATURE: self.act_tool_sign,
            ToolMode.REDACT: self.act_tool_redact,
        }
        act = mapping.get(mode)
        if act is not None and not act.isChecked():
            act.setChecked(True)

    def _sync_status_bar(self) -> None:
        ctrl = self.current_controller()
        if ctrl is None:
            self.lbl_security_status.setText("Ready")
            self.lbl_view_status.setText("No Document Open")
            self.lbl_page_counter.setText("Page 0 of 0")
            return

        if ctrl.encryption_config.enabled:
            self.lbl_security_status.setText("🔒 AES-256 Protected")
        else:
            self.lbl_security_status.setText("🔓 Unencrypted")

        is_cont = ctrl.view_mode == ViewMode.CONTINUOUS
        self.act_toggle_view_mode.setChecked(is_cont)
        self.btn_view_mode.setChecked(is_cont)
        self.btn_view_mode.setText("📜 Continuous" if is_cont else "📄 Single Page")
        self.lbl_view_status.setText(
            "View: Continuous Scroll" if is_cont else "View: Single Page"
        )

        total = ctrl.page_count
        cur = ctrl.current_page + 1 if total > 0 else 0
        self.lbl_page_counter.setText(f"Page {cur} of {total}")

        pct = int(round(ctrl.zoom * 100))
        self.lbl_zoom_pct.setText(f"{pct}%")
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(pct)
        self.zoom_slider.blockSignals(False)

    def _on_theme_changed(self, _mode_str: str) -> None:
        tm = self.theme_manager
        tm.apply_to_app()

        # Update dynamic vector icons for current theme
        self.act_open.setIcon(tm.icon("open"))
        self.act_save.setIcon(tm.icon("save"))
        self.act_undo.setIcon(tm.icon("undo"))
        self.act_redo.setIcon(tm.icon("redo"))
        self.act_tool_pan.setIcon(tm.icon("pan"))
        self.act_tool_highlight.setIcon(tm.icon("highlight"))
        self.act_tool_note.setIcon(tm.icon("sticky_note"))
        self.act_tool_sign.setIcon(tm.icon("signature"))
        self.act_tool_redact.setIcon(tm.icon("redact"))
        self.act_organize.setIcon(tm.icon("organize"))
        self.act_rot_left.setIcon(tm.icon("rotate_left"))
        self.act_rot_right.setIcon(tm.icon("rotate_right"))
        self.act_encrypt.setIcon(tm.icon("encrypt"))

        if tm.is_dark:
            self.act_toggle_theme.setIcon(tm.icon("theme_dark"))
            self.act_toggle_theme.setText("☀ Light Mode")
            self.btn_theme_toggle.setIcon(tm.icon("theme_dark"))
            self.btn_theme_toggle.setText("☀ Light Mode")
        else:
            self.act_toggle_theme.setIcon(tm.icon("theme_light"))
            self.act_toggle_theme.setText("🌙 Dark Mode")
            self.btn_theme_toggle.setIcon(tm.icon("theme_light"))
            self.btn_theme_toggle.setText("🌙 Dark Mode")

        bg_color = tm.canvas_background_color()
        for i in range(self.tab_widget.count()):
            w = self.tab_widget.widget(i)
            if isinstance(w, DocumentTabWidget):
                w.set_canvas_background(bg_color)

    # ------------------------------------------------------------------
    # Drag-and-Drop File Opening
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return
        super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local.lower().endswith(".pdf"):
                self.action_open_pdf(local)
        event.acceptProposedAction()
