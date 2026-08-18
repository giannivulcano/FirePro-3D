"""tests/test_dynamic_input_multiview.py — HUD view selection with >1 view.

The bare harness used by the other dynamic-input modules attaches exactly one
view to the scene, which makes ``views()[0]`` trivially correct.  The real app
attaches **two**: a vestigial ``MainWindow.view`` that is never parented into
the tab widget and never shown, and the plan view the user actually works in.
Indexing ``views()[0]`` therefore parented the HUD into an invisible widget
tree — the HUD was built and shown but no ancestor was visible, while
``is_input_mode()`` latched True and made the cursor inert.

These tests pin the invariant from both ends: the HUD lands on the *visible*
view, and a HUD that cannot become visible never latches input mode.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest

from firepro3d import snap_engine
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import, required before MainWindow()
_main_module.View3D = View3D
from main import MainWindow


def _armed_line(scene, anchor=QPointF(0, 0), resolved=QPointF(1000, 0)):
    """Arm ``draw_line`` with *anchor* and publish *resolved*.

    Mirrors the state a first click plus one mouse-move leaves behind, which
    is the only state a placement schema may engage from.
    """
    scene.set_mode("draw_line")
    scene._draw_line_anchor = QPointF(anchor)
    scene.publish_placement_state(anchor, resolved)


# ─────────────────────────────────────────────────────────────────────────────
# Bare two-view scene
# ─────────────────────────────────────────────────────────────────────────────

class TestTwoViewScene:
    """A scene with a hidden view at index 0 and a shown view at index 1."""

    @pytest.fixture
    def two_views(self, qapp):
        """Reproduce the app's shape: hidden orphan first, visible view second.

        Order matters — the hidden view is created first precisely because
        that is the index ``views()[0]`` would have picked.
        """
        scene = Model_Space()
        hidden = Model_View(scene)          # the vestigial MainWindow.view
        hidden.resize(800, 600)
        hidden.resetTransform()

        shown = Model_View(scene)           # the plan view the user works in
        shown.resize(800, 600)
        shown.resetTransform()
        shown.show()
        QTest.qWaitForWindowExposed(shown)

        yield scene, hidden, shown

        scene.end_dynamic_input()
        shown.close()
        hidden.close()

    def test_hud_parents_to_the_visible_view(self, two_views):
        scene, hidden, shown = two_views
        _armed_line(scene)

        assert scene.begin_dynamic_input() is True
        hud = scene.dynamic_input
        assert hud is not None
        assert hud.parent() is shown.viewport()
        assert hud.parent() is not hidden.viewport()

    def test_hud_is_actually_visible(self, two_views):
        """The whole point: ``show()`` ran *and* an ancestor chain carries it."""
        scene, hidden, shown = two_views
        _armed_line(scene)
        scene.begin_dynamic_input()

        hud = scene.dynamic_input
        assert hud.isVisible() is True
        w = hud.parentWidget()
        while w is not None:
            assert w.isVisible() is True, f"invisible ancestor: {w}"
            w = w.parentWidget()

    def test_typed_engage_also_lands_on_the_visible_view(self, two_views):
        """The digit path shares ``begin_dynamic_input``; prove it end to end."""
        scene, hidden, shown = two_views
        _armed_line(scene)
        QTest.keyClick(shown, Qt.Key.Key_5)

        hud = scene.dynamic_input
        assert hud is not None
        assert hud.parent() is shown.viewport()
        assert hud.isVisible() is True

    def test_no_visible_view_refuses_the_engage(self, qapp):
        """A scene whose only views are hidden must not latch input mode.

        Without this, ``is_input_mode()`` would be True with no reachable HUD:
        the cursor goes inert, clicks stop committing and Escape is the only
        way out.
        """
        scene = Model_Space()
        hidden = Model_View(scene)
        hidden.resize(800, 600)
        hidden.resetTransform()
        _armed_line(scene)

        assert scene.begin_dynamic_input() is False
        assert scene.dynamic_input is None
        assert scene.is_input_mode() is False
        hidden.close()

    def test_end_restores_focus_to_the_visible_view(self, two_views):
        """Tear-down must not hand focus to the invisible orphan."""
        scene, hidden, shown = two_views
        _armed_line(scene)
        scene.begin_dynamic_input()
        scene.end_dynamic_input()

        assert not scene.is_input_mode()
        assert hidden.hasFocus() is False


# ─────────────────────────────────────────────────────────────────────────────
# Real MainWindow
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def _main_window_singleton(qapp):
    """Module-scoped MainWindow, shared for speed.

    Save/restore SNAP_TOLERANCE_PX: MainWindow overwrites the module-level
    constant from QSettings and would leak that value into other test modules.
    """
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    win = MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    win._modified = False
    win.close()
    win.deleteLater()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


@pytest.fixture
def main_window(_main_window_singleton):
    """Per-test view of the shared MainWindow, left in cursor mode."""
    win = _main_window_singleton
    win.scene.end_dynamic_input()
    yield win
    win.scene.end_dynamic_input()
    win.scene.set_mode("select")


def _active_plan_view(win):
    """Return the plan ``Model_View`` currently shown in the central tabs."""
    for i in range(win.central_tabs.count()):
        if win.central_tabs.tabText(i).startswith("Plan: "):
            win.central_tabs.setCurrentIndex(i)
            return win.central_tabs.widget(i)
    return None


class TestRealMainWindow:
    """The configuration that actually shipped the bug: two attached views."""

    def test_scene_really_has_more_than_one_view(self, main_window):
        """Guard the premise — if this ever drops to one, the rest is vacuous."""
        assert len(main_window.scene.views()) > 1

    def test_hud_is_visible_under_a_real_main_window(self, main_window):
        win = main_window
        plan_view = _active_plan_view(win)
        assert plan_view is not None
        QTest.qWait(10)

        _armed_line(win.scene)
        assert win.scene.begin_dynamic_input() is True

        hud = win.scene.dynamic_input
        assert hud.isVisible() is True
        w = hud.parentWidget()
        while w is not None:
            assert w.isVisible() is True, f"invisible ancestor: {w}"
            w = w.parentWidget()

    def test_hud_parents_to_the_active_plan_view(self, main_window):
        """Not merely *some* view — the plan view the user is looking at."""
        win = main_window
        plan_view = _active_plan_view(win)
        QTest.qWait(10)

        _armed_line(win.scene)
        win.scene.begin_dynamic_input()

        hud = win.scene.dynamic_input
        assert hud.parent() is plan_view.viewport()
        assert hud.parent() is not win.view.viewport()

    def test_tab_engages_and_a_second_tab_is_not_soft_locked(self, main_window):
        """The user-visible symptom: engage, cancel, engage again.

        With the HUD stranded in an invisible tree the first Tab latched input
        mode and the placement was soft-locked — no HUD, no preview, no commit.
        """
        win = main_window
        plan_view = _active_plan_view(win)
        plan_view.setFocus()
        QTest.qWait(10)

        _armed_line(win.scene)
        QTest.keyClick(plan_view, Qt.Key.Key_Tab)
        assert win.scene.is_input_mode() is True
        assert win.scene.dynamic_input.isVisible() is True

        win.scene.end_dynamic_input()
        assert win.scene.is_input_mode() is False

        _armed_line(win.scene)
        QTest.keyClick(plan_view, Qt.Key.Key_Tab)
        assert win.scene.is_input_mode() is True
        assert win.scene.dynamic_input.isVisible() is True


class TestTabSwitchCancelsPlacement:
    """A placement belongs to the view it was started in.

    Every plan tab is a ``Model_View`` over the *same* ``Model_Space``, so the
    preview ``QGraphicsItem``s render in all of them by definition, while the
    committed geometry is level-filtered and appears in only one.  Switching
    tabs mid-placement therefore showed a ghost in a plan that could never
    receive the line.  It also stranded the HUD on a now-hidden view — the
    same invisible-HUD soft-lock 62996eb fixed, reached by a different door.
    """

    def test_switching_tabs_closes_the_hud(self, main_window):
        win = main_window
        plan_idx = win.central_tabs.currentIndex()
        for i in range(win.central_tabs.count()):
            if win.central_tabs.tabText(i).startswith("Plan: "):
                plan_idx = i
                break
        win.central_tabs.setCurrentIndex(plan_idx)
        _armed_line(win.scene)
        assert win.scene.begin_dynamic_input() is True

        other = next(i for i in range(win.central_tabs.count())
                     if i != plan_idx)
        win.central_tabs.setCurrentIndex(other)   # real signal wiring
        QTest.qWait(20)

        assert win.scene.is_input_mode() is False
        assert win.scene.dynamic_input is None

    def test_switching_tabs_clears_the_placement_anchor(self, main_window):
        """No anchor means no ghost — the preview cannot outlive the switch."""
        win = main_window
        plan_idx = next(i for i in range(win.central_tabs.count())
                        if win.central_tabs.tabText(i).startswith("Plan: "))
        win.central_tabs.setCurrentIndex(plan_idx)
        _armed_line(win.scene)
        assert win.scene.get_placement_anchor() is not None

        other = next(i for i in range(win.central_tabs.count())
                     if i != plan_idx)
        win.central_tabs.setCurrentIndex(other)
        QTest.qWait(20)

        assert win.scene.get_placement_anchor() is None
        assert win.scene.get_resolved_point() is None
