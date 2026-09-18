"""tests/test_geo2d_panel.py

Property-panel behaviour for the level-less 2D primitives (containment C3).

Since C3 the primitives carry NO level / offset / elevation rows (that scope
moved to the placed BlockInstance — see test_block_instance_level.py). What the
panel still owns for primitives is the fill affordance:
  - A fillable RectangleItem shows a "Fill" row.
  - A LineItem (non-fillable) does NOT show a "Fill" row (neither in
    get_properties() nor as a rendered panel row).
"""

from __future__ import annotations

from firepro3d.property_manager import PropertyManager
from firepro3d.level_manager import LevelManager
from firepro3d.geometry_2d import RectangleItem, LineItem
from firepro3d.scale_manager import ScaleManager
from PyQt6.QtCore import QPointF


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_scene(qapp):
    """Return a minimal Model_Space with a LevelManager and ScaleManager."""
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    s._level_manager = LevelManager()
    s.scale_manager = ScaleManager()
    return s


def _make_panel(scene) -> PropertyManager:
    pm = PropertyManager()
    pm.set_level_manager(scene._level_manager)
    return pm


def _row_labels(pm: PropertyManager) -> list[str]:
    form = pm._form
    texts = []
    for i in range(form.rowCount()):
        lbl_item = form.itemAt(i, form.ItemRole.LabelRole)
        if lbl_item and lbl_item.widget():
            texts.append(lbl_item.widget().text())
    return texts


# ── tests ─────────────────────────────────────────────────────────────────────

def test_primitive_panel_has_no_level_rows(qapp):
    """A level-less primitive shows no Level / Level Offset / Elevation rows."""
    scene = _make_scene(qapp)
    rect = RectangleItem(QPointF(0, 0), QPointF(200, 100))
    scene.addItem(rect)

    pm = _make_panel(scene)
    pm.show_properties(rect)

    labels = _row_labels(pm)
    for banned in ("Level", "Level Offset", "Elevation"):
        assert banned not in labels, f"{banned!r} row must not appear; rows: {labels}"


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
