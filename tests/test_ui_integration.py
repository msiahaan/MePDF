"""Integration tests for MainWindow, Multi-Tab Workspace, Theme Toggle, SignatureStore, and Redaction Save-As safety."""

from __future__ import annotations

from pathlib import Path
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from mepdf.core.document_controller import ToolMode, ViewMode
from mepdf.core.signature_store import SignatureStore
from mepdf.ui.main_window import MainWindow
from mepdf.ui.theme import ThemeManager, ThemeMode


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_signature_store_white_background_removal_and_library(tmp_path: Path, qapp) -> None:
    store = SignatureStore(storage_dir=tmp_path / "sigs")

    # Create an image with a solid white background and a dark blue stroke
    raw = QImage(200, 80, QImage.Format.Format_RGB32)
    raw.fill(QColor(255, 255, 255))
    painter = QPainter(raw)
    painter.setPen(QColor("#0f296b"))
    painter.drawLine(20, 40, 180, 40)
    painter.end()

    cleaned = SignatureStore.remove_white_background(raw)
    assert not cleaned.isNull()
    # Corner pixel should now be transparent
    assert cleaned.pixelColor(0, 0).alpha() == 0

    saved = store.save_signature("CEO Signature", cleaned)
    listed = store.list_signatures()
    assert len(listed) == 1
    assert listed[0].name == "CEO Signature"
    assert len(listed[0].load_png_bytes()) > 50

    store.delete_signature(saved.sig_id)
    assert len(store.list_signatures()) == 0


def test_main_window_multitab_theme_toggle_and_redaction_save_safety(tmp_path: Path, qapp) -> None:
    theme_mgr = ThemeManager(initial_mode=ThemeMode.DARK)
    store = SignatureStore(storage_dir=tmp_path / "sigs")
    win = MainWindow(theme_manager=theme_mgr, signature_store=store)

    # 1. Open two tabs (Sample PDF + Blank PDF)
    tab1 = win.action_open_sample_pdf()
    tab2 = win.action_new_blank_pdf()
    assert win.tab_widget.count() == 2
    assert win.current_tab() is tab2

    # Switch back to tab1
    win.tab_widget.setCurrentWidget(tab1)
    ctrl = tab1.controller
    assert ctrl.page_count == 3
    assert len(tab1.canvas._page_items) == 3
    assert not tab1.canvas._page_items[0].pixmap().isNull()

    # 2. Toggle Dark <-> Light theme
    assert theme_mgr.mode == ThemeMode.DARK
    new_theme = win.action_toggle_theme()
    assert new_theme == ThemeMode.LIGHT
    assert theme_mgr.is_dark is False
    win.action_toggle_theme()
    assert theme_mgr.is_dark is True

    # 3. Toggle Continuous <-> Single-Page View
    assert ctrl.view_mode == ViewMode.CONTINUOUS
    win.action_toggle_view_mode()
    assert ctrl.view_mode == ViewMode.SINGLE_PAGE
    win.action_toggle_view_mode()
    assert ctrl.view_mode == ViewMode.CONTINUOUS

    # 4. Save tab1 to disk, then test 2-step redaction + _redacted.pdf Save-As safety
    orig_file = tmp_path / "contract.pdf"
    ctrl.save_to_file(str(orig_file))
    assert ctrl.should_force_save_as() is False

    # Add a redaction and apply it permanently
    ctrl.add_redaction(0, (50, 200, 300, 240))
    assert ctrl.pending_redactions_count() == 1
    applied = ctrl.apply_all_redactions(sanitize_metadata=True)
    assert applied == 1
    assert ctrl.has_applied_redactions is True
    assert ctrl.should_force_save_as() is True
    assert ctrl.suggested_save_as_path().endswith("contract_redacted.pdf")

    # 5. Test Undo restores pre-redaction state and clears force-save-as flag
    ctrl.undo_stack.undo()
    assert ctrl.pending_redactions_count() == 1
    assert ctrl.has_applied_redactions is False
    ctrl.undo_stack.redo()
    assert ctrl.pending_redactions_count() == 0
    assert ctrl.has_applied_redactions is True


def test_toolbar_annotate_and_sign_actions_and_canvas_interactions(tmp_path: Path, qapp) -> None:
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent

    theme_mgr = ThemeManager(initial_mode=ThemeMode.DARK)
    store = SignatureStore(storage_dir=tmp_path / "sigs2")
    win = MainWindow(theme_manager=theme_mgr, signature_store=store)
    tab = win.action_open_sample_pdf()
    ctrl = tab.controller
    canvas = tab.canvas

    # 1. Trigger toolbar/menu QActions directly and verify ToolMode switches
    win.act_tool_highlight.trigger()
    assert ctrl.tool_mode == ToolMode.HIGHLIGHT

    win.act_tool_note.trigger()
    assert ctrl.tool_mode == ToolMode.STICKY_NOTE

    win.act_tool_redact.trigger()
    assert ctrl.tool_mode == ToolMode.REDACT

    win.act_tool_pan.trigger()
    assert ctrl.tool_mode == ToolMode.PAN

    # 2. Clicking a color swatch in InspectorPanel while in PAN mode switches to HIGHLIGHT
    swatch_btn, expected_rgb, _hex = tab.inspector_panel._swatch_buttons[1]
    swatch_btn.click()
    assert ctrl.highlight_color == expected_rgb
    assert ctrl.tool_mode == ToolMode.HIGHLIGHT

    # 3. Simulate a purely horizontal mouse drag (dy = 0) on page 0 in HIGHLIGHT mode
    page0_scene_rect = canvas._page_scene_rects[0]
    start_scene = QPointF(page0_scene_rect.left() + 80, page0_scene_rect.top() + 160)
    end_scene = QPointF(page0_scene_rect.left() + 340, page0_scene_rect.top() + 160)
    start_vp = canvas.mapFromScene(start_scene)
    end_vp = canvas.mapFromScene(end_scene)

    press_ev = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(start_vp),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    move_ev = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(end_vp),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    release_ev = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(end_vp),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    canvas.mousePressEvent(press_ev)
    canvas.mouseMoveEvent(move_ev)
    canvas.mouseReleaseEvent(release_ev)

    annots = ctrl.list_annotations(page_index=0)
    assert len(annots) == 1
    assert annots[0].annot_type == "Highlight"

    # 4. Place E-Signature overlay and click its "✔ Stamp" button
    sig_img = SignatureStore.render_typed_signature("Alex Rivera")
    png_bytes = SignatureStore.qimage_to_png_bytes(sig_img)
    ctrl.request_signature_placement(png_bytes)
    assert ctrl.tool_mode == ToolMode.SIGNATURE
    assert canvas._signature_overlay is not None

    # Click the Stamp button on the overlay
    overlay = canvas._signature_overlay
    stamp_scene_pt = overlay.mapToScene(overlay._stamp_btn_rect().center())
    stamp_vp_pt = canvas.mapFromScene(stamp_scene_pt)
    stamp_press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(stamp_vp_pt),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    canvas.mousePressEvent(stamp_press)
    qapp.processEvents()

    assert canvas._signature_overlay is None
    assert ctrl.tool_mode == ToolMode.PAN

