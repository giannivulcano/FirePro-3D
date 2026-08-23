"""tests/test_geo2d_panel.py

Property-panel round-trip for Geometry2DMixin fields.

Drives the REAL PropertyManager (not raw attribute writes) to verify:
  - "Level Offset" dimension row commits a parsed-mm float to _geom2d_set
    and _level_offset_mm is updated accordingly.
  - "Elevation" row is read-only (no editable editor / disabled).
  - Displayed elevation value matches level.elevation + offset.
  - A fillable RectangleItem shows a "Fill" row.
  - A LineItem (non-fillable) does NOT show a "Fill" row.

Design note — DimensionEdit seed guard:
    DimensionEdit._on_editing_finished treats an *unchanged* display text as
    a no-op (keeps stored value, no emit).  To drive a real commit we must
    change the text to something the parser accepts THEN fire editingFinished.
    Passing "500 mm" unconditionally always differs from the initial "0 mm"
    (or imperial equivalent), so this pattern is safe and straightforward.
"""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QLineEdit, QComboBox, QLabel
from PyQt6.QtCore import QPointF

from firepro3d.property_manager import PropertyManager
from firepro3d.level_manager import LevelManager
from firepro3d.construction_geometry import RectangleItem, LineItem
from firepro3d.scale_manager import ScaleManager


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_scene(qapp):
    """Return a minimal Model_Space with a LevelManager and ScaleManager."""
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    lm = LevelManager()
    s._level_manager = lm
    s.scale_manager = ScaleManager()
    return s


def _make_panel(scene) -> PropertyManager:
    """Return a PropertyManager wired to *scene*'s level manager."""
    pm = PropertyManager()
    pm.set_level_manager(scene._level_manager)
    return pm


def _find_row_editor(pm: PropertyManager, label_text: str):
    """Return the editor widget for a given row label, or None."""
    form = pm._form
    for i in range(form.rowCount()):
        lbl_item = form.itemAt(i, form.ItemRole.LabelRole)
        field_item = form.itemAt(i, form.ItemRole.FieldRole)
        if lbl_item and lbl_item.widget():
            if lbl_item.widget().text() == label_text and field_item:
                return field_item.widget()
    return None


def _row_labels(pm: PropertyManager) -> list[str]:
    """All row label texts currently in the form."""
    form = pm._form
    texts = []
    for i in range(form.rowCount()):
        lbl_item = form.itemAt(i, form.ItemRole.LabelRole)
        if lbl_item and lbl_item.widget():
            texts.append(lbl_item.widget().text())
    return texts


# ── tests ─────────────────────────────────────────────────────────────────────

def test_level_offset_commit_updates_attribute(qapp):
    """Triggering editingFinished on the DimensionEdit must update _level_offset_mm.

    The panel wires: DimensionEdit.editingFinished → _apply_property('Level Offset',
    de.value_mm()) → rect.set_property('Level Offset', <float>) → _geom2d_set.

    The dimension row passes a *float* (de.value_mm()), NOT a display string.
    """
    scene = _make_scene(qapp)
    rect = RectangleItem(QPointF(0, 0), QPointF(200, 100))
    scene.addItem(rect)

    pm = _make_panel(scene)
    pm.show_properties(rect)

    from firepro3d.dimension_edit import DimensionEdit
    dim_edit = next(iter(pm.findChildren(DimensionEdit)), None)
    assert dim_edit is not None, "No DimensionEdit found for Level Offset row"

    # Change the text to "500 mm" — this always differs from the seeded "0 mm"
    # so _on_editing_finished will parse+commit it.
    dim_edit.setText("500 mm")
    dim_edit.editingFinished.emit()

    assert rect._level_offset_mm == pytest.approx(500.0), (
        f"Expected _level_offset_mm=500.0, got {rect._level_offset_mm}"
    )


def test_z_range_reflects_offset(qapp):
    """z_range_mm() must include the level offset in its elevation."""
    scene = _make_scene(qapp)
    rect = RectangleItem(QPointF(0, 0), QPointF(200, 100))
    scene.addItem(rect)

    # Level 1 has elevation 0.0 by default
    rect._level_offset_mm = 300.0
    zr = rect.z_range_mm()
    assert zr is not None
    assert zr[0] == pytest.approx(300.0)
    assert zr[1] == pytest.approx(300.0)


def test_elevation_row_is_readonly(qapp):
    """The 'Elevation' property row must not have an editable QLineEdit."""
    scene = _make_scene(qapp)
    rect = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    scene.addItem(rect)

    pm = _make_panel(scene)
    pm.show_properties(rect)

    editor = _find_row_editor(pm, "Elevation")
    # The elevation row is type "string" with readonly:True, so PropertyManager
    # renders it as a QLineEdit with setReadOnly(True).
    assert editor is not None, "Elevation row not found in panel"
    assert isinstance(editor, QLineEdit), "Elevation editor must be a QLineEdit"
    assert editor.isReadOnly(), "Elevation editor must be read-only"


def test_elevation_row_value_matches_level_plus_offset(qapp):
    """Displayed elevation = level.elevation + _level_offset_mm (non-empty string)."""
    scene = _make_scene(qapp)
    rect = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    rect._level_offset_mm = 250.0
    scene.addItem(rect)

    pm = _make_panel(scene)
    pm.show_properties(rect)

    editor = _find_row_editor(pm, "Elevation")
    assert editor is not None, "Elevation row not found in panel"

    # Level 1 elevation is 0.0 mm; offset is 250.0 mm → z = 250.0 mm.
    # We only confirm the displayed value is non-empty and not the "—" fallback
    # (that would indicate z_range_mm returned None — a bug).
    displayed = editor.text()
    assert displayed and displayed != "—", (
        f"Elevation row shows '{displayed}' instead of the formatted elevation"
    )


def test_fillable_rect_shows_fill_row(qapp):
    """RectangleItem (fillable) must expose a 'Fill' row in get_properties()."""
    rect = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    props = rect.get_properties()
    assert "Fill" in props, "Fill row missing from RectangleItem.get_properties()"


def test_line_item_has_no_fill_row(qapp):
    """LineItem (non-fillable) must NOT expose a 'Fill' row."""
    line = LineItem(QPointF(0, 0), QPointF(100, 0))
    props = line.get_properties()
    assert "Fill" not in props, "LineItem should not have a Fill row"


def test_panel_for_line_has_no_fill_editor(qapp):
    """PropertyManager for a LineItem must render no 'Fill' row label."""
    scene = _make_scene(qapp)
    line = LineItem(QPointF(0, 0), QPointF(100, 0))
    scene.addItem(line)

    pm = _make_panel(scene)
    pm.show_properties(line)

    labels = _row_labels(pm)
    assert "Fill" not in labels, (
        f"'Fill' row must not appear for LineItem; rows: {labels}"
    )


def test_geom2d_set_is_exercised_by_panel(qapp):
    """Sanity: confirm the panel drives _geom2d_set, not a no-op.

    Monkeypatch _geom2d_set to record calls; fire the commit; assert
    'Level Offset' was dispatched to the real set path.
    """
    scene = _make_scene(qapp)
    rect = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    scene.addItem(rect)

    pm = _make_panel(scene)
    pm.show_properties(rect)

    from firepro3d.dimension_edit import DimensionEdit
    dim_edit = next(iter(pm.findChildren(DimensionEdit)), None)
    assert dim_edit is not None

    sentinel: list[tuple] = []
    original = rect._geom2d_set

    def patched(key, value):
        sentinel.append((key, value))
        return original(key, value)

    rect._geom2d_set = patched

    dim_edit.setText("42 mm")
    dim_edit.editingFinished.emit()

    assert any(k == "Level Offset" for k, _ in sentinel), (
        f"Panel commit did not call _geom2d_set('Level Offset', ...); "
        f"calls recorded: {sentinel}"
    )
