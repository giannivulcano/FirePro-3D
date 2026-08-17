"""tests/test_dynamic_input_parity.py — mouse vs HUD produce identical geometry.

Covers ``Model_Space._commit_draw_line_at``, the point-taking commit extracted
from ``_press_draw_line`` so that Dynamic Input and the mouse click share one
line-building path instead of two.
"""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt, QTimer
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QGraphicsView

from firepro3d.model_space import Model_Space


@pytest.fixture
def scene(qapp):
    return Model_Space()


class TestCommitDrawLineAt:

    def test_creates_line_item(self, scene):
        scene.set_mode("draw_line")
        scene._draw_line_anchor = QPointF(0, 0)
        before = len(scene._draw_lines)
        scene._commit_draw_line_at(QPointF(100, 0))
        assert len(scene._draw_lines) == before + 1
        item = scene._draw_lines[-1]
        assert item.line().p1() == QPointF(0, 0)
        assert item.line().p2() == QPointF(100, 0)

    def test_clears_anchor_after_commit(self, scene):
        scene.set_mode("draw_line")
        scene._draw_line_anchor = QPointF(0, 0)
        scene._commit_draw_line_at(QPointF(100, 0))
        assert scene._draw_line_anchor is None

    def test_rejects_zero_length(self, scene):
        scene.set_mode("draw_line")
        scene._draw_line_anchor = QPointF(0, 0)
        before = len(scene._draw_lines)
        scene._commit_draw_line_at(QPointF(0.1, 0))
        # nothing created, anchor still armed
        assert len(scene._draw_lines) == before
        assert scene._draw_line_anchor == QPointF(0, 0)

    def test_no_anchor_is_a_noop(self, scene):
        scene.set_mode("draw_line")
        scene._draw_line_anchor = None
        before = len(scene._draw_lines)
        scene._commit_draw_line_at(QPointF(100, 0))
        assert len(scene._draw_lines) == before

    def test_gridline_mode_creates_gridline(self, scene):
        scene.set_mode("draw_gridline")
        scene._draw_line_anchor = QPointF(0, 0)
        before = len(scene._gridlines)
        scene._commit_draw_line_at(QPointF(1000, 0))
        assert len(scene._gridlines) == before + 1
        assert len(scene._draw_lines) == 0
        assert scene._draw_line_anchor is None

    def test_clears_published_placement_state(self, scene):
        scene.set_mode("draw_line")
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(100, 0))
        assert scene.get_resolved_point() is not None
        scene._commit_draw_line_at(QPointF(100, 0))
        assert scene.get_resolved_point() is None

    def test_single_place_mode_exits_to_select(self, scene):
        scene.set_mode("draw_line")
        scene.single_place_mode = True
        scene._draw_line_anchor = QPointF(0, 0)
        scene._commit_draw_line_at(QPointF(100, 0))
        assert scene.mode == "select"

    def test_repeat_mode_rearms(self, scene):
        scene.set_mode("draw_line")
        scene.single_place_mode = False
        scene._draw_line_anchor = QPointF(0, 0)
        scene._commit_draw_line_at(QPointF(100, 0))
        assert scene.mode == "draw_line"

    def test_repeat_mode_emits_start_instruction(self, scene):
        scene.set_mode("draw_line")
        scene.single_place_mode = False
        seen = []
        scene.instructionChanged.connect(seen.append)
        scene._draw_line_anchor = QPointF(0, 0)
        scene._commit_draw_line_at(QPointF(100, 0))
        assert seen[-1] == "Pick first point"

    def test_gridline_repeat_mode_emits_gridline_wording(self, scene):
        scene.set_mode("draw_gridline")
        scene.single_place_mode = False
        seen = []
        scene.instructionChanged.connect(seen.append)
        scene._draw_line_anchor = QPointF(0, 0)
        scene._commit_draw_line_at(QPointF(1000, 0))
        assert seen[-1] == "Pick start point"


def _drive_dyninput(length_text, angle_text="0"):
    """Fill the live modal ``_DynInput`` and accept it.

    Scheduled via ``QTimer.singleShot`` so it runs inside the dialog's own
    modal ``exec()`` loop. We deliberately do NOT monkeypatch ``QDialog.exec``:
    reassigning a sip method at class level corrupts its C++ slot binding for
    the rest of the process. Driving the live dialog avoids that entirely.

    Args:
        length_text: Text to type into the first (Length) field.
        angle_text: Text to type into the second (Angle) field.
    """
    w = QApplication.activeModalWidget() or QApplication.activePopupWidget()
    if w is None:
        for tw in QApplication.topLevelWidgets():
            if hasattr(tw, "_order") and tw.isVisible():
                w = tw
                break
    if w is None or not hasattr(w, "_order"):
        return
    w._order[0].setText(length_text)
    if len(w._order) > 1:
        w._order[1].setText(angle_text)
    w.accept()


class TestModalTypedCommitDelegates:
    """The modal ``_DynInput`` line path delegates to ``_commit_draw_line_at``.

    Before this fix the modal built the line itself and skipped the too-short
    guard, so a typed zero length created a degenerate line that the mouse
    click path refuses.
    """

    def test_typed_zero_length_is_rejected(self, scene):
        view = QGraphicsView(scene)
        view.resize(400, 400)
        view.resetTransform()
        scene.set_mode("draw_line")
        scene._draw_line_anchor = QPointF(0, 0)
        before = len(scene._draw_lines)

        QTimer.singleShot(0, lambda: _drive_dyninput("0"))
        scene._handle_tab_input()
        view.hide()

        # No degenerate line, and the anchor stays armed for a re-pick.
        assert len(scene._draw_lines) == before
        assert scene._draw_line_anchor == QPointF(0, 0)

    def test_typed_real_length_still_commits(self, scene):
        """Guard the other direction: a valid typed length must still build."""
        view = QGraphicsView(scene)
        view.resize(400, 400)
        view.resetTransform()
        scene.set_mode("draw_line")
        scene._draw_line_anchor = QPointF(0, 0)
        before = len(scene._draw_lines)

        QTimer.singleShot(0, lambda: _drive_dyninput("1000", "0"))
        scene._handle_tab_input()
        view.hide()

        assert len(scene._draw_lines) == before + 1
        item = scene._draw_lines[-1]
        assert item.line().p1() == QPointF(0, 0)
        assert item.line().p2().x() == pytest.approx(1000.0, abs=1.0)
        assert item.line().p2().y() == pytest.approx(0.0, abs=1.0)
        # Delegation side effects the old inline path lacked.
        assert scene._draw_line_anchor is None
        assert scene.get_resolved_point() is None

    def test_typed_commit_clears_placement_state(self, scene):
        view = QGraphicsView(scene)
        view.resize(400, 400)
        view.resetTransform()
        scene.set_mode("draw_line")
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(100, 0))
        assert scene.get_resolved_point() is not None

        QTimer.singleShot(0, lambda: _drive_dyninput("1000", "0"))
        scene._handle_tab_input()
        view.hide()

        assert scene.get_resolved_point() is None


def _click(scene, view, scene_pt, ctrl=False):
    """Send a left press at ``scene_pt`` through ``_press_draw_line``."""
    mods = (Qt.KeyboardModifier.ControlModifier if ctrl
            else Qt.KeyboardModifier.NoModifier)
    vp = view.mapFromScene(scene_pt)
    ev = QMouseEvent(QEvent.Type.GraphicsSceneMousePress,
                     QPointF(vp),
                     Qt.MouseButton.LeftButton,
                     Qt.MouseButton.LeftButton,
                     mods)
    scene._press_draw_line(ev, scene_pt, scene_pt, None, None, None)


class TestCtrlConstraintStaysInPicker:
    """Ctrl angle-constraint lives in ``_press_draw_line``, not the commit.

    ``_commit_draw_line_at`` trusts ``tip`` to arrive pre-constrained, so the
    picker must apply it. These two tests fail in opposite directions: one if
    Ctrl stops constraining, one if the constraint leaks into the un-Ctrl'd
    path.
    """

    def _run(self, scene, ctrl):
        view = QGraphicsView(scene)
        view.resize(400, 400)
        view.resetTransform()
        scene.set_mode("draw_line")
        scene.single_place_mode = False
        anchor = QPointF(0, 0)
        raw = QPointF(1000, 300)     # ~16.7° — off any 15°/45° snap increment
        _click(scene, view, anchor)
        _click(scene, view, raw, ctrl=ctrl)
        view.hide()
        assert scene._draw_lines, "no line was created"
        return scene._draw_lines[-1].line().p2(), anchor, raw

    def test_ctrl_click_snaps_to_constrained_angle(self, scene):
        tip, anchor, raw = self._run(scene, ctrl=True)
        expected = scene._constrain_angle(anchor, raw)
        assert tip.x() == pytest.approx(expected.x(), abs=1e-6)
        assert tip.y() == pytest.approx(expected.y(), abs=1e-6)

    def test_plain_click_is_not_snapped(self, scene):
        tip, anchor, raw = self._run(scene, ctrl=False)
        constrained = scene._constrain_angle(anchor, raw)
        # Lands on the raw point ...
        assert tip.x() == pytest.approx(raw.x(), abs=1e-6)
        assert tip.y() == pytest.approx(raw.y(), abs=1e-6)
        # ... and the constraint genuinely would have moved it, so this test
        # is not vacuously green.
        assert math.hypot(constrained.x() - raw.x(),
                          constrained.y() - raw.y()) > 1.0
