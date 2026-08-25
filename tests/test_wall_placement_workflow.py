"""tests/test_wall_placement_workflow.py — wall as a variant-bearing placement mode.

Task 4: one ``"wall"`` scene-mode carries ``_wall_primitive ∈ {"line","polyline","rect"}``;
←/→ cycles the primitive via ``_PLACEMENT_VARIANTS``; ``set_mode("wall_rect")`` aliases
into ``wall`` + ``rect`` primitive (backward-compat shim).

Task 5: "line" primitive places ONE segment then re-arms; "polyline" chains (as before).

Task 6: W key shortcut enters wall mode; ribbon button has no dropdown.
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


@pytest.fixture
def scene(qapp):
    return Model_Space()


def test_wall_defaults_to_line_primitive(scene):
    scene.set_mode("wall")
    assert scene._wall_primitive == "line"


def test_arrow_cycles_line_polyline_rect(scene):
    scene.set_mode("wall")
    assert scene.cycle_placement_variant(+1) is True
    assert scene._wall_primitive == "polyline"
    assert scene.cycle_placement_variant(+1) is True
    assert scene._wall_primitive == "rect"
    assert scene.cycle_placement_variant(+1) is True
    assert scene._wall_primitive == "line"


def test_no_cycle_past_step_zero(scene):
    scene.set_mode("wall")
    scene._wall_anchor = QPointF(0, 0)
    assert scene.cycle_placement_variant(+1) is False


def test_primitive_is_session_sticky(scene):
    scene.set_mode("wall")
    scene.cycle_placement_variant(+1)
    scene.set_mode("select")
    scene.set_mode("wall")
    assert scene._wall_primitive == "polyline"


def test_entry_readout_has_label_and_hint(scene):
    msgs = []
    scene.instructionChanged.connect(msgs.append)
    scene.set_mode("wall")
    assert msgs, "set_mode('wall') should emit an instruction"
    assert "Wall (Line)" in msgs[-1] and "(←/→ to change)" in msgs[-1]


def test_wall_rect_mode_alias_folds_to_rect_primitive(scene):
    # Backward-compat: the ribbon still calls set_mode("wall_rect") until Task 6.
    scene.set_mode("wall_rect")
    assert scene.mode == "wall"
    assert scene._wall_primitive == "rect"


# ── Task 5: finish-vs-continue (line vs polyline) ─────────────────────────────
# These three tests drive the REAL entry point: posted QMouseEvent on a SHOWN,
# activated Model_View (per memory: "Test the real entry point").


def test_line_primitive_places_one_wall_then_rearms(qapp, shown_model_view):
    """Line primitive: two clicks → 1 wall → anchor reset (no chain)."""
    view, scene = shown_model_view
    scene.set_mode("wall")          # default primitive is "line"
    assert scene._wall_primitive == "line"
    _click(view, QPointF(0, 0))
    _click(view, QPointF(1000, 0))  # commits ONE wall
    assert len(scene._walls) == 1
    assert scene._wall_anchor is None   # re-armed fresh (not chained)


def test_polyline_primitive_chains(qapp, shown_model_view):
    """Polyline primitive: third click extends from the shared endpoint."""
    view, scene = shown_model_view
    scene.set_mode("wall")
    scene.cycle_placement_variant(+1)   # line → polyline
    assert scene._wall_primitive == "polyline"
    _click(view, QPointF(0, 0))
    _click(view, QPointF(1000, 0))      # wall 1, chain continues
    _click(view, QPointF(1000, 1000))   # wall 2 from shared endpoint
    assert len(scene._walls) == 2
    assert scene._wall_anchor is not None   # still chaining


def test_line_geometry_parity_with_polyline_first_segment(qapp, shown_model_view):
    """Line variant geometry equals polyline's first segment (same builder)."""
    view, scene = shown_model_view
    scene.set_mode("wall")          # "line"
    _click(view, QPointF(0, 0))
    _click(view, QPointF(1000, 0))
    w = scene._walls[0]
    # The view's center is at scene (0,0) but mapFromScene rounds to integer
    # viewport pixels, so the snapped scene coordinates can land a few mm off
    # the requested integer point.  Use a 20 mm tolerance — tight enough to
    # confirm we got the right segment but loose enough to survive viewport
    # pixel rounding in an empty scene with no snap targets.
    assert abs(w.pt1.x() - 0) < 20 and abs(w.pt1.y() - 0) < 20
    assert abs(w.pt2.x() - 1000) < 20 and abs(w.pt2.y() - 0) < 20


# ── Task 6: W shortcut ────────────────────────────────────────────────────────

def _key(view, key):
    """Post a bare key press+release through the real event pipeline."""
    vp = view.viewport()
    for et in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(vp,
            QKeyEvent(et, key, Qt.KeyboardModifier.NoModifier))


def test_w_enters_wall_mode_via_focused_view(qapp, shown_model_view):
    """W key on a focused view must enter wall mode."""
    view, scene = shown_model_view
    scene.set_mode("select")
    view.setFocus()
    _key(view, Qt.Key.Key_W)
    assert scene.mode == "wall"


# ── Task 7: Spacebar cycles wall alignment (sole binding) ─────────────────────

def test_spacebar_cycles_wall_alignment(qapp, shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("wall")
    a0 = scene._wall_alignment
    _key(view, Qt.Key.Key_Space)
    assert scene._wall_alignment != a0


def test_left_shift_no_longer_cycles_wall_alignment(scene):
    scene.set_mode("wall")
    a0 = scene._wall_alignment
    assert scene.cycle_placement_ambiguity() is False
    assert scene._wall_alignment == a0


def test_spacebar_ignored_while_hud_engaged(qapp, shown_model_view, monkeypatch):
    view, scene = shown_model_view
    scene.set_mode("wall")
    monkeypatch.setattr(scene, "is_input_mode", lambda: True)
    a0 = scene._wall_alignment
    _key(view, Qt.Key.Key_Space)
    assert scene._wall_alignment == a0


# ── Task 8: primitive-aware HUD schema + typed placement applier ──────────────

def test_wall_line_schema_is_line(scene):
    scene.set_mode("wall")                       # line primitive
    assert scene.active_schema() is SCHEMAS["line"]


def test_wall_polyline_schema_is_line(scene):
    scene.set_mode("wall")
    scene.cycle_placement_variant(+1)            # -> polyline
    assert scene.active_schema() is SCHEMAS["line"]


def test_wall_rect_schema_is_rectangle(scene):
    scene.set_mode("wall")
    scene.cycle_placement_variant(+1); scene.cycle_placement_variant(+1)  # -> rect
    assert scene.active_schema() is SCHEMAS["rectangle"]


def test_typed_line_wall_matches_mouse(qapp, shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("wall")
    _click(view, QPointF(0, 0))                  # anchor via real event
    ok = scene._apply_wall_dynamic_input(QPointF(1000, 0))
    assert ok is not False
    assert len(scene._walls) == 1
    assert scene._walls[0].pt2 == QPointF(1000, 0)


# ── Task 8 fixes: rect anchor + live readout ─────────────────────────────────


def test_rect_wall_hud_opens_after_first_corner(qapp, shown_model_view):
    """get_placement_anchor must return the rect anchor after the first click.

    FIX 1: before the fix, get_placement_anchor returned self._wall_anchor for
    ALL wall primitives.  For the rect primitive only _wall_rect_anchor is
    ever set; _wall_anchor stays None.  So _hud_available() saw anchor=None
    and begin_dynamic_input() returned False — the HUD could never open for
    typed rect-wall placement.
    """
    view, scene = shown_model_view
    scene.set_mode("wall")
    scene.cycle_placement_variant(+1)   # line -> polyline
    scene.cycle_placement_variant(+1)   # polyline -> rect
    assert scene._wall_primitive == "rect"
    _click(view, QPointF(0, 0))                      # sets _wall_rect_anchor
    assert scene.get_placement_anchor() is not None  # RED before fix
    # With the anchor known the HUD must be willing to engage.
    assert scene.begin_dynamic_input() is True       # RED before fix
    scene.end_dynamic_input()                        # teardown


def test_typed_rect_wall_builds_four_walls(qapp, shown_model_view):
    """Typed rect placement must build exactly 4 wall segments."""
    view, scene = shown_model_view
    scene.set_mode("wall")
    scene.cycle_placement_variant(+1)   # line -> polyline
    scene.cycle_placement_variant(+1)   # polyline -> rect
    assert scene._wall_primitive == "rect"
    _click(view, QPointF(0, 0))
    scene._apply_wall_dynamic_input(QPointF(1000, 800))
    assert len(scene._walls) == 4


class _MoveEventStub:
    """Minimal stand-in for ``QGraphicsSceneMouseEvent``.

    PyQt6 refuses to instantiate QGraphicsSceneMouseEvent headlessly.
    Wall move handlers only touch ``event.modifiers()``, so this stub
    covers the whole event surface they use.
    """
    def __init__(self, modifiers=None):
        from PyQt6.QtCore import Qt
        self._mods = modifiers or Qt.KeyboardModifier.NoModifier

    def modifiers(self):
        return self._mods


def test_move_wall_publishes_placement_state(scene):
    """_move_wall must publish the resolved tip via publish_placement_state.

    FIX 2: before the fix _resolved_point stayed None during wall placement
    because _move_wall never called publish_placement_state.  This test
    drives the move handler directly (posted MouseMove is inert in PyQt6 —
    project limitation documented in test_dynamic_input_seam.py) with the
    anchor set, and asserts that get_resolved_point() reflects the tip.
    """
    scene.set_mode("wall")
    scene._wall_anchor = QPointF(0, 0)
    tip = QPointF(1000, 0)
    scene._move_wall(_MoveEventStub(), tip)
    got = scene.get_resolved_point()
    assert got is not None, "_move_wall must call publish_placement_state when anchor is set"
    assert abs(got.x() - 1000) < 1 and abs(got.y() - 0) < 1


def test_move_wall_rect_publishes_placement_state(scene):
    """_move_wall_rect must publish the resolved opposite corner.

    FIX 2: same gap — _move_wall_rect never called publish_placement_state,
    leaving the live readout frozen at 0mm/0°.  Driven via direct handler
    call (posted MouseMove is inert).
    """
    scene.set_mode("wall")
    scene.cycle_placement_variant(+1)   # line -> polyline
    scene.cycle_placement_variant(+1)   # polyline -> rect
    # Arm the preview rect that _move_wall_rect checks before publishing.
    from PyQt6.QtWidgets import QGraphicsRectItem
    from PyQt6.QtCore import QRectF
    scene._wall_rect_anchor = QPointF(0, 0)
    scene._wall_rect_preview = QGraphicsRectItem(QRectF(0, 0, 1, 1))
    scene.addItem(scene._wall_rect_preview)
    opposite = QPointF(1000, 800)
    scene._move_wall_rect(_MoveEventStub(), opposite)
    got = scene.get_resolved_point()
    assert got is not None, "_move_wall_rect must call publish_placement_state when anchor is set"
    assert abs(got.x() - 1000) < 1 and abs(got.y() - 800) < 1
