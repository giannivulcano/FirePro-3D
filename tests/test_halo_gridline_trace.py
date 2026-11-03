"""GridlineItem HALO composite-trace hook (selection-mode.md 4.2).

A gridline is a composite (line + bubbles); its HALO preselection trace must
union all parts, trim the line at each visible bubble's block outline (never
reach into the bubble) and include both outlines, mirroring
GridlineItem.paint(). Since SB4b the bubbles are annotation blocks sized in
scene units, so the hook needs no view scale.
"""
import math

import pytest

from firepro3d.halo import halo_scene_path
from tests.test_sb4b_gridline_bubble import CIRCLE_R, _bubble_def, _gridline, _scene


def _make(qapp):
    sc = _scene()
    _bubble_def(sc)
    gl = _gridline(sc, (0.0, 0.0), (0.0, 1000.0))        # vertical
    return sc, gl


def test_trace_unions_line_and_both_bubbles(qapp):
    _sc, gl = _make(qapp)
    p = gl.halo_trace_path()
    br = p.boundingRect().adjusted(-1e-6, -1e-6, 1e-6, 1e-6)     # float noise of the union
    for b in (gl.bubble1, gl.bubble2):
        assert br.contains(gl.mapFromItem(b, b.outline_path()).boundingRect())
    # a bare line is 2 elements; the composite carries both outlines too
    assert p.elementCount() > 2
    assert not halo_scene_path(gl).isEmpty()


def test_extension_trimmed_at_bubble_edge_not_center(qapp):
    sc, gl = _make(qapp)
    r = CIRCLE_R * sc.scale_manager.drawing_scale
    b1 = gl.bubble1.pos()
    p = gl.halo_trace_path()
    # The traced line's first vertex must sit ~r from the near bubble centre
    # (edge), not AT the centre. elementAt(0) is the moveTo start of the line.
    start = p.elementAt(0)
    d_center = math.hypot(start.x - b1.x(), start.y - b1.y())
    assert d_center == pytest.approx(r, abs=0.05 * sc.scale_manager.drawing_scale)
    assert d_center > r * 0.5                  # definitely not at the centre


def test_hidden_bubble_extends_to_endpoint(qapp):
    _sc, gl = _make(qapp)
    gl.set_bubble_visible(1, False)            # hide the start bubble
    b1 = gl.bubble1.pos()
    p = gl.halo_trace_path()
    start = p.elementAt(0)
    # With bubble1 hidden the line runs to the bubble anchor itself (no trim).
    assert abs(start.x - b1.x()) < 1e-6 and abs(start.y - b1.y()) < 1e-6


def test_scale_argument_is_accepted_and_ignored(qapp):
    _sc, gl = _make(qapp)
    assert gl.halo_trace_path(None) == gl.halo_trace_path(7.0)
