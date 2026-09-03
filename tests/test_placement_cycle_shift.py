"""tests/test_placement_cycle_shift.py — Spacebar cycles placement ambiguity.

Spacebar is the single "cycle whatever is ambiguous" key across placement/select
modes: select -> next similar element, pipe -> Z-stacked node candidate, wall ->
alignment, opening -> alignment.  It is gated off while a Dynamic Input HUD field
holds focus (Space types into the field), cycles once per physical press
(autorepeat ignored), and is consumed only when something actually cycled.

The former Left-Shift tap that used to carry these jobs was removed (it tripped
Windows Sticky Keys and stole a pure modifier); Left-Shift is once again just a
modifier.
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


def _space(autorepeat=False):
    """A bare-modifier Space KeyPress. ``autorepeat`` marks an OS key-repeat."""
    return QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space,
                     Qt.KeyboardModifier.NoModifier, 0, 0, 0,
                     " ", autorepeat, 1)


# Windows native codes: left Shift = scan 0x2A (42) / VK_LSHIFT 0xA0.
def _lshift(kind):
    mods = (Qt.KeyboardModifier.ShiftModifier if kind is QEvent.Type.KeyPress
            else Qt.KeyboardModifier.NoModifier)
    return QKeyEvent(kind, Qt.Key.Key_Shift, mods, 42, 0xA0, 0, "", False, 1)


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
    """The pure cycler, independent of the key that triggers it (now incl. wall)."""

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


class TestSpacebarDrivesCycle:
    """Space, through the real shown/focused view, drives the cycle."""

    def test_space_cycles_wall_alignment_through_view(self, scene, view):
        scene.set_mode("wall")
        scene._wall_alignment = "Center"
        view.setFocus()
        QApplication.sendEvent(view, _space())
        assert scene._wall_alignment == "Left"

    def test_space_direct_cycles_similar_selection(self, scene):
        scene.set_mode("select")
        g1 = GridlineItem(QPointF(0, 0), QPointF(100, 0), label="1")
        g2 = GridlineItem(QPointF(0, 50), QPointF(100, 50), label="2")
        for g in (g1, g2):
            scene.addItem(g); scene._gridlines.append(g)
        g1.setSelected(True)
        scene.keyPressEvent(_space())
        assert g2.isSelected() and not g1.isSelected()


class TestSpaceGatedByInputMode:
    """A Space that lands while a HUD field holds focus must not cycle."""

    def test_space_does_not_cycle_while_wall_hud_engaged(self, scene, view):
        # Wall is a HUD applier and its line-primitive anchor is _wall_anchor,
        # so an armed wall placement can open + engage a real DynamicInputHud.
        scene.set_mode("wall")
        scene._wall_primitive = "line"
        scene._wall_alignment = "Center"
        scene._wall_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(1000, 0))
        assert scene.begin_dynamic_input(seed="1") is True
        assert scene.is_input_mode() is True
        scene.keyPressEvent(_space())
        assert scene._wall_alignment == "Center"     # gated: no cycle
        assert scene.is_input_mode() is True          # HUD still engaged


class TestAutorepeatIgnored:
    """Holding Space (OS autorepeat) cycles at most once, not continuously."""

    def test_autorepeat_space_does_not_cycle(self, scene):
        scene.set_mode("wall")
        scene._wall_alignment = "Center"
        scene.keyPressEvent(_space(autorepeat=True))
        assert scene._wall_alignment == "Center"


class TestLeftShiftNoLongerCycles:
    """The Left-Shift tap is gone; Shift stays a pure modifier."""

    def test_left_shift_tap_cycles_nothing(self, scene):
        scene.set_mode("wall")
        scene._wall_alignment = "Center"
        scene.keyPressEvent(_lshift(QEvent.Type.KeyPress))
        scene.keyReleaseEvent(_lshift(QEvent.Type.KeyRelease))
        assert scene._wall_alignment == "Center"

    def test_shift_click_still_multiselects(self, scene, view):
        # Two selectable gridlines; Shift+click the second adds it to the
        # selection instead of replacing (Left-Shift-as-modifier preserved).
        g1 = GridlineItem(QPointF(0, 0), QPointF(1000, 0), label="1")
        g2 = GridlineItem(QPointF(0, 500), QPointF(1000, 500), label="2")
        for g in (g1, g2):
            scene.addItem(g); scene._gridlines.append(g)
        g1.setSelected(True)
        vp = view.viewport()
        view_pt = view.mapFromScene(QPointF(500, 500))
        gp = vp.mapToGlobal(view_pt)
        for et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            QApplication.sendEvent(vp, QMouseEvent(
                et, QPointF(view_pt), QPointF(gp),
                Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.ShiftModifier))
        QApplication.processEvents()
        assert g1.isSelected() and g2.isSelected()


class TestNoCycleFallsThrough:
    """Space with nothing to cycle leaves state alone and is not consumed."""

    def test_space_in_empty_select_is_noop(self, scene):
        scene.set_mode("select")   # nothing selected -> nothing to cycle
        ev = _space()
        scene.keyPressEvent(ev)
        assert ev.isAccepted() is False
