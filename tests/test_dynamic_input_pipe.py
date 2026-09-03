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
