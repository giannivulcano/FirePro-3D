"""tests/test_placement_variants.py — generic placement-variant cycle.

Covers ``Model_Space.cycle_placement_variant`` and the ``_PLACEMENT_VARIANTS``
registry (Task 13): ←/→ cycles the placement variant of a multi-variant tool
(arc centre-first vs start-first; rectangle corner vs centre) at step 0 only,
the chosen index is session-sticky per mode, and the step-0 readout carries the
``(←/→ to change)`` hint that disappears once the first point is placed.

Arrow-key wiring itself lands in Task 14 — these tests drive
``cycle_placement_variant`` directly.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtTest import QTest

from firepro3d.model_space import (
    Model_Space,
    _ARC_VARIANT_CENTER,
    _ARC_VARIANT_START,
)


def _arrow(key):
    """Build a real KeyPress event for an arrow key (no modifiers)."""
    return QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, "")


@pytest.fixture
def scene(qapp):
    return Model_Space()


class TestArcVariantCycle:
    def test_cycle_flips_center_to_start_and_wraps(self, scene):
        scene.set_mode("draw_arc")
        assert scene._arc_variant == _ARC_VARIANT_CENTER
        assert scene.cycle_placement_variant(+1) is True
        assert scene._arc_variant == _ARC_VARIANT_START
        # Second call wraps back to center.
        assert scene.cycle_placement_variant(+1) is True
        assert scene._arc_variant == _ARC_VARIANT_CENTER

    def test_negative_direction_cycles(self, scene):
        scene.set_mode("draw_arc")
        assert scene.cycle_placement_variant(-1) is True
        assert scene._arc_variant == _ARC_VARIANT_START

    def test_no_cycle_past_step_zero(self, scene):
        scene.set_mode("draw_arc")
        # Place the first point (centre) → step 1.
        scene._press_draw_arc(None, None, QPointF(0, 0), None, None, None)
        assert scene._draw_arc_step == 1
        before = scene._arc_variant
        assert scene.cycle_placement_variant(+1) is False
        assert scene._arc_variant == before


class TestRectangleVariantCycle:
    def test_cycle_flips_corner_center_corner(self, scene):
        scene.set_mode("draw_rectangle")
        assert scene._draw_rect_from_center is False
        assert scene.cycle_placement_variant(+1) is True
        assert scene._draw_rect_from_center is True
        assert scene.cycle_placement_variant(+1) is True
        assert scene._draw_rect_from_center is False

    def test_no_cycle_after_first_corner(self, scene):
        scene.set_mode("draw_rectangle")
        scene._draw_rect_anchor = QPointF(0, 0)  # first corner placed
        assert scene.cycle_placement_variant(+1) is False

    def test_no_cycle_while_rotating(self, scene):
        scene.set_mode("draw_rectangle")
        scene._draw_rect_rotating = True
        assert scene.cycle_placement_variant(+1) is False


class TestNonVariantModes:
    def test_draw_line_does_not_cycle(self, scene):
        scene.set_mode("draw_line")
        assert scene.cycle_placement_variant(+1) is False

    def test_select_does_not_cycle(self, scene):
        scene.set_mode("select")
        assert scene.cycle_placement_variant(+1) is False


class TestSessionSticky:
    def test_arc_variant_survives_mode_round_trip(self, scene):
        scene.set_mode("draw_arc")
        scene.cycle_placement_variant(+1)
        assert scene._arc_variant == _ARC_VARIANT_START
        scene.set_mode("select")
        scene.set_mode("draw_arc")
        # Sticky index re-applied on re-entry.
        assert scene._arc_variant == _ARC_VARIANT_START

    def test_rectangle_variant_survives_mode_round_trip(self, scene):
        scene.set_mode("draw_rectangle")
        scene.cycle_placement_variant(+1)
        assert scene._draw_rect_from_center is True
        scene.set_mode("select")
        scene.set_mode("draw_rectangle")
        assert scene._draw_rect_from_center is True


class TestReadout:
    def _collect(self, scene):
        msgs: list[str] = []
        scene.instructionChanged.connect(msgs.append)
        return msgs

    def test_entry_readout_carries_label_and_hint(self, scene):
        msgs = self._collect(scene)
        scene.set_mode("draw_rectangle")
        assert msgs, "set_mode should emit an instruction"
        last = msgs[-1]
        assert "Corner Rectangle" in last
        assert "(←/→ to change)" in last

    def test_cycle_readout_switches_label(self, scene):
        scene.set_mode("draw_rectangle")
        msgs = self._collect(scene)
        scene.cycle_placement_variant(+1)
        assert msgs
        last = msgs[-1]
        assert "Center Rectangle" in last
        assert "(←/→ to change)" in last

    def test_first_click_instruction_has_no_hint(self, scene):
        scene.set_mode("draw_rectangle")
        msgs = self._collect(scene)
        scene._press_draw_rectangle(None, None, QPointF(0, 0), None, None, None)
        assert msgs, "first click should emit a next-step instruction"
        assert all("to change" not in m for m in msgs)

    def test_arc_entry_readout(self, scene):
        msgs = self._collect(scene)
        scene.set_mode("draw_arc")
        last = msgs[-1]
        assert "Center Point Arc" in last
        assert "(←/→ to change)" in last


class TestInputModeGate:
    def test_no_cycle_while_hud_field_focused(self, scene, monkeypatch):
        scene.set_mode("draw_arc")
        monkeypatch.setattr(scene, "is_input_mode", lambda: True)
        before = scene._arc_variant
        assert scene.cycle_placement_variant(+1) is False
        assert scene._arc_variant == before


class TestArrowKeyWiring:
    """Task 14: ←/→ in ``keyPressEvent`` drive ``cycle_placement_variant``."""

    def test_right_arrow_flips_and_accepts(self, scene):
        scene.set_mode("draw_arc")
        assert scene._arc_variant == _ARC_VARIANT_CENTER
        ev = _arrow(Qt.Key.Key_Right)
        scene.keyPressEvent(ev)
        assert scene._arc_variant == _ARC_VARIANT_START
        assert ev.isAccepted()

    def test_left_arrow_flips_back_and_accepts(self, scene):
        scene.set_mode("draw_arc")
        # Right first → start; Left should wrap back to center.
        scene.keyPressEvent(_arrow(Qt.Key.Key_Right))
        assert scene._arc_variant == _ARC_VARIANT_START
        ev = _arrow(Qt.Key.Key_Left)
        scene.keyPressEvent(ev)
        assert scene._arc_variant == _ARC_VARIANT_CENTER
        assert ev.isAccepted()

    def test_left_arrow_from_center_wraps_to_start(self, scene):
        scene.set_mode("draw_arc")
        ev = _arrow(Qt.Key.Key_Left)
        scene.keyPressEvent(ev)
        assert scene._arc_variant == _ARC_VARIANT_START
        assert ev.isAccepted()

    def test_no_consume_past_step_zero(self, scene):
        scene.set_mode("draw_arc")
        scene._press_draw_arc(None, None, QPointF(0, 0), None, None, None)
        assert scene._draw_arc_step == 1
        before = scene._arc_variant
        ev = _arrow(Qt.Key.Key_Right)
        scene.keyPressEvent(ev)
        assert scene._arc_variant == before
        assert not ev.isAccepted()

    def test_no_consume_in_non_variant_mode(self, scene):
        scene.set_mode("draw_line")
        ev = _arrow(Qt.Key.Key_Right)
        scene.keyPressEvent(ev)
        # Variant machinery untouched; event falls through (not accepted here).
        assert not ev.isAccepted()

    def test_rectangle_right_arrow_flips_and_accepts(self, scene):
        scene.set_mode("draw_rectangle")
        assert scene._draw_rect_from_center is False
        ev = _arrow(Qt.Key.Key_Right)
        scene.keyPressEvent(ev)
        assert scene._draw_rect_from_center is True
        assert ev.isAccepted()


class TestSetModeFocusReturn:
    """Regression: activating a placement tool must return keyboard focus to the
    visible plan view, so ←/→ (dispatched in ``Model_Space.keyPressEvent``) reach
    the scene at step 0.  Without this a ribbon-button click leaves focus on the
    ribbon and the arrows cycle ribbon widgets instead of the placement variant.
    """

    @pytest.fixture
    def shown_view(self, scene):
        from firepro3d.model_view import Model_View
        from PyQt6.QtTest import QTest
        v = Model_View(scene)
        v.resize(400, 300)
        v.show()
        QTest.qWaitForWindowExposed(v)
        v.activateWindow()          # hasFocus() is False unless the window is active
        yield v
        v.close()

    def test_set_mode_returns_focus_to_visible_view(self, qapp, scene, shown_view):
        # Simulate the ribbon holding focus after a tool-button click.
        shown_view.clearFocus()
        qapp.processEvents()
        assert not shown_view.hasFocus()
        scene.set_mode("draw_arc")
        qapp.processEvents()
        assert shown_view.hasFocus(), \
            "set_mode must hand keyboard focus back to the visible plan view"

    def test_arrow_cycles_variant_through_the_view_after_set_mode(self, qapp, scene, shown_view):
        # The whole chain: tool activated → view focused → arrow delivered to the
        # focused view reaches Model_Space.keyPressEvent → variant cycles.
        shown_view.clearFocus()
        scene.set_mode("draw_arc")
        qapp.processEvents()
        assert shown_view.hasFocus()
        QTest.keyClick(shown_view, Qt.Key.Key_Right)
        assert scene._arc_variant == _ARC_VARIANT_START
