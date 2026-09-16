"""tests/test_reference_line.py — finite reference/construction line (task D).

Covers the core wiring: placement via the Line ←/→ variant, serialization
round-trip (item + undo capture/restore), delete routing, and the default
`printed=False`. Paper/block exclusion + the property ToggleSwitch are covered
separately (commit 2).
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from firepro3d.geometry_2d import ReferenceLineItem, LineItem


def _press_at(view, scene_pt: QPointF) -> None:
    vp = view.mapFromScene(scene_pt)
    for etype in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        ev = QMouseEvent(etype, QPointF(vp), Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(view.viewport(), ev)
    QApplication.processEvents()


def test_reference_line_is_a_lineitem_subclass():
    # Snap participation + base editing come for free via isinstance(item, LineItem).
    assert issubclass(ReferenceLineItem, LineItem)


def test_reference_line_defaults_not_printed():
    rl = ReferenceLineItem(QPointF(0, 0), QPointF(10, 0))
    assert rl.printed is False


def test_reference_line_serialization_roundtrip():
    rl = ReferenceLineItem(QPointF(1, 2), QPointF(30, 40), "#abcdef", 1.0, printed=True)
    d = rl.to_dict()
    assert d["type"] == "reference_line"
    assert d["printed"] is True
    back = ReferenceLineItem.from_dict(d)
    assert back.printed is True
    assert (back._pt1.x(), back._pt1.y()) == (1, 2)
    assert (back._pt2.x(), back._pt2.y()) == (30, 40)
    # Absent flag defaults to not-printed (old records / forward-compat).
    assert ReferenceLineItem.from_dict(
        {"pt1": [0, 0], "pt2": [1, 1]}).printed is False


def test_placement_via_line_reference_variant(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_line")
    scene.cycle_placement_variant(+1)           # Line -> Reference Line
    assert scene._draw_line_variant == "reference"
    _press_at(view, QPointF(0, 0)); _press_at(view, QPointF(600, 0))
    assert len(scene._reference_lines) == 1, "reference line not tracked"
    assert len(scene._draw_lines) == 0, "should NOT be a normal line"
    rl = scene._reference_lines[0]
    assert isinstance(rl, ReferenceLineItem)
    assert rl.isSelected() and scene.mode == "select"   # single-placement


def test_line_variant_still_makes_normal_line(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_line")                 # default variant = "line"
    _press_at(view, QPointF(0, 0)); _press_at(view, QPointF(600, 0))
    assert len(scene._draw_lines) == 1
    assert len(scene._reference_lines) == 0


def test_delete_routes_to_reference_lines(shown_model_view):
    view, scene = shown_model_view
    rl = ReferenceLineItem(QPointF(0, 0), QPointF(10, 0))
    scene.addItem(rl); scene._reference_lines.append(rl)
    assert scene._remove_item_from_lists(rl) is True
    assert rl not in scene._reference_lines


def test_undo_restore_preserves_reference_line(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_line"); scene.cycle_placement_variant(+1)
    _press_at(view, QPointF(0, 0)); _press_at(view, QPointF(600, 0))
    assert len(scene._reference_lines) == 1
    printed_flag = scene._reference_lines[0].printed
    scene.undo()
    assert len(scene._reference_lines) == 0
    scene.redo()
    assert len(scene._reference_lines) == 1
    assert scene._reference_lines[0].printed == printed_flag


# ── commit 2: printed exclusion + display category + property toggle ──────────


def test_paper_export_excludes_non_printed_includes_printed(shown_model_view):
    from PyQt6.QtCore import QRectF
    from firepro3d import paper_display
    view, scene = shown_model_view
    off = ReferenceLineItem(QPointF(0, 0), QPointF(100, 0), printed=False)
    on = ReferenceLineItem(QPointF(0, 50), QPointF(100, 50), printed=True)
    for it in (off, on):
        scene.addItem(it); scene._reference_lines.append(it)
    saved = paper_display.apply_paper_overrides(scene, QRectF(-1000, -1000, 3000, 3000))
    assert off.isVisible() is False, "non-printing reference line must be excluded from plots"
    assert on.isVisible() is True, "printed reference line must plot"
    paper_display.restore_model_display(saved)
    assert off.isVisible() is True, "visibility must be restored after the render pass"


def test_block_definition_excludes_non_printed_includes_printed(qapp):
    from PyQt6.QtWidgets import QTabWidget
    from firepro3d.model_space import Model_Space
    from firepro3d.block_editor import BlockEditorManager
    w = BlockEditorManager(QTabWidget(), Model_Space()).open_new()
    s = w.editor_scene
    off = ReferenceLineItem(QPointF(0, 0), QPointF(100, 0), printed=False)
    on = ReferenceLineItem(QPointF(0, 50), QPointF(100, 50), printed=True)
    for it in (off, on):
        s.addItem(it); s._reference_lines.append(it)
    prims = w.gather_primitives()
    assert on in prims, "printed reference line must be in the block definition"
    assert off not in prims, "non-printing reference line must be excluded from the block"


def test_reference_lines_display_category(shown_model_view):
    from firepro3d import display_manager
    view, scene = shown_model_view
    assert "Reference Lines" in display_manager._CATEGORY_MAP
    rl = ReferenceLineItem(QPointF(0, 0), QPointF(10, 0))
    scene.addItem(rl); scene._reference_lines.append(rl)
    members = display_manager._items_for_category_static(scene, "Reference Lines")
    assert rl in members
    # It must NOT double up in the 2D Geometry category.
    assert rl not in display_manager._items_for_category_static(scene, "2D Geometry")


def test_printed_property_uses_toggle_field():
    rl = ReferenceLineItem(QPointF(0, 0), QPointF(10, 0))
    props = rl.get_properties()
    assert props["Printed"]["type"] == "toggle"
    assert props["Printed"]["value"] is False
    rl.set_property("Printed", True)
    assert rl.printed is True
