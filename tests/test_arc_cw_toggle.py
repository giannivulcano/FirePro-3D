"""Space flips the sweep direction in the Center / Start arc variants.

User 2026-10-01 (P1): at the span step Space toggles CCW <-> CW, reset per
placement, like the End Points minor/major toggle.  The ``arc_span`` HUD stays
an unsigned magnitude swept in the live direction (2026-10-02 ruling).
"""
import math
import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent

from firepro3d.dynamic_input import SCHEMAS
from firepro3d.geometry_2d import ArcItem
from firepro3d.model_space import (Model_Space, _ARC_VARIANT_CENTER,
                                   _ARC_VARIANT_START)


def _scene(variant):
    s = Model_Space(scene_role="block_editor")
    s.set_mode("draw_arc")
    while s._arc_variant != variant:
        assert s.cycle_placement_variant(+1)
    return s


@pytest.fixture
def scene(qapp):
    return _scene(_ARC_VARIANT_CENTER)


class _Ev:
    """Unmodified press: the Center/Start handlers read ``modifiers()``."""

    def modifiers(self):
        return Qt.KeyboardModifier.NoModifier


def _press(s, x, y):
    s._press_draw_arc(_Ev(), None, QPointF(x, y), None, None, None)


def _placed(s):
    return [i for i in s._draw_arcs if isinstance(i, ArcItem)][-1]


def _ends(arc):
    return {(round(p.x(), 4), round(p.y(), 4)) for p in arc.grip_points()[1:3]}


def _arm_span_step(s):
    """Centre (0,0), start at bearing 0° (rim (100, 0)) → span step."""
    _press(s, 0, 0); _press(s, 100, 0)
    assert s._draw_arc_step == 2


def _assert_cw_270(arc):
    # Start 0° swept CW to bearing 90° (scene (0, -100)) is the 270° arc
    # through bearing -135° — the lower-left of the circle (scene y down).
    assert arc._span_deg == pytest.approx(270.0)
    assert _ends(arc) == {(100.0, 0.0), (0.0, -100.0)}
    mid = arc.arc_midpoint()
    assert mid.x() == pytest.approx(-100 / math.sqrt(2))
    assert mid.y() == pytest.approx(100 / math.sqrt(2))


def test_center_space_sweeps_cw(scene):
    _arm_span_step(scene)
    assert scene.cycle_placement_ambiguity() is True
    _press(scene, 0, -100)
    _assert_cw_270(_placed(scene))


def test_start_variant_space_sweeps_cw(qapp):
    s = _scene(_ARC_VARIANT_START)
    _press(s, 100, 0)          # start point
    _press(s, 0, 0)            # centre
    assert s._draw_arc_step == 2
    assert s.cycle_placement_ambiguity() is True
    _press(s, 0, -100)
    _assert_cw_270(_placed(s))


def test_default_stays_ccw(scene):
    _arm_span_step(scene)
    _press(scene, 0, -100)
    arc = _placed(scene)
    assert arc._span_deg == pytest.approx(90.0)
    assert arc.arc_midpoint().y() < 0.0            # upper-right quadrant


def test_space_twice_returns_to_ccw(scene):
    _arm_span_step(scene)
    assert scene.cycle_placement_ambiguity() is True
    assert scene.cycle_placement_ambiguity() is True
    _press(scene, 0, -100)
    assert _placed(scene)._span_deg == pytest.approx(90.0)


def test_direction_resets_per_placement(scene):
    _arm_span_step(scene)
    scene.cycle_placement_ambiguity()
    _press(scene, 0, -100)                         # CW commit
    assert scene.mode == "select"                  # one-shot: back to Select
    scene.set_mode("draw_arc")                     # the user re-arms the tool
    assert scene._arc_variant == _ARC_VARIANT_CENTER
    _arm_span_step(scene)
    _press(scene, 0, -100)
    assert _placed(scene)._span_deg == pytest.approx(90.0)


def test_typed_span_sweeps_in_live_direction(scene):
    _arm_span_step(scene)
    scene.cycle_placement_ambiguity()
    assert scene._geom_ctl._apply_arc_dynamic_input({"span_deg": 45.0})
    arc = _placed(scene)
    assert arc._span_deg == pytest.approx(45.0)
    h = round(100 / math.sqrt(2), 4)
    assert _ends(arc) == {(100.0, 0.0), (h, h)}    # bearing -45° (below +x)


def test_hud_seed_is_unsigned_magnitude_in_live_direction(scene):
    _arm_span_step(scene)
    scene.publish_placement_state(scene._draw_arc_center, QPointF(0, -100))
    seed = scene._plc._transform_seed_values(SCHEMAS["arc_span"])
    assert seed["Span"] == pytest.approx(90.0)
    scene.cycle_placement_ambiguity()
    seed = scene._plc._transform_seed_values(SCHEMAS["arc_span"])
    assert seed["Span"] == pytest.approx(270.0)
    assert seed["ArcLength"] == pytest.approx(math.radians(270.0) * 100.0)


def test_space_before_span_step_cycles_nothing(scene):
    _press(scene, 0, 0)
    assert scene._draw_arc_step == 1
    assert scene.cycle_placement_ambiguity() is False


def test_space_key_event_flips_direction(scene):
    _arm_span_step(scene)
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space,
                   Qt.KeyboardModifier.NoModifier)
    scene.keyPressEvent(ev)
    assert ev.isAccepted()
    _press(scene, 0, -100)
    _assert_cw_270(_placed(scene))
