"""tests/test_placement_cycle_shift.py — Left-Shift tap cycles placement ambiguity.

Tab now engages the Dynamic Input HUD in every mode, so the three cycling jobs
it used to own — cycle similar selection, cycle pipe Z-candidates, cycle wall
alignment — move to a **Left-Shift tap**: a clean press/release of the left
Shift key with no click or other key in between.  Holding Shift as a modifier
(Shift+click to multi-select, Shift+drag to constrain) must never cycle, which
is why the cycle fires on *release* only when the tap stayed clean.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.gridline import GridlineItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View


# Windows native codes: left Shift = scan 0x2A (42) / VK_LSHIFT 0xA0;
# right Shift = scan 0x36 (54) / VK_RSHIFT 0xA1.
def _lshift(kind):
    mods = (Qt.KeyboardModifier.ShiftModifier if kind is QEvent.Type.KeyPress
            else Qt.KeyboardModifier.NoModifier)
    return QKeyEvent(kind, Qt.Key.Key_Shift, mods, 42, 0xA0, 0, "", False, 1)


def _rshift(kind):
    mods = (Qt.KeyboardModifier.ShiftModifier if kind is QEvent.Type.KeyPress
            else Qt.KeyboardModifier.NoModifier)
    return QKeyEvent(kind, Qt.Key.Key_Shift, mods, 54, 0xA1, 0, "", False, 1)


def _key(text):
    return QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A,
                     Qt.KeyboardModifier.NoModifier, text)


def _tap(scene):
    scene.keyPressEvent(_lshift(QEvent.Type.KeyPress))
    scene.keyReleaseEvent(_lshift(QEvent.Type.KeyRelease))


@pytest.fixture
def scene(qapp):
    return Model_Space()


@pytest.fixture
def view(scene):
    v = Model_View(scene); v.resize(800, 600); v.resetTransform()
    v.centerOn(0, 0); v.show()
    QTest.qWaitForWindowExposed(v)
    yield v
    v.close()


class TestCyclePlacementAmbiguity:
    """The pure cycler, independent of the key that triggers it."""

    def test_wall_mode_cycles_alignment(self, scene):
        scene.set_mode("wall")
        scene._wall_alignment = "Center"
        assert scene.cycle_placement_ambiguity() is True
        assert scene._wall_alignment == "Left"
        scene.cycle_placement_ambiguity()
        assert scene._wall_alignment == "Right"
        scene.cycle_placement_ambiguity()
        assert scene._wall_alignment == "Center"

    def test_pipe_mode_cycles_candidates(self, scene):
        # Candidates need a z_pos: _emit_pipe_tab_readout formats their elevation.
        cand = [type("N", (), {"z_pos": float(i)})() for i in range(3)]
        scene.set_mode("pipe")
        scene._pipe_ctl._tab_candidates = cand
        scene._pipe_ctl._tab_index = 0
        assert scene.cycle_placement_ambiguity() is True
        assert scene._pipe_ctl._tab_index == 1

    def test_pipe_mode_no_cycle_with_one_candidate(self, scene):
        scene.set_mode("pipe")
        scene._pipe_ctl._tab_candidates = [type("N", (), {"z_pos": 0.0})()]
        assert scene.cycle_placement_ambiguity() is False

    def test_select_mode_cycles_similar(self, scene):
        scene.set_mode("select")
        g1 = GridlineItem(QPointF(0, 0), QPointF(100, 0), label="1")
        g2 = GridlineItem(QPointF(0, 50), QPointF(100, 50), label="2")
        for g in (g1, g2):
            scene.addItem(g); scene._gridlines.append(g)
        g1.setSelected(True)
        assert scene.cycle_placement_ambiguity() is True
        assert g2.isSelected() and not g1.isSelected()

    def test_plain_drawing_mode_returns_false(self, scene):
        scene.set_mode("draw_line")
        assert scene.cycle_placement_ambiguity() is False


class TestLeftShiftTap:
    """A clean Left-Shift tap fires the cycle on release."""

    def test_tap_cycles_wall_alignment(self, scene):
        scene.set_mode("wall")
        scene._wall_alignment = "Center"
        _tap(scene)
        assert scene._wall_alignment == "Left"

    def test_two_taps_advance_twice(self, scene):
        scene.set_mode("wall")
        scene._wall_alignment = "Center"
        _tap(scene)
        _tap(scene)
        assert scene._wall_alignment == "Right"

    def test_release_without_press_does_nothing(self, scene):
        scene.set_mode("wall")
        scene._wall_alignment = "Center"
        scene.keyReleaseEvent(_lshift(QEvent.Type.KeyRelease))
        assert scene._wall_alignment == "Center"


class TestTapIsBrokenByModifierUse:
    """Holding Shift as a modifier must never cycle."""

    def test_a_key_between_press_and_release_breaks_the_tap(self, scene):
        scene.set_mode("wall")
        scene._wall_alignment = "Center"
        scene.keyPressEvent(_lshift(QEvent.Type.KeyPress))
        scene.keyPressEvent(_key("a"))          # another key → not a tap
        scene.keyReleaseEvent(_lshift(QEvent.Type.KeyRelease))
        assert scene._wall_alignment == "Center"

    def test_a_click_between_press_and_release_breaks_the_tap(self, scene, view):
        """Shift+click (multi-select) must not cycle."""
        scene.set_mode("wall")
        scene._wall_alignment = "Center"
        scene.keyPressEvent(_lshift(QEvent.Type.KeyPress))
        # A real click through the view reaches Model_Space.mousePressEvent.
        vp = view.viewport()
        view_pt = view.mapFromScene(QPointF(0, 0))
        gp = vp.mapToGlobal(view_pt)
        for et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            QApplication.sendEvent(vp, QMouseEvent(
                et, QPointF(view_pt), QPointF(gp),
                Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.ShiftModifier))
        QApplication.processEvents()
        scene.keyReleaseEvent(_lshift(QEvent.Type.KeyRelease))
        assert scene._wall_alignment == "Center"

    def test_right_shift_never_cycles(self, scene):
        scene.set_mode("wall")
        scene._wall_alignment = "Center"
        scene.keyPressEvent(_rshift(QEvent.Type.KeyPress))
        scene.keyReleaseEvent(_rshift(QEvent.Type.KeyRelease))
        assert scene._wall_alignment == "Center"


class TestTapDoesNotEngageInput:

    def test_tap_leaves_input_mode_alone(self, scene, view):
        scene.set_mode("draw_line")
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(100, 0))
        _tap(scene)
        assert not scene.is_input_mode()
        assert scene.dynamic_input is None
