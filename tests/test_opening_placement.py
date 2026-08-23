"""tests/test_opening_placement.py — unified "opening" placement mode (§7.6).

Drives the REAL entry point: posted ``QMouseEvent`` / ``QKeyEvent`` on a SHOWN,
focused ``Model_View``.  Calling the handlers directly gives false green (memory:
"Test the real entry point"), so every interaction goes through ``sendEvent``.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt, QEvent
from PyQt6.QtGui import QMouseEvent, QKeyEvent
from PyQt6.QtWidgets import QApplication

from firepro3d.wall import WallSegment


def _click(view, scene_pt):
    vp = view.viewport()
    p = view.mapFromScene(scene_pt)
    for et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        ev = QMouseEvent(et, p.toPointF(), vp.mapToGlobal(p).toPointF(),
                         Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(vp, ev)


def _key(view, key):
    for et in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(view.viewport(),
            QKeyEvent(et, key, Qt.KeyboardModifier.NoModifier))


def test_click_on_wall_places_opening(qapp, shown_model_view):
    view, scene = shown_model_view
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    scene.set_mode("opening", template="door_914")
    _click(view, QPointF(500, 0))
    assert len(w.openings) == 1
    assert w.openings[0].feature_id == "door_914"


def test_click_empty_space_rejected(qapp, shown_model_view):
    """A click well off the wall must not host an opening on it.

    A real wall is present so the assertion is non-vacuous: if the
    empty-space guard in _press_opening were removed, _find_wall_at would
    return None and the handler would return early — but if the guard were
    *replaced* with unconditional placement (or the click hit the wall), the
    wall would gain an opening and the assert would go red.  The wall lies on
    y=0; the click lands at y=500 (250× the 200 mm half-thickness away) so
    wall.shape().contains(QPointF(500, 500)) is False and the guard fires.
    """
    view, scene = shown_model_view
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    scene.set_mode("opening", template="door_914")
    _click(view, QPointF(500, 500))          # well off the wall (wall lies on y=0)
    assert len(w.openings) == 0              # nothing hosted from an empty-space click


def test_spacebar_cycles_alignment_during_placement(qapp, shown_model_view):
    view, scene = shown_model_view
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    scene.set_mode("opening", template="door_914")
    a0 = scene._opening_alignment
    _key(view, Qt.Key.Key_Space)
    assert scene._opening_alignment != a0


def test_arrow_toggles_hinge_and_facing_during_placement(qapp, shown_model_view):
    view, scene = shown_model_view
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    scene.set_mode("opening", template="door_914")
    assert scene._opening_mirror_hinge is False
    _key(view, Qt.Key.Key_Left)
    assert scene._opening_mirror_hinge is True
    assert scene._opening_mirror_facing is False
    _key(view, Qt.Key.Key_Up)
    assert scene._opening_mirror_facing is True


def test_placed_opening_carries_cycle_state(qapp, shown_model_view):
    view, scene = shown_model_view
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    scene.set_mode("opening", template="door_914")
    _key(view, Qt.Key.Key_Space)          # cycle alignment off Centered
    _key(view, Qt.Key.Key_Left)           # hinge flip
    aligned = scene._opening_alignment
    _click(view, QPointF(400, 0))
    assert len(w.openings) == 1
    op = w.openings[0]
    assert op.alignment == aligned
    assert op.mirror_hinge is True
    assert op.mirror_facing is False   # facing was never toggled; default must survive
    assert op.level == w.level
