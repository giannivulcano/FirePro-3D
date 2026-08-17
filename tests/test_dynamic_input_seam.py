"""tests/test_dynamic_input_seam.py — the ``Model_Space`` dynamic-input seam.

Anchor publication and placement-state readback, i.e. the scene-side half of
dynamic input.  The HUD widget itself is covered by
``tests/test_dynamic_input_widget.py``.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt

from PyQt6.QtGui import QKeyEvent
from PyQt6.QtTest import QTest

from firepro3d.construction_geometry import PolylineItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.node import Node


@pytest.fixture
def scene(qapp):
    sc = Model_Space()
    yield sc


@pytest.fixture
def view(scene):
    """A real ``Model_View`` on *scene*, needed for HUD parenting/positioning.

    ``begin_dynamic_input`` parents the HUD to ``views()[0].viewport()``, so
    every engage-path test needs an attached view rather than a bare scene.
    """
    v = Model_View(scene)
    v.resize(800, 600)
    v.resetTransform()
    yield v
    v.close()


class _MoveEventStub:
    """Minimal stand-in for the mouse-move event ``_move_draw_line`` reads.

    ``QGraphicsSceneMouseEvent`` cannot be instantiated or sub-classed under
    PyQt6, so a real event cannot be built headlessly.  ``_move_draw_line``
    touches only ``modifiers()`` on the event (the position arrives as the
    separate ``snapped`` argument), so this covers the whole surface the
    handler uses.
    """

    def __init__(self, modifiers=Qt.KeyboardModifier.NoModifier):
        self._modifiers = modifiers

    def modifiers(self):
        return self._modifiers


class TestPlacementAnchor:

    def test_none_when_nothing_started(self, scene):
        scene.mode = "draw_line"
        assert scene.get_placement_anchor() is None

    def test_draw_line_anchor(self, scene):
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(10, 20)
        assert scene.get_placement_anchor() == QPointF(10, 20)

    def test_draw_gridline_shares_line_anchor(self, scene):
        scene.mode = "draw_gridline"
        scene._draw_line_anchor = QPointF(1, 2)
        assert scene.get_placement_anchor() == QPointF(1, 2)

    def test_rectangle_anchor(self, scene):
        scene.mode = "draw_rectangle"
        scene._draw_rect_anchor = QPointF(3, 4)
        assert scene.get_placement_anchor() == QPointF(3, 4)

    def test_circle_centre(self, scene):
        scene.mode = "draw_circle"
        scene._draw_circle_center = QPointF(5, 6)
        assert scene.get_placement_anchor() == QPointF(5, 6)

    def test_wall_anchor(self, scene):
        scene.mode = "wall"
        scene._wall_anchor = QPointF(7, 8)
        assert scene.get_placement_anchor() == QPointF(7, 8)

    def test_unknown_mode_is_none(self, scene):
        scene.mode = "select"
        scene._draw_line_anchor = QPointF(10, 20)
        assert scene.get_placement_anchor() is None

    def test_construction_line_is_out_of_scope(self, scene):
        """construction_line is excluded by design — no dynamic input."""
        scene.mode = "construction_line"
        scene._cline_anchor = QPointF(9, 9)
        assert scene.get_placement_anchor() is None

    # ── Branches with real logic ──────────────────────────────────────────

    def test_polyline_returns_last_vertex(self, scene):
        """The anchor is the most recent vertex, not the first."""
        pl = PolylineItem(QPointF(1, 1))
        pl.append_point(QPointF(2, 2))
        pl.append_point(QPointF(3, 3))
        scene.mode = "polyline"
        scene._polyline_active = pl
        assert scene.get_placement_anchor() == QPointF(3, 3)

    def test_polyline_none_when_no_active(self, scene):
        scene.mode = "polyline"
        scene._polyline_active = None
        assert scene.get_placement_anchor() is None

    def test_pipe_returns_node_scene_pos(self, scene):
        """pipe mode stores a Node; the anchor is its scene position.

        The Node sits off-origin so a bug returning a default QPointF()
        cannot pass.
        """
        scene.mode = "pipe"
        scene.node_start_pos = Node(5.0, 7.0)
        assert scene.get_placement_anchor() == QPointF(5.0, 7.0)

    def test_move_returns_raw_point(self, scene):
        """move mode stores a raw QPointF, not a Node."""
        scene.mode = "move"
        scene.node_start_pos = QPointF(11, 22)
        assert scene.get_placement_anchor() == QPointF(11, 22)

    def test_pipe_none_when_no_start_node(self, scene):
        scene.mode = "pipe"
        scene.node_start_pos = None
        assert scene.get_placement_anchor() is None

    # ── Aliasing ──────────────────────────────────────────────────────────

    def test_returned_point_is_a_copy(self, scene):
        """Callers may mutate the result without corrupting internal state."""
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(1, 2)
        a = scene.get_placement_anchor()
        a.setX(999)
        assert scene._draw_line_anchor == QPointF(1, 2)

        # The polyline branch reaches into the item — mutating the result
        # must not relocate an already-committed vertex.
        pl = PolylineItem(QPointF(1, 1))
        pl.append_point(QPointF(3, 4))
        scene.mode = "polyline"
        scene._polyline_active = pl
        b = scene.get_placement_anchor()
        b.setY(-777)
        assert pl._points[-1] == QPointF(3, 4)


class TestPublishPlacementState:

    def test_publishes_resolved_point_not_raw_cursor(self, scene):
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(0, 0)
        scene._last_scene_pos = QPointF(500, -3)      # raw cursor
        constrained = QPointF(500, 0)                 # what Ctrl produced
        scene.publish_placement_state(QPointF(0, 0), constrained)
        assert scene.get_resolved_point() == constrained

    def test_move_draw_line_publishes_the_constrained_point(self, scene):
        """Drive the real handler: the published point must be Ctrl-snapped.

        The previous guard passed the constrained point into
        ``publish_placement_state`` by hand, so it could not tell a publish of
        ``tip`` from a publish of the raw ``snapped`` cursor.  Here the raw
        cursor sits a few degrees off horizontal — well inside the 45° snap —
        so the two points are numerically distinct and only the constrained
        one can satisfy the assertion.

        Driven via ``_move_draw_line`` with a ``_MoveEventStub`` rather than a
        real ``QGraphicsSceneMouseEvent``, which PyQt6 refuses to instantiate.
        """
        anchor = QPointF(0, 0)
        scene.mode = "draw_line"
        scene._draw_line_anchor = anchor
        raw = QPointF(1000, -30)          # ~1.7° off horizontal
        scene._last_scene_pos = raw

        scene._move_draw_line(
            _MoveEventStub(Qt.KeyboardModifier.ControlModifier), raw)

        expected = scene._constrain_angle(anchor, raw)
        got = scene.get_resolved_point()
        assert got is not None
        assert got == expected
        # The constraint actually moved the point, so this is a real distinction.
        assert expected != raw
        assert got != raw

    def test_move_draw_line_readout_matches_the_constrained_point(self, scene):
        """The readout is derived from the same constrained point, not the raw one."""
        anchor = QPointF(0, 0)
        scene.mode = "draw_line"
        scene._draw_line_anchor = anchor
        raw = QPointF(1000, -30)

        scene._move_draw_line(
            _MoveEventStub(Qt.KeyboardModifier.ControlModifier), raw)

        # Snapped to horizontal → 0°, not the raw cursor's ~1.7°.
        assert scene._draw_dim_hint == "L 1000.450 mm  A 0°"

    def test_sets_dim_hint_from_schema(self, scene):
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(1000, -1000))
        assert scene._draw_dim_hint == "L 1414.214 mm  A 45°"

    def test_dim_hint_honours_scale_calibration(self, scene):
        """Scene units are converted through the scene's own ScaleManager.

        This is the assertion that catches treating scene units as mm: at
        2 px/mm a 6000-scene-unit line is 3000 mm, and the readout must say so.
        """
        scene.scale_manager.set_pixels_per_mm(2.0)
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(6000, 0))
        hint = scene._draw_dim_hint
        assert "3000" in hint
        assert "6000" not in hint
        assert hint == "L 3000.000 mm  A 0°"

    def test_clear_resets_both(self, scene):
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(100, 0))
        scene.clear_placement_state()
        assert scene.get_resolved_point() is None
        assert scene._draw_dim_hint is None

    def test_no_schema_mode_publishes_point_without_hint(self, scene):
        scene.mode = "select"
        scene.publish_placement_state(QPointF(0, 0), QPointF(9, 9))
        assert scene.get_resolved_point() == QPointF(9, 9)
        assert scene._draw_dim_hint is None

    def test_resolved_point_is_a_copy(self, scene):
        """Same aliasing guard as get_placement_anchor."""
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(0, 0)
        p = QPointF(100, 0)
        scene.publish_placement_state(QPointF(0, 0), p)
        got = scene.get_resolved_point()
        got.setX(999)
        assert scene.get_resolved_point() == QPointF(100, 0)

    def test_gridline_replicate_teardown_drops_the_point(self, scene):
        """Cancelling replication must not leave the last point readable.

        ``_end_gridline_replicate`` returns to select mode, so without a full
        clear a caller reading ``get_resolved_point()`` before the next
        mouse-move would get the cancelled placement's point.
        """
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(100, 0))
        assert scene.get_resolved_point() is not None

        scene._end_gridline_replicate()

        assert scene.get_resolved_point() is None
        assert scene._draw_dim_hint is None


def _press(key, text, mods=Qt.KeyboardModifier.NoModifier):
    """Return a real ``KeyPress`` event.

    ``QTest.keyClick`` cannot send an arbitrary ``text()``, and the engage
    branch keys off ``event.text()``, so these events are built explicitly.
    """
    return QKeyEvent(QEvent.Type.KeyPress, key, mods, text)


def _armed_line(scene, anchor=QPointF(0, 0), resolved=QPointF(1000, 0)):
    """Arm ``draw_line`` with *anchor* and publish *resolved*.

    Mirrors the state a first click plus one mouse-move leaves behind, which
    is the only state a placement schema may engage from.
    """
    scene.mode = "draw_line"
    scene._draw_line_anchor = QPointF(anchor)
    scene.publish_placement_state(anchor, resolved)


class TestEngage:
    """Digit/Tab engage, and the gates that must refuse to engage."""

    def test_digit_engages_and_lands_in_field_one(self, scene, view):
        _armed_line(scene)
        scene.keyPressEvent(_press(Qt.Key.Key_5, "5"))

        assert scene.is_input_mode()
        hud = scene.dynamic_input
        assert hud is not None
        first = hud.field_names()[0]
        assert hud.editor(first).text() == "5"

    def test_seeds_from_resolved_point_not_raw_cursor(self, scene, view):
        """WYSIWYG: the seed is the constrained point, never ``_last_scene_pos``.

        The decoy cursor sits at 45°/1414 while the published point is a
        horizontal 1000, so a seed taken from the raw cursor cannot pass.
        """
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(0, 0)
        scene._last_scene_pos = QPointF(1000, -1000)          # decoy
        scene.publish_placement_state(QPointF(0, 0), QPointF(1000, 0))

        assert scene.begin_dynamic_input() is True
        hud = scene.dynamic_input
        assert hud.editor("Length").value_mm() == pytest.approx(1000.0)
        assert hud.editor("Angle").value_mm() == pytest.approx(0.0)

    def test_placement_schema_needs_an_anchor(self, scene, view):
        scene.mode = "draw_line"
        scene._draw_line_anchor = None
        assert scene.begin_dynamic_input() is False
        assert scene.dynamic_input is None
        assert not scene.is_input_mode()

    def test_digit_does_not_engage_without_anchor(self, scene, view):
        scene.mode = "draw_line"
        scene._draw_line_anchor = None
        scene.keyPressEvent(_press(Qt.Key.Key_5, "5"))
        assert not scene.is_input_mode()

    def test_transform_schema_engages_without_an_anchor(self, scene, view):
        """gridline_offset resolves a distance, so it has no anchor by nature."""
        scene.mode = "gridline_offset"
        assert scene.get_placement_anchor() is None
        assert scene.begin_dynamic_input(seed="3") is True
        hud = scene.dynamic_input
        assert hud.schema.name == "distance"
        assert hud.editor("Distance").text() == "3"

    def test_transform_seed_uses_replicate_state(self, scene, view):
        scene.mode = "gridline_array"
        scene._replicate_spacing = 250.0
        scene._replicate_count = 4
        assert scene.begin_dynamic_input() is True
        hud = scene.dynamic_input
        assert hud.editor("Spacing").value_mm() == pytest.approx(250.0)
        assert hud.editor("Count").value_mm() == pytest.approx(4.0)

    def test_transform_seed_falls_back_to_defaults(self, scene, view):
        scene.mode = "gridline_offset"
        scene._replicate_spacing = 0.0
        scene.begin_dynamic_input()
        assert (scene.dynamic_input.editor("Distance").value_mm()
                == pytest.approx(1000.0))

    def test_no_schema_mode_does_not_engage(self, scene, view):
        scene.mode = "select"
        assert scene.begin_dynamic_input() is False
        assert scene.dynamic_input is None

    def test_second_engage_is_a_no_op(self, scene, view):
        _armed_line(scene)
        assert scene.begin_dynamic_input(seed="7") is True
        hud = scene.dynamic_input
        assert scene.begin_dynamic_input(seed="9") is False
        assert scene.dynamic_input is hud            # not rebuilt
        assert hud.editor("Length").text() == "7"    # not reseeded

    def test_textless_key_does_not_engage(self, scene, view):
        """``"" in ENGAGE_CHARS`` is True in Python — the empty-text trap.

        F5 and a bare Shift both carry ``text() == ""``; either engaging
        would mean every non-text key opens the HUD.
        """
        _armed_line(scene)
        for key in (Qt.Key.Key_F5, Qt.Key.Key_Shift):
            scene.keyPressEvent(_press(key, ""))
            assert not scene.is_input_mode()
            assert scene.dynamic_input is None

    def test_non_engage_character_does_not_engage(self, scene, view):
        _armed_line(scene)
        scene.keyPressEvent(_press(Qt.Key.Key_A, "a"))
        assert not scene.is_input_mode()

    def test_modified_digit_does_not_engage(self, scene, view):
        """Ctrl+1 belongs to the window, not to a typed value."""
        _armed_line(scene)
        scene.keyPressEvent(
            _press(Qt.Key.Key_1, "1", Qt.KeyboardModifier.ControlModifier))
        assert not scene.is_input_mode()

    def test_minus_engages(self, scene, view):
        _armed_line(scene)
        scene.keyPressEvent(_press(Qt.Key.Key_Minus, "-"))
        assert scene.is_input_mode()
        assert scene.dynamic_input.editor("Length").text() == "-"

    def test_tab_engages_through_the_view(self, scene, view):
        """Drive the real key event through ``Model_View.keyPressEvent``."""
        _armed_line(scene)
        QTest.keyClick(view, Qt.Key.Key_Tab)
        assert scene.is_input_mode()
        # No seed on Tab: the field keeps its seeded value.
        assert (scene.dynamic_input.editor("Length").value_mm()
                == pytest.approx(1000.0))

    def test_tab_does_not_engage_when_refused(self, scene, view):
        """Tab in select mode must not open a HUD."""
        scene.mode = "select"
        QTest.keyClick(view, Qt.Key.Key_Tab)
        assert not scene.is_input_mode()
        assert scene.dynamic_input is None


class TestInputModeInertness:
    """While the HUD is open the cursor drives nothing."""

    def test_mouse_move_is_inert(self, scene, view):
        _armed_line(scene)
        scene.begin_dynamic_input()
        before = scene.get_resolved_point()
        scene._last_scene_pos = None

        # A real QGraphicsSceneMouseEvent cannot be constructed under PyQt6,
        # but the guard is the first statement in the handler, so None never
        # reaches the body — an AttributeError here *is* the failure signal.
        scene.mouseMoveEvent(None)

        assert scene._last_scene_pos is None            # handler bailed
        assert scene.get_resolved_point() == before     # seed untouched

    def test_mouse_press_is_inert(self, scene, view):
        _armed_line(scene)
        scene.begin_dynamic_input()
        scene.mousePressEvent(None)
        assert scene._draw_line_anchor == QPointF(0, 0)  # nothing committed
        assert len(scene._draw_lines) == 0

    def test_publish_is_a_no_op_in_input_mode(self, scene, view):
        _armed_line(scene)
        scene.begin_dynamic_input()
        scene.publish_placement_state(QPointF(0, 0), QPointF(-9999, -9999))
        assert scene.get_resolved_point() == QPointF(1000, 0)


class TestCommitAndCancel:

    def test_commit_places_geometry_and_exits_input_mode(self, scene, view):
        _armed_line(scene)
        scene.begin_dynamic_input()
        hud = scene.dynamic_input
        hud.set_values({"Length": 2000.0, "Angle": 90.0})
        hud._accept()

        assert not scene.is_input_mode()
        assert scene.dynamic_input is None
        assert len(scene._draw_lines) == 1
        line = scene._draw_lines[0].line()
        # 90° Y-up from the origin → straight up in a Y-down scene.
        assert line.p2().x() == pytest.approx(0.0, abs=1e-6)
        assert line.p2().y() == pytest.approx(-2000.0, abs=1e-6)
        # The commit path cleared the anchor, so the mode is re-armed.
        assert scene._draw_line_anchor is None

    def test_commit_resolves_before_closing(self, scene, view):
        """Ordering guard: ``_commit_draw_line_at`` re-reads scene anchor state.

        Resolving after the HUD tear-down would still work, but resolving
        after the *commit* would not — asserting the geometry (not merely that
        a line exists) pins the order.
        """
        _armed_line(scene, anchor=QPointF(100, 100),
                    resolved=QPointF(1100, 100))
        scene.begin_dynamic_input()
        scene.dynamic_input.set_values({"Length": 500.0, "Angle": 0.0})
        scene.dynamic_input._accept()

        line = scene._draw_lines[0].line()
        assert line.p1() == QPointF(100, 100)
        assert line.p2().x() == pytest.approx(600.0)

    def test_cancel_closes_hud_but_keeps_the_mode(self, scene, view):
        """Esc rung 0: leave input mode, stay armed in the placement mode."""
        _armed_line(scene)
        scene.begin_dynamic_input()
        scene.dynamic_input.cancelled.emit()

        assert not scene.is_input_mode()
        assert scene.dynamic_input is None
        assert scene.mode == "draw_line"
        assert scene._draw_line_anchor == QPointF(0, 0)
        assert len(scene._draw_lines) == 0

    def test_mode_switch_closes_the_hud(self, scene, view):
        """A HUD outlives neither its schema nor its anchor.

        Switching modes from the ribbon while typing would otherwise strand an
        editable widget whose applier belongs to the mode just left.
        """
        _armed_line(scene)
        scene.begin_dynamic_input()
        scene.set_mode("select")
        assert not scene.is_input_mode()
        assert scene.dynamic_input is None

    def test_single_place_commit_still_closes_cleanly(self, scene, view):
        """The commit path calls ``set_mode`` itself — no double tear-down."""
        _armed_line(scene)
        scene.single_place_mode = True
        scene.begin_dynamic_input()
        scene.dynamic_input.set_values({"Length": 1000.0, "Angle": 0.0})
        scene.dynamic_input._accept()
        assert len(scene._draw_lines) == 1
        assert scene.mode == "select"
        assert scene.dynamic_input is None

    def test_unmapped_mode_applier_raises(self, scene, view):
        """Modes without an applier fail loudly rather than silently no-op."""
        scene.mode = "draw_rectangle"
        with pytest.raises(NotImplementedError):
            scene.apply_dynamic_input(QPointF(1, 1))

    def test_gridline_commit_uses_the_same_path(self, scene, view):
        scene.mode = "draw_gridline"
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(1000, 0))
        scene.begin_dynamic_input()
        scene.dynamic_input.set_values({"Length": 3000.0, "Angle": 0.0})
        scene.dynamic_input._accept()
        assert len(scene._gridlines) == 1
        assert not scene.is_input_mode()


class TestPlaceDynamicInput:
    """HUD positioning mirrors the painted Dim HUD's edge-flip rule."""

    def test_positions_near_the_cursor(self, scene, view):
        view._last_vp_pos = QPoint(100, 200)
        _armed_line(scene)
        scene.begin_dynamic_input()
        hud = scene.dynamic_input
        assert hud.parent() is view.viewport()
        # ``isVisible()`` would be False here for a reason unrelated to the
        # seam — the test never shows the view, and a child of a hidden parent
        # is never visible.  ``isHidden()`` records the explicit show/hide.
        assert not hud.isHidden()
        assert hud.x() == 100 + 14

    def test_flips_at_the_right_edge(self, scene, view):
        view._last_vp_pos = QPoint(view.viewport().width() - 5, 100)
        _armed_line(scene)
        scene.begin_dynamic_input()
        hud = scene.dynamic_input
        assert hud.x() + hud.width() <= view.viewport().width()
        assert hud.x() >= 0

    def test_falls_back_to_viewport_centre(self, scene, view):
        view._last_vp_pos = None
        _armed_line(scene)
        scene.begin_dynamic_input()
        hud = scene.dynamic_input
        assert 0 <= hud.x() <= view.viewport().width()
        assert 0 <= hud.y() <= view.viewport().height()
