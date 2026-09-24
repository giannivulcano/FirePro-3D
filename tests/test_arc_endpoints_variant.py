"""End-Points arc variant (user 2026-09-23 grill Q6)."""
import math
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.model_space import Model_Space, _ARC_VARIANT_ENDPOINTS
from firepro3d.geometry_2d import ArcItem


@pytest.fixture
def scene(qapp):
    s = Model_Space(scene_role="block_editor")
    s.set_mode("draw_arc")
    while s._arc_variant != _ARC_VARIANT_ENDPOINTS:
        assert s.cycle_placement_variant(+1)
    return s


def _press(s, x, y):
    s._press_draw_arc(None, None, QPointF(x, y), None, None, None)


def _placed(s):
    return [i for i in s._draw_arcs if isinstance(i, ArcItem)][-1]


def _ends(arc):
    p = arc.grip_points()
    return p[1], p[2]


def test_arc_passes_through_both_picked_ends(scene):
    _press(scene, 0, 0); _press(scene, 100, 0); _press(scene, 50, 40)
    a, b = _ends(_placed(scene))
    got = {(round(a.x(), 6), round(a.y(), 6)), (round(b.x(), 6), round(b.y(), 6))}
    assert got == {(0.0, 0.0), (100.0, 0.0)}


def test_centre_off_bisector_is_projected(scene):
    _press(scene, 0, 0); _press(scene, 100, 0); _press(scene, 80, 40)
    c = _placed(scene).grip_points()[0]
    assert c.x() == pytest.approx(50.0)


def test_default_minor_bulges_away_from_centre_side(scene):
    _press(scene, 0, 0); _press(scene, 100, 0); _press(scene, 50, 40)  # centre below
    arc = _placed(scene)
    assert arc._span_deg < 180.0
    assert arc.arc_midpoint().y() < 0.0            # bulges up (away)


def test_space_toggles_major(scene):
    _press(scene, 0, 0); _press(scene, 100, 0)
    assert scene.cycle_placement_ambiguity() is True
    _press(scene, 50, 40)
    arc = _placed(scene)
    assert arc._span_deg > 180.0
    assert arc.arc_midpoint().y() > 0.0            # bulges toward the centre side


def test_cursor_side_flips_bulge(scene):
    _press(scene, 0, 0); _press(scene, 100, 0); _press(scene, 50, -40)
    assert _placed(scene).arc_midpoint().y() > 0.0


def test_zero_chord_rejected(scene):
    _press(scene, 0, 0); _press(scene, 0.1, 0)
    assert scene._draw_arc_step == 1


def test_typed_radius_below_half_chord_rejected(scene):
    _press(scene, 0, 0); _press(scene, 100, 0)
    assert scene._apply_arc_dynamic_input({"radius": 40.0}) is False
    assert scene._apply_arc_dynamic_input({"radius": 50.0}) is True
    assert _placed(scene)._radius == pytest.approx(50.0)


def test_start_variant_prompt_asks_for_centre(qapp):     # fold G
    s = Model_Space(scene_role="block_editor")
    s.set_mode("draw_arc")
    s.cycle_placement_variant(+1)                          # Start Point Arc
    seen = []
    s.instructionChanged.connect(seen.append)
    s._press_draw_arc(None, None, QPointF(0, 0), None, None, None)
    assert seen[-1] == "Pick center point"


def test_escape_mid_centre_step_tears_down_previews(scene):
    _press(scene, 0, 0); _press(scene, 100, 0)
    scene._move_draw_arc(None, QPointF(50, 40))
    items = [scene._draw_arc_preview, scene._draw_arc_ref_line0,
             scene._draw_arc_ref_start, scene._draw_arc_ref_sweep]
    assert all(i is not None and i.scene() is scene for i in items)
    scene.set_mode("select")
    assert all(i.scene() is None for i in items)
    assert scene._draw_arc_ep_a is None and scene._draw_arc_ep_b is None
    assert scene._draw_arc_step == 0


def test_semicircle_keeps_last_hovered_side(scene):
    _press(scene, 0, 0); _press(scene, 100, 0)
    scene._move_draw_arc(None, QPointF(50, 40))      # hover: centre below
    _press(scene, 50, 0)                              # commit on the chord
    arc = _placed(scene)
    assert arc._span_deg == pytest.approx(180.0)
    assert arc.arc_midpoint().y() < 0.0              # bulges up (away)


def test_typed_radius_preview_point_on_bisector(scene):
    _press(scene, 0, 0); _press(scene, 100, 0)
    anchor = scene.get_placement_anchor()
    c = scene._transform_preview_point({"radius": 60.0}, anchor)
    assert c.x() == pytest.approx(50.0)
    assert math.hypot(c.x(), c.y()) == pytest.approx(60.0)


# ── 90° snap (smoke-test tweak 2026-09-24) ────────────────────────────────
# Chord (0,0)→(100,0): half-chord h = 50, so a centre at t = ±50 from the
# midpoint makes C→A ⟂ C→B (a 90° minor arc).  With no view attached the
# tolerance falls back to SNAP_TOLERANCE_PX at scale 1.0 (15 scene mm).

def test_near_90_centre_snaps_to_exact_quarter(scene):
    _press(scene, 0, 0); _press(scene, 100, 0); _press(scene, 50, 53)
    arc = _placed(scene)
    assert arc._span_deg == pytest.approx(90.0, abs=1e-9)
    assert arc._radius == pytest.approx(50.0 * math.sqrt(2.0), abs=1e-9)


def test_near_90_major_snaps_to_exact_270(scene):
    _press(scene, 0, 0); _press(scene, 100, 0)
    assert scene.cycle_placement_ambiguity() is True
    _press(scene, 50, 47)
    assert _placed(scene)._span_deg == pytest.approx(270.0, abs=1e-9)


def test_far_from_90_not_snapped(scene):
    _press(scene, 0, 0); _press(scene, 100, 0); _press(scene, 50, 80)
    assert _placed(scene)._span_deg != pytest.approx(90.0, abs=1.0)


def test_90_snap_applies_to_preview(scene):
    _press(scene, 0, 0); _press(scene, 100, 0)
    scene._geom_ctl._preview_from_arc_ep(QPointF(50, 53))
    c = scene._draw_arc_ref_start.line().p1()           # centre end of radial
    assert (c.x(), c.y()) == (pytest.approx(50.0), pytest.approx(50.0, abs=1e-9))


def test_90_snap_tolerance_scales_with_zoom(scene):
    from PyQt6.QtWidgets import QGraphicsView
    v = QGraphicsView(scene)
    v.scale(10.0, 10.0)            # 15 px → 1.5 mm: 3 mm off is outside
    try:
        _press(scene, 0, 0); _press(scene, 100, 0); _press(scene, 50, 53)
        assert _placed(scene)._span_deg != pytest.approx(90.0, abs=0.5)
    finally:
        v.setScene(None)


def test_typed_radius_not_snapped_to_90(scene):
    _press(scene, 0, 0); _press(scene, 100, 0)
    assert scene._apply_arc_dynamic_input({"radius": 72.0}) is True
    assert _placed(scene)._radius == pytest.approx(72.0)
