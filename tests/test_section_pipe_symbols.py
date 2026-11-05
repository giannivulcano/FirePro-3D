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
    # The S: the SVG's relative cubics made absolute, scaled 10x about (10, 10).
    x, y = 10.0, 1.0
    want = [(x, y)]
    for c in ((-0.00678, 0.054255, -5.0356192, 5.3732865, 0.0, 9.0),
              (4.766864, 3.433153, 0.0, 9.0, 0.0, 9.0)):
        want += [(x + c[0], y + c[1]), (x + c[2], y + c[3]), (x + c[4], y + c[5])]
        x, y = x + c[4], y + c[5]
    got = [p.elementAt(i) for i in range(p.elementCount() - 7, p.elementCount())]
    for e, (a, b) in zip(got, want):
        assert (e.x, e.y) == pytest.approx(((a - 10.0) * 10.0, (b - 10.0) * 10.0))


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


def test_kept_spans_trims_a_line_leaving_the_symbol_toward_the_viewer():
    """P1: joined at the symbol, heading nearer: it is not "in front"."""
    from firepro3d.section_pipe_symbols import kept_spans
    circles = [(0.0, 0.0, 1.0, 100.0)]
    assert kept_spans((0.0, 0.0), (10.0, 0.0), 100.0, 50.0, circles, [0.0], 1.0) == pytest.approx(
        [(0.1, 1.0)])


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


PX = 2.0


def _pipe(ms, a, b):
    """Real pipe between real nodes at (x, y, z); z is set after add_pipe (it
    recomputes z from the level). Stacked nodes need Node directly."""
    def node(x, y, z):
        n = Node(x, y, z)
        ms.addItem(n)
        ms.sprinkler_system.add_node(n)
        return n
    n1, n2 = node(*a), node(*b)
    p = ms.add_pipe(n1, n2)
    n1.z_pos, n2.z_pos = a[2], b[2]
    return p


def _render(sec, rect):
    img = QImage(int(rect.width() * PX), int(rect.height() * PX),
                 QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    sec.render(p, QRectF(img.rect()), rect)
    p.end()
    return img


def _ink(img, rect, x, y, reach=2):
    """Non-transparent pixels near scene (x, y): (count, one colour name)."""
    cx, cy = int((x - rect.x()) * PX), int((y - rect.y()) * PX)
    n, col = 0, None
    for i in range(cx - reach, cx + reach + 1):
        for j in range(cy - reach, cy + reach + 1):
            c = img.pixelColor(i, j)
            if c.alpha() > 60:
                n += 1
                col = c.name()
    return n, col


def _cut_scene(section_scene_for):
    return _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)


def _symbols(sec, pipe):
    from firepro3d.section_scene import _ElevPipeSymbol, _ROLE_SOURCE
    return [i for i in sec.items()
            if isinstance(i, _ElevPipeSymbol) and i.data(_ROLE_SOURCE) is pipe]


def _lines(sec, pipe):
    from firepro3d.section_scene import _ElevProxyLine, _ROLE_SOURCE
    return [i for i in sec.items()
            if isinstance(i, _ElevProxyLine) and i.data(_ROLE_SOURCE) is pipe]


CENTRE = (3000.0, -2500.0)
RECT = QRectF(2800.0, -2700.0, 400.0, 400.0)


def test_perpendicular_cut_draws_the_riser_symbol_in_pipe_colour(qapp, section_scene_for):
    """AC1: plan size, S curve in the pipe colour, not white."""
    ms, sec = _cut_scene(section_scene_for)
    pipe = _pipe(ms, (3000.0, -1000.0, 2500.0), (3000.0, 1000.0, 2500.0))
    sec.rebuild()
    (s,) = _symbols(sec, pipe)
    assert s.rect().width() == pytest.approx(pipe._RISER_SIZE_MM)
    assert s.rect().center() == QPointF(*CENTRE)
    img = _render(sec, RECT)
    assert _ink(img, RECT, *CENTRE)[1] == "#e62828"          # the S at the centre
    assert _ink(img, RECT, CENTRE[0] + 40.0, CENTRE[1])[0] == 0   # hollow beside it


def test_pipe_behind_trims_at_the_cut_symbol(qapp, section_scene_for):
    """AC1: no ink from a behind pipe inside the circle, ink outside it."""
    ms, sec = _cut_scene(section_scene_for)
    _pipe(ms, (3000.0, -1000.0, 2500.0), (3000.0, 1000.0, 2500.0))
    _pipe(ms, (2000.0, -1000.0, 2500.0), (4000.0, -1000.0, 2500.0))
    sec.rebuild()
    img = _render(sec, RECT)
    assert _ink(img, RECT, CENTRE[0] + 40.0, CENTRE[1])[0] == 0
    assert _ink(img, RECT, CENTRE[0] + 120.0, CENTRE[1])[0] > 0
    # It stops at the drawn circle (ink radius 69.6), not the 75 mm viewBox edge.
    assert _ink(img, RECT, CENTRE[0] + 72.0, CENTRE[1], reach=1)[0] > 0


@pytest.mark.parametrize("value", [None, ""])
def test_unset_or_empty_section_colour_is_no_fill(qapp, section_scene_for, value):
    """AC2."""
    from PyQt6.QtCore import QSettings
    s = QSettings("GV", "FirePro3D")
    s.remove("display/Pipe/section") if value is None else s.setValue("display/Pipe/section", value)
    ms, sec = _cut_scene(section_scene_for)
    _pipe(ms, (3000.0, -1000.0, 2500.0), (3000.0, 1000.0, 2500.0))
    sec.rebuild()
    img = _render(sec, RECT)
    assert _ink(img, RECT, CENTRE[0] + 40.0, CENTRE[1])[0] == 0
    s.remove("display/Pipe/section")


def test_set_section_colour_fills_inside_the_circle(qapp, section_scene_for):
    """AC2: and the behind pipe still trims under it."""
    from PyQt6.QtCore import QSettings
    s = QSettings("GV", "FirePro3D")
    s.setValue("display/Pipe/section", "#00ff00")
    ms, sec = _cut_scene(section_scene_for)
    _pipe(ms, (3000.0, -1000.0, 2500.0), (3000.0, 1000.0, 2500.0))
    sec.rebuild()
    img = _render(sec, RECT)
    assert _ink(img, RECT, CENTRE[0] + 40.0, CENTRE[1])[1] == "#00ff00"
    assert _ink(img, RECT, *CENTRE)[1] == "#e62828"          # the S stays on top
    s.remove("display/Pipe/section")


def test_angled_cut_draws_symbol_and_the_part_beyond_only(qapp, section_scene_for):
    """AC3: 45 deg. Near end in front of the cut, far end behind it (look side
    is scene -y); the line runs crossing -> far end."""
    ms, sec = _cut_scene(section_scene_for)
    pipe = _pipe(ms, (2000.0, 1000.0, 2500.0), (5000.0, -2000.0, 2500.0))
    sec.rebuild()
    (s,) = _symbols(sec, pipe)
    assert s.rect().center().x() == pytest.approx(3000.0)
    (ln,) = _lines(sec, pipe)
    xs = sorted((ln.line().x1(), ln.line().x2()))
    assert xs == pytest.approx([3000.0, 5000.0])
    img = _render(sec, RECT)
    assert _ink(img, RECT, CENTRE[0] + 40.0, CENTRE[1])[0] == 0      # none inside
    assert _ink(img, RECT, CENTRE[0] + 120.0, CENTRE[1])[0] > 0      # the line beyond


def test_angled_cut_line_clips_laterally(qapp, section_scene_for):
    """AC3: the beyond part stops at the crop edge."""
    ms, sec = _cut_scene(section_scene_for)
    pipe = _pipe(ms, (8000.0, 1000.0, 2500.0), (12000.0, -3000.0, 2500.0))
    sec.rebuild()
    (ln,) = _lines(sec, pipe)
    assert max(ln.line().x1(), ln.line().x2()) == pytest.approx(10000.0)
    assert min(ln.line().x1(), ln.line().x2()) == pytest.approx(9000.0)


def test_pipe_along_the_cut_is_a_full_length_line(qapp, section_scene_for):
    """AC4 / AC8: a real Pipe on the cut line; no symbol, zone behind."""
    from firepro3d.section_marker import ZONE_BEHIND
    ms, sec = _cut_scene(section_scene_for)
    pipe = _pipe(ms, (2000.0, 0.0, 2500.0), (6000.0, 0.0, 2500.0))
    sec.rebuild()
    assert sec.zone_of(pipe) == ZONE_BEHIND
    assert not _symbols(sec, pipe)
    (ln,) = _lines(sec, pipe)
    assert sorted((ln.line().x1(), ln.line().x2())) == pytest.approx([2000.0, 6000.0])


def test_vertical_pipe_on_the_cut_line_is_a_line(qapp, section_scene_for):
    """R-5: its centreline lies in the cut plane."""
    ms, sec = _cut_scene(section_scene_for)
    pipe = _pipe(ms, (3000.0, 0.0, 0.0), (3000.0, 0.0, 3000.0))
    sec.rebuild()
    assert not _symbols(sec, pipe)
    (ln,) = _lines(sec, pipe)
    assert ln.line().x1() == pytest.approx(ln.line().x2())


@pytest.mark.parametrize("scene_kind", ["section", "elevation"])
def test_end_on_pipe_not_crossing_draws_the_c(qapp, section_scene_for, scene_kind):
    """AC5: in a section and a cardinal elevation; no line, gap down (none joined)."""
    if scene_kind == "section":
        ms, sec = _cut_scene(section_scene_for)
    else:
        ms, sec = section_scene_for("north")
    pipe = _pipe(ms, (3000.0, -1000.0, 2500.0), (3000.0, -3000.0, 2500.0))
    sec.rebuild()
    (s,) = _symbols(sec, pipe)
    assert not _lines(sec, pipe)
    c = s.rect().center()
    assert s.rect().width() == pytest.approx(150.0)
    rect = QRectF(c.x() - 200.0, c.y() - 200.0, 400.0, 400.0)
    img = _render(sec, rect)
    r = 69.0
    assert _ink(img, rect, c.x(), c.y() + r, reach=4)[0] == 0        # gap down
    assert _ink(img, rect, c.x(), c.y() - r, reach=4)[0] > 0


@pytest.mark.parametrize("far,gap", [
    ((4000.0, -1000.0, 2500.0), (1, 0)),      # joined pipe to the right
    ((2000.0, -1000.0, 2500.0), (-1, 0)),     # left
    ((3000.0, -1000.0, 3500.0), (0, -1)),     # riser up: scene y is negative z
    ((3000.0, -1000.0, 1500.0), (0, 1)),      # drop down
    ((3500.0, -500.0, 2500.0), (1, 0)),       # right and nearer the viewer (I1)
])
def test_c_gap_faces_the_joined_pipe(qapp, section_scene_for, far, gap):
    """AC5: rendered, each of four directions, opposite side keeps ink."""
    ms, sec = _cut_scene(section_scene_for)
    near = Node(3000.0, -1000.0, 2500.0)
    back = Node(3000.0, -3000.0, 2500.0)
    other = Node(*far)
    for n in (near, back, other):
        ms.addItem(n)
        ms.sprinkler_system.add_node(n)
    ms.add_pipe(near, back)
    ms.add_pipe(near, other)
    near.z_pos, back.z_pos, other.z_pos = 2500.0, 2500.0, far[2]
    sec.rebuild()
    cx, cy = 3000.0, -2500.0
    rect = QRectF(cx - 200.0, cy - 200.0, 400.0, 400.0)
    img = _render(sec, rect)
    r = 69.0
    # The joined pipe stops at the circle, so sample the gap 30 degrees off its axis.
    side = (-gap[1], gap[0])
    gx = gap[0] * math.cos(math.radians(30)) + side[0] * 0.5
    gy = gap[1] * math.cos(math.radians(30)) + side[1] * 0.5
    assert _ink(img, rect, cx + gx * r, cy + gy * r, reach=4)[0] == 0
    assert _ink(img, rect, cx - gap[0] * r, cy - gap[1] * r, reach=4)[0] > 0
    assert _ink(img, rect, cx + gap[0] * 40.0, cy + gap[1] * 40.0)[0] == 0    # P1: stops
    assert _ink(img, rect, cx + gap[0] * 120.0, cy + gap[1] * 120.0)[0] > 0   # and resumes


def test_coincident_end_on_pipes_draw_one_symbol(qapp, section_scene_for):
    """P5: a run heading away stacks at one point; the nearest draws."""
    from firepro3d.section_scene import _ElevPipeSymbol
    ms, sec = _cut_scene(section_scene_for)
    _pipe(ms, (3000.0, -500.0, 2500.0), (3000.0, -1500.0, 2500.0))
    _pipe(ms, (3000.0, -1500.0, 2500.0), (3000.0, -2500.0, 2500.0))
    sec.rebuild()
    assert len([i for i in sec.items() if isinstance(i, _ElevPipeSymbol)]) == 1


def test_cut_symbol_wins_over_a_coincident_c(qapp, section_scene_for):
    """P5 "cut first": a run through the cut, then on away from the viewer."""
    from firepro3d.section_scene import _ElevCutEllipse, _ElevPipeSymbol
    ms, sec = _cut_scene(section_scene_for)
    _pipe(ms, (3000.0, 1000.0, 2500.0), (3000.0, -1000.0, 2500.0))
    _pipe(ms, (3000.0, -1000.0, 2500.0), (3000.0, -3000.0, 2500.0))
    sec.rebuild()
    (only,) = [i for i in sec.items() if isinstance(i, _ElevPipeSymbol)]
    assert isinstance(only, _ElevCutEllipse)


def test_line_in_front_of_a_c_is_not_trimmed(qapp, section_scene_for):
    """P1: only pipes behind the C trim. Rendered: the line crosses the hollow."""
    ms, sec = _cut_scene(section_scene_for)
    _pipe(ms, (3000.0, -2000.0, 2500.0), (3000.0, -3000.0, 2500.0))      # C at d=2000
    _pipe(ms, (2000.0, -500.0, 2500.0), (4000.0, -500.0, 2500.0))        # in front
    sec.rebuild()
    img = _render(sec, RECT)
    assert _ink(img, RECT, *CENTRE)[0] > 0
    assert _ink(img, RECT, CENTRE[0] + 40.0, CENTRE[1])[0] > 0


def test_c_takes_the_plan_size_from_the_largest_pipe_at_its_node(qapp, section_scene_for):
    """R-6 same size: a Branch riser on a Main draws what the plan fitting draws."""
    ms, sec = _cut_scene(section_scene_for)
    near = Node(3000.0, -1000.0, 2500.0)
    back = Node(3000.0, -3000.0, 2500.0)
    other = Node(6000.0, -1000.0, 2500.0)
    for n in (near, back, other):
        ms.addItem(n)
        ms.sprinkler_system.add_node(n)
    branch = ms.add_pipe(near, back)
    main = ms.add_pipe(near, other)
    main._properties["Line Type"]["value"] = "Main"
    near.z_pos, back.z_pos, other.z_pos = 2500.0, 2500.0, 2500.0
    near.fitting.update()
    sec.rebuild()
    (s,) = _symbols(sec, branch)
    f = near.fitting
    drawn = max(f.symbol.boundingRect().width(), f.symbol.boundingRect().height()) * f.symbol_scale
    assert drawn == pytest.approx(75.0 * math.sqrt(2) * 2)    # the rule's Main size
    assert s.rect().width() == pytest.approx(drawn)


def test_zero_length_pipe_draws_nothing(qapp, section_scene_for):
    ms, sec = _cut_scene(section_scene_for)
    pipe = _pipe(ms, (3000.0, -1000.0, 2500.0), (3000.0, -1000.0, 2500.0))
    sec.rebuild()
    assert not _symbols(sec, pipe) and not _lines(sec, pipe)
