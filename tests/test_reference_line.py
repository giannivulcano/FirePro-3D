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
