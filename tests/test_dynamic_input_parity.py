"""tests/test_dynamic_input_parity.py — mouse vs HUD produce identical geometry.

Covers ``Model_Space._commit_draw_line_at``, the point-taking commit extracted
from ``_press_draw_line`` so that Dynamic Input and the mouse click share one
line-building path instead of two.
"""

from __future__ import annotations

import dataclasses
import math

import pytest
from PyQt6.QtCore import QEvent, QObject, QPointF, Qt, QTimer
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QGraphicsView

from firepro3d.dynamic_input import SCHEMAS
from firepro3d.gridline import GridlineItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.node import Node


@pytest.fixture
def scene(qapp):
    return Model_Space()


@pytest.fixture
def view(scene):
    """A real, **shown** ``Model_View``, required by every HUD-driven path.

    ``begin_dynamic_input`` parents the HUD to the first *visible* view and
    refuses outright when no attached view is visible, so the mouse-vs-HUD
    parity cases cannot run on a bare scene or on a merely-constructed view.
    """
    v = Model_View(scene)
    v.resize(800, 600)
    v.resetTransform()
    v.show()
    QTest.qWaitForWindowExposed(v)
    yield v
    v.close()


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


class TestTypedLineCommitViaHud:
    """The HUD's typed line delegates to ``_commit_draw_line_at``.

    Ports the retired ``TestModalTypedCommitDelegates`` onto the surviving
    surface: the modal ``_DynInput`` is gone (T17), so the HUD is the only
    typed-input path, and it must share the click path's commit rather than
    build the line itself.  The old "typed zero length is rejected" case cannot
    reach the commit here — ``Length`` carries ``minimum=0.0``, so
    ``DimensionEdit`` reverts a typed ``0`` to the last valid value before it
    ever resolves (that revert is the very thing that killed the
    ``_DynInput.value() → 0.0`` bug).  Commit-level rejection is covered by
    ``TestCommitDrawLineAt.test_rejects_zero_length``.
    """

    def _arm(self, scene):
        scene.set_mode("draw_line")
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(100, 0))
        assert scene.begin_dynamic_input() is True

    def test_typed_length_commits_via_the_shared_path(self, scene, view):
        self._arm(scene)
        before = len(scene._draw_lines)
        scene.dynamic_input.editor("Length").setText("1000")
        scene.dynamic_input.editor("Angle").setText("0")
        scene.dynamic_input._accept()

        assert len(scene._draw_lines) == before + 1
        item = scene._draw_lines[-1]
        assert item.line().p1() == QPointF(0, 0)
        assert item.line().p2().x() == pytest.approx(1000.0, abs=1.0)
        assert item.line().p2().y() == pytest.approx(0.0, abs=1.0)
        # Delegation side effects the old inline modal path lacked.
        assert scene._draw_line_anchor is None
        assert scene.get_resolved_point() is None

    def test_typed_commit_clears_placement_state(self, scene, view):
        self._arm(scene)
        assert scene.get_resolved_point() is not None
        scene.dynamic_input.editor("Length").setText("1000")
        scene.dynamic_input.editor("Angle").setText("0")
        scene.dynamic_input._accept()
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


# ── Task 2: _preview_from_resolved dispatch ───────────────────────────────
#
# The preview-drawing tail of every ``_move_*`` handler is extracted into a
# per-mode ``_preview_from_<mode>`` so the Dynamic Input field-commit path can
# redraw the *same* preview from a resolved point (not the mouse).  Parity with
# the mouse path is proven by the surviving parity tests; this pins the new
# entry point directly.


class TestPreviewFromResolved:

    def test_moves_line_ghost(self, scene, view):
        """``_preview_from_resolved`` points the rubber-band line at the arg."""
        scene.set_mode("draw_line")
        _click(scene, view, QPointF(0, 0))          # arm the anchor
        assert scene._draw_line_anchor == QPointF(0, 0)

        scene._preview_from_resolved(QPointF(1000, 0))

        line = scene.preview_pipe.line()
        assert abs(line.x2() - 1000) < 1e-6
        assert abs(line.y2() - 0) < 1e-6
        assert scene.preview_pipe.isVisible()

    def test_moves_rectangle_preview(self, scene, view):
        """The rect preview redraws from the resolved corner point."""
        scene.set_mode("draw_rectangle")
        scene._press_draw_rectangle(_FakeEvent(), QPointF(0, 0), QPointF(0, 0),
                                    None, None, None)
        assert scene._draw_rect_preview is not None

        scene._preview_from_resolved(QPointF(300, -200))

        r = scene._draw_rect_preview.rect()
        assert r.width() == pytest.approx(300.0, abs=1e-6)
        assert r.height() == pytest.approx(200.0, abs=1e-6)

    def test_moves_circle_preview(self, scene, view):
        """The circle preview redraws from the resolved rim point."""
        scene.set_mode("draw_circle")
        scene._press_draw_circle(_FakeEvent(), QPointF(0, 0), QPointF(0, 0),
                                 None, None, None)
        assert scene._draw_circle_preview is not None

        scene._preview_from_resolved(QPointF(120, 0))

        r = scene._draw_circle_preview.rect()
        assert r.width() == pytest.approx(240.0, abs=1e-6)

    def test_noop_when_mode_has_no_preview(self, scene, view):
        """A mode absent from the table is a silent no-op, not a crash."""
        scene.set_mode("select")
        scene._preview_from_resolved(QPointF(1, 1))   # must not raise


# ── Task 10: mouse-vs-HUD parity ──────────────────────────────────────────
#
# The architectural claim under test is that dynamic input is an alternative
# *point source*, not an alternative *commit path*: a schema resolves typed
# values into the same point a mouse click would have produced, and
# ``Model_Space`` hands that point to the existing click-commit path.  If that
# holds, the two routes must produce byte-identical geometry by construction.
#
# Both routes are therefore asked for the *same* geometry — the mouse target
# is computed with ``SCHEMAS["line"].resolve`` rather than by hand — so any
# disagreement the assertions catch is the production code's, never the test's
# own arithmetic drifting from the resolver's.

_COLLECTION_FOR_MODE = {"draw_line": "_draw_lines", "draw_gridline": "_gridlines"}


def _items(scene, mode):
    """Return the scene collection *mode* commits into."""
    return getattr(scene, _COLLECTION_FOR_MODE[mode])


def _place_by_mouse(scene, view, mode, anchor, length, angle):
    """Place a line-like item by two clicks and return its ``QLineF``.

    The second click lands on ``SCHEMAS["line"].resolve(anchor, ...)`` so the
    mouse is asked for exactly the point the typed path will resolve to.

    Args:
        scene: The ``Model_Space`` under test.
        view: An attached view, used to map scene coordinates for the event.
        mode: ``"draw_line"`` or ``"draw_gridline"``.
        anchor: First-click point in scene coordinates.
        length: Line length in scene units.
        angle: Line angle in degrees, Y-up.

    Returns:
        The committed item's line.
    """
    scene.set_mode(mode)
    scene.single_place_mode = False
    tip = SCHEMAS["line"].resolve(anchor, {"Length": length, "Angle": angle})
    _click(scene, view, anchor)
    _click(scene, view, tip)
    items = _items(scene, mode)
    assert items, f"mouse path created no {mode} item"
    return items[-1].line()


def _place_by_hud(scene, view, mode, anchor, length, angle):
    """Place the same item by typing Length/Angle into the HUD.

    Arms the anchor and publishes a placement state exactly as a first click
    plus one mouse-move would, engages the HUD, then types into the real
    editors and commits through ``_on_dynamic_input_committed`` — the slot the
    ``committed`` signal reaches in production.

    Args:
        scene: The ``Model_Space`` under test.
        view: An attached view; the HUD parents to its viewport.
        mode: ``"draw_line"`` or ``"draw_gridline"``.
        anchor: The armed anchor in scene coordinates.
        length: Length to type, in scene units.
        angle: Angle to type, in degrees Y-up.

    Returns:
        The committed item's line.
    """
    scene.set_mode(mode)
    scene.single_place_mode = False
    scene._draw_line_anchor = QPointF(anchor)
    # A decoy seed well away from the target: the committed geometry must come
    # from the typed text, so a path that silently reused the published point
    # cannot pass.
    scene.publish_placement_state(anchor, QPointF(anchor.x() + 1.0, anchor.y()))
    assert scene.begin_dynamic_input() is True

    hud = scene.dynamic_input
    hud.editor("Length").setText(str(length))
    hud.editor("Angle").setText(str(angle))
    scene._on_dynamic_input_committed(hud.values())

    items = _items(scene, mode)
    assert items, f"HUD path created no {mode} item"
    return items[-1].line()


def _assert_same_line(mouse, hud):
    """Assert two ``QLineF`` results are identical to floating-point tolerance."""
    assert mouse.p1().x() == pytest.approx(hud.p1().x(), abs=1e-6)
    assert mouse.p1().y() == pytest.approx(hud.p1().y(), abs=1e-6)
    assert mouse.p2().x() == pytest.approx(hud.p2().x(), abs=1e-6)
    assert mouse.p2().y() == pytest.approx(hud.p2().y(), abs=1e-6)


# (label, anchor, length, angle)
#
# 30° and -30° are the load-bearing cases: an axis-aligned line has a zero
# component on one axis, so a sign error in the Y-up→Y-down conversion is
# invisible there and shows up only off-axis.  The negative angle and the
# off-origin anchor cover the two other places a sign or an offset can be lost.
_PARITY_CASES = [
    ("axis_aligned_east", QPointF(0, 0), 1000.0, 0.0),
    ("axis_aligned_north", QPointF(0, 0), 1000.0, 90.0),
    ("oblique_30", QPointF(0, 0), 1000.0, 30.0),
    ("oblique_negative_30", QPointF(0, 0), 1000.0, -30.0),
    ("oblique_135", QPointF(0, 0), 2500.0, 135.0),
    ("off_origin_anchor", QPointF(-750.0, 1200.0), 1750.0, 30.0),
]


class TestMouseVsHudParity:
    """The same placement, driven both ways, must land on the same geometry.

    Parity here is a claim about *architecture*, not about arithmetic: because
    both routes end in ``_commit_draw_line_at``, the only thing that can differ
    is the point handed to it.  A failure in this class therefore means the
    typed path has grown a second commit route, or the schema's Y-up conversion
    disagrees with what the mouse produces.
    """

    @pytest.mark.parametrize("label,anchor,length,angle", _PARITY_CASES,
                             ids=[c[0] for c in _PARITY_CASES])
    def test_draw_line_parity(self, scene, view, label, anchor, length, angle):
        mouse = _place_by_mouse(scene, view, "draw_line", anchor, length, angle)
        hud = _place_by_hud(scene, view, "draw_line", anchor, length, angle)
        _assert_same_line(mouse, hud)

    @pytest.mark.parametrize("label,anchor,length,angle", _PARITY_CASES,
                             ids=[c[0] for c in _PARITY_CASES])
    def test_draw_gridline_parity(self, scene, view, label, anchor, length,
                                  angle):
        mouse = _place_by_mouse(scene, view, "draw_gridline", anchor, length,
                                angle)
        hud = _place_by_hud(scene, view, "draw_gridline", anchor, length, angle)
        _assert_same_line(mouse, hud)

    def test_oblique_case_really_is_off_axis(self, scene, view):
        """Guard the guard: the 30° cases must exercise both components.

        If ``resolve`` ever degenerated to an axis-aligned result the parity
        parametrisation would still pass — both paths would agree on the wrong
        point.  Pin that the 30° target has a non-trivial X *and* Y offset.
        """
        tip = SCHEMAS["line"].resolve(QPointF(0, 0),
                                      {"Length": 1000.0, "Angle": 30.0})
        assert abs(tip.x()) > 1.0
        assert abs(tip.y()) > 1.0

    def test_hud_geometry_is_not_merely_the_published_seed(self, scene, view):
        """The typed value, not the seed, is what gets committed.

        ``_place_by_hud`` publishes a 1-unit decoy; if the commit path used the
        published point instead of the resolved one, every parity case above
        would fail — but only because of that decoy.  Assert it explicitly so
        the intent survives a future refactor of the helper.
        """
        line = _place_by_hud(scene, view, "draw_line", QPointF(0, 0),
                             1000.0, 0.0)
        assert line.p2().x() == pytest.approx(1000.0, abs=1e-6)


class TestTypedAngleConvention:
    """Angles are Y-up (0° = right, 90° = up) while scene Y grows downward."""

    def test_typed_angle_is_y_up(self, scene, view):
        """Typing 90° must place the tip at *negative* scene Y.

        This is the single most error-prone fact in the feature: dropping the
        negation in ``resolve_line`` sends every typed vertical line the wrong
        way, and no axis-aligned horizontal case would notice.
        """
        line = _place_by_hud(scene, view, "draw_line", QPointF(0, 0),
                             2000.0, 90.0)
        assert line.p2().x() == pytest.approx(0.0, abs=1e-6)
        assert line.p2().y() == pytest.approx(-2000.0, abs=1e-6)
        assert line.p2().y() < 0

    def test_typed_negative_angle_goes_the_other_way(self, scene, view):
        """-90° is the mirror: positive scene Y, i.e. downward on screen."""
        line = _place_by_hud(scene, view, "draw_line", QPointF(0, 0),
                             2000.0, -90.0)
        assert line.p2().y() == pytest.approx(2000.0, abs=1e-6)
        assert line.p2().y() > 0

    def test_typed_oblique_angle_signs(self, scene, view):
        """30° is right-and-up: +X, −Y.  Both components must be signed."""
        line = _place_by_hud(scene, view, "draw_line", QPointF(0, 0),
                             1000.0, 30.0)
        assert line.p2().x() == pytest.approx(1000.0 * math.cos(math.radians(30)),
                                              abs=1e-6)
        assert line.p2().y() == pytest.approx(-1000.0 * math.sin(math.radians(30)),
                                              abs=1e-6)

    def test_readout_and_commit_agree_on_the_angle(self, scene, view):
        """WYSIWYG: what the readout reports is what a commit reproduces.

        ``seed`` is ``resolve``'s inverse, so a sign error in either would show
        up as a round-trip that does not return the point it started from.
        """
        anchor = QPointF(0, 0)
        tip = QPointF(1000.0, -577.35)          # ~30° up-right
        values = SCHEMAS["line"].seed(anchor, tip)
        assert values["Angle"] == pytest.approx(30.0, abs=0.01)
        back = SCHEMAS["line"].resolve(anchor, values)
        assert back.x() == pytest.approx(tip.x(), abs=1e-6)
        assert back.y() == pytest.approx(tip.y(), abs=1e-6)


class TestUndoParity:
    """A HUD commit pushes exactly one undo state — the same as a click.

    Undo lives on ``Model_Space.push_undo_state``, which appends a captured
    network snapshot to ``_undo_stack`` and moves ``_undo_pos``.  The counter
    below monkeypatches that single entry point rather than inspecting the
    stack, so it counts *calls* and cannot be fooled by a snapshot that happens
    to coalesce.
    """

    def _count_pushes(self, scene, monkeypatch):
        """Replace ``push_undo_state`` with a call counter and return it."""
        calls = []
        monkeypatch.setattr(scene, "push_undo_state",
                            lambda *a, **k: calls.append(1))
        return calls

    def test_hud_commit_pushes_exactly_one_undo_state(self, scene, view,
                                                      monkeypatch):
        scene.set_mode("draw_line")
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(1, 0))
        assert scene.begin_dynamic_input() is True
        hud = scene.dynamic_input
        hud.editor("Length").setText("1000")
        hud.editor("Angle").setText("0")

        calls = self._count_pushes(scene, monkeypatch)
        scene._on_dynamic_input_committed(hud.values())

        assert len(scene._draw_lines) == 1       # it really did commit
        assert calls == [1]                      # exactly one push

    def test_hud_commit_matches_the_mouse_push_count(self, scene, view,
                                                     monkeypatch):
        """Parity again, on the undo axis rather than the geometry axis."""
        calls = self._count_pushes(scene, monkeypatch)
        _place_by_mouse(scene, view, "draw_line", QPointF(0, 0), 1000.0, 0.0)
        mouse_pushes = len(calls)

        calls.clear()
        _place_by_hud(scene, view, "draw_line", QPointF(0, 0), 1000.0, 0.0)
        hud_pushes = len(calls)

        assert mouse_pushes == 1
        assert hud_pushes == mouse_pushes

    def test_rejected_hud_commit_pushes_nothing(self, scene, view, monkeypatch):
        """A too-short typed line is refused, so there is nothing to undo.

        ``Length`` has ``minimum=0.0`` so a typed ``0`` never reaches the slot;
        this drives the slot directly with a sub-tolerance length to reach the
        commit's own too-short guard.
        """
        scene.set_mode("draw_line")
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(1, 0))
        assert scene.begin_dynamic_input() is True

        calls = self._count_pushes(scene, monkeypatch)
        scene._on_dynamic_input_committed({"Length": 0.1, "Angle": 0.0})

        assert len(scene._draw_lines) == 0
        assert calls == []

    def test_real_undo_stack_grows_by_one(self, scene, view):
        """The unpatched mechanism, so the counter above is not a fiction.

        Pins that ``push_undo_state`` is genuinely what backs undo here: the
        stack gains one entry and ``_undo_pos`` follows it.
        """
        scene.set_mode("draw_line")
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(1, 0))
        assert scene.begin_dynamic_input() is True
        hud = scene.dynamic_input
        hud.editor("Length").setText("1000")
        hud.editor("Angle").setText("0")

        depth_before = len(scene._undo_stack)
        pos_before = scene._undo_pos
        scene._on_dynamic_input_committed(hud.values())

        assert len(scene._undo_stack) == depth_before + 1
        assert scene._undo_pos == pos_before + 1


class _TeardownWatch(QObject):
    """Records the HUD's tear-down in a shared ordering log.

    ``end_dynamic_input`` hides the HUD and then unparents it, so a ``Hide``
    event on the widget is an observable, production-driven marker for "the
    HUD teardown has begun" — no production hook is added for the test.
    """

    def __init__(self, log):
        super().__init__()
        self._log = log

    def eventFilter(self, obj, event):  # noqa: N802 (Qt naming)
        if event.type() == QEvent.Type.Hide:
            self._log.append("teardown")
        return False


class TestResolveBeforeCloseOrdering:
    """``schema.resolve`` must run *before* ``end_dynamic_input``.

    ``_on_dynamic_input_committed`` captures the schema and anchor up front, so
    merely swapping the resolve and the tear-down leaves the resulting geometry
    unchanged — which is precisely why the invariant was guarded by a comment
    and nothing else.  The distinction is therefore pinned as an *ordering* of
    two observable events rather than as a difference in the committed values.

    ``resolve`` is observed by handing the scene a ``dataclasses.replace``
    copy of the live schema whose ``resolve`` records the call and then
    delegates to the real one; the tear-down is observed through the ``Hide``
    event Qt delivers when ``end_dynamic_input`` hides the widget.  Both are
    real production events, so the log is a faithful trace of the slot.

    Why the ordering matters at all: the applier re-reads the scene's anchor
    state and calls ``clear_placement_state()``.  Resolving after tear-down
    happens to work today only because the anchor was captured earlier — the
    ordering is the thing that keeps it safe if the capture ever moves, and a
    swap makes this class fail immediately.
    """

    def _run(self, scene, view, monkeypatch):
        """Commit through the HUD and return the ordered event log."""
        scene.set_mode("draw_line")
        scene.single_place_mode = False
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(1, 0))
        assert scene.begin_dynamic_input() is True
        hud = scene.dynamic_input

        log = []
        watch = _TeardownWatch(log)
        hud.installEventFilter(watch)

        real = scene.active_schema()

        def _recording_resolve(anchor, values):
            log.append("resolve")
            return real.resolve(anchor, values)

        # A frozen-dataclass copy: the registry's shared Schema is never
        # mutated, so no other test can see this instrumentation.
        recording = dataclasses.replace(real, resolve=_recording_resolve)
        monkeypatch.setattr(scene, "active_schema", lambda: recording)

        hud.editor("Length").setText("1000")
        hud.editor("Angle").setText("0")
        scene._on_dynamic_input_committed(hud.values())
        return log

    def test_resolve_runs_before_the_hud_is_torn_down(self, scene, view,
                                                      monkeypatch):
        log = self._run(scene, view, monkeypatch)
        assert "resolve" in log, "the schema resolver was never called"
        assert "teardown" in log, "the HUD was never torn down"
        assert log.index("resolve") < log.index("teardown"), (
            f"resolve must precede end_dynamic_input; got {log}")

    def test_the_ordering_probe_sees_a_real_commit(self, scene, view,
                                                   monkeypatch):
        """Non-vacuity: the instrumented run still places real geometry.

        Without this a future change that made the slot bail early would leave
        the ordering assertion trivially satisfiable.
        """
        self._run(scene, view, monkeypatch)
        assert len(scene._draw_lines) == 1
        assert scene._draw_lines[-1].line().p2().x() == pytest.approx(1000.0,
                                                                     abs=1e-6)

    def test_geometry_reflects_the_anchor_as_it_was_at_commit_time(
            self, scene, view):
        """The reason the ordering exists, asserted on the geometry itself.

        ``_commit_draw_line_at`` clears ``_draw_line_anchor`` and the published
        placement state.  A resolve that read the anchor after the applier had
        run would find None; asserting the committed line starts at the
        *original* off-origin anchor pins that the resolve saw live state.
        """
        anchor = QPointF(250.0, -400.0)
        line = _place_by_hud(scene, view, "draw_line", anchor, 1000.0, 0.0)
        assert line.p1().x() == pytest.approx(250.0, abs=1e-6)
        assert line.p1().y() == pytest.approx(-400.0, abs=1e-6)
        # ...and the commit really did tear that state down afterwards.
        assert scene._draw_line_anchor is None
        assert scene.get_resolved_point() is None


class TestCancelLeavesNoGeometry:
    """Escape after typing must create nothing and leave the placement armed."""

    def _engage(self, scene, anchor=QPointF(0, 0)):
        scene.set_mode("draw_line")
        scene.single_place_mode = False
        scene._draw_line_anchor = QPointF(anchor)
        scene.publish_placement_state(anchor, QPointF(anchor.x() + 1000.0,
                                                      anchor.y()))
        assert scene.begin_dynamic_input() is True
        return scene.dynamic_input

    def test_escape_after_typing_creates_nothing(self, scene, view):
        """Driven with a real key event: the cancel path runs through the HUD."""
        from PyQt6.QtTest import QTest

        hud = self._engage(scene)
        ed = hud.editor("Length")
        ed.selectAll()
        QTest.keyClicks(ed, "5000")

        QTest.keyClick(ed, Qt.Key.Key_Escape)

        assert len(scene._draw_lines) == 0
        assert not scene.is_input_mode()
        # The HUD survives as the passive readout for the still-live placement
        # (decision S1); what must not survive is the typed value.
        assert scene.dynamic_input is not None
        assert not scene.dynamic_input.is_engaged()

    def test_cancel_leaves_the_anchor_armed(self, scene, view):
        """Escape steps back to the cursor; it does not abandon the placement.

        The user must be able to carry straight on with the mouse, so the mode
        and the armed anchor both survive.
        """
        from PyQt6.QtTest import QTest

        hud = self._engage(scene, anchor=QPointF(120.0, 340.0))
        QTest.keyClick(hud.editor("Length"), Qt.Key.Key_Escape)

        assert scene.mode == "draw_line"
        assert scene._draw_line_anchor == QPointF(120.0, 340.0)

    def test_the_user_can_carry_on_by_mouse_after_cancelling(self, scene, view):
        """End to end: cancel, then finish the very same line with a click.

        The surviving anchor is only useful if the next click completes the
        placement, so the guard is asserted as behaviour rather than as state.
        """
        from PyQt6.QtTest import QTest

        anchor = QPointF(0, 0)
        hud = self._engage(scene, anchor)
        ed = hud.editor("Length")
        ed.selectAll()
        QTest.keyClicks(ed, "5000")
        QTest.keyClick(ed, Qt.Key.Key_Escape)
        assert len(scene._draw_lines) == 0

        # One click finishes it — no re-arming click needed.
        tip = SCHEMAS["line"].resolve(anchor, {"Length": 1000.0, "Angle": 0.0})
        _click(scene, view, tip)

        assert len(scene._draw_lines) == 1
        line = scene._draw_lines[-1].line()
        assert line.p1() == anchor
        assert line.p2().x() == pytest.approx(1000.0, abs=1e-6)
        # The typed-then-cancelled 5000 left no trace.
        assert line.p2().x() != pytest.approx(5000.0, abs=1.0)

    def test_cancel_pushes_no_undo_state(self, scene, view, monkeypatch):
        """Nothing was placed, so nothing may enter the undo stack."""
        from PyQt6.QtTest import QTest

        hud = self._engage(scene)
        calls = []
        monkeypatch.setattr(scene, "push_undo_state",
                            lambda *a, **k: calls.append(1))
        QTest.keyClick(hud.editor("Length"), Qt.Key.Key_Escape)
        assert calls == []


# ── Task 14: polyline reuses the Line schema ──────────────────────────────
#
# Polyline is the only mode whose anchor *re-arms*: every committed vertex
# becomes the anchor for the next segment.  It therefore exercises the whole
# S1 lifecycle — arm → read out → commit → re-arm → read out — which
# ``draw_line`` cannot reach, arming and committing exactly once.


class _FakeEvent:
    """Minimal press/move-event stand-in carrying only modifier state."""

    def __init__(self, ctrl: bool = False):
        self._mods = (Qt.KeyboardModifier.ControlModifier if ctrl
                      else Qt.KeyboardModifier.NoModifier)

    def modifiers(self):
        return self._mods


def _start_polyline(scene, at=QPointF(0, 0)):
    """First click: create the active polyline at *at* and return it.

    Routed through ``"select"`` deliberately.  ``set_mode``'s polyline teardown
    is keyed on the **target** mode, so re-setting ``"polyline"`` clears nothing
    and a second call would keep extending the first polyline instead of
    starting a fresh one.
    """
    scene.set_mode("select")
    scene.set_mode("polyline")
    scene._press_polyline(_FakeEvent(), at, at, None, None, None)
    return scene._polyline_active


def _click_vertex(scene, tip):
    """Append a vertex by a subsequent click at *tip*."""
    scene._press_polyline(_FakeEvent(), tip, tip, None, None, None)


def _append_by_hud(scene, length, angle):
    """Engage the HUD on the live polyline and commit one typed vertex.

    Publishes a 1-unit decoy first, so a path that silently committed the
    published point rather than the resolved one cannot pass.
    """
    anchor = scene.get_placement_anchor()
    scene.publish_placement_state(anchor, QPointF(anchor.x() + 1.0, anchor.y()))
    assert scene.begin_dynamic_input() is True
    hud = scene.dynamic_input
    hud.editor("Length").setText(str(length))
    hud.editor("Angle").setText(str(angle))
    scene._on_dynamic_input_committed(hud.values())


class TestPolylineParity:

    def test_hud_appends_one_vertex(self, scene, view):
        pl = _start_polyline(scene)
        before = len(pl._points)
        _append_by_hud(scene, 200, 0)
        assert len(pl._points) == before + 1

    def test_vertex_position_is_y_up(self, scene, view):
        """90° is up, i.e. *negative* scene Y — the feature's easiest sign error."""
        pl = _start_polyline(scene)
        _append_by_hud(scene, 100, 90)
        assert pl._points[-1].x() == pytest.approx(0.0, abs=1e-6)
        assert pl._points[-1].y() == pytest.approx(-100.0, abs=1e-6)

    def test_hud_closes_and_anchor_advances(self, scene, view):
        pl = _start_polyline(scene)
        _append_by_hud(scene, 100, 0)
        assert not scene.is_input_mode()
        assert scene.get_placement_anchor() == pl._points[-1]

    def test_chain_continues_from_the_new_anchor(self, scene, view):
        """The re-arm is real: a second typed segment starts where the first ended.

        This is the case ``draw_line`` cannot cover — if the applier failed to
        advance the anchor, the second segment would restart from the origin and
        land at (0, -100) instead of (100, -100).
        """
        pl = _start_polyline(scene)
        _append_by_hud(scene, 100, 0)
        _append_by_hud(scene, 100, 90)
        assert len(pl._points) == 3
        assert pl._points[-1].x() == pytest.approx(100.0, abs=1e-6)
        assert pl._points[-1].y() == pytest.approx(-100.0, abs=1e-6)

    def test_vertex_is_not_merely_the_published_seed(self, scene, view):
        """The typed value wins over the 1-unit decoy ``_append_by_hud`` publishes."""
        pl = _start_polyline(scene)
        _append_by_hud(scene, 1000, 0)
        assert pl._points[-1].x() == pytest.approx(1000.0, abs=1e-6)

    def test_commit_without_an_active_polyline_is_a_noop(self, scene):
        scene.set_mode("select")
        scene.set_mode("polyline")
        scene._commit_polyline_at(QPointF(100, 0))
        assert scene._polyline_active is None

    def test_commit_clears_the_published_placement_state(self, scene, view):
        """The published point belonged to the segment just finished."""
        _start_polyline(scene)
        _append_by_hud(scene, 1000, 0)
        assert scene.get_resolved_point() is None


_POLYLINE_CASES = [
    ("axis_aligned_east", QPointF(0, 0), 1000.0, 0.0),
    ("axis_aligned_north", QPointF(0, 0), 1000.0, 90.0),
    ("oblique_30", QPointF(0, 0), 1750.0, 30.0),
    ("oblique_negative_30", QPointF(0, 0), 1750.0, -30.0),
    ("off_origin_anchor", QPointF(-750.0, 1200.0), 1750.0, 30.0),
]


class TestPolylineMouseVsHudParity:
    """The same vertex, clicked and typed, must land on the same point.

    Both routes end in ``_commit_polyline_at``, so the only thing that can
    differ is the point handed to it.  The mouse target is computed with
    ``SCHEMAS["line"].resolve`` rather than by hand, so a disagreement is
    always the production code's and never the test's own arithmetic.
    """

    @pytest.mark.parametrize("label,anchor,length,angle", _POLYLINE_CASES,
                             ids=[c[0] for c in _POLYLINE_CASES])
    def test_same_vertex_either_way(self, scene, view, label, anchor, length,
                                    angle):
        tip = SCHEMAS["line"].resolve(anchor, {"Length": length,
                                               "Angle": angle})
        pl_mouse = _start_polyline(scene, anchor)
        _click_vertex(scene, tip)
        mouse_pt = QPointF(pl_mouse._points[-1])

        pl_hud = _start_polyline(scene, anchor)
        _append_by_hud(scene, length, angle)
        hud_pt = QPointF(pl_hud._points[-1])

        assert mouse_pt.x() == pytest.approx(hud_pt.x(), abs=1e-6)
        assert mouse_pt.y() == pytest.approx(hud_pt.y(), abs=1e-6)


class TestPolylineUndoParity:
    """A typed vertex must push exactly as many undo states as a clicked one.

    For polyline that number is **zero**: undo is pushed once at *finalize*
    (``model_space.py``'s double-click branch), not per vertex.  The mouse is
    the reference, so both directions are pinned — the retired modal
    ``_DynInput`` polyline branch pushed per vertex, which put half-drawn
    polylines on the undo stack and is precisely the drift this task removes.
    """

    def _count_pushes(self, scene, monkeypatch):
        calls = []
        monkeypatch.setattr(scene, "push_undo_state",
                            lambda *a, **k: calls.append(1))
        return calls

    def test_clicked_vertex_pushes_nothing(self, scene, view, monkeypatch):
        pl = _start_polyline(scene)
        calls = self._count_pushes(scene, monkeypatch)
        _click_vertex(scene, QPointF(1000, 0))
        assert len(pl._points) == 2          # it really did append
        assert calls == []

    def test_typed_vertex_pushes_nothing_either(self, scene, view, monkeypatch):
        pl = _start_polyline(scene)
        calls = self._count_pushes(scene, monkeypatch)
        _append_by_hud(scene, 1000, 0)
        assert len(pl._points) == 2          # it really did append
        assert calls == []


# ── Task 12: rectangle ────────────────────────────────────────────────────


def _engage_rect(scene, anchor=QPointF(0, 0), from_centre=False):
    """Arm a rectangle placement and engage the HUD on it."""
    scene.set_mode("draw_rectangle")
    scene.single_place_mode = False
    scene._draw_rect_from_center = from_centre
    scene._draw_rect_anchor = QPointF(anchor)
    # Decoy seed 1 unit away, so a path reusing the published point fails.
    scene.publish_placement_state(anchor, QPointF(anchor.x() + 1.0,
                                                 anchor.y() - 1.0))
    assert scene.begin_dynamic_input() is True
    return scene.dynamic_input


def _rect_tuple(item):
    r = item.rect()
    return (r.x(), r.y(), r.width(), r.height())


class TestRectangleParity:
    """Corner mode: the typed rectangle and the dragged one must coincide.

    The schema's X/Y are **signed** (``seed_rectangle`` keeps the sign so
    ``resolve_rectangle`` round-trips the drag point exactly), because in
    corner mode the drag direction chooses the quadrant.  From-centre re-applies
    ``abs()`` and so ignores it.
    """

    def test_mouse_and_hud_agree(self, scene, view):
        scene.set_mode("draw_rectangle")
        scene.single_place_mode = False
        scene._draw_rect_from_center = False
        scene._draw_rect_anchor = QPointF(0, 0)
        assert scene._commit_draw_rectangle_at(QPointF(300.0, -200.0)) is True
        by_mouse = _rect_tuple(scene._draw_rects[-1])

        hud = _engage_rect(scene)
        hud.editor("X").setText("300")
        hud.editor("Y").setText("200")          # Y-up
        scene._on_dynamic_input_committed(hud.values())
        by_hud = _rect_tuple(scene._draw_rects[-1])

        assert by_hud == pytest.approx(by_mouse)

    def test_negative_extents_keep_the_dragged_quadrant(self, scene, view):
        """A left/down drag stays left/down — the sign is the geometry."""
        scene.set_mode("draw_rectangle")
        scene.single_place_mode = False
        scene._draw_rect_from_center = False
        scene._draw_rect_anchor = QPointF(0, 0)
        assert scene._commit_draw_rectangle_at(QPointF(-300.0, 200.0)) is True
        by_mouse = _rect_tuple(scene._draw_rects[-1])

        hud = _engage_rect(scene)
        hud.editor("X").setText("-300")
        hud.editor("Y").setText("-200")
        scene._on_dynamic_input_committed(hud.values())
        by_hud = _rect_tuple(scene._draw_rects[-1])

        assert by_hud == pytest.approx(by_mouse)
        # Non-vacuous: this really is the other quadrant from the positive case.
        assert by_mouse[0] < 0

    def test_from_centre_uses_half_extents(self, scene, view):
        hud = _engage_rect(scene, from_centre=True)
        hud.editor("X").setText("100")
        hud.editor("Y").setText("50")
        scene._on_dynamic_input_committed(hud.values())
        x, y, w, h = _rect_tuple(scene._draw_rects[-1])
        assert w == pytest.approx(200.0)        # half-extent 100 either side
        assert h == pytest.approx(100.0)
        assert x == pytest.approx(-100.0)
        assert y == pytest.approx(-50.0)

    def test_too_small_is_refused_and_keeps_the_hud_open(self, scene, view):
        """F1/D2: the schema minimum is 0.0, so 0.1 parses and the commit
        refuses it — the case that used to no-op after the HUD had closed."""
        hud = _engage_rect(scene)
        hud.editor("X").setText("0.1")
        hud.editor("Y").setText("0.1")
        scene._on_dynamic_input_committed(hud.values())

        assert len(scene._draw_rects) == 0
        assert scene.is_input_mode()
        assert hud.has_invalid_field()
        assert scene._draw_rect_anchor == QPointF(0, 0)

    def test_applier_reports_its_verdict(self, scene):
        scene.set_mode("draw_rectangle")
        scene._draw_rect_from_center = False
        scene._draw_rect_anchor = QPointF(0, 0)
        assert scene._commit_draw_rectangle_at(QPointF(0.1, 0.1)) is False
        scene._draw_rect_anchor = QPointF(0, 0)
        assert scene._commit_draw_rectangle_at(QPointF(300, -200)) is True
        scene._draw_rect_anchor = None
        assert scene._commit_draw_rectangle_at(QPointF(300, -200)) is False

    def test_commit_clears_anchor_preview_and_placement_state(self, scene, view):
        scene.set_mode("draw_rectangle")
        scene.single_place_mode = False
        scene._draw_rect_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(300, -200))
        scene._commit_draw_rectangle_at(QPointF(300.0, -200.0))
        assert scene._draw_rect_anchor is None
        assert scene._draw_rect_preview is None
        assert scene.get_resolved_point() is None

    def test_move_publishes_instead_of_painting_a_hint(self, scene, view):
        scene.set_mode("draw_rectangle")
        # The first press arms the anchor *and* builds the preview rect, which
        # the move branch requires; pre-setting the anchor would instead send
        # this press down the commit branch.
        scene._press_draw_rectangle(_FakeEvent(), QPointF(0, 0), QPointF(0, 0),
                                    None, None, None)
        assert scene._draw_rect_preview is not None
        scene._move_draw_rectangle(_FakeEvent(), QPointF(300, -200))
        pt = scene.get_resolved_point()
        assert pt is not None
        assert pt.x() == pytest.approx(300.0, abs=1e-6)
        assert pt.y() == pytest.approx(-200.0, abs=1e-6)
        assert scene._draw_dim_hint is None

    def test_hud_commit_pushes_exactly_one_undo_state(self, scene, view,
                                                      monkeypatch):
        hud = _engage_rect(scene)
        hud.editor("X").setText("300")
        hud.editor("Y").setText("200")
        calls = []
        monkeypatch.setattr(scene, "push_undo_state",
                            lambda *a, **k: calls.append(1))
        scene._on_dynamic_input_committed(hud.values())
        assert len(scene._draw_rects) == 1
        assert calls == [1]


# ── Task 13: circle ───────────────────────────────────────────────────────


def _engage_circle(scene, centre=QPointF(0, 0)):
    """Arm a circle placement and engage the HUD on it."""
    scene.set_mode("draw_circle")
    scene.single_place_mode = False
    scene._draw_circle_center = QPointF(centre)
    scene.publish_placement_state(centre, QPointF(centre.x() + 1.0, centre.y()))
    assert scene.begin_dynamic_input() is True
    return scene.dynamic_input


class TestCircleParity:
    """F6: ``resolve_circle`` picks an arbitrary direction because the commit
    takes ``hypot``.  That cross-module dependency is pinned here, at the seam.
    """

    def test_mouse_and_hud_agree(self, scene, view):
        scene.set_mode("draw_circle")
        scene.single_place_mode = False
        scene._draw_circle_center = QPointF(0, 0)
        assert scene._commit_draw_circle_at(QPointF(120.0, 0.0)) is True
        by_mouse = scene._draw_circles[-1].rect()

        hud = _engage_circle(scene)
        hud.editor("Radius").setText("120")
        scene._on_dynamic_input_committed(hud.values())
        by_hud = scene._draw_circles[-1].rect()

        assert by_hud.width() == pytest.approx(by_mouse.width())
        assert by_hud.center().x() == pytest.approx(by_mouse.center().x())
        assert by_hud.center().y() == pytest.approx(by_mouse.center().y())

    def test_radius_direction_is_irrelevant(self, scene, view):
        """Any rim point of the same magnitude yields the same circle, which is
        what lets ``resolve_circle`` emit a bare +X point."""
        scene.set_mode("draw_circle")
        scene.single_place_mode = False
        scene._draw_circle_center = QPointF(0, 0)
        scene._commit_draw_circle_at(QPointF(0.0, -50.0))
        a = scene._draw_circles[-1].rect()

        scene._draw_circle_center = QPointF(0, 0)
        scene._commit_draw_circle_at(QPointF(50.0, 0.0))
        b = scene._draw_circles[-1].rect()

        assert a.width() == pytest.approx(b.width())
        assert a.center().x() == pytest.approx(b.center().x())
        assert a.center().y() == pytest.approx(b.center().y())

    def test_hud_radius_is_measured_from_the_centre(self, scene, view):
        hud = _engage_circle(scene, QPointF(250.0, -400.0))
        hud.editor("Radius").setText("120")
        scene._on_dynamic_input_committed(hud.values())
        r = scene._draw_circles[-1].rect()
        assert r.center().x() == pytest.approx(250.0, abs=1e-6)
        assert r.center().y() == pytest.approx(-400.0, abs=1e-6)
        assert r.width() == pytest.approx(240.0, abs=1e-6)

    def test_too_small_is_refused_and_keeps_the_hud_open(self, scene, view):
        hud = _engage_circle(scene)
        hud.editor("Radius").setText("0.1")
        scene._on_dynamic_input_committed(hud.values())

        assert len(scene._draw_circles) == 0
        assert scene.is_input_mode()
        assert hud.has_invalid_field()
        # The placement survives, so retyping is possible — the circle path used
        # to clear the centre even when it rejected.
        assert scene._draw_circle_center == QPointF(0, 0)

    def test_refused_circle_pushes_no_undo_state(self, scene, view, monkeypatch):
        """It used to push one for a circle it never created."""
        scene.set_mode("draw_circle")
        scene._draw_circle_center = QPointF(0, 0)
        calls = []
        monkeypatch.setattr(scene, "push_undo_state",
                            lambda *a, **k: calls.append(1))
        assert scene._commit_draw_circle_at(QPointF(0.1, 0.0)) is False
        assert calls == []

    def test_applier_reports_its_verdict(self, scene):
        scene.set_mode("draw_circle")
        scene._draw_circle_center = QPointF(0, 0)
        assert scene._commit_draw_circle_at(QPointF(0.1, 0.0)) is False
        scene._draw_circle_center = QPointF(0, 0)
        assert scene._commit_draw_circle_at(QPointF(120, 0)) is True
        scene._draw_circle_center = None
        assert scene._commit_draw_circle_at(QPointF(120, 0)) is False

    def test_commit_clears_centre_preview_and_placement_state(self, scene, view):
        scene.set_mode("draw_circle")
        scene.single_place_mode = False
        scene._draw_circle_center = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(120, 0))
        scene._commit_draw_circle_at(QPointF(120.0, 0.0))
        assert scene._draw_circle_center is None
        assert scene._draw_circle_preview is None
        assert scene.get_resolved_point() is None

    def test_move_publishes_instead_of_painting_a_hint(self, scene, view):
        scene.set_mode("draw_circle")
        scene._press_draw_circle(_FakeEvent(), QPointF(0, 0), QPointF(0, 0),
                                 None, None, None)
        assert scene._draw_circle_preview is not None
        scene._move_draw_circle(_FakeEvent(), QPointF(120, 0))
        pt = scene.get_resolved_point()
        assert pt is not None
        assert pt.x() == pytest.approx(120.0, abs=1e-6)
        assert scene._draw_dim_hint is None

    def test_hud_commit_pushes_exactly_one_undo_state(self, scene, view,
                                                      monkeypatch):
        hud = _engage_circle(scene)
        hud.editor("Radius").setText("120")
        calls = []
        monkeypatch.setattr(scene, "push_undo_state",
                            lambda *a, **k: calls.append(1))
        scene._on_dynamic_input_committed(hud.values())
        assert len(scene._draw_circles) == 1
        assert calls == [1]


class TestApplierRejectionKeepsTheHudOpen:
    """D2: the applier reports its verdict; the schema does not mirror it.

    The too-short/too-small threshold lives in the commit path.  Copying it
    into the schema's ``minimum`` was rejected as unexpressible (rectangle's
    X/Y are signed) and as a mirrored guard that would drift.  So an applier
    returns False and the HUD stays open with the offending field flagged,
    instead of the placement silently evaporating into a status-bar message
    the user never sees because the HUD has already closed.
    """

    def _engage(self, scene, anchor=QPointF(0, 0)):
        scene.set_mode("draw_line")
        scene.single_place_mode = False
        scene._draw_line_anchor = QPointF(anchor)
        scene.publish_placement_state(anchor, QPointF(anchor.x() + 1000.0,
                                                     anchor.y()))
        assert scene.begin_dynamic_input() is True
        return scene.dynamic_input

    def test_too_short_typed_line_keeps_the_hud_engaged(self, scene, view):
        """0.3 parses (minimum is 0.0) and resolves, then the commit refuses."""
        hud = self._engage(scene)
        hud.editor("Length").setText("0.3")
        hud.editor("Angle").setText("0")
        scene._on_dynamic_input_committed(hud.values())

        assert len(scene._draw_lines) == 0
        assert scene.is_input_mode(), "HUD closed on a refused commit"
        assert scene.dynamic_input is hud

    def test_refusal_flags_the_offending_field(self, scene, view):
        hud = self._engage(scene)
        hud.editor("Length").setText("0.3")
        hud.editor("Angle").setText("0")
        scene._on_dynamic_input_committed(hud.values())
        assert hud.has_invalid_field()

    def test_the_anchor_survives_a_refusal(self, scene, view):
        """The placement is still live, so the user can simply retype."""
        hud = self._engage(scene, QPointF(120.0, 340.0))
        hud.editor("Length").setText("0.3")
        hud.editor("Angle").setText("0")
        scene._on_dynamic_input_committed(hud.values())
        assert scene._draw_line_anchor == QPointF(120.0, 340.0)

    def test_retyping_a_valid_length_then_commits(self, scene, view):
        """The recovery path: refusal must not wedge the HUD."""
        hud = self._engage(scene)
        hud.editor("Length").setText("0.3")
        hud.editor("Angle").setText("0")
        scene._on_dynamic_input_committed(hud.values())
        assert len(scene._draw_lines) == 0

        ed = hud.editor("Length")
        ed.selectAll()
        QTest.keyClicks(ed, "1000")
        scene._on_dynamic_input_committed(hud.values())

        assert len(scene._draw_lines) == 1
        assert scene._draw_lines[-1].line().p2().x() == pytest.approx(1000.0,
                                                                     abs=1e-6)
        assert not scene.is_input_mode(), "HUD stayed open after a real commit"

    def test_a_successful_commit_still_closes_the_hud(self, scene, view):
        """The other direction, so the refusal branch cannot swallow everything."""
        hud = self._engage(scene)
        hud.editor("Length").setText("1000")
        hud.editor("Angle").setText("0")
        scene._on_dynamic_input_committed(hud.values())
        assert len(scene._draw_lines) == 1
        assert not scene.is_input_mode()

    def test_appliers_report_their_verdict(self, scene):
        """The protocol itself: True on commit, False on refusal or no anchor."""
        scene.set_mode("draw_line")
        scene._draw_line_anchor = QPointF(0, 0)
        assert scene._commit_draw_line_at(QPointF(1000, 0)) is True

        scene._draw_line_anchor = QPointF(0, 0)
        assert scene._commit_draw_line_at(QPointF(0.1, 0)) is False

        scene._draw_line_anchor = None
        assert scene._commit_draw_line_at(QPointF(1000, 0)) is False

    def test_polyline_applier_reports_its_verdict(self, scene, view):
        pl = _start_polyline(scene)
        assert scene._commit_polyline_at(QPointF(1000, 0)) is True
        assert len(pl._points) == 2
        scene.set_mode("select")
        scene.set_mode("polyline")
        assert scene._commit_polyline_at(QPointF(1000, 0)) is False

    def test_apply_dynamic_input_forwards_the_verdict(self, scene):
        scene.set_mode("draw_line")
        scene._draw_line_anchor = QPointF(0, 0)
        assert scene.apply_dynamic_input(QPointF(0.1, 0)) is False
        scene._draw_line_anchor = QPointF(0, 0)
        assert scene.apply_dynamic_input(QPointF(1000, 0)) is True


class _FakeDblEvent:
    """Minimal double-click event: left button, accept() is a no-op."""

    def button(self):
        return Qt.MouseButton.LeftButton

    def accept(self):
        pass


class TestPolylineDoubleClickFinish:
    """Double-click finishes at the last *single-clicked* vertex.

    Qt delivers Press → Release → DblClick → Release for a double click, so it
    contributes exactly **one** extra press — the same thing the neighbouring
    pipe branch's comment says ("fires a press first").  The polyline branch
    popped two vertices, which discarded a genuinely placed one: the segment
    under the ghost *and* the last committed segment both vanished on finish.
    """

    def _finish(self, scene, pts):
        """Single-click every point in *pts*, then double-click one past the end."""
        pl = _start_polyline(scene, pts[0])
        for p in pts[1:]:
            _click_vertex(scene, p)
        return pl

    def test_double_click_keeps_every_single_clicked_segment(self, scene, view):
        pl = self._finish(scene, [QPointF(0, 0), QPointF(1000, 0),
                                  QPointF(2000, 0)])
        # Qt's own press for the double click lands first, at the ghost's tip.
        _click_vertex(scene, QPointF(3000, 0))
        scene.mouseDoubleClickEvent(_FakeDblEvent())

        assert [(p.x(), p.y()) for p in pl._points] == [
            (0.0, 0.0), (1000.0, 0.0), (2000.0, 0.0)]

    def test_the_ghost_tip_vertex_is_the_one_dropped(self, scene, view):
        """Only the double-click's own vertex goes — nothing the user clicked."""
        pl = self._finish(scene, [QPointF(0, 0), QPointF(1000, 0),
                                  QPointF(2000, 0)])
        _click_vertex(scene, QPointF(3000, 0))
        assert len(pl._points) == 4          # the extra vertex really was added
        scene.mouseDoubleClickEvent(_FakeDblEvent())
        assert len(pl._points) == 3          # exactly one removed, not two

    def test_finish_finalizes_and_clears_the_active_polyline(self, scene, view):
        pl = self._finish(scene, [QPointF(0, 0), QPointF(1000, 0),
                                  QPointF(2000, 0)])
        _click_vertex(scene, QPointF(3000, 0))
        scene.mouseDoubleClickEvent(_FakeDblEvent())
        assert scene._polyline_active is None
        assert pl.isSelected()

    def test_two_point_polyline_survives_the_finish(self, scene, view):
        """The minimum viable polyline is not popped out of existence."""
        pl = self._finish(scene, [QPointF(0, 0), QPointF(1000, 0)])
        scene.mouseDoubleClickEvent(_FakeDblEvent())
        assert len(pl._points) == 2
        assert scene._polyline_active is None

    def test_finish_pushes_one_undo_state(self, scene, view, monkeypatch):
        """Undo is pushed at finalize — the counterpart to the per-vertex
        push that ``_commit_polyline_at`` deliberately omits."""
        pl = self._finish(scene, [QPointF(0, 0), QPointF(1000, 0),
                                  QPointF(2000, 0)])
        _click_vertex(scene, QPointF(3000, 0))
        calls = []
        monkeypatch.setattr(scene, "push_undo_state",
                            lambda *a, **k: calls.append(1))
        scene.mouseDoubleClickEvent(_FakeDblEvent())
        assert calls == [1]


class TestPolylineReadout:
    """``_move_polyline`` publishes placement state instead of a painted hint."""

    def test_move_publishes_the_constrained_point(self, scene, view):
        _start_polyline(scene)
        scene._move_polyline(_FakeEvent(), QPointF(1000, -500))
        pt = scene.get_resolved_point()
        assert pt is not None
        assert pt.x() == pytest.approx(1000.0, abs=1e-6)
        assert pt.y() == pytest.approx(-500.0, abs=1e-6)

    def test_move_leaves_no_painted_hint(self, scene, view):
        """One HUD, not two (S1): the widget is the readout."""
        _start_polyline(scene)
        scene._move_polyline(_FakeEvent(), QPointF(1000, -500))
        assert scene._draw_dim_hint is None

    def test_ctrl_constrained_point_is_what_gets_published(self, scene, view):
        """Publishing after the Ctrl constraint is what keeps readout and seed
        from disagreeing with the preview."""
        pl = _start_polyline(scene)
        raw = QPointF(1000, 300)             # ~16.7° — off any snap increment
        scene._move_polyline(_FakeEvent(ctrl=True), raw)
        expected = scene._constrain_angle(pl._points[-1], raw)
        pt = scene.get_resolved_point()
        assert pt.x() == pytest.approx(expected.x(), abs=1e-6)
        assert pt.y() == pytest.approx(expected.y(), abs=1e-6)
        # Non-vacuous: the constraint genuinely would have moved the raw point.
        assert math.hypot(expected.x() - raw.x(),
                          expected.y() - raw.y()) > 1.0


# ── Gridline replicate (T16) ──────────────────────────────────────────────
#
# The two transform schemas.  A vertical source gridline is used throughout
# because its perpendicular vector is exactly ``(-1, 0)``: a cursor at +X
# therefore yields a *negative* ``_replicate_spacing``, which is what makes the
# sign handling below testable rather than incidental.


def _armed_replicate(scene, kind, cursor_x=800.0, count=1):
    """Arm a gridline replicate placement with the cursor at *cursor_x*.

    The signed spacing comes from driving the real move handler rather than
    from assigning ``_replicate_spacing``, so the sign under test is the one
    the cursor actually produces.

    Returns:
        The source ``GridlineItem``.
    """
    src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
    scene.addItem(src)
    scene._gridlines.append(src)
    scene._start_gridline_replicate(src, kind)
    scene._replicate_count = count          # after: _start resets it to 1
    scene._move_gridline_replicate(None, QPointF(cursor_x, 2500.0))
    return src


class TestGridlineReplicateReadout:
    """The transform modes carry a passive HUD like every placement mode."""

    def test_engages_without_a_placement_anchor(self, scene, view):
        """The engage gate's anchor test is conditioned on ``is_placement``."""
        _armed_replicate(scene, "offset")
        assert scene.get_placement_anchor() is None
        assert scene.begin_dynamic_input() is True

    def test_readout_appears_without_engaging(self, scene, view):
        _armed_replicate(scene, "offset")
        scene._sync_dynamic_input()
        assert scene.dynamic_input is not None
        assert not scene.is_input_mode()

    def test_move_leaves_no_painted_hint(self, scene, view):
        """One HUD, not two (S1): the widget is the readout."""
        _armed_replicate(scene, "array", count=4)
        assert scene._draw_dim_hint is None

    def test_seed_is_the_magnitude_of_the_signed_projection(self, scene, view):
        """``Distance`` has ``minimum=0.0``, so a signed seed is unreadable.

        The side is the cursor's, carried in ``_replicate_spacing``; the field
        holds the magnitude the user types against.
        """
        _armed_replicate(scene, "offset", cursor_x=2400.0)
        assert scene._replicate_spacing == pytest.approx(-2400.0)
        scene.begin_dynamic_input()
        assert scene.dynamic_input.values()["Distance"] == pytest.approx(2400.0)

    def test_array_seeds_spacing_magnitude_and_count(self, scene, view):
        _armed_replicate(scene, "array", cursor_x=-1200.0, count=3)
        scene.begin_dynamic_input()
        vals = scene.dynamic_input.values()
        assert vals["Spacing"] == pytest.approx(1200.0)
        assert vals["Count"] == pytest.approx(3.0)


class TestGridlineReplicateAppliers:
    """Enter places the copies — it does not merely redraw the ghost.

    Updating the preview and closing would strand the typed value: the HUD
    tears down on a successful commit and the next mouse move recomputes
    ``_replicate_spacing`` from the cursor, silently discarding what was typed.
    """

    def test_typed_distance_places_one_copy_on_the_cursor_side(self, scene, view):
        _armed_replicate(scene, "offset", cursor_x=800.0)
        before = len(scene._gridlines)
        scene.begin_dynamic_input()
        scene.dynamic_input.editor("Distance").setText("1500")
        scene.dynamic_input._accept()
        assert len(scene._gridlines) == before + 1
        # +X, the side the cursor established — never mirrored to -1500 by the
        # negative sign the projection carries.
        assert scene._gridlines[-1].grip_points()[0].x() == pytest.approx(1500.0)

    def test_typed_distance_follows_the_cursor_to_the_other_side(self, scene, view):
        _armed_replicate(scene, "offset", cursor_x=-800.0)
        scene.begin_dynamic_input()
        scene.dynamic_input.editor("Distance").setText("1500")
        scene.dynamic_input._accept()
        assert scene._gridlines[-1].grip_points()[0].x() == pytest.approx(-1500.0)

    def test_array_places_count_copies_at_typed_spacing(self, scene, view):
        _armed_replicate(scene, "array", cursor_x=500.0, count=1)
        before = len(scene._gridlines)
        scene.begin_dynamic_input()
        scene.dynamic_input.editor("Spacing").setText("1000")
        scene.dynamic_input.editor("Count").setText("4")
        scene.dynamic_input._accept()
        assert len(scene._gridlines) == before + 4
        xs = sorted(round(g.grip_points()[0].x(), 1)
                    for g in scene._gridlines[-4:])
        assert xs == [1000.0, 2000.0, 3000.0, 4000.0]

    def test_commit_closes_the_hud_and_ends_the_mode(self, scene, view):
        _armed_replicate(scene, "offset")
        scene.begin_dynamic_input()
        scene.dynamic_input.editor("Distance").setText("1500")
        scene.dynamic_input._accept()
        assert scene.dynamic_input is None
        assert scene.mode == "select"
        assert scene._replicate_source is None

    def test_undo_removes_the_typed_copies_in_one_step(self, scene, view):
        _armed_replicate(scene, "array", cursor_x=500.0, count=1)
        scene.push_undo_state()
        before = len(scene._gridlines)
        scene.begin_dynamic_input()
        scene.dynamic_input.editor("Spacing").setText("1000")
        scene.dynamic_input.editor("Count").setText("3")
        scene.dynamic_input._accept()
        assert len(scene._gridlines) == before + 3
        scene.undo()
        assert len(scene._gridlines) == before


class TestGridlineReplicateRejection:
    """D2: the applier reports its verdict; a refusal keeps the HUD open."""

    def test_distance_under_the_floor_is_refused(self, scene, view):
        _armed_replicate(scene, "offset")
        before = len(scene._gridlines)
        scene.begin_dynamic_input()
        # Parses and resolves fine (the field minimum is 0.0); the commit path
        # is what rejects it, at the same abs(dist) < 0.5 floor the click uses.
        scene.dynamic_input.editor("Distance").setText("0.2")
        scene.dynamic_input._accept()
        assert len(scene._gridlines) == before

    def test_a_refusal_keeps_the_placement_live(self, scene, view):
        _armed_replicate(scene, "offset")
        scene.begin_dynamic_input()
        scene.dynamic_input.editor("Distance").setText("0.2")
        scene.dynamic_input._accept()
        assert scene.dynamic_input is not None
        assert scene.dynamic_input.has_invalid_field() is True
        assert scene.mode == "gridline_offset"
        assert scene._replicate_source is not None

    def test_a_refused_spacing_still_shows_the_typed_count(self, scene, view):
        """The count is accepted independently of the spacing that was refused."""
        _armed_replicate(scene, "array", cursor_x=800.0, count=1)
        scene.begin_dynamic_input()
        scene.dynamic_input.editor("Spacing").setText("0.2")
        scene.dynamic_input.editor("Count").setText("3")
        scene.dynamic_input._accept()
        assert scene._replicate_count == 3
        assert len(scene._replicate_ghost) == 3

    def test_count_below_one_is_refused_by_the_field(self, scene, view):
        _armed_replicate(scene, "array", cursor_x=500.0, count=3)
        before = len(scene._gridlines)
        scene.begin_dynamic_input()
        scene.dynamic_input.editor("Count").setText("0")
        scene.dynamic_input._accept()
        assert scene.dynamic_input.has_invalid_field() is True
        assert len(scene._gridlines) == before


class TestGridlineReplicateParity:
    """A typed distance and the same distance walked to with the mouse agree."""

    def test_mouse_and_hud_agree(self, scene, view):
        _armed_replicate(scene, "offset", cursor_x=1500.0)
        scene._commit_gridline_replicate()
        mouse_x = scene._gridlines[-1].grip_points()[0].x()

        # Same magnitude typed from a cursor nowhere near it.
        _armed_replicate(scene, "offset", cursor_x=800.0)
        scene.begin_dynamic_input()
        scene.dynamic_input.editor("Distance").setText("1500")
        scene.dynamic_input._accept()
        hud_x = scene._gridlines[-1].grip_points()[0].x()

        assert hud_x == pytest.approx(mouse_x)
        assert mouse_x == pytest.approx(1500.0)   # non-vacuous


# ── Move displacement (T15) ───────────────────────────────────────────────
#
# ``move`` is a transform schema (resolves to a dict, not a point) that
# *nonetheless has an anchor* — the base point, ``node_start_pos``.  That is
# what distinguishes it from the gridline replicate transforms, which are
# anchorless, and it is why the displacement schema carries ``needs_anchor``:
# the HUD must stay shut until the base point is picked, or it would float a
# dead ``0,0`` readout the moment move mode is entered.


def _arm_move(scene, base, moved_item):
    """Enter move mode with *moved_item* selected and *base* as the base point.

    Mirrors the real flow: ``_selected_items`` is what ``move_items`` reads,
    and ``node_start_pos`` is the base point the second click would have set.
    """
    scene.set_mode("move")
    scene._selected_items = [moved_item]
    scene.node_start_pos = QPointF(base)


class TestMoveHudGate:
    """The move HUD is gated on the base point, unlike the anchorless transforms."""

    def test_no_hud_before_the_base_point(self, scene, view):
        """Entering move mode is not enough — there is nothing to read out yet."""
        scene.set_mode("move")
        scene._selected_items = [Node(0, 0)]
        assert scene.node_start_pos is None
        assert scene.get_placement_anchor() is None
        assert scene._hud_available() is False
        assert scene.begin_dynamic_input(seed="1") is False
        assert scene.dynamic_input is None

    def test_hud_available_once_the_base_point_is_set(self, scene, view):
        _arm_move(scene, QPointF(0, 0), Node(0, 0))
        assert scene.get_placement_anchor() == QPointF(0, 0)
        assert scene._hud_available() is True
        assert scene.begin_dynamic_input() is True

    def test_move_handler_publishes_the_live_offset(self, scene, view):
        """After the base point, the move handler feeds the HUD (no painted hint)."""
        _arm_move(scene, QPointF(0, 0), Node(0, 0))
        scene._move_paste_move(_FakeEvent(), QPointF(300, -200))
        pt = scene.get_resolved_point()
        assert pt is not None
        scene.begin_dynamic_input()
        vals = scene.dynamic_input.values()
        assert vals["dX"] == pytest.approx(300.0)
        assert vals["dY"] == pytest.approx(200.0)      # Y-up: -scene Y


class TestMoveApplier:
    """Typed dX/dY moves the selection and ends the mode (transform applier)."""

    def test_offset_is_y_up(self, scene, view):
        _arm_move(scene, QPointF(0, 0), Node(0, 0))
        moved = []
        scene.move_items = lambda off: moved.append(off)
        scene.begin_dynamic_input()
        scene.dynamic_input.editor("dX").setText("100")
        scene.dynamic_input.editor("dY").setText("50")
        scene.dynamic_input._accept()
        assert moved[0].x() == pytest.approx(100.0)
        assert moved[0].y() == pytest.approx(-50.0)    # dY up = -scene Y

    def test_negative_components_allowed(self, scene, view):
        _arm_move(scene, QPointF(0, 0), Node(0, 0))
        moved = []
        scene.move_items = lambda off: moved.append(off)
        scene.begin_dynamic_input()
        scene.dynamic_input.editor("dX").setText("-25")
        scene.dynamic_input.editor("dY").setText("-10")
        scene.dynamic_input._accept()
        assert moved[0].x() == pytest.approx(-25.0)
        assert moved[0].y() == pytest.approx(10.0)

    def test_commit_closes_the_hud_and_exits_move_mode(self, scene, view):
        _arm_move(scene, QPointF(0, 0), Node(0, 0))
        scene.move_items = lambda off: None
        scene.begin_dynamic_input()
        scene.dynamic_input.editor("dX").setText("10")
        scene.dynamic_input._accept()
        assert scene.node_start_pos is None
        assert scene.mode in (None, "select")
        assert scene.dynamic_input is None

    def test_the_selection_really_moves(self, scene, view):
        node = Node(0, 0)
        scene.addItem(node)
        _arm_move(scene, QPointF(0, 0), node)
        scene.begin_dynamic_input()
        scene.dynamic_input.editor("dX").setText("300")
        scene.dynamic_input.editor("dY").setText("200")
        scene.dynamic_input._accept()
        assert node.scenePos().x() == pytest.approx(300.0)
        assert node.scenePos().y() == pytest.approx(-200.0)

    def test_undo_reverses_the_typed_move_in_one_step(self, scene, view):
        # Registered through the sprinkler system so the undo snapshot captures
        # it — a bare addItem'd Node is invisible to _capture_network.
        node = scene.add_node(0, 0)
        scene.push_undo_state()
        _arm_move(scene, QPointF(0, 0), node)
        scene.begin_dynamic_input()
        scene.dynamic_input.editor("dX").setText("300")
        scene.dynamic_input._accept()
        assert node.scenePos().x() == pytest.approx(300.0)
        scene.undo()
        node_after = next(n for n in scene.items() if isinstance(n, Node))
        assert node_after.scenePos().x() == pytest.approx(0.0)


class TestMoveParity:
    """A typed displacement and the same displacement dragged agree."""

    def test_mouse_and_hud_agree(self, scene, view):
        drag = QPointF(300, -200)          # +300 right, 200 up (scene Y down)

        node_mouse = Node(1000, 1000)
        scene.addItem(node_mouse)
        _arm_move(scene, QPointF(0, 0), node_mouse)
        # The click path takes the offset from base point to the release point.
        scene._press_paste_move(_FakeEvent(), None, drag, None, None, None)
        mouse_pos = node_mouse.scenePos()

        node_hud = Node(1000, 1000)
        scene.addItem(node_hud)
        _arm_move(scene, QPointF(0, 0), node_hud)
        scene.begin_dynamic_input()
        scene.dynamic_input.editor("dX").setText("300")
        scene.dynamic_input.editor("dY").setText("200")   # Y-up magnitude
        scene.dynamic_input._accept()
        hud_pos = node_hud.scenePos()

        assert hud_pos.x() == pytest.approx(mouse_pos.x())
        assert hud_pos.y() == pytest.approx(mouse_pos.y())
        assert mouse_pos.x() == pytest.approx(1300.0)      # non-vacuous


class TestPasteStaysOutOfTheHud:
    """F2: paste shares node_start_pos and the handler but must not open a HUD.

    ``paste`` commits via ``paste_items``, ``move`` via ``move_items``.  Adding
    paste to the HUD without its own applier would engage on a paste and commit
    it as a move of the current selection, so paste is deliberately absent from
    both the schema and applier tables and from ``get_placement_anchor``.
    """

    def test_paste_has_no_anchor_even_with_a_base_point(self, scene, view):
        scene.set_mode("paste")
        scene.node_start_pos = QPointF(0, 0)
        assert scene.get_placement_anchor() is None

    def test_paste_mode_opens_no_hud(self, scene, view):
        scene.set_mode("paste")
        scene.node_start_pos = QPointF(0, 0)
        assert scene.active_schema() is None
        assert scene._hud_available() is False
        assert scene.begin_dynamic_input(seed="1") is False
        assert scene.dynamic_input is None


# ── Task 3: ghost updates on each field commit ────────────────────────────
#
# While a HUD field is engaged the mouse is inert (§4.5), so the placement
# ghost would sit frozen at its engage-time seed.  Each Tab field-commit fires
# ``fieldCommitted``; the scene re-resolves the HUD's *current* values through
# the active schema and redraws the same preview the mouse would — so typing a
# Length then Tab moves the ghost, and typing an Angle then Tab moves it again.


class TestGhostUpdatesOnFieldCommit:
    """A field-commit (Tab) redraws the placement ghost from what was typed."""

    def _engage(self, scene, view, anchor=QPointF(0, 0)):
        """Arm a draw_line placement, seed a decoy, and engage the HUD.

        The published seed is deliberately far from any value the test types,
        so a ghost still sitting on the seed cannot masquerade as a ghost that
        followed the typed field.
        """
        scene.set_mode("draw_line")
        scene.single_place_mode = False
        scene._draw_line_anchor = QPointF(anchor)
        scene.publish_placement_state(anchor, QPointF(anchor.x() + 800.0,
                                                      anchor.y()))
        assert scene.begin_dynamic_input() is True
        return scene.dynamic_input

    def test_ghost_updates_on_field_commit_line(self, scene, view):
        hud = self._engage(scene, view)

        ed = hud.editor("Length")
        ed.selectAll()
        ed.setText("1200")
        QTest.keyClick(ed, Qt.Key.Key_Tab)          # commits Length, wraps focus

        line = scene.preview_pipe.line()
        assert abs(line.x2() - 1200) < 1e-6, "ghost length follows typed Length"
        assert abs(line.y2()) < 1e-6, "angle still at its 0° seed"

        ea = hud.editor("Angle")
        ea.selectAll()
        ea.setText("90")
        QTest.keyClick(ea, Qt.Key.Key_Tab)          # commits Angle

        line = scene.preview_pipe.line()
        assert abs(line.x2()) < 1e-3 and abs(line.y2() + 1200) < 1e-3, (
            "ghost follows typed Angle (Y-up: 90° points to -y)")

    def _engage_rect(self, scene, view, anchor=QPointF(0, 0)):
        """First-click a rectangle, seed a decoy far corner, and engage.

        Drives the real press/move path (not the bare ``_engage_rect`` helper)
        so ``_draw_rect_preview`` actually exists for the ghost to follow, and
        seeds a decoy corner far from the value the test types.
        """
        scene.set_mode("draw_rectangle")
        scene.single_place_mode = False
        scene._press_draw_rectangle(_FakeEvent(), None, QPointF(anchor),
                                    None, None, None)
        scene._move_draw_rectangle(_FakeEvent(),
                                   QPointF(anchor.x() + 800.0,
                                           anchor.y() - 400.0))    # decoy
        assert scene.begin_dynamic_input() is True
        return scene.dynamic_input

    def test_ghost_updates_on_field_commit_rectangle(self, scene, view):
        # Confirmation: rectangle is a placement schema, so Task 3's handler
        # already redraws its ghost on field-commit.  X/Y are SIGNED and Y-up
        # (resolve_rectangle does anchor.y() - Y); the preview normalises.
        hud = self._engage_rect(scene, view)

        ed = hud.editor("X")
        ed.selectAll()
        ed.setText("1000")
        QTest.keyClick(ed, Qt.Key.Key_Tab)          # commits X, wraps focus

        ey = hud.editor("Y")
        ey.selectAll()
        ey.setText("500")
        QTest.keyClick(ey, Qt.Key.Key_Tab)          # commits Y

        rect = scene._draw_rect_preview.rect()
        # Corner mode from (0,0): far corner = (1000, -500) → normalised rect
        # spans width 1000, height 500 (and the decoy 800×400 is gone).
        assert rect.width() == pytest.approx(1000.0), "width follows typed X"
        assert rect.height() == pytest.approx(500.0), "height follows typed Y"

    def _engage_circle(self, scene, view, centre=QPointF(0, 0)):
        """First-click a circle centre, seed a decoy rim, and engage."""
        scene.set_mode("draw_circle")
        scene.single_place_mode = False
        scene._press_draw_circle(_FakeEvent(), None, QPointF(centre),
                                 None, None, None)
        scene._move_draw_circle(_FakeEvent(),
                                QPointF(centre.x() + 200.0, centre.y()))  # decoy
        assert scene.begin_dynamic_input() is True
        return scene.dynamic_input

    def test_ghost_updates_on_field_commit_circle(self, scene, view):
        # Confirmation: circle is a placement schema — the handler redraws it.
        # _preview_from_circle sets the ellipse rect to (cx-r, cy-r, 2r, 2r).
        hud = self._engage_circle(scene, view)

        ed = hud.editor("Radius")
        ed.selectAll()
        ed.setText("750")
        QTest.keyClick(ed, Qt.Key.Key_Tab)          # commits Radius

        rect = scene._draw_circle_preview.rect()
        assert rect.width() == pytest.approx(1500.0), "diameter follows Radius"
        assert rect.height() == pytest.approx(1500.0)
        assert rect.center().x() == pytest.approx(0.0), "still centred on centre"
        assert rect.center().y() == pytest.approx(0.0)

    def _engage_move(self, scene, view, base=QPointF(0, 0)):
        """Arm move on a Node at *base*, build its ghost base, and engage.

        Mirrors ``_press_paste_move``'s first click: it sets ``node_start_pos``
        and builds ``_move_ghost_base`` from the live selection.  A decoy drag
        seeds the ghost far from the value the test types.
        """
        node = Node(base.x(), base.y())
        scene.addItem(node)
        scene.set_mode("move")
        scene._selected_items = [node]
        scene.node_start_pos = QPointF(base)
        scene._move_ghost_base = scene._build_move_ghost_base(is_paste=False)
        scene._preview_from_move(QPointF(base.x() + 800.0, base.y()))  # decoy
        assert scene.begin_dynamic_input() is True
        return scene.dynamic_input, node

    def test_ghost_updates_on_field_commit_move(self, scene, view):
        # move is a TRANSFORM schema (returns_point False).  Its schema resolves
        # to {"offset": QPointF}; the field-commit handler must convert that to
        # the target point the base lands on (base + offset) for the ghost.
        hud, node = self._engage_move(scene, view)

        ed = hud.editor("dX")
        ed.selectAll()
        ed.setText("300")
        QTest.keyClick(ed, Qt.Key.Key_Tab)          # commits dX, wraps focus

        ey = hud.editor("dY")
        ey.selectAll()
        ey.setText("200")
        QTest.keyClick(ey, Qt.Key.Key_Tab)          # commits dY

        # Y-up: dY 200 = scene -200.  Ghost = base silhouette translated by
        # (300, -200) from _move_ghost_base.
        assert scene._move_ghost, "the ghost is populated after commit"
        base = scene._move_ghost_base[0]
        got = scene._move_ghost[0]
        assert got.boundingRect().center().x() == pytest.approx(
            base.boundingRect().center().x() + 300.0), "ghost dX follows typed"
        assert got.boundingRect().center().y() == pytest.approx(
            base.boundingRect().center().y() - 200.0), "ghost dY is Y-up"


# ── Task 5: arc commit extraction ─────────────────────────────────────────
#
# Arc was the only multi-click mode whose third-click commit lived inline in
# ``_press_draw_arc``.  ``_commit_draw_arc_at`` extracts it so a later task can hand
# it a Dynamic Input span the same way the other appliers take a resolved
# point.  These tests drive the commit method directly (no HUD yet) and pin the
# span derivation + degenerate reject the click path used, so the extraction is
# a proven pure refactor.


def _arm_arc(scene, center=QPointF(0, 0), radius=1000.0, start_deg=0.0):
    """Arm an arc placement at ``_draw_arc_step == 2`` (centre + rim picked)."""
    scene.set_mode("draw_arc")
    scene._draw_arc_center = QPointF(center)
    scene._draw_arc_radius = radius
    scene._draw_arc_start_deg = start_deg
    scene._draw_arc_step = 2


def _arcs(scene):
    return [i for i in scene.items() if type(i).__name__ == "ArcItem"]


class TestCommitArcAt:
    """The extracted arc commit: span derivation, reject, and state reset."""

    def test_commit_draw_arc_at_builds_item(self, scene):
        _arm_arc(scene)
        ok = scene._commit_draw_arc_at(QPointF(0, -1000))   # 90° CCW (Y-up)
        assert ok is True
        arcs = _arcs(scene)
        assert len(arcs) == 1
        assert abs(arcs[0]._span_deg - 90.0) < 0.5

    def test_commit_draw_arc_at_rejects_degenerate(self, scene):
        _arm_arc(scene)
        ok = scene._commit_draw_arc_at(QPointF(1000, 0))    # end == start → 360 → reject
        assert ok is False
        assert not _arcs(scene)

    def test_commit_draw_arc_at_appends_to_draw_arcs(self, scene):
        _arm_arc(scene)
        before = len(scene._draw_arcs)
        assert scene._commit_draw_arc_at(QPointF(0, -1000)) is True
        assert len(scene._draw_arcs) == before + 1
        assert scene._draw_arcs[-1] is _arcs(scene)[-1]

    def test_commit_draw_arc_at_resets_state(self, scene):
        _arm_arc(scene)
        scene._commit_draw_arc_at(QPointF(0, -1000))
        assert scene._draw_arc_center is None
        assert scene._draw_arc_radius == 0.0
        assert scene._draw_arc_start_deg == 0.0
        assert scene._draw_arc_step == 0

    def test_rejected_arc_leaves_no_undo_and_no_item(self, scene, monkeypatch):
        _arm_arc(scene)
        calls = []
        monkeypatch.setattr(scene, "push_undo_state",
                            lambda *a, **k: calls.append(1))
        assert scene._commit_draw_arc_at(QPointF(1000, 0)) is False
        assert calls == []
        assert not _arcs(scene)

    def test_commit_draw_arc_at_pushes_one_undo_state(self, scene, monkeypatch):
        _arm_arc(scene)
        calls = []
        monkeypatch.setattr(scene, "push_undo_state",
                            lambda *a, **k: calls.append(1))
        assert scene._commit_draw_arc_at(QPointF(0, -1000)) is True
        assert calls == [1]

    def test_commit_draw_arc_at_unarmed_returns_false(self, scene):
        # No centre armed (the sibling _commit_* methods all no-op when unarmed).
        # Matters because this becomes an FSM-independent Dynamic Input applier.
        scene.set_mode("draw_arc")
        scene._draw_arc_center = None
        assert scene._commit_draw_arc_at(QPointF(0, -1000)) is False
        assert not _arcs(scene)

    def test_single_place_mode_exits_to_select(self, scene):
        _arm_arc(scene)
        scene.single_place_mode = True
        scene._commit_draw_arc_at(QPointF(0, -1000))
        assert scene.mode == "select"

    def test_repeat_mode_rearms(self, scene):
        _arm_arc(scene)
        scene.single_place_mode = False
        seen = []
        scene.instructionChanged.connect(seen.append)
        scene._commit_draw_arc_at(QPointF(0, -1000))
        assert scene.mode == "draw_arc"
        assert seen[-1] == "Pick center point"
