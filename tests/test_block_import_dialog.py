"""Tests for BlockImportDialog — the flattened block-editor import dialog.

Construction tests verify the structural guarantees (no rail, no name field,
no levels picker, flat panel, noop step navigation) and that the parent dialog
still builds its full UI by default (backwards-compat guard).
"""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget

from firepro3d.block_import_dialog import BlockImportDialog
from firepro3d.underlay_import_dialog import ImportParams


# ---------------------------------------------------------------------------
# CYCLE 1 — construction + structural invariants
# ---------------------------------------------------------------------------


def test_block_import_dialog_constructs_flat(qapp):
    dlg = BlockImportDialog(None)
    try:
        assert dlg.objectName() == "BlockImportDialog"
        assert "Import Geometry" in dlg.windowTitle()

        # No levels picker, no name field (block-specific omissions).
        assert not hasattr(dlg, "_levels_picker"), (
            "_levels_picker must not be built when include_levels=False")
        assert not hasattr(dlg, "_name_edit"), (
            "_name_edit must not be built when include_name=False")

        # Rail detached (hidden / no parent).
        rail = getattr(dlg, "_rail", None)
        assert rail is None or rail.parent() is None or rail.isHidden(), (
            "Rail must be detached or hidden after _flatten_layout()")

        # Flat panel attribute present AND actually placed in the visible layout
        # (a failed layout-swap would leave it orphaned with no parent — the
        # 'right panel not visible' bug).
        assert hasattr(dlg, "_flat_panel"), (
            "_flat_panel (QScrollArea) must be created by _flatten_layout()")
        assert dlg._flat_panel.parentWidget() is not None, (
            "_flat_panel must be parented into the body layout, not orphaned")
        # The old QStackedWidget must be emptied (all 3 pages reparented out).
        assert dlg._panel_stack.count() == 0, (
            "all panel pages must be moved out of the stack into the flat column")
        # All three pages live in the flat column and are visible.
        col = dlg._flat_panel.widget()
        page_kids = [c for c in col.findChildren(QWidget)
                     if c.parent() is col]
        assert len(page_kids) >= 3, (
            f"expected >=3 section pages in the flat column, got {len(page_kids)}")

        # Params still work (empty levels/name via guards).
        p = dlg.get_import_params()
        assert isinstance(p, ImportParams)
        assert p.levels == [], f"Expected empty levels, got {p.levels!r}"
        assert p.name == "", f"Expected empty name, got {p.name!r}"
    finally:
        dlg.deleteLater()


# ---------------------------------------------------------------------------
# CYCLE 2 — step-navigation is a no-op
# ---------------------------------------------------------------------------


def test_block_import_dialog_switch_step_is_noop(qapp):
    dlg = BlockImportDialog(None)
    try:
        dlg._switch_step("content")    # must not raise (no rail/stack navigation)
        dlg._switch_step("place")
        dlg._switch_step("source")
        dlg._on_rail_clicked("content")  # also must not raise
    finally:
        dlg.deleteLater()


# ---------------------------------------------------------------------------
# Multi-layout DWG/DXF auto-previews the Model layout (block-specific)
# ---------------------------------------------------------------------------


def test_multi_layout_auto_selects_model(qapp):
    import ezdxf
    doc = ezdxf.new()
    doc.modelspace().add_line((0, 0), (10, 0))
    doc.layouts.new("Sheet1")                 # -> multi-layout (Model + sheets)
    dlg = BlockImportDialog(None)
    try:
        dlg._file_type = "dxf"
        dlg._on_dxf_read("plan.dxf", doc)
        # Block editor auto-selects Model instead of leaving the "pick a layout"
        # placeholder (the shared underlay dialog leaves it unselected).
        assert dlg._layout_combo.currentText() == "Model"
    finally:
        dlg.deleteLater()


# ---------------------------------------------------------------------------
# CYCLE 3 — parent still builds name+levels by default (backwards-compat)
# ---------------------------------------------------------------------------


def test_underlay_dialog_keeps_name_and_levels_by_default(qapp):
    from firepro3d.underlay_import_dialog import UnderlayImportDialog
    dlg = UnderlayImportDialog(None, levels=["Level 1"], current_level="Level 1")
    try:
        assert hasattr(dlg, "_name_edit"), (
            "_name_edit must be present on the default (include_name=True) dialog")
        assert hasattr(dlg, "_levels_picker"), (
            "_levels_picker must be present on the default (include_levels=True) dialog")
    finally:
        dlg.deleteLater()


# ---------------------------------------------------------------------------
# CYCLE 4 — _controls_panel is still present (needed by _set_controls_enabled)
# ---------------------------------------------------------------------------


def test_block_import_dialog_controls_panel_present(qapp):
    dlg = BlockImportDialog(None)
    try:
        panel = getattr(dlg, "_controls_panel", None)
        assert panel is not None, (
            "_controls_panel must survive _flatten_layout() for extraction guarding")
        # Must be enable/disable-able without raising.
        dlg._set_controls_enabled(False)
        dlg._set_controls_enabled(True)
    finally:
        dlg.deleteLater()
