"""tests/test_dynamic_input_lifecycle.py — one HUD for the whole placement.

Decision S1: the ``DynamicInputHud`` widget is not opened by the engage key and
closed by Enter.  It is built as soon as a placement anchor is armed, spends
most of its life as a passive read-only readout following the cursor, is
*engaged* into an editor by Tab or a typed digit, and is closed when the
placement ends.

The distinction these tests exist to protect is that ``is_input_mode()`` means
**a field has focus**, not **a HUD exists**.  Everything that makes the canvas
inert — the mouse guards in ``Model_Space``, the click-focus recovery in
``Model_View.mousePressEvent``, the publish no-op — hangs off it, so a HUD that
is merely on screen must leave all of them alone.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLineEdit

from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View

_TRANSPARENT = Qt.WidgetAttribute.WA_TransparentForMouseEvents


@pytest.fixture
def scene(qapp):
    return Model_Space()


@pytest.fixture
def view(scene):
    """A real, **shown** view — the HUD is parented to the first visible one."""
    v = Model_View(scene)
    v.resize(800, 600)
    v.resetTransform()
    v.show()
    QTest.qWaitForWindowExposed(v)
    yield v
    v.close()


class _MoveEventStub:
    """Stand-in for the mouse-move event; PyQt6 will not build a real one."""

    def __init__(self, modifiers=Qt.KeyboardModifier.NoModifier):
        self._modifiers = modifiers

    def modifiers(self):
        return self._modifiers


def _drag_to(scene, point, anchor=QPointF(0, 0)):
    """Arm ``draw_line`` at *anchor* and take the cursor to *point*.

    Mirrors ``mouseMoveEvent``'s own order — mode handler publishes, then the
    sync reflects it — because a ``QGraphicsSceneMouseEvent`` cannot be
    instantiated under PyQt6 and so the real handler cannot be driven whole.
    """
    scene.mode = "draw_line"
    if scene._draw_line_anchor is None:
        scene._draw_line_anchor = QPointF(anchor)
    scene._move_draw_line(_MoveEventStub(), point)
    scene._sync_dynamic_input()
    return scene.dynamic_input


def _press_at(view, scene_pt):
    """Send a real left-button press through the view at *scene_pt*."""
    vp = view.mapFromScene(scene_pt)
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(vp),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(view.viewport(), ev)


class TestReadoutLifecycle:

    def test_no_hud_before_an_anchor_is_armed(self, scene, view):
        scene.mode = "draw_line"
        scene._move_draw_line(_MoveEventStub(), QPointF(500, 0))
        scene._sync_dynamic_input()
        assert scene.dynamic_input is None

    def test_hud_appears_once_the_anchor_is_armed(self, scene, view):
        hud = _drag_to(scene, QPointF(1000, 0))
        assert hud is not None
        assert hud.isVisible()

    def test_readout_hud_is_not_input_mode(self, scene, view):
        """The whole point of S1: existing is not the same as being engaged."""
        _drag_to(scene, QPointF(1000, 0))
        assert scene.dynamic_input is not None
        assert not scene.is_input_mode()

    def test_readout_shows_the_live_geometry(self, scene, view):
        hud = _drag_to(scene, QPointF(1000, 0))
        assert hud.editor("Length").text() == "1000.000 mm"
        assert hud.editor("Angle").text() == "0°"

    def test_readout_follows_the_cursor(self, scene, view):
        """Reseeded every frame while unengaged — it is the live readout now."""
        hud = _drag_to(scene, QPointF(1000, 0))
        first = hud.editor("Length").text()
        _drag_to(scene, QPointF(0, -2000))
        assert hud.editor("Length").text() != first
        assert hud.editor("Length").text() == "2000.000 mm"
        assert hud.editor("Angle").text() == "90°"

    def test_readout_closes_when_the_anchor_goes_away(self, scene, view):
        _drag_to(scene, QPointF(1000, 0))
        scene._draw_line_anchor = None
        scene._sync_dynamic_input()
        assert scene.dynamic_input is None

    def test_readout_closes_on_mode_switch(self, scene, view):
        _drag_to(scene, QPointF(1000, 0))
        scene.set_mode("select")
        assert scene.dynamic_input is None

    def test_a_mode_without_an_applier_gets_no_hud(self, scene, view):
        """``draw_rectangle`` has a schema but no applier yet — no HUD."""
        scene.mode = "draw_rectangle"
        scene._draw_rect_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(100, 100))
        scene._sync_dynamic_input()
        assert scene.dynamic_input is None


class TestReadoutLeavesTheCanvasAlone:
    """A HUD that only reads out must change nothing about cursor mode."""

    def test_readout_is_transparent_to_the_mouse(self, scene, view):
        hud = _drag_to(scene, QPointF(1000, 0))
        assert hud.testAttribute(_TRANSPARENT)

    def test_readout_children_are_transparent_too(self, scene, view):
        """The attribute does not inherit, so every child needs it set.

        Without this the labels and editors keep swallowing clicks even though
        the container ignores them — and the editor is the widest child, so it
        is exactly what would sit under the cursor.
        """
        hud = _drag_to(scene, QPointF(1000, 0))
        children = hud.findChildren(QLineEdit)
        assert children
        assert all(c.testAttribute(_TRANSPARENT) for c in children)

    def test_a_click_still_commits_while_the_readout_is_up(self, scene, view):
        """End to end: the readout must not intercept the finishing click.

        Driven through the real view press handler, which is where the
        click-focus recovery guard lives — that guard used to fire whenever a
        HUD existed, which under S1 would swallow every second click of every
        line the user draws.
        """
        _drag_to(scene, QPointF(1000, 0))
        assert len(scene._draw_lines) == 0

        _press_at(view, QPointF(1000, 0))

        assert len(scene._draw_lines) == 1
        assert scene._draw_line_anchor is None

    def test_committing_click_takes_the_readout_with_it(self, scene, view):
        _drag_to(scene, QPointF(1000, 0))
        _press_at(view, QPointF(1000, 0))
        assert scene.dynamic_input is None


class TestEngagingAnExistingReadout:

    def test_tab_engages_the_hud_that_is_already_up(self, scene, view):
        """Engage moves the keyboard into the readout; it does not rebuild it.

        Rebuilding would throw away the very numbers the user is looking at and
        reseed from scratch, which is how the seed and the screen drift apart.
        """
        hud = _drag_to(scene, QPointF(1000, 0))
        assert scene.begin_dynamic_input() is True
        assert scene.dynamic_input is hud
        assert scene.is_input_mode()

    def test_engaged_hud_accepts_the_mouse_again(self, scene, view):
        hud = _drag_to(scene, QPointF(1000, 0))
        scene.begin_dynamic_input()
        assert not hud.testAttribute(_TRANSPARENT)
        assert all(not c.testAttribute(_TRANSPARENT)
                   for c in hud.findChildren(QLineEdit))

    def test_typed_digit_engages_and_lands_in_the_first_field(
            self, scene, view):
        from PyQt6.QtGui import QKeyEvent

        hud = _drag_to(scene, QPointF(1000, 0))
        scene.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_7,
                                      Qt.KeyboardModifier.NoModifier, "7"))
        assert scene.is_input_mode()
        assert scene.dynamic_input is hud
        assert hud.editor("Length").text() == "7"

    def test_engaging_freezes_the_readout(self, scene, view):
        """The sync must not reseed under a value the user is typing."""
        hud = _drag_to(scene, QPointF(1000, 0))
        scene.begin_dynamic_input()
        hud.editor("Length").setText("4321")

        scene._sync_dynamic_input()

        assert hud.editor("Length").text() == "4321"

    def test_engage_before_any_mouse_move_still_works(self, scene, view):
        """Tab straight after the first click, pointer never moved.

        No sync has run, so there is no HUD to engage — the create path has to
        survive for this case or Tab would silently do nothing.
        """
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(0, 0)
        assert scene.dynamic_input is None

        assert scene.begin_dynamic_input() is True
        assert scene.is_input_mode()

    def test_engage_is_refused_with_no_anchor(self, scene, view):
        scene.mode = "draw_line"
        scene._draw_line_anchor = None
        assert scene.begin_dynamic_input() is False
        assert scene.dynamic_input is None


class TestEscapeDemotesRatherThanCloses:

    def test_escape_returns_to_the_readout(self, scene, view):
        hud = _drag_to(scene, QPointF(1000, 0))
        scene.begin_dynamic_input()
        scene.dynamic_input.cancelled.emit()

        assert scene.dynamic_input is hud
        assert not scene.is_input_mode()
        assert hud.testAttribute(_TRANSPARENT)

    def test_the_readout_tracks_the_cursor_again_after_escape(
            self, scene, view):
        hud = _drag_to(scene, QPointF(1000, 0))
        scene.begin_dynamic_input()
        scene.dynamic_input.cancelled.emit()

        _drag_to(scene, QPointF(0, -3000))

        assert scene.dynamic_input is hud
        assert hud.editor("Length").text() == "3000.000 mm"


class TestOriginIsNotFalsy:
    """A resolved point of exactly (0, 0) is a point, not a missing one.

    PyQt gives ``QPointF`` a ``__bool__`` that is False at the origin, so the
    seed's ``point or anchor`` fallback discarded it — and osnapping to the
    origin is ordinary in CAD.
    """

    def test_readout_survives_the_cursor_crossing_the_origin(self, scene, view):
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(-1000, 0)
        scene.publish_placement_state(QPointF(-1000, 0), QPointF(0, 0))
        scene._sync_dynamic_input()
        assert scene.dynamic_input.editor("Length").text() == "1000.000 mm"

    def test_engaging_at_the_origin_seeds_the_real_length(self, scene, view):
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(-1000, 0)
        scene.publish_placement_state(QPointF(-1000, 0), QPointF(0, 0))
        assert scene.begin_dynamic_input() is True
        assert scene.dynamic_input.values()["Length"] == pytest.approx(1000.0)
