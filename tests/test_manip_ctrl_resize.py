"""tests/test_manip_ctrl_resize.py — Ctrl (from-centre) resize keeps the centre fixed.

Bug (user, 2026-09-16; backlog #425/426): during a Ctrl / from-centre resize the
preview anchors about the frame CENTRE, but the release bake anchored about the
OPPOSITE CORNER, so the rectangle jumped ~the handle displacement on release.

Ground truth: a from-centre resize must leave the rectangle's centre unchanged.
Driven through the real ResizeHandle.on_drag -> on_release -> _bake_scale seam
(snap neutralised — orthogonal to this bug), plus a direct _bake_scale contrast.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QTransform

from firepro3d.geometry_2d import RectangleItem
from firepro3d.manip_math import HandleRole


def _rect(scene):
    item = RectangleItem(QPointF(0, 0), QPointF(100, 100), "#ffffff", 1.0)
    scene.addItem(item)
    return item


def test_bake_scale_from_center_preserves_centre(shown_model_view):
    _view, scene = shown_model_view
    item = _rect(scene)
    manip = scene._manipulator
    c0 = item.manip_bounds().center()
    manip._bake_scale([item], HandleRole.TOP_LEFT, (2.0, 2.0),
                      QRectF(0, 0, 100, 100), QTransform(), from_center=True)
    c1 = item.manip_bounds().center()
    assert abs(c1.x() - c0.x()) < 1e-6 and abs(c1.y() - c0.y()) < 1e-6
    # ...and it actually grew (guards against a no-op passing vacuously).
    assert item.manip_bounds().width() > 150.0


def test_bake_scale_corner_anchor_moves_centre(shown_model_view):
    """Contrast: the non-Ctrl corner anchor deliberately holds the opposite
    corner, so the centre DOES move — proving the from_center flag is what
    changes the anchor (not the factors)."""
    _view, scene = shown_model_view
    item = _rect(scene)
    manip = scene._manipulator
    c0 = item.manip_bounds().center()
    manip._bake_scale([item], HandleRole.TOP_LEFT, (2.0, 2.0),
                      QRectF(0, 0, 100, 100), QTransform(), from_center=False)
    c1 = item.manip_bounds().center()
    assert abs(c1.x() - c0.x()) > 40.0 or abs(c1.y() - c0.y()) > 40.0


def test_ctrl_resize_gesture_preserves_centre(shown_model_view):
    """Full press->drag(Ctrl)->release through the manipulator keeps the centre."""
    _view, scene = shown_model_view
    item = _rect(scene)
    item.setSelected(True)
    manip = scene._manipulator
    manip._snap = lambda p: p          # neutralise OSNAP (orthogonal to this bug)
    manip.rebake()
    c0 = item.manip_bounds().center()

    r0 = QRectF(manip._rect)
    start = r0.topLeft()
    manip._begin("resize", start, QPointF(0, 0), HandleRole.TOP_LEFT)
    ctrl = Qt.KeyboardModifier.ControlModifier
    # Drag the TL corner out to (-50,-50); screen delta clears the drag threshold.
    manip._update(QPointF(-50, -50), ctrl, QPointF(200, 200))
    assert manip._last_from_center is True
    manip._finish(QPointF(-50, -50), ctrl)

    c1 = item.manip_bounds().center()
    assert abs(c1.x() - c0.x()) < 1.0 and abs(c1.y() - c0.y()) < 1.0
    assert item.manip_bounds().width() > 150.0
