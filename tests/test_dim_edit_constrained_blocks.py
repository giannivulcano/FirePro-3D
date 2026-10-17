"""Typed dim edits on fully-constrained library blocks (D6 / D55).

A dim's readout anchor law (line keeps p1, angle pivots about the end nearer
the vertex, rect keeps left / bottom) is a strong preference, not a lock: when
the block's other constraints contradict the anchor (a line whose midpoint is
locked to the origin, a rect centred on the origin), the edit must still land
by moving the geometry the constraints allow -- never be rejected.
"""
import math
import os

import pytest

from firepro3d.block_editor import BlockEditorWidget
from firepro3d.block_library import load_block_file
from firepro3d.model_space import Model_Space

_FIX = os.path.join(os.path.dirname(__file__), "fixtures", "blocks")


def _open(name):
    defn = load_block_file(os.path.join(_FIX, name))
    assert defn is not None
    w = BlockEditorWidget(Model_Space())
    w.seed_from_definition(defn)
    return w, w.editor_scene.constraint_ctl


def _dims(ctl, typ):
    return [c for c in ctl.constraints if c.type == typ and c.driving]


def _all_hold(ctl):
    """Every enabled driving dim measures its stored value."""
    for c in ctl.constraints:
        if c.type.startswith("dim_") and c.driving and c.enabled:
            assert ctl.measure(c) == pytest.approx(c.value, abs=1e-5), c.type


@pytest.mark.parametrize("which,new", [(0, 60.0), (1, 30.0)])
def test_sprinkler_angle_dims_update(qapp, which, new):
    w, ctl = _open("sprinkler_2.fpdb")
    # [0] = 90 deg between the two lines, [1] = 45 deg line-to-x-axis
    ang = _dims(ctl, "dim_angle")
    c = ang[which]
    assert ctl.set_value(c.id, new)
    assert c.value == pytest.approx(new)
    assert c.id not in ctl.red
    _all_hold(ctl)


def test_pipe_break_reference_rect_dim_resizes(qapp):
    w, ctl = _open("pipe_break.fpdb")
    (d,) = _dims(ctl, "dim_distance")
    new = d.value * 1.5
    assert ctl.set_value(d.id, new)
    assert d.value == pytest.approx(new)
    _all_hold(ctl)
