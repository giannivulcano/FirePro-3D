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
    """Updated for 4-variant list: Line→Polyline→Corner Rect→Center Rect→Line."""
    scene.set_mode("wall")
    assert scene.cycle_placement_variant(+1) is True
    assert scene._wall_primitive == "polyline"
    assert scene.cycle_placement_variant(+1) is True
    assert scene._wall_primitive == "rect"
    assert scene._wall_rect_from_center is False   # corner rect
    assert scene.cycle_placement_variant(+1) is True
    assert scene._wall_primitive == "rect"
    assert scene._wall_rect_from_center is True    # center rect
    assert scene.cycle_placement_variant(+1) is True
    assert scene._wall_primitive == "line"         # wraps back


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
    # The Left-Shift *tap* that once cycled placement ambiguity was removed;
    # Left-Shift is now a pure modifier.  A clean left-Shift press/release must
    # leave wall alignment untouched.  (Wall alignment now cycles on Space via
    # cycle_placement_ambiguity — covered in test_placement_cycle_shift.py.)
    scene.set_mode("wall")
    a0 = scene._wall_alignment
    press = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Shift,
                      Qt.KeyboardModifier.ShiftModifier, 42, 0xA0, 0, "", False, 1)
    release = QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Shift,
                        Qt.KeyboardModifier.NoModifier, 42, 0xA0, 0, "", False, 1)
    scene.keyPressEvent(press)
    scene.keyReleaseEvent(release)
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
    """Typed rect placement (3-step) must build exactly 4 wall segments.

    Updated for the 3-step workflow: first click anchors, second typed point
    advances to the rotate step, third typed angle commits.
    """
    view, scene = shown_model_view
    scene.set_mode("wall")
    scene.cycle_placement_variant(+1)   # line -> polyline
    scene.cycle_placement_variant(+1)   # polyline -> corner rect
    assert scene._wall_primitive == "rect"
    _click(view, QPointF(0, 0))                                     # step 1: anchor
    ok = scene._apply_wall_dynamic_input(QPointF(1000, 800))        # step 2: size → rotate step
    assert ok is not False, "Sizing step should not refuse a valid rect"
    assert scene._wall_rect_rotating is True, "Should now be in rotate step"
    ok2 = scene._apply_wall_dynamic_input({"angle_deg": 0.0})       # step 3: commit at 0°
    assert ok2 is not False
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


def test_move_wall_rect_publishes_placement_state_sizing(scene):
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


# ── Task N: 4-variant cycle + Corner/Center + rotate step ────────────────────


def test_arrow_cycles_four_variants(scene):
    """←/→ must cycle Line→Polyline→Corner Rect→Center Rect→Line (4 variants)."""
    scene.set_mode("wall")
    # Starting at index 0 (line)
    assert scene._wall_primitive == "line"
    assert scene.cycle_placement_variant(+1) is True
    assert scene._wall_primitive == "polyline"
    assert scene.cycle_placement_variant(+1) is True
    assert scene._wall_primitive == "rect"
    assert scene._wall_rect_from_center is False, "index 2 must be Corner Rect"
    assert scene.cycle_placement_variant(+1) is True
    assert scene._wall_primitive == "rect"
    assert scene._wall_rect_from_center is True, "index 3 must be Center Rect"
    assert scene.cycle_placement_variant(+1) is True
    assert scene._wall_primitive == "line", "cycle must wrap back to Line"


def test_center_rect_wall_centred_on_first_click(qapp, shown_model_view):
    """Center Rect: 2 sizing clicks → 4 walls; combined bounding centre ≈ first click."""
    view, scene = shown_model_view
    scene.set_mode("wall")
    # Cycle to Center Rect (index 3)
    scene.cycle_placement_variant(+1)  # line -> polyline
    scene.cycle_placement_variant(+1)  # polyline -> corner rect
    scene.cycle_placement_variant(+1)  # corner rect -> center rect
    assert scene._wall_primitive == "rect"
    assert scene._wall_rect_from_center is True
    centre_pt = QPointF(500, 500)
    corner_pt = QPointF(700, 700)   # 200×200 half-extents → 400×400 full rect
    _click(view, centre_pt)         # first click: centre
    _click(view, corner_pt)         # second click: corner (enters rotate step)
    # Third click to commit at ~0° rotation (click far right of pivot)
    rotate_pt = QPointF(900, 500)   # due east → 0°
    _click(view, rotate_pt)
    assert len(scene._walls) == 4, f"Expected 4 walls, got {len(scene._walls)}"
    # Compute bounding box of all wall endpoints
    xs = [w.pt1.x() for w in scene._walls] + [w.pt2.x() for w in scene._walls]
    ys = [w.pt1.y() for w in scene._walls] + [w.pt2.y() for w in scene._walls]
    bx = (min(xs) + max(xs)) / 2
    by = (min(ys) + max(ys)) / 2
    # Centre must be within 30 mm of the first click (viewport rounding + snap)
    assert abs(bx - centre_pt.x()) < 30, f"Bounding centre x={bx:.1f} far from {centre_pt.x()}"
    assert abs(by - centre_pt.y()) < 30, f"Bounding centre y={by:.1f} far from {centre_pt.y()}"


def test_corner_rect_wall_builds_four_walls_with_rotate(qapp, shown_model_view):
    """Corner Rect: 2 sizing clicks then a ~0° rotate click → 4 walls."""
    view, scene = shown_model_view
    scene.set_mode("wall")
    scene.cycle_placement_variant(+1)  # line -> polyline
    scene.cycle_placement_variant(+1)  # polyline -> corner rect
    assert scene._wall_primitive == "rect"
    assert scene._wall_rect_from_center is False
    _click(view, QPointF(0, 0))        # first corner
    _click(view, QPointF(1000, 800))   # opposite corner → enters rotate step
    # Confirm rotate step is active before third click
    assert scene._wall_rect_rotating is True, "After 2nd click, must be in rotate step"
    _click(view, QPointF(1200, 0))     # third click: rotate commit ~0°
    assert len(scene._walls) == 4, f"Expected 4 walls, got {len(scene._walls)}"


def test_rect_wall_rotate_produces_rotated_walls(qapp, shown_model_view):
    """Corner Rect + angled third click → 4 walls, at least one not axis-aligned."""
    view, scene = shown_model_view
    scene.set_mode("wall")
    scene.cycle_placement_variant(+1)  # -> polyline
    scene.cycle_placement_variant(+1)  # -> corner rect
    _click(view, QPointF(0, 0))        # first corner
    _click(view, QPointF(800, 800))    # second corner → rotate step
    assert scene._wall_rect_rotating is True
    # Click at 45° from pivot (0,0): up-right → 45° Y-up
    _click(view, QPointF(600, -600))   # NE in Qt scene (y-up 45°)
    assert len(scene._walls) == 4, f"Expected 4 walls, got {len(scene._walls)}"
    # At least one wall must be non-axis-aligned (both dx and dy are non-zero)
    non_axis = [
        w for w in scene._walls
        if abs(w.pt2.x() - w.pt1.x()) > 1 and abs(w.pt2.y() - w.pt1.y()) > 1
    ]
    assert len(non_axis) >= 1, (
        "A rotated rect must have at least one non-axis-aligned wall; "
        f"walls: {[(w.pt1, w.pt2) for w in scene._walls]}"
    )


def test_wall_rect_schema_is_step_aware(scene):
    """Rect primitive: sizing step → SCHEMAS['rectangle']; rotating → SCHEMAS['rotation']."""
    scene.set_mode("wall")
    scene.cycle_placement_variant(+1)  # -> polyline
    scene.cycle_placement_variant(+1)  # -> corner rect
    assert scene._wall_primitive == "rect"
    # Before any anchor: active_schema returns rectangle (same as before)
    # (anchor gate keeps HUD shut anyway, but the schema itself should be rectangle)
    scene._wall_rect_anchor = QPointF(0, 0)   # simulate first click
    assert scene.active_schema() is SCHEMAS["rectangle"], (
        "Sizing step must use rectangle schema"
    )
    # Simulate advancing to rotate step
    scene._wall_rect_rotating = True
    assert scene.active_schema() is SCHEMAS["rotation"], (
        "Rotate step must use rotation schema"
    )
    scene._wall_rect_rotating = False   # cleanup


# ── Parity: rotated_rect_corners vs RectangleItem.set_angle + mapToScene ──────


def test_rotated_rect_corners_parity_with_rectangle_item():
    """rotated_rect_corners must reproduce RectangleItem.set_angle scene coords.

    RectangleItem is the ground truth for the 2D-geo rect and by extension for
    the wall rect rotation formula.  This test samples three angles to verify
    the pure math helper is bit-for-bit consistent with the Qt transform path
    the user actually sees.
    """
    import math
    from PyQt6.QtCore import QPointF
    from firepro3d.construction_geometry import RectangleItem, rotated_rect_corners

    pt1 = QPointF(0.0, 0.0)
    pt2 = QPointF(200.0, 100.0)
    pivot = QPointF(0.0, 0.0)

    for angle_deg in (0.0, 30.0, 90.0, -45.0, 135.0):
        item = RectangleItem(pt1, pt2)
        item.set_angle(angle_deg, pivot)

        r = item.rect()
        local_corners = [
            QPointF(r.left(), r.top()),    # TL
            QPointF(r.right(), r.top()),   # TR
            QPointF(r.right(), r.bottom()), # BR
            QPointF(r.left(), r.bottom()),  # BL
        ]
        expected = [item.mapToScene(c) for c in local_corners]
        got = rotated_rect_corners(pt1, pt2, angle_deg, pivot)

        for i, (e, g) in enumerate(zip(expected, got)):
            assert abs(e.x() - g.x()) < 1e-6 and abs(e.y() - g.y()) < 1e-6, (
                f"angle={angle_deg}° corner {i}: expected ({e.x():.6f},{e.y():.6f})"
                f" got ({g.x():.6f},{g.y():.6f})"
            )


def test_wall_rect_rotate_hud_angle_live_seeds(qapp, shown_model_view):
    """Rotate-step passive HUD seeds the live pivot→cursor angle (not frozen 0°).

    Regression: ``_transform_seed_values`` for the "rotation" schema fell through
    to ``_rect_rotation_angle_to``, which reads the 2D-geo ``_draw_rect_pivot``
    (None during wall placement) → 0°.  A ``wall`` branch now uses
    ``_wall_rect_rotation_angle_to`` (the wall pivot).
    """
    view, scene = shown_model_view
    scene.set_mode("wall")
    scene.cycle_placement_variant(+1)
    scene.cycle_placement_variant(+1)          # -> Corner Rectangle
    _click(view, QPointF(0, 0))                # anchor
    _click(view, QPointF(1000, 500))           # size (non-degenerate) → rotate step
    assert scene._wall_rect_rotating is True
    pivot = scene._wall_rect_pivot
    # Publish a resolved point 45° up-right of the pivot (Y-up: y decreases up).
    scene.publish_placement_state(pivot, QPointF(pivot.x() + 100, pivot.y() - 100))
    vals = scene._transform_seed_values(SCHEMAS["rotation"])
    assert abs(vals["Angle"] - 45.0) < 0.5     # RED before fix: 0.0 (wrong pivot)
