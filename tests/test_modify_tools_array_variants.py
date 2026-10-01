"""P1 DD5: Array variants (Linear / 2D / Polar), angle lock, session memory.

Governing: docs/superpowers/specs/2026-10-01-scene-tools-p1-batch-design.md
DD5 + acceptance M1 (folded into scene-tools.md D10 at Account). Every guard
drives the real path: a shown Model_View over a real block_editor
Model_Space, real mouse events, the real HUD (begin_dynamic_input / editor
text / Tab / Esc / _accept), and asserts scene coordinates of the copies.
The views ignore the real OS mouse (``ignore_os_mouse``) so a user's cursor
over the test window cannot inject moves.
"""
import math

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest

from tests._modify_tools_helpers import add_primitive, ignore_os_mouse
from tests._snap_polish_helpers import click, close_view, make_view, move

COS30 = math.cos(math.radians(30.0))
SIN30 = math.sin(math.radians(30.0))


def _view(**kw):
    """A shown Model_View (``make_view``) deaf to the real OS mouse."""
    view, scene = make_view(**kw)
    ignore_os_mouse(view)
    return view, scene


def _type(scene, **fields):
    """Engage the HUD, type *fields* by name, press the HUD's Enter path."""
    assert scene.begin_dynamic_input() is True
    for name, text in fields.items():
        scene.dynamic_input.editor(name).setText(text)
    scene.dynamic_input._accept()


def _centres(circles):
    return sorted((round(c._center.x(), 2), round(c._center.y(), 2))
                  for c in circles)


def test_typed_count_prefills_the_next_array(qapp):
    """DD5 memory: a typed Count is remembered for the next Array on the same
    canvas (it used to fall back to the fixed default 3)."""
    view, scene = _view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")          # centre (0,0) r=50
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(200, 0))
        _type(scene, Spacing="200", Count="4")
        assert len(getattr(scene, attr)) == 4
        p0 = scene._undo_pos
        # Run 2: click-commit at the cursor spacing — Count is the remembered 4.
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(0, -300))
        click(view, QPointF(0, -300))
        lst = getattr(scene, attr)
        assert len(lst) == 4 + 3                                       # [RED]
        assert _centres(lst[4:]) == [(0.0, -900.0), (0.0, -600.0), (0.0, -300.0)]
        assert scene._undo_pos == p0 + 1
        assert item.isSelected()
    finally:
        close_view(view, scene)


def _assert_points(points, expected, tol=0.01):
    """Scene points match *expected* (order-free; float-noise-safe sort)."""
    key = lambda p: (round(p[0], 3), round(p[1], 3))
    got = sorted(((p.x(), p.y()) for p in points), key=key)
    exp = sorted(expected, key=key)
    assert len(got) == len(exp), (got, exp)
    for (gx, gy), (ex, ey) in zip(got, exp):
        assert gx == pytest.approx(ex, abs=tol), (got, exp)
        assert gy == pytest.approx(ey, abs=tol), (got, exp)


def _tab_angle(scene, text):
    """Real HUD keys: type Angle, Tab (field commit), Esc (back to cursor)."""
    assert scene.begin_dynamic_input() is True
    hud = scene.dynamic_input
    hud.editor("Angle").setText(text)
    QTest.keyClick(hud.editor("Angle"), Qt.Key.Key_Tab)
    QTest.keyClick(hud.editor("Spacing"), Qt.Key.Key_Escape)
    assert not scene.is_input_mode()


def test_typed_angle_30_places_copies_along_30_degrees_yup(qapp):
    """M1: Linear with a typed Angle 30° puts copy k at base + k·sp·(cos30,
    −sin30) in SCENE (Y-down) coordinates — up and to the right on screen."""
    view, scene = _view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")          # centre (0,0)
        p0 = scene._undo_pos
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(200, 0))      # aim +X
        _type(scene, Angle="30", Spacing="150", Count="3")
        _assert_points([c._center for c in getattr(scene, attr)],   # [RED]
                       [(150 * k * COS30, -150 * k * SIN30) for k in range(3)])
        assert scene._undo_pos == p0 + 1
        assert item.isSelected()
        scene.undo()
        assert len(getattr(scene, attr)) == 1
    finally:
        close_view(view, scene)


def test_typed_angle_locks_direction_cursor_sets_spacing_only(qapp):
    """DD5: after Angle 30 + Tab, Esc hands back the cursor — which now sets
    only the spacing: the projection of base->cursor onto the 30° line."""
    view, scene = _view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(200, 0))
        _tab_angle(scene, "30")
        move(view, QPointF(300, -40)); click(view, QPointF(300, -40))
        sp = 300 * COS30 + 40 * SIN30          # (300,-40)·(cos30, -sin30)
        _assert_points([c._center for c in getattr(scene, attr)],   # [RED]
                       [(sp * k * COS30, -sp * k * SIN30) for k in range(3)])
    finally:
        close_view(view, scene)


def test_typed_zero_angle_releases_the_lock(qapp):
    """DD5: 0 releases the lock — the cursor aims (direction + spacing) again."""
    view, scene = _view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(200, 0))
        _tab_angle(scene, "30")
        move(view, QPointF(300, -40))
        sp = 300 * COS30 + 40 * SIN30
        # Locked: the ghost copies sit on the 30° line.
        _assert_points([p.boundingRect().center() for p in scene._move_ghost],  # [RED]
                       [(sp * k * COS30, -sp * k * SIN30) for k in (1, 2)])
        _tab_angle(scene, "0")
        move(view, QPointF(300, -40)); click(view, QPointF(300, -40))
        _assert_points([c._center for c in getattr(scene, attr)],
                       [(300 * k, -40 * k) for k in range(3)])
    finally:
        close_view(view, scene)


def test_typed_angle_lock_carries_to_the_next_array(qapp):
    """DD5 session memory: a typed Angle starts the next Array locked (and
    the typed Count pre-fills it)."""
    view, scene = _view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(200, 0))
        _type(scene, Angle="30", Spacing="100", Count="2")
        assert len(getattr(scene, attr)) == 2
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(300, -40))
        click(view, QPointF(300, -40))
        sp = 300 * COS30 + 40 * SIN30
        _assert_points([c._center for c in getattr(scene, attr)[2:]],  # [RED]
                       [(sp * COS30, -sp * SIN30)])
    finally:
        close_view(view, scene)
