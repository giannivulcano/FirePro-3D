"""tests/test_floor_placement_workflow.py — floor as a variant-bearing placement mode.

Task 5 (floor-workflow branch): one ``"floor"`` scene-mode carries
``_floor_primitive ∈ {"rect","polygon"}``; ←/→ cycles the primitive via
``_PLACEMENT_VARIANTS`` (Corner Rect → Center Rect → Polygon); the rect
primitive runs the 3-step anchor→size→ROTATE flow (mirroring the wall rect);
the polygon primitive keeps the click-vertex-closing FloorSlab flow.

``F`` enters floor mode; the ribbon button is one checkable button (no dropdown).

Mirrors ``tests/test_wall_placement_workflow.py`` — posted QMouseEvent/QKeyEvent
on a SHOWN, activated ``Model_View`` (per memory: "Test the real entry point";
QTest.mouseMove is inert here).
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, Qt, QEvent
from PyQt6.QtGui import QMouseEvent, QKeyEvent
from PyQt6.QtWidgets import QApplication

from firepro3d.model_space import Model_Space
from firepro3d.dynamic_input import SCHEMAS


def _click(view, scene_pt):
    """Post a left-button press+release at scene_pt through the real event pipeline."""
    vp = view.viewport()
    p = view.mapFromScene(scene_pt)
    for et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        ev = QMouseEvent(et, p.toPointF(), vp.mapToGlobal(p).toPointF(),
                         Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(vp, ev)


def _key(view, key):
    """Post a bare key press+release through the real event pipeline."""
    vp = view.viewport()
    for et in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(vp,
            QKeyEvent(et, key, Qt.KeyboardModifier.NoModifier))


@pytest.fixture
def scene(qapp):
    return Model_Space()


# ── Test 1: F enters floor mode ───────────────────────────────────────────────

def test_F_enters_floor_mode(qapp, shown_model_view):
    """F key on a focused view must enter floor mode."""
    view, scene = shown_model_view
    scene.set_mode("select")
    view.setFocus()
    _key(view, Qt.Key.Key_F)
    assert scene.mode == "floor"


# ── Test 2: ←/→ cycles the 3 primitives ───────────────────────────────────────

def test_cycle_primitives(scene):
    """←/→ cycles Corner-Rect → Center-Rect → Polygon → (wrap) Corner-Rect."""
    scene.set_mode("floor")
    # Index 0: Corner Rectangle
    assert scene._floor_primitive == "rect"
    assert scene._floor_rect_from_center is False
    # -> Center Rectangle
    assert scene.cycle_placement_variant(+1) is True
    assert scene._floor_primitive == "rect"
    assert scene._floor_rect_from_center is True
    # -> Polygon
    assert scene.cycle_placement_variant(+1) is True
    assert scene._floor_primitive == "polygon"
    # wrap back to Corner Rectangle
    assert scene.cycle_placement_variant(+1) is True
    assert scene._floor_primitive == "rect"
    assert scene._floor_rect_from_center is False
    # reverse direction
    assert scene.cycle_placement_variant(-1) is True
    assert scene._floor_primitive == "polygon"


# ── Test 3: rect corner 3-step commits a 4-point FloorSlab ─────────────────────

def test_rect_corner_three_step_commits_floorslab(qapp, shown_model_view):
    """Corner Rect: 3 clicks (anchor, size, rotate) → one 4-point FloorSlab."""
    view, scene = shown_model_view
    scene.set_mode("floor")
    assert scene._floor_primitive == "rect"
    assert scene._floor_rect_from_center is False
    _click(view, QPointF(0, 0))         # step 1: anchor
    _click(view, QPointF(1000, 800))    # step 2: size → rotate step
    assert scene._floor_rect_rotating is True
    _click(view, QPointF(1200, 0))      # step 3: rotate ~0° commit
    assert len(scene._floor_slabs) == 1
    slab = scene._floor_slabs[0]
    assert len(slab._points) == 4


# ── Test 4: polygon closes and commits ────────────────────────────────────────

def test_polygon_closes_and_commits(qapp, shown_model_view):
    """Polygon: 3 vertices then a click near the first → closed 3-point FloorSlab."""
    view, scene = shown_model_view
    scene.set_mode("floor")
    scene.cycle_placement_variant(+1)   # corner rect -> center rect
    scene.cycle_placement_variant(+1)   # center rect -> polygon
    assert scene._floor_primitive == "polygon"
    _click(view, QPointF(0, 0))
    _click(view, QPointF(1000, 0))
    _click(view, QPointF(1000, 1000))
    # Click near the first vertex closes (>=3 points).
    _click(view, QPointF(0, 0))
    assert len(scene._floor_slabs) == 1
    slab = scene._floor_slabs[0]
    assert len(slab._points) == 3
    assert scene._floor_active is None


# ── Test 5: continuous placement + Esc exits ──────────────────────────────────

def test_continuous_placement(qapp, shown_model_view):
    """After a rect commit, mode is still 'floor'; Esc exits placement."""
    view, scene = shown_model_view
    scene.set_mode("floor")
    _click(view, QPointF(0, 0))
    _click(view, QPointF(1000, 800))
    _click(view, QPointF(1200, 0))          # commit
    assert len(scene._floor_slabs) == 1
    assert scene.mode == "floor"            # continuous — still armed
    view.setFocus()
    _key(view, Qt.Key.Key_Escape)
    assert scene.mode in (None, "select")


# ── Test 6: Space / ↑ / ↓ are inert during floor placement ────────────────────

def test_spacebar_and_updown_inert(qapp, shown_model_view):
    """Space/↑/↓ must not change the primitive or commit anything in floor mode."""
    view, scene = shown_model_view
    scene.set_mode("floor")
    prim0 = scene._floor_primitive
    fc0 = scene._floor_rect_from_center
    n0 = len(scene._floor_slabs)
    for k in (Qt.Key.Key_Space, Qt.Key.Key_Up, Qt.Key.Key_Down):
        _key(view, k)
    assert scene._floor_primitive == prim0
    assert scene._floor_rect_from_center == fc0
    assert len(scene._floor_slabs) == n0


# ── Test 7: one checkable Floor button, no dropdown menu ───────────────────────


@pytest.fixture()
def mw(qapp, tmp_path, monkeypatch):
    """Fresh MainWindow with safe teardown (mirrors test_apply_level_uses_resolver)."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    import main as main_mod
    from firepro3d.view_3d import View3D
    from firepro3d import snap_engine
    main_mod.View3D = View3D
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    w = main_mod.MainWindow()
    yield w
    w._modified = False
    w.close()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


def test_one_checkable_floor_button_no_menu(mw):
    """The Floor ribbon button is checkable and has no QMenu (dropdown removed)."""
    btn = mw._mode_buttons.get("floor")
    assert btn is not None, "Floor mode button must be registered"
    assert btn.isCheckable() is True
    assert btn.menu() is None, "Floor button must have no dropdown menu"
