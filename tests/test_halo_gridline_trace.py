"""GridlineItem HALO composite-trace hook (selection-mode.md §4.2).

A gridline is a composite (line + extension + bubbles); its HALO preselection
trace must union all parts, trim the extension at each visible bubble's edge
(never reach into the bubble), and include the bubble circles — mirroring
GridlineItem.paint(). The bubbles are screen-fixed (ItemIgnoresTransformations),
so the hook takes the view's scene->device scale.
"""
import math
from PyQt6.QtCore import QPointF
from firepro3d.model_space import Model_Space
from firepro3d.gridline import GridlineItem, GridBubble


def _make(qapp):
    sc = Model_Space()
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 1000))   # vertical
    sc.addItem(gl)
    return sc, gl


def test_trace_unions_line_and_both_bubbles(qapp):
    _sc, gl = _make(qapp)
    p = gl.halo_trace_path(1.0)                            # scale 1 -> r == RADIUS_PX
    # A bare line is 2 elements; a composite with two ellipses is many more.
    assert p.elementCount() > 2
    # Both bubble circles are inside the trace bounds.
    br = p.boundingRect()
    for b in (gl.bubble1.pos(), gl.bubble2.pos()):
        assert br.contains(b)


def test_extension_trimmed_at_bubble_edge_not_center(qapp):
    _sc, gl = _make(qapp)
    scale = 1.0
    r = GridBubble.RADIUS_PX / scale
    b1 = gl.bubble1.pos()
    b2 = gl.bubble2.pos()
    p = gl.halo_trace_path(scale)
    # The traced line's first vertex must sit ~r from the near bubble center
    # (edge), not AT the center. elementAt(0) is the moveTo start of the line.
    start = p.elementAt(0)
    d_center = math.hypot(start.x - b1.x(), start.y - b1.y())
    assert abs(d_center - r) < 1e-6            # trimmed exactly to the edge
    assert d_center > r * 0.5                  # definitely not at the center


def test_hidden_bubble_extends_to_endpoint(qapp):
    _sc, gl = _make(qapp)
    gl.set_bubble_visible(1, False)            # hide the start bubble
    b1 = gl.bubble1.pos()
    p = gl.halo_trace_path(1.0)
    start = p.elementAt(0)
    # With bubble1 hidden the line runs to the bubble anchor itself (no trim).
    assert abs(start.x - b1.x()) < 1e-6 and abs(start.y - b1.y()) < 1e-6


def test_headless_fallback_is_bare_line(qapp):
    _sc, gl = _make(qapp)
    p = gl.halo_trace_path(None)               # no scale -> cannot size bubbles
    assert p.elementCount() == 2               # moveTo + lineTo only
