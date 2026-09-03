"""T19 — pipe as a Dynamic Input HUD client (typed Length+Angle)."""
import math
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.dynamic_input import (is_valid_relative_angle,
                                     DynamicInputHud, SCHEMAS)


class TestRelativeAngleValidation:
    @pytest.mark.parametrize("deg", [0, 45, 90, 135, 180, 225, 270, 315,
                                     -45, -90, -135, 360, 405])
    def test_multiples_of_45_are_valid(self, deg):
        assert is_valid_relative_angle(float(deg)) is True

    @pytest.mark.parametrize("deg", [1, 37, 44, 46, 89, 22.5, -30])
    def test_non_multiples_are_invalid(self, deg):
        assert is_valid_relative_angle(float(deg)) is False

    @pytest.mark.parametrize("deg", [44.999, 45.0009, 89.9995, -44.9990])
    def test_seed_float_dust_is_tolerated(self, deg):
        # A value seeded from the live preview carries sub-degree float dust
        # from get_vector_angle/subtraction; it must still validate.
        assert is_valid_relative_angle(float(deg)) is True


class TestHudFieldLabelAndInvalid:
    def test_set_field_label_changes_caption(self, qapp):
        hud = DynamicInputHud(SCHEMAS["line"])
        hud.set_field_label("Angle", "Rel A")
        assert hud.field_label_text("Angle") == "Rel A"

    def test_mark_field_invalid_flags_named_field(self, qapp):
        hud = DynamicInputHud(SCHEMAS["line"])
        assert hud.has_invalid_field() is False
        hud.mark_field_invalid("Angle")
        assert hud.has_invalid_field() is True
        assert hud.editor("Angle").property("invalid") == "true"


from firepro3d.node import Node
from firepro3d.pipe import Pipe


def _make_pipe_scene(shown_model_view):
    """Return (view, scene) in pipe mode with a fresh sprinkler system."""
    view, scene = shown_model_view
    scene.set_mode("pipe")
    return view, scene


class TestCommitPipeAtExtraction:
    def test_commit_pipe_at_places_a_segment(self, qapp, shown_model_view):
        view, scene = _make_pipe_scene(shown_model_view)
        # Arm a start node by a first press at the origin.
        scene._pipe_ctl.press_pipe(None, QPointF(0, 0), QPointF(0, 0),
                                   None, None, None)
        assert isinstance(scene.node_start_pos, Node)
        n0 = scene.node_start_pos
        before = len(scene.sprinkler_system.pipes)
        ok = scene._pipe_ctl._commit_pipe_at(QPointF(1000, 0), None)
        assert ok is True
        assert len(scene.sprinkler_system.pipes) == before + 1
        # Polyline continuation: node_start_pos advanced to the new end node.
        assert scene.node_start_pos is not n0
        assert scene.node_start_pos.scenePos() == QPointF(1000, 0)


class TestPipePublishesResolvedPoint:
    def test_move_pipe_publishes_snapped_endpoint(self, qapp, shown_model_view):
        view, scene = _make_pipe_scene(shown_model_view)
        scene._pipe_ctl.press_pipe(None, QPointF(0, 0), QPointF(0, 0),
                                   None, None, None)
        assert scene.get_resolved_point() is None  # nothing published yet
        scene._pipe_ctl.move_pipe(None, QPointF(1000, 0))
        assert scene.get_resolved_point() == QPointF(1000, 0)


class TestPipeAngleModeLabeling:
    def _engage(self, scene):
        assert scene.begin_dynamic_input() is True
        return scene.dynamic_input

    def test_free_node_labels_absolute_A(self, qapp, shown_model_view):
        view, scene = _make_pipe_scene(shown_model_view)
        # Lone start node (no coplanar pipe) → free/absolute.
        scene._pipe_ctl.press_pipe(None, QPointF(0, 0), QPointF(0, 0),
                                   None, None, None)
        scene._pipe_ctl.move_pipe(None, QPointF(0, 1000))   # publish a preview
        hud = self._engage(scene)
        assert hud.field_label_text("Angle") == "A"
        scene.end_dynamic_input()

    def test_connected_node_labels_relative(self, qapp, shown_model_view):
        view, scene = _make_pipe_scene(shown_model_view)
        # Draw one segment so the end node has a coplanar reference pipe.
        scene._pipe_ctl.press_pipe(None, QPointF(0, 0), QPointF(0, 0),
                                   None, None, None)
        scene._pipe_ctl._commit_pipe_at(QPointF(1000, 0), None)  # node_start_pos now the end node
        scene._pipe_ctl.move_pipe(None, QPointF(1000, 1000))     # publish a preview off the ref
        hud = self._engage(scene)
        assert hud.field_label_text("Angle") == "Rel A"
        scene.end_dynamic_input()


def _end_away_from(pipe, start_pt):
    """The pipe endpoint node that is NOT at *start_pt* (the placement start)."""
    return pipe.node2 if pipe.node1.scenePos() == start_pt else pipe.node1


class TestPipeAngleModeCommit:
    def _arm_and_engage(self, scene, first, preview):
        scene._pipe_ctl.press_pipe(None, first, first, None, None, None)
        scene._pipe_ctl.move_pipe(None, preview)
        assert scene.begin_dynamic_input() is True
        return scene.dynamic_input

    def test_free_typed_angle_is_exact(self, qapp, shown_model_view):
        view, scene = _make_pipe_scene(shown_model_view)
        hud = self._arm_and_engage(scene, QPointF(0, 0), QPointF(0, 1000))
        # Type absolute 30° Y-up, length 1000 → resolve_line (1000·cos30, -1000·sin30).
        hud.set_values({"Length": 1000.0, "Angle": 30.0})
        scene._on_dynamic_input_committed(hud.values())
        p = scene.sprinkler_system.pipes[-1]
        end = _end_away_from(p, QPointF(0, 0)).scenePos()
        assert end.x() == pytest.approx(1000 * math.cos(math.radians(30)), abs=1e-6)
        assert end.y() == pytest.approx(-1000 * math.sin(math.radians(30)), abs=1e-6)

    def test_connected_typed_45_is_on_grid_and_matches_mouse(self, qapp, shown_model_view):
        view, scene = _make_pipe_scene(shown_model_view)
        # A NON-axis-aligned reference pipe (≈30°): this is what distinguishes a
        # RELATIVE frame from an ABSOLUTE one — the reference's 45° grid lines do
        # NOT coincide with the absolute 45° grid, so an absolute (resolve_line)
        # commit would land off the reference grid and fail the idempotency check.
        scene._pipe_ctl.press_pipe(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
        start = QPointF(866.0254, 500.0)                          # ~30° from origin
        scene._pipe_ctl._commit_pipe_at(start, None)             # direct: exact ref axis
        node = scene.node_start_pos                               # the start-of-2nd-seg node
        assert node.scenePos() == start
        scene._pipe_ctl.move_pipe(None, QPointF(-100, 760))      # preview off the ref
        assert scene.begin_dynamic_input() is True
        hud = scene.dynamic_input
        assert is_valid_relative_angle(hud.values()["Angle"])     # seeded value is on-grid
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        scene._on_dynamic_input_committed(hud.values())
        # Polyline continuation advances node_start_pos to the typed segment's end
        # node — robust to any wye stub the sharp-angle join may add.
        typed_end = scene.node_start_pos.scenePos()
        v_new = (typed_end.x() - start.x(), typed_end.y() - start.y())
        # Length preserved …
        assert math.hypot(*v_new) == pytest.approx(1000, abs=1e-6)
        # … and the segment sits on the REFERENCE's grid: the angle between the
        # reference pipe and the typed segment is an exact 45° multiple.  This is
        # measured directly from the two segment vectors (not via a post-commit
        # snap, which would pick the just-placed pipe as its own reference), so it
        # genuinely distinguishes a RELATIVE frame from an ABSOLUTE one: an
        # absolute-45 commit against this ~30° reference yields ~75° — not a 45°
        # multiple — and fails here.
        v_ref = (0.0 - start.x(), 0.0 - start.y())   # ref pipe's other end is the origin
        cos_a = ((v_ref[0] * v_new[0] + v_ref[1] * v_new[1])
                 / (math.hypot(*v_ref) * math.hypot(*v_new)))
        inter = math.degrees(math.acos(max(-1.0, min(1.0, cos_a))))
        assert abs(inter - round(inter / 45.0) * 45.0) == pytest.approx(0.0, abs=1e-4)

    def test_connected_non_45_is_refused_not_rounded(self, qapp, shown_model_view):
        view, scene = _make_pipe_scene(shown_model_view)
        scene._pipe_ctl.press_pipe(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
        scene._pipe_ctl._commit_pipe_at(QPointF(1000, 0), None)
        scene._pipe_ctl.move_pipe(None, QPointF(1700, 700))
        assert scene.begin_dynamic_input() is True
        hud = scene.dynamic_input
        before = len(scene.sprinkler_system.pipes)
        hud.set_values({"Length": 1000.0, "Angle": 37.0})   # off-grid relative
        scene._on_dynamic_input_committed(hud.values())
        assert len(scene.sprinkler_system.pipes) == before   # nothing placed
        assert hud.has_invalid_field() is True
        assert scene.is_input_mode() is True                  # HUD still open

    def test_polyline_continuation_after_typed_commit(self, qapp, shown_model_view):
        view, scene = _make_pipe_scene(shown_model_view)
        hud = self._arm_and_engage(scene, QPointF(0, 0), QPointF(1000, 0))
        hud.set_values({"Length": 1000.0, "Angle": 0.0})
        scene._on_dynamic_input_committed(hud.values())
        # After commit the chain advances to the new end node.
        assert scene.node_start_pos.scenePos().x() == pytest.approx(1000, abs=1e-6)
