"""Pipe symbols in sections and elevations (section-view-subsystem s5)."""
import math
import re

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QImage, QPainter

from firepro3d.assets import asset_path
from firepro3d.node import Node
from tests.test_section_classification import _placed_scene


def test_cut_path_matches_the_shipped_svg():
    """The redrawn symbol is the plan's: same circle radius, same S."""
    from firepro3d import section_pipe_symbols as sps
    svg = open(asset_path("fitting_symbols", "riser_passthrough.svg"), encoding="utf-8").read()
    assert float(re.search(r'\br="([\d.]+)"', svg).group(1)) == pytest.approx(sps.SVG_RADIUS)
    assert 'd="m 10,1 c -0.00678,0.054255 -5.0356192,5.3732865 0,9 4.766864,3.433153 0,9 0,9"' in svg
    p = sps.cut_symbol_path(0.0, 0.0, 200.0)
    br = p.boundingRect()
    assert br.width() == pytest.approx(2 * sps.SVG_RADIUS * 10.0, abs=0.01)
    assert p.contains(QPointF(0.0, 0.0)) is not None


def test_end_on_gap_is_the_svg_gap():
    """elbow_down.svg's arc leaves 90 degrees open."""
    from firepro3d import section_pipe_symbols as sps
    assert sps.GAP_DEG == 90.0
    p = sps.end_on_path(0.0, 0.0, 200.0, 1.0, 0.0)          # gap faces +x
    r = sps.SVG_RADIUS * 10.0
    pts = [p.pointAtPercent(i / 200.0) for i in range(201)]
    assert min(math.hypot(q.x() - r, q.y()) for q in pts) > r * 0.7   # none near +x
    assert min(math.hypot(q.x() + r, q.y()) for q in pts) < 1.0       # on the far side


def test_kept_spans_cuts_a_gap_behind_a_symbol():
    from firepro3d.section_pipe_symbols import kept_spans
    circles = [(5.0, 0.0, 1.0, 0.0)]
    spans = kept_spans((0.0, 0.0), (10.0, 0.0), 1.0, 1.0, circles, [5.0], 1.0)
    assert spans == pytest.approx([(0.0, 0.4), (0.6, 1.0)])


def test_kept_spans_leaves_a_line_in_front_of_the_symbol():
    from firepro3d.section_pipe_symbols import kept_spans
    circles = [(5.0, 0.0, 1.0, 500.0)]                       # symbol deeper than the line
    assert kept_spans((0.0, 0.0), (10.0, 0.0), 100.0, 100.0, circles, [5.0], 1.0) is None


def test_kept_spans_misses():
    from firepro3d.section_pipe_symbols import kept_spans
    assert kept_spans((0.0, 5.0), (10.0, 5.0), 0.0, 0.0,
                      [(5.0, 0.0, 1.0, 0.0)], [5.0], 1.0) is None


def test_plan_symbol_size_matches_a_real_fitting(qapp, section_scene_for):
    """The shared size is what the plan fitting actually draws."""
    from firepro3d.fitting import Fitting
    ms, _sec = section_scene_for("north")
    a = ms.add_node(0.0, 0.0); b = ms.add_node(3000.0, 0.0)
    pipe = ms.add_pipe(a, b)
    f = a.fitting
    drawn = max(f.symbol.boundingRect().width(), f.symbol.boundingRect().height()) * f.symbol_scale
    assert Fitting.plan_symbol_mm(pipe.display_width_mm(), pipe._display_scale) == pytest.approx(drawn)
