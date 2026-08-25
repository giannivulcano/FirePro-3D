"""Unit tests for the one shared pixel<->scene conversion (SNAP refinement)."""
import math
import pytest
from firepro3d.snap_engine import px_to_scene, scene_to_px


def test_px_to_scene_and_back_roundtrips():
    for scale in (0.02, 1.0, 10.0):
        assert math.isclose(px_to_scene(20.0, scale), 20.0 / scale)
        assert math.isclose(scene_to_px(px_to_scene(20.0, scale), scale), 20.0)


def test_nonpositive_scale_is_clamped():
    # A zero/negative view scale must not divide-by-zero; treat as 1.0.
    assert px_to_scene(20.0, 0.0) == 20.0
    assert px_to_scene(20.0, -3.0) == 20.0
    assert scene_to_px(5.0, 0.0) == 5.0
