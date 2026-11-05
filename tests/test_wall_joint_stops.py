"""Wall joint stops: a wall stops flat on the walls it meets, with a seam.

Hand-derived geometry: 300 mm walls meeting at the origin, y grows downward.
LEFT and DOWN form the shaft corner, RIGHT comes in from the east.
"""
from __future__ import annotations

import itertools
import math
import random

import pytest
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen

from firepro3d.level_manager import LevelManager
from firepro3d.wall import WallSegment

HALF = 150.0
LOW = -1500.0        # Top Offset of a wall that ends below its neighbours


def _ms():
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    s._level_manager = LevelManager()
    lm = s._level_manager
    if lm.get("Level 2") is None:
        lm.add_level("Level 2", elevation=lm.get("Level 1").elevation + 3000.0)
    return s


def _wall(s, p1, p2, top_offset=0.0, j1="Auto", j2="Auto"):
    w = WallSegment(QPointF(*p1), QPointF(*p2), thickness_mm=2 * HALF)
    w._top_offset_mm = top_offset
    w._join_mode_pt1 = j1
    w._join_mode_pt2 = j2
    s.addItem(w)
    s._walls.append(w)
    assert abs(w.half_thickness_scene() - HALF) < 1e-9
    w.invalidate_geometry()
    return w


def _left(s, **kw):
    return _wall(s, (-1500, 0), (0, 0), **kw)


def _down(s, **kw):
    return _wall(s, (0, 0), (0, 1500), **kw)


def _right(s, **kw):
    return _wall(s, (0, 0), (1500, 0), **kw)


def _pts(wall):
    body = wall.outline().body
    return [(round(body.at(i).x(), 3), round(body.at(i).y(), 3))
            for i in range(body.count())]


def _on_segment(pt, a, b, tol=1e-3):
    dx, dy = b.x() - a.x(), b.y() - a.y()
    length = math.hypot(dx, dy)
    if length == 0.0:
        return False
    t = ((pt.x() - a.x()) * dx + (pt.y() - a.y()) * dy) / length
    d = abs((pt.x() - a.x()) * dy - (pt.y() - a.y()) * dx) / length
    return d <= tol and -tol <= t <= length + tol


def _stroked(wall, x, y):
    return any(_on_segment(QPointF(x, y), a, b)
               for a, b in wall.outline().stroke_segments)


def _assert_shaft_stop(left, down, right):
    assert min(x for x, _y in _pts(right)) == pytest.approx(HALF)
    assert (HALF, -HALF) in _pts(left) and (-HALF, HALF) in _pts(left)
    assert (HALF, -HALF) in _pts(down) and (-HALF, HALF) in _pts(down)
    assert _stroked(right, HALF, 0.0), "seam on the contact edge"
    assert not _stroked(down, HALF, 0.0), "the stopper alone owns the seam"
    assert _stroked(right, 800.0, -HALF), "far face kept"
    assert not _stroked(left, 0.0, 0.0), "the L's own mitre stays unlined"
    assert not _stroked(down, 0.0, 0.0), "the L's own mitre stays unlined"


def test_shaft_by_height(qapp):
    s = _ms()
    left, down = _left(s), _down(s)
    _assert_shaft_stop(left, down, _right(s, top_offset=LOW))


def test_shaft_by_explicit_butt_at_equal_tops(qapp):
    s = _ms()
    left, down = _left(s), _down(s)
    _assert_shaft_stop(left, down, _right(s, j1="Butt"))


def test_shaft_any_creation_order(qapp):
    s = _ms()
    right = _right(s, top_offset=LOW)
    down, left = _down(s), _left(s)
    _assert_shaft_stop(left, down, right)


def test_down_butt_gives_a_straight_through_tee(qapp):
    s = _ms()
    left, right = _left(s), _right(s)
    down = _down(s, j1="Butt")
    assert min(y for _x, y in _pts(down)) == pytest.approx(HALF)
    assert max(x for x, _y in _pts(left)) == pytest.approx(0.0)
    assert min(x for x, _y in _pts(right)) == pytest.approx(0.0)
    assert _stroked(down, 0.0, HALF), "seam"
    assert not _stroked(left, 0.0, 0.0), "no line across the through walls"


def _is_pie(*walls):
    return all(w.outline().wedge[0] or w.outline().wedge[1] for w in walls)


@pytest.mark.parametrize("tops, expect_pie, stopped", [
    ((0.0, 0.0, 0.0), True, ()),                    # all the same
    ((0.0, LOW, LOW), True, ()),                    # one tallest wall
    ((0.0, -500.0, LOW), True, ()),                 # one tallest wall
    ((0.0, 0.0, LOW), False, (2,)),                 # two tall, one low
])
def test_height_rule_table(qapp, tops, expect_pie, stopped):
    s = _ms()
    walls = [_left(s, top_offset=tops[0]), _down(s, top_offset=tops[1]),
             _right(s, top_offset=tops[2])]
    assert _is_pie(*walls) is expect_pie
    assert [i for i, w in enumerate(walls) if w.outline().seams] == list(stopped)


def test_two_low_walls_both_stop_at_a_cross(qapp):
    s = _ms()
    left, right = _left(s), _right(s)
    up = _wall(s, (0, -1500), (0, 0), top_offset=LOW)
    down = _down(s, top_offset=LOW)
    assert up.outline().seams and down.outline().seams
    assert not left.outline().seams and not right.outline().seams


def test_solid_keeps_a_low_wall_in_the_pie(qapp):
    s = _ms()
    walls = [_left(s), _down(s), _right(s, top_offset=LOW, j1="Solid")]
    assert _is_pie(*walls)
    assert not walls[2].outline().seams


def test_two_wall_corner_lower_wall_stops(qapp):
    s = _ms()
    left = _left(s)
    down = _down(s, top_offset=LOW)
    assert max(x for x, _y in _pts(left)) == pytest.approx(HALF)
    assert min(y for _x, y in _pts(down)) == pytest.approx(HALF)
    assert _stroked(down, 0.0, HALF), "seam"


def test_two_wall_corner_solid_keeps_the_mitre(qapp):
    s = _ms()
    left = _left(s)
    down = _down(s, top_offset=LOW, j1="Solid")
    assert (HALF, -HALF) in _pts(left) and (-HALF, HALF) in _pts(left)
    assert (HALF, -HALF) in _pts(down) and (-HALF, HALF) in _pts(down)
    assert not down.outline().seams


def test_two_wall_corner_explicit_butt_matches_the_height_stop(qapp):
    s = _ms()
    left = _left(s)
    down = _down(s, j1="Butt")
    assert max(x for x, _y in _pts(left)) == pytest.approx(HALF)
    assert min(y for _x, y in _pts(down)) == pytest.approx(HALF)


def test_butt_on_the_taller_wall_makes_it_the_one_that_stops(qapp):
    s = _ms()
    left = _left(s, j2="Butt")
    down = _down(s, top_offset=LOW)
    assert max(x for x, _y in _pts(left)) == pytest.approx(-HALF)
    assert not down.outline().seams and left.outline().seams


def test_two_butts_of_three_keep_todays_result(qapp):
    s = _ms()
    left = _left(s)
    down, right = _down(s, j1="Butt"), _right(s, j1="Butt")
    assert not down.outline().seams and not right.outline().seams
    assert min(y for _x, y in _pts(down)) == pytest.approx(0.0)
    assert left.outline().body.count() == 5


def test_angled_stopper_wraps_the_outer_corner(qapp):
    s = _ms()
    left, down = _left(s), _down(s)
    ne = _wall(s, (0, 0), (1200, -1200), top_offset=LOW)
    assert (HALF, -HALF) in _pts(ne), "the end hugs the L's outer corner"
    assert len(ne.outline().seams) == 2
    for wall in (left, down):
        overlap = ne.path().intersected(wall.path())
        assert overlap.boundingRect().width() * overlap.boundingRect().height() < 1.0
    assert _stroked(left, -800.0, -HALF)
    assert _stroked(down, HALF, 800.0)


def test_stop_at_right_alignment_keeps_every_body(qapp):
    from firepro3d.wall import ALIGN_RIGHT
    s = _ms()
    left, down = _left(s), _down(s)
    right = _right(s, top_offset=LOW)
    for wall in (left, down, right):
        wall._alignment = ALIGN_RIGHT
    for wall in (left, down, right):
        wall.invalidate_geometry()
    for wall in (left, down, right):
        assert wall.outline().stroke_segments, "body kept in the union"


def test_top_offset_edit_refreshes_the_partners(qapp):
    s = _ms()
    left, down, right = _left(s), _down(s), _right(s)
    assert _is_pie(left, down, right)
    right.set_property("Top Offset", str(LOW))
    assert right.outline().seams, "the panel path takes effect"
    assert not left.outline().wedge[1], "the partner left the pie"


def test_level_elevation_edit_refreshes_joints(qapp):
    s = _ms()
    left, down = _left(s), _down(s)
    right = _wall(s, (0, 0), (1500, 0))
    right._top_level = "Level 1"
    right.invalidate_geometry()
    assert right.outline().seams, "precondition: a lower wall"
    lm = s._level_manager
    lm.get("Level 2").elevation = lm.get("Level 1").elevation
    lm.update_elevations(s)
    assert not right.outline().seams
    assert _is_pie(left, down, right)


def test_stop_survives_save_and_reload(qapp, tmp_path):
    s = _ms()
    _left(s), _down(s), _right(s, top_offset=LOW)
    path = str(tmp_path / "stops.fpd")
    s.save_to_file(path)
    fresh = _ms()
    fresh.load_from_file(path)
    stopped = [w for w in fresh._walls if w.outline().seams]
    assert len(fresh._walls) == 3 and len(stopped) == 1
    assert min(x for x, _y in _pts(stopped[0])) == pytest.approx(HALF)


def test_one_tallest_wall_stays_a_pie_with_a_solid_low_wall(qapp):
    s = _ms()
    walls = [_left(s), _down(s, top_offset=LOW, j1="Solid"),
             _right(s, top_offset=LOW)]
    assert _is_pie(*walls)
    assert not walls[2].outline().seams


def _rot(x, y, deg):
    a = math.radians(deg)
    return (x * math.cos(a) - y * math.sin(a),
            x * math.sin(a) + y * math.cos(a))


@pytest.mark.parametrize("deg", [17.3, 33.0, 61.7, 123.4, 207.9, 301.1])
def test_rotated_shaft_keeps_every_body_and_owns_one_seam(qapp, deg):
    """Float-noisy shared edges: the union must keep all three bodies."""
    s = _ms()
    left = _wall(s, _rot(-1500, 0, deg), (0, 0))
    down = _wall(s, (0, 0), _rot(0, 1500, deg))
    right = _wall(s, (0, 0), _rot(1500, 0, deg), top_offset=LOW)
    assert _stroked(left, *_rot(-800, -HALF, deg)), "left far face"
    assert _stroked(left, *_rot(-800, HALF, deg)), "left near face"
    assert _stroked(down, *_rot(HALF, 800, deg)), "down far face"
    assert _stroked(right, *_rot(800, HALF, deg)), "right face"
    assert _stroked(right, *_rot(HALF, 0, deg)), "seam"
    assert not _stroked(down, *_rot(HALF, 0, deg)), "stopper owns the seam"
    assert not _stroked(left, 0.0, 0.0), "no line on the mitre"


# A stop either fits on every wall or does not happen (R7) ─────────────────

def _bodies(*walls):
    return [_pts(w) for w in walls]


def _corner(s, t1, t2, al1, al2, deg, top=0.0, j1="Auto"):
    tall = _wall2(s, (-1500, 0), (0, 0), t1, al1)
    end = (1500 * math.cos(math.radians(deg)),
           1500 * math.sin(math.radians(deg)))
    low = _wall2(s, (0, 0), end, t2, al2, top, j1)
    tall.invalidate_geometry()
    low.invalidate_geometry()
    return tall, low


def _wall2(s, p1, p2, thickness, alignment, top=0.0, j1="Auto"):
    w = WallSegment(QPointF(*p1), QPointF(*p2), thickness_mm=thickness)
    w._alignment = alignment
    w._top_offset_mm = top
    w._join_mode_pt1 = j1
    s.addItem(w)
    s._walls.append(w)
    w.invalidate_geometry()
    return w


def _end_corners(wall, ep):
    quad = wall.outline().quad
    return (quad[0], quad[1]) if ep == 0 else (quad[3], quad[2])


def _raw_end(wall, ep):
    """The drawn end is still the wall's untrimmed end."""
    raw = wall.quad_points()
    want = (raw[0], raw[1]) if ep == 0 else (raw[3], raw[2])
    return all(math.hypot(a.x() - b.x(), a.y() - b.y()) < 1e-6
               for a, b in zip(_end_corners(wall, ep), want))


def _on_body(pt, wall):
    body = wall.outline().body
    n = body.count()
    return any(_on_segment(pt, body.at(i), body.at((i + 1) % n))
               for i in range(n))


def _area(path):
    total = 0.0
    for poly in path.toSubpathPolygons():
        pts = [poly.at(i) for i in range(poly.count())]
        total += abs(sum(a.x() * b.y() - b.x() * a.y()
                         for a, b in zip(pts, pts[1:] + pts[:1]))) / 2.0
    return total


def _on_line(pt, line):
    a, b = line
    length = math.hypot(b.x() - a.x(), b.y() - a.y())
    return abs((pt.x() - a.x()) * (b.y() - a.y())
               - (pt.y() - a.y()) * (b.x() - a.x())) / length < 1e-3


def _assert_lands_on(stopper, ep, joined, label):
    """The stopped end sits on the joined bodies, and overlaps none."""
    for pt in _end_corners(stopper, ep):
        assert any(_on_body(pt, w) for w in joined), f"{label}: end in the air"
    for wall in joined:
        # A lone joined wall can end exactly where it started (the stopper's
        # far face on its raw end); walls that mitre always move their end.
        assert len(joined) == 1 or not _raw_end(wall, 0 if wall._pt1
                                                == stopper._pt1 else 1), (
            f"{label}: stopper trimmed beside a raw wall")
        assert _area(stopper.path().intersected(wall.path())) < 1.0, (
            f"{label}: stopper runs into a joined wall")
    if len(joined) == 1:
        wall = joined[0]
        ends = _end_corners(wall, 0 if wall._pt1 == stopper._pt1 else 1)
        assert any(all(_on_line(pt, face) for pt in ends)
                   for face in stopper.outline().faces), (
            f"{label}: the joined wall does not cross the stopper's end")


@pytest.mark.parametrize("al", ["Center", "Left", "Right"])
@pytest.mark.parametrize("thick", [(200, 200), (100, 300), (300, 100)])
def test_corner_never_stops_on_one_side_only(qapp, al, thick):
    stopped = fell_back = 0
    for deg in range(10, 176, 5):
        s = _ms()
        tall, low = _corner(s, *thick, "Center", al, deg, LOW)
        if low.outline().seams:
            stopped += 1
            _assert_lands_on(low, 0, [tall], str(deg))
        else:
            fell_back += 1
            s2 = _ms()
            twin = _corner(s2, *thick, "Center", al, deg)
            assert _bodies(tall, low) == _bodies(*twin), (
                f"{deg}: no stop must equal today's result")
    assert stopped, "the sweep never exercised a stop"
    assert fell_back, "the sweep never exercised the fallback"


@pytest.mark.parametrize("al", ["Center", "Left", "Right"])
@pytest.mark.parametrize("thick", [(200, 200), (300, 100)])
def test_butt_that_does_not_fit_keeps_todays_corner(qapp, al, thick):
    """No stop: the Butt end stays flat, the other wall mitres as it does
    beside an Auto wall (its body reads only the other wall's raw faces)."""
    fell_back = 0
    for deg in range(10, 176, 5):
        s, s2 = _ms(), _ms()
        tall, low = _corner(s, *thick, "Center", al, deg, j1="Butt")
        if low.outline().seams:
            continue
        fell_back += 1
        auto_tall, _auto_low = _corner(s2, *thick, "Center", al, deg)
        assert _pts(tall) == _pts(auto_tall), f"{deg}: not today's corner"
        raw = low.quad_points()
        assert _pts(low)[0] == (round(raw[0].x(), 3), round(raw[0].y(), 3))
    assert fell_back, "the sweep never exercised the fallback"


@pytest.mark.parametrize("gap", [25, 55, 85])
@pytest.mark.parametrize("al", ["Center", "Left", "Right"])
def test_three_wall_stop_fits_or_stays_todays_pie(qapp, gap, al):
    """LEFT and the second wall sit *gap* degrees apart; a sharp gap has no
    mitre to stop on, so the stop must not happen beside two raw walls."""
    def build(s, deg, top):
        a = math.radians(180 + gap)
        d = math.radians(deg)
        left = _wall2(s, (-1500, 0), (0, 0), 200, "Center")
        other = _wall2(s, (0, 0), (1500 * math.cos(a), 1500 * math.sin(a)),
                       200, al)
        low = _wall2(s, (0, 0), (1500 * math.cos(d), 1500 * math.sin(d)),
                     100, "Center", top)
        for w in (left, other):
            w.invalidate_geometry()
        return left, other, low

    stopped = fell_back = 0
    for deg in range(5, 175, 10):
        s, s2 = _ms(), _ms()
        left, other, low = build(s, deg, LOW)
        if low.outline().seams:
            stopped += 1
            _assert_lands_on(low, 0, [left, other], str(deg))
        else:
            fell_back += 1
            assert (_bodies(left, other, low)
                    == _bodies(*build(s2, deg, 0.0))), f"{deg}: not today's"
    assert stopped + fell_back == 17
    assert fell_back if gap == 25 else stopped


def _four_walls(s, cfg, mode, stop=True):
    walls = []
    for i, (deg, thick, al) in enumerate(cfg):
        a = math.radians(deg)
        asks = stop and i == 0
        walls.append(_wall2(
            s, (0, 0), (1500 * math.cos(a), 1500 * math.sin(a)), thick, al,
            LOW if asks and mode == "height" else 0.0,
            "Butt" if asks and mode == "butt" else "Auto"))
    for w in walls:
        w.invalidate_geometry()
    return walls


@pytest.mark.parametrize("mode", ["butt", "height"])
def test_four_wall_stop_fits_or_stays_todays_pie(qapp, mode):
    """A pie of three joined walls can drop a sharp pair; a stop must not
    land beside the dropped walls (R7)."""
    rng = random.Random(7)
    stopped = fell_back = 0
    for _ in range(150):
        cfg = [(rng.uniform(0, 360), rng.choice((100, 200, 300)),
                rng.choice(("Center", "Left", "Right"))) for _i in range(4)]
        s, s2 = _ms(), _ms()
        walls = _four_walls(s, cfg, mode)
        twin = _four_walls(s2, cfg, mode, stop=False)
        if walls[0].outline().seams:
            stopped += 1
            _assert_lands_on(walls[0], 0, walls[1:], str(cfg))
        else:
            fell_back += 1
            first = 0 if mode == "height" else 1
            assert (_bodies(*walls[first:]) == _bodies(*twin[first:])
                    ), f"{cfg}: not today's result"
    assert stopped and fell_back


# A level edit touches only the joints it changes ─────────────────────────

def _count_rebuilds(monkeypatch):
    rebuilt = []
    real = WallSegment._rebuild_outline

    def spy(self, extra=None):
        rebuilt.append(self)
        real(self, extra)

    monkeypatch.setattr(WallSegment, "_rebuild_outline", spy)
    return rebuilt


def test_level_edit_that_changes_no_joint_rebuilds_nothing(qapp, monkeypatch):
    s = _ms()
    left, down = _left(s), _down(s)
    right = _right(s, top_offset=LOW)
    assert right.outline().seams
    rebuilt = _count_rebuilds(monkeypatch)
    lm = s._level_manager
    lm.get("Level 2").elevation += 500.0
    lm.update_elevations(s)
    assert rebuilt == []
    assert right.outline().seams


def test_level_edit_rebuilds_only_the_changed_junction(qapp, monkeypatch):
    s = _ms()
    left, down = _left(s), _down(s)
    right = _wall(s, (0, 0), (1500, 0))
    right._top_level = "Level 1"
    right.invalidate_geometry()
    # Beyond LEFT's far end: its stroke reads LEFT's union body
    beyond = _wall(s, (-3000, 0), (-1500, 0))
    # A separate corner that the edit leaves alone
    far_a = _wall(s, (9000, 0), (10500, 0))
    far_b = _wall(s, (10500, 0), (10500, 1500))
    assert right.outline().seams
    beyond.outline()
    far_a.outline()
    assert beyond._outline.stroke_segments is not None

    rebuilt = _count_rebuilds(monkeypatch)
    lm = s._level_manager
    lm.get("Level 2").elevation = lm.get("Level 1").elevation
    lm.update_elevations(s)

    assert {id(w) for w in rebuilt} == {id(left), id(down), id(right)}
    assert beyond._outline.stroke_segments is None, "neighbour kept old lines"
    assert far_a._outline.stroke_segments is not None
    assert not right.outline().seams
    assert _is_pie(left, down, right)


# ---------------------------------------------------------------------------
# Seam weight: one stroke over the fills, whatever order the walls were drawn
# ---------------------------------------------------------------------------

_PX_PER_MM = 0.25
_FILL = "#c0c0c0"
_LINE = "#000000"
_SEAM_RECT = QRectF(-400.3, -400.7, 1200, 1200)     # sub-pixel, so AA shows
_PEN_MM = 40.0
_SEAM_CASES = {
    # case: walls, the stopper, the seam's end points, samples along it
    "shaft": ({"L": ((-1500, 0), (0, 0), 0.0), "D": ((0, 0), (0, 1500), 0.0),
               "R": ((0, 0), (1500, 0), LOW)},
              "R", ((HALF, -HALF), (HALF, HALF)), [(HALF, 60.0)]),
    "through": ({"L": ((-1500, 0), (0, 0), 0.0), "R": ((0, 0), (1500, 0), 0.0),
                 "D": ((0, 0), (0, 1500), LOW)},
                "D", ((-HALF, HALF), (HALF, HALF)),
                [(-60.0, HALF), (60.0, HALF)]),
    "corner": ({"L": ((-1500, 0), (0, 0), 0.0), "D": ((0, 0), (0, 1500), LOW)},
               "D", ((-HALF, HALF), (HALF, HALF)), [(0.0, HALF)]),
}
_SEAM_ORDERS = [(case, order) for case, spec in _SEAM_CASES.items()
                for order in itertools.permutations(spec[0])]
_SEAM_IDS = [f"{c}-{''.join(o)}" for c, o in _SEAM_ORDERS]


def _styled_scene(case, order, paper, stopper_line=_LINE):
    s = _ms()
    walls, stopper, _seam, _samples = _SEAM_CASES[case]
    for key in order:
        p1, p2, top = walls[key]
        w = _wall(s, p1, p2, top_offset=top)
        w._fill_mode = "Solid"
        w._display_fill_color = _FILL
        w._display_color = stopper_line if key == stopper else _LINE
        if paper:
            w._paper_pen_width = _PEN_MM
            w._paper_fill_opaque = True
    assert sum(len(w.outline().seams) for w in s._walls) >= 1, "scene has a stop"
    return s


def _seam_images(s, case, paper):
    """The scene, and one stroke of the seam on a plain fill at the same spot."""
    size = (int(_SEAM_RECT.width() * _PX_PER_MM),
            int(_SEAM_RECT.height() * _PX_PER_MM))
    img = QImage(*size, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    s.render(p, QRectF(0, 0, *size), _SEAM_RECT,
             Qt.AspectRatioMode.IgnoreAspectRatio)
    p.end()
    (ax, ay), (bx, by) = _SEAM_CASES[case][2]
    away = 2 * _PEN_MM
    inside = QPoint(
        int(((ax + bx) / 2 + (away if ax == bx else 0) - _SEAM_RECT.x())
            * _PX_PER_MM),
        int(((ay + by) / 2 + (away if ay == by else 0) - _SEAM_RECT.y())
            * _PX_PER_MM))
    ref = QImage(*size, QImage.Format.Format_RGB32)
    ref.fill(img.pixelColor(inside))
    p = QPainter(ref)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(_PX_PER_MM, _PX_PER_MM)
    p.translate(-_SEAM_RECT.x(), -_SEAM_RECT.y())
    pen = QPen(QColor(_LINE), _PEN_MM if paper else 1.0)
    pen.setCosmetic(not paper)
    p.setPen(pen)
    p.drawLine(QPointF(ax, ay), QPointF(bx, by))
    p.end()
    return img, ref


def _across(img, case, sample, paper):
    """Red channel of the pixels across the seam at *sample*."""
    (ax, _ay), (bx, _by) = _SEAM_CASES[case][2]
    reach = int(_PEN_MM * _PX_PER_MM) + 4 if paper else 4
    x = int((sample[0] - _SEAM_RECT.x()) * _PX_PER_MM)
    y = int((sample[1] - _SEAM_RECT.y()) * _PX_PER_MM)
    dx, dy = (1, 0) if ax == bx else (0, 1)
    return [img.pixelColor(x + dx * i, y + dy * i).red()
            for i in range(-reach, reach + 1)]


@pytest.mark.parametrize("paper", [False, True], ids=["canvas", "paper"])
@pytest.mark.parametrize("case,order", _SEAM_ORDERS, ids=_SEAM_IDS)
def test_seam_is_one_stroke_over_the_fills(qapp, case, order, paper):
    s = _styled_scene(case, order, paper)
    img, ref = _seam_images(s, case, paper)
    for sample in _SEAM_CASES[case][3]:
        got = _across(img, case, sample, paper)
        want = _across(ref, case, sample, paper)
        assert min(want) < 90, "the reference shows a dark line"
        assert all(abs(g - w) <= 8 for g, w in zip(got, want)), (got, want)


@pytest.mark.parametrize("case,order", _SEAM_ORDERS, ids=_SEAM_IDS)
def test_seam_keeps_the_stopper_colour(qapp, case, order):
    s = _styled_scene(case, order, paper=True, stopper_line="#ff0000")
    img, _ref = _seam_images(s, case, paper=True)
    for sample in _SEAM_CASES[case][3]:
        centre = img.pixelColor(
            int((sample[0] - _SEAM_RECT.x()) * _PX_PER_MM),
            int((sample[1] - _SEAM_RECT.y()) * _PX_PER_MM))
        assert (centre.red(), centre.green()) == (255, 0), centre.name()


def test_seam_painter_follows_a_stacking_change(qapp):
    # On paper: the wide pen and opaque fill show a stale painter at any offset.
    s = _styled_scene("shaft", ("R", "L", "D"), paper=True)
    right = next(w for w in s._walls if w.outline().seams)
    down = next(w for w in s._walls if w.pt2.y() > 1000)

    def assert_one_stroke():
        img, ref = _seam_images(s, "shaft", True)
        got = _across(img, "shaft", (HALF, 60.0), True)
        want = _across(ref, "shaft", (HALF, 60.0), True)
        assert all(abs(g - w) <= 8 for g, w in zip(got, want)), (got, want)

    assert_one_stroke()
    right.setZValue(down.zValue() + 1.0)         # the stopper now paints last
    assert_one_stroke()
