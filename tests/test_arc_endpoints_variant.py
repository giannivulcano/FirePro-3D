"""End-Points arc variant (user 2026-09-23 grill Q6)."""
import math
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.model_space import Model_Space, _ARC_VARIANT_ENDPOINTS
from firepro3d.geometry_2d import ArcItem


def _close(p, q, tol=1e-6):
    return abs(p.x() - q.x()) < tol and abs(p.y() - q.y()) < tol


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
