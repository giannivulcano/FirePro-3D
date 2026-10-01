"""Slice 9 guards: one close helper, either-point rule (2d-geometry.md §4).

Real Model_Space + shown Model_View (tests/_snap_polish_helpers), posted
press/move events, Ctrl on the events that need it. The view is made deaf to
the real OS mouse (tests/_modify_tools_helpers.ignore_os_mouse). The
"tip-only" cases put the Ctrl-constrained tip on vertex 0 with the cursor
~490 mm (~120 px) away. They are RED before DD8, because the old code tested
only the cursor. The "cursor-only" cases put the cursor on vertex 0 with a
constrained tip ~358 mm away. The old code already closed these, so they are
parity guards.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, Qt

from firepro3d.geometry_drawing_controller import close_hit
from tests._modify_tools_helpers import ignore_os_mouse
from tests._snap_polish_helpers import click, close_view, make_view, move

CTRL = Qt.KeyboardModifier.ControlModifier

# Tip-only: vertices (0,0) (1000,0) (1000,1000). From the last vertex the raw
# cursor sits 20 deg off the -135 deg ray to vertex 0 (Qt Y-down), at the
# same distance. Ctrl snaps the ray back to -135 deg, so the tip lands on
# (0,0) and the cursor stays ~491 mm away.
TIP_ONLY_VERTS = [(0, 0), (1000, 0), (1000, 1000)]
_R = math.hypot(1000, 1000)
_A = math.radians(-135 + 20)
TIP_ONLY_CURSOR = QPointF(1000 + _R * math.cos(_A), 1000 + _R * math.sin(_A))

# Cursor-only: vertices (0,0) (1000,0) (1000,500). The cursor sits on vertex 0.
# The -153.4 deg ray Ctrl-rounds to -135 deg, so the tip lands ~358 mm away.
CURSOR_ONLY_VERTS = [(0, 0), (1000, 0), (1000, 500)]
CURSOR_ON_V0 = QPointF(2, 2)


def _view(**kw):
    view, scene = make_view(**kw)
    ignore_os_mouse(view)
    return view, scene


def test_close_hit_is_the_either_point_rule():
    first = QPointF(0, 0)
    far = QPointF(500, 0)
    near = QPointF(7, 0)               # 7 mm at 1 px/mm: inside 8 px
    assert close_hit(first, near, far, 1.0) is True        # tip only
    assert close_hit(first, far, near, 1.0) is True        # cursor only
    assert close_hit(first, far, far, 1.0) is False
    assert close_hit(first, QPointF(9, 0), far, 1.0) is False
    assert close_hit(first, QPointF(30, 0), far, 0.25) is True   # 8 px = 32 mm


def test_tip_only_fixture_really_is_tip_only():
    assert math.hypot(TIP_ONLY_CURSOR.x(), TIP_ONLY_CURSOR.y()) > 400


# ── polyline ────────────────────────────────────────────────────────────────

def _polyline(view, scene, verts):
    scene.set_mode("polyline")
    for v in verts:
        click(view, QPointF(*v))
    pl = scene._polyline_active
    assert pl is not None and len(pl._points) == len(verts)
    return pl


def test_polyline_closes_on_the_constrained_tip(qapp):
    view, scene = _view()                          # block_editor, m11 = 0.25
    try:
        pl = _polyline(view, scene, TIP_ONLY_VERTS)
        move(view, TIP_ONLY_CURSOR, mods=CTRL)
        ring = scene._polyline_close_indicator
        assert ring is not None and ring.isVisible()                    # [RED]
        assert math.hypot(ring.pos().x(), ring.pos().y()) < 0.5   # on vertex 0
        click(view, TIP_ONLY_CURSOR, mods=CTRL)
        assert pl.is_closed() and len(pl._points) == 3                  # [RED]
        assert scene._polyline_active is None and scene.mode == "select"
        assert not scene._polyline_close_indicator.isVisible()
    finally:
        close_view(view, scene)


def test_polyline_closes_on_the_cursor_with_ctrl_held(qapp):
    view, scene = _view()
    try:
        pl = _polyline(view, scene, CURSOR_ONLY_VERTS)
        click(view, CURSOR_ON_V0, mods=CTRL)
        assert pl.is_closed() and len(pl._points) == 3
        assert scene.mode == "select"
    finally:
        close_view(view, scene)


# ── floor polygon (plan scene) ──────────────────────────────────────────────

def _floor(view, scene, verts):
    scene._set_floor_primitive("polygon")
    for v in verts:
        click(view, QPointF(*v))
    assert scene._floor_active is not None
    assert len(scene._floor_active._points) == len(verts)


def test_floor_closes_on_the_constrained_tip_and_shows_the_ring(qapp):
    view, scene = _view(role="plan", mode="floor")
    try:
        _floor(view, scene, TIP_ONLY_VERTS)
        move(view, TIP_ONLY_CURSOR, mods=CTRL)
        ring = scene._polyline_close_indicator
        assert ring is not None and ring.isVisible()                    # [RED]
        assert math.hypot(ring.pos().x(), ring.pos().y()) < 0.5   # on vertex 0
        click(view, TIP_ONLY_CURSOR, mods=CTRL)
        assert scene._floor_active is None                              # [RED]
        assert len(scene._floor_slabs) == 1
        assert len(scene._floor_slabs[0]._points) == 3
        assert not scene._polyline_close_indicator.isVisible()
    finally:
        close_view(view, scene)


def test_floor_closes_on_the_cursor_with_ctrl_held(qapp):
    view, scene = _view(role="plan", mode="floor")
    try:
        _floor(view, scene, CURSOR_ONLY_VERTS)
        click(view, CURSOR_ON_V0, mods=CTRL)
        assert scene._floor_active is None
        assert len(scene._floor_slabs[0]._points) == 3
    finally:
        close_view(view, scene)


def _key(view, key):
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtWidgets import QApplication
    for et in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(view.viewport(), QKeyEvent(
            et, key, Qt.KeyboardModifier.NoModifier))
    QApplication.processEvents()


def test_floor_enter_with_the_ring_up_closes_and_hides_it(qapp):
    """Enter keeps floor mode (no mode switch tears the ring down), so the
    close path itself must hide the cue."""
    view, scene = _view(role="plan", mode="floor")
    try:
        _floor(view, scene, TIP_ONLY_VERTS)
        move(view, CURSOR_ON_V0)
        assert scene._polyline_close_indicator.isVisible()
        _key(view, Qt.Key.Key_Return)
        assert scene._floor_active is None and len(scene._floor_slabs) == 1
        assert not scene._polyline_close_indicator.isVisible()
    finally:
        close_view(view, scene)


# ── ring survives a scene reset (New / Open → _clear_scene) ─────────────────

def _capture_hook(monkeypatch):
    """Record exceptions escaping Qt virtuals (PyQt aborts on them otherwise)."""
    import sys
    caught = []
    monkeypatch.setattr(sys, "excepthook",
                        lambda et, ev, tb: caught.append((et, ev)))
    return caught


def _ring_up_then_reset(view, scene, draw):
    draw(view, scene, CURSOR_ONLY_VERTS)
    move(view, CURSOR_ON_V0)
    assert scene._polyline_close_indicator.isVisible()
    scene._clear_scene()          # the real New / Open reset (scene.clear())


def test_ring_survives_clear_scene_then_shows_on_a_floor(qapp, monkeypatch):
    """Plan scene (2D polylines are block-editor only): floor ring, reset,
    floor ring again."""
    caught = _capture_hook(monkeypatch)
    view, scene = _view(role="plan", mode="floor")
    try:
        _ring_up_then_reset(view, scene, _floor)
        scene.set_mode("floor")
        _floor(view, scene, TIP_ONLY_VERTS)
        move(view, CURSOR_ON_V0)
        ring = scene._polyline_close_indicator
        assert caught == []                                              # [RED]
        assert ring is not None and ring.scene() is scene and ring.isVisible()
        assert math.hypot(ring.pos().x(), ring.pos().y()) < 0.5
    finally:
        close_view(view, scene)


def test_ring_survives_clear_scene_then_shows_on_a_spline(qapp, monkeypatch):
    caught = _capture_hook(monkeypatch)
    view, scene = _view()                          # block_editor
    try:
        _ring_up_then_reset(view, scene, _polyline)
        scene.set_mode("draw_spline")
        for p in [(200, 200), (1000, 200), (1000, -600)]:
            click(view, QPointF(*p))
        move(view, QPointF(204, 196))
        ring = scene._polyline_close_indicator
        assert caught == []                                              # [RED]
        assert ring is not None and ring.scene() is scene and ring.isVisible()
        assert math.hypot(ring.pos().x() - 200, ring.pos().y() - 200) < 0.5
    finally:
        close_view(view, scene)


# ── roof polygon (plan scene; RoofDialog stubbed: it is modal) ───────────────

class _AcceptRoofDialog:
    """Stands in for the modal RoofDialog. It accepts and returns the
    defaults it was given, so the real close path runs to completion."""

    def __init__(self, parent=None, defaults=None, **_kw):
        self._d = dict(defaults or {})

    def exec(self):
        from PyQt6.QtWidgets import QDialog
        return QDialog.DialogCode.Accepted

    def get_params(self):
        return {**self._d, "eave_level": None}


def _roof(view, scene, verts):
    for v in verts:
        click(view, QPointF(*v))
    assert scene._roof_active is not None
    assert len(scene._roof_active._points) == len(verts)


def test_roof_closes_on_the_constrained_tip_and_shows_the_ring(qapp, monkeypatch):
    monkeypatch.setattr("firepro3d.model_space.RoofDialog", _AcceptRoofDialog)
    view, scene = _view(role="plan", mode="roof")
    try:
        _roof(view, scene, TIP_ONLY_VERTS)
        move(view, TIP_ONLY_CURSOR, mods=CTRL)
        ring = scene._polyline_close_indicator
        assert ring is not None and ring.isVisible()                    # [RED]
        assert math.hypot(ring.pos().x(), ring.pos().y()) < 0.5   # on vertex 0
        click(view, TIP_ONLY_CURSOR, mods=CTRL)
        assert scene._roof_active is None                               # [RED]
        assert len(scene._roofs) == 1 and len(scene._roofs[0]._points) == 3
        assert not scene._polyline_close_indicator.isVisible()
    finally:
        close_view(view, scene)


def test_roof_closes_on_the_cursor_with_ctrl_held(qapp, monkeypatch):
    monkeypatch.setattr("firepro3d.model_space.RoofDialog", _AcceptRoofDialog)
    view, scene = _view(role="plan", mode="roof")
    try:
        _roof(view, scene, CURSOR_ONLY_VERTS)
        click(view, CURSOR_ON_V0, mods=CTRL)
        assert scene._roof_active is None
        assert len(scene._roofs[0]._points) == 3
    finally:
        close_view(view, scene)


def test_roof_vertex_pop_fires_on_the_constrained_tip(qapp):
    """Two vertices, so there is no close yet. The Ctrl tip lands on vertex 0
    with the cursor ~347 mm away. The vertex is popped instead of a
    near-duplicate being added."""
    view, scene = _view(role="plan", mode="roof")
    try:
        _roof(view, scene, [(0, 0), (1000, 0)])
        a = math.radians(180 - 20)                 # 20 deg off the 180 deg ray
        cursor = QPointF(1000 + 1000 * math.cos(a), 1000 * math.sin(a))
        click(view, cursor, mods=CTRL)
        pts = scene._roof_active._points
        assert len(pts) == 1                                             # [RED]
        assert math.hypot(pts[0].x() - 1000, pts[0].y()) < 0.5           # vertex 0 popped
    finally:
        close_view(view, scene)
