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


class _MoveEventStub:
    """Minimal stand-in for ``QGraphicsSceneMouseEvent``.

    PyQt6 refuses to instantiate QGraphicsSceneMouseEvent headlessly, and a
    posted QMouseEvent does not drive the scene's mouseMoveEvent (project
    limitation — see test_wall_placement_workflow.py / memory "QTest.mouseMove
    is inert here").  The floor move handlers only touch ``event.modifiers()``,
    so this stub covers the whole event surface they use.
    """

    def __init__(self, modifiers=None):
        self._mods = modifiers or Qt.KeyboardModifier.NoModifier

    def modifiers(self):
        return self._mods


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


# ── HUD live-update during floor placement ────────────────────────────────────
#
# The passive HUD readout is what ``_seed_values_for(active_schema,
# get_placement_anchor())`` returns after each move — that is exactly what
# ``_sync_dynamic_input`` feeds to ``hud.set_values``.  These tests drive the
# real move path (the ``_MOVE_DISPATCH`` handler the mouse uses) and read that
# seed, NOT the dead ``_draw_dim_hint`` painted string.  A frozen readout shows
# up as identical seed values at two different cursor positions.


def _seeded(scene):
    """Return the HUD seed values ``_sync_dynamic_input`` would push this frame."""
    return scene._seed_values_for(scene.active_schema(),
                                  scene.get_placement_anchor())


def _drive_move(scene, snapped):
    """Run the real per-mode move handler for the given cursor point.

    Mirrors ``mouseMoveEvent``: clear the published point (the frame reset),
    dispatch to the mode handler, then let the seed be read.  Posted
    QMouseEvent is inert in PyQt6 (see module docstring), so the handler is
    invoked the same way the dispatch table would.
    """
    scene.clear_placement_state()
    scene._move_floor_router(_MoveEventStub(), snapped)


def test_polygon_hud_length_live_updates(qapp, shown_model_view):
    """Polygon: the seeded HUD Length/Angle must track the cursor after a vertex.

    RED before the fix — ``_move_floor`` never called ``publish_placement_state``,
    so ``get_resolved_point()`` stayed None and ``_seed_values_for`` fell back to
    ``schema.seed(anchor, anchor)`` = a frozen zero-length readout at every
    cursor position.
    """
    view, scene = shown_model_view
    scene.set_mode("floor")
    scene.cycle_placement_variant(+1)   # corner rect -> center rect
    scene.cycle_placement_variant(+1)   # center rect -> polygon
    assert scene._floor_primitive == "polygon"

    _click(view, QPointF(0, 0))         # first vertex arms the polygon chain
    assert scene._floor_active is not None

    _drive_move(scene, QPointF(1000, 0))
    pt_a = scene.get_resolved_point()
    seed_a = _seeded(scene)
    assert pt_a is not None, (
        "_move_floor must publish the resolved cursor so the HUD can seed")

    _drive_move(scene, QPointF(0, 1000))
    pt_b = scene.get_resolved_point()
    seed_b = _seeded(scene)
    assert pt_b is not None

    # The published point and the seeded readout must both reflect the cursor
    # and DIFFER between the two positions (not frozen at zero).
    assert seed_a["Length"] > 1.0
    assert seed_b["Length"] > 1.0
    assert abs(seed_a["Length"] - seed_b["Length"]) < 1e-6  # same 1000mm radius
    assert abs(seed_a["Angle"] - seed_b["Angle"]) > 1.0     # 0° vs +90° differ


def test_rect_hud_size_live_updates(qapp, shown_model_view):
    """Corner Rect sizing: seeded W/H must track the cursor and differ per move."""
    view, scene = shown_model_view
    scene.set_mode("floor")
    assert scene._floor_primitive == "rect"
    assert scene._floor_rect_from_center is False

    _click(view, QPointF(0, 0))         # first corner -> sizing step
    assert scene._floor_rect_anchor is not None
    assert scene._floor_rect_rotating is False

    _drive_move(scene, QPointF(1000, 800))
    pt_a = scene.get_resolved_point()
    seed_a = _seeded(scene)
    assert pt_a is not None, "sizing move must publish the far corner"

    _drive_move(scene, QPointF(500, 300))
    pt_b = scene.get_resolved_point()
    seed_b = _seeded(scene)
    assert pt_b is not None

    # rectangle schema seeds the signed X/Y extents of the far corner.
    assert abs(seed_a["X"] - 1000) < 1 and abs(seed_a["Y"]) > 0
    assert abs(seed_b["X"] - 500) < 1
    assert abs(seed_a["X"] - seed_b["X"]) > 1.0
    assert abs(seed_a["Y"] - seed_b["Y"]) > 1.0


def test_rect_hud_rotate_angle_live_updates(qapp, shown_model_view):
    """Corner Rect rotate step: seeded Angle must track the cursor and differ."""
    view, scene = shown_model_view
    scene.set_mode("floor")
    assert scene._floor_primitive == "rect"

    _click(view, QPointF(0, 0))         # anchor
    _click(view, QPointF(1000, 800))    # size -> rotate step
    assert scene._floor_rect_rotating is True
    assert scene.active_schema().name == "rotation"

    _drive_move(scene, QPointF(1200, 0))
    pt_a = scene.get_resolved_point()
    seed_a = _seeded(scene)
    assert pt_a is not None, "rotate move must publish the orientation point"

    _drive_move(scene, QPointF(0, 1200))
    pt_b = scene.get_resolved_point()
    seed_b = _seeded(scene)
    assert pt_b is not None

    assert abs(seed_a["Angle"] - seed_b["Angle"]) > 1.0


# ── Template name seeds placed floors (uniquified on collision) ────────────────

def _place_polygon_floor(view, scene, origin=(0.0, 0.0)):
    """Place ONE triangular floor via the real polygon commit path.

    Drives ``_press_floor`` through posted clicks: 3 vertices then a
    close-near-first click.  Returns the newly committed FloorSlab.
    """
    ox, oy = origin
    _click(view, QPointF(ox, oy))
    _click(view, QPointF(ox + 1000, oy))
    _click(view, QPointF(ox + 1000, oy + 1000))
    _click(view, QPointF(ox, oy))          # close near first vertex
    return scene._floor_slabs[-1]


def test_template_name_seeds_placed_floor(qapp, shown_model_view):
    """A user-authored template name seeds the placed slab's name verbatim."""
    view, scene = shown_model_view
    scene.set_mode("floor")
    scene.cycle_placement_variant(+1)   # corner rect -> center rect
    scene.cycle_placement_variant(+1)   # center rect -> polygon
    scene._get_floor_template().name = "Slab"
    slab = _place_polygon_floor(view, scene)
    assert slab.name == "Slab"


def test_duplicate_floor_name_appends_number(qapp, shown_model_view):
    """Colliding template names uniquify with the smallest N >= 1."""
    view, scene = shown_model_view
    scene.set_mode("floor")
    scene.cycle_placement_variant(+1)
    scene.cycle_placement_variant(+1)
    scene._get_floor_template().name = "Slab"
    n1 = _place_polygon_floor(view, scene, origin=(0, 0))
    n2 = _place_polygon_floor(view, scene, origin=(3000, 0))
    n3 = _place_polygon_floor(view, scene, origin=(6000, 0))
    assert [n1.name, n2.name, n3.name] == ["Slab", "Slab 1", "Slab 2"]


def test_default_template_name_uses_floor(qapp, shown_model_view):
    """The default "(Template)" name falls back to base "Floor"."""
    view, scene = shown_model_view
    scene.set_mode("floor")
    scene.cycle_placement_variant(+1)
    scene.cycle_placement_variant(+1)
    # template name left at its default "(Template)"
    assert scene._get_floor_template().name == "(Template)"
    n1 = _place_polygon_floor(view, scene, origin=(0, 0))
    n2 = _place_polygon_floor(view, scene, origin=(3000, 0))
    assert [n1.name, n2.name] == ["Floor", "Floor 1"]


def test_blank_template_name_uses_floor(qapp, shown_model_view):
    """A blank template name falls back to base "Floor"."""
    view, scene = shown_model_view
    scene.set_mode("floor")
    scene.cycle_placement_variant(+1)
    scene.cycle_placement_variant(+1)
    scene._get_floor_template().name = ""
    slab = _place_polygon_floor(view, scene)
    assert slab.name == "Floor"


# ── Unit tests for the naming helpers (stubbed scene state) ────────────────────

def test_unique_floor_name_helper(scene):
    """_unique_floor_name uniquifies against existing slab names."""
    class _S:
        def __init__(self, name):
            self.name = name
    scene._floor_slabs = [_S("Slab"), _S("Slab 1"), None]
    assert scene._unique_floor_name("Floor") == "Floor"      # free
    assert scene._unique_floor_name("Slab") == "Slab 2"      # Slab + Slab 1 taken -> 2


def test_floor_base_name_helper(scene):
    """_floor_base_name reads the template, defaulting to "Floor"."""
    scene._get_floor_template().name = "(Template)"
    assert scene._floor_base_name() == "Floor"
    scene._get_floor_template().name = ""
    assert scene._floor_base_name() == "Floor"
    scene._get_floor_template().name = "  Deck  "
    assert scene._floor_base_name() == "Deck"
