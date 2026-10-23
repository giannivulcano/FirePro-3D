"""Wall polish junction guards: G3 (per-level joins, D4) and the outline
cache (D2/D6); G1/G2 pixel guards are added in Task 4."""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.level_manager import LevelManager
from firepro3d.wall import WallSegment


def _ms():
    """Model_Space with Levels 1-5, 3 m apart (Level 1/2 elevations as the
    LevelManager defaults them)."""
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    s._level_manager = LevelManager()
    lm = s._level_manager
    e1 = lm.get("Level 1").elevation
    if lm.get("Level 2") is None:
        lm.add_level("Level 2", elevation=e1 + 3000.0)
    e2 = lm.get("Level 2").elevation
    for i, name in enumerate(("Level 3", "Level 4", "Level 5"), start=1):
        lm.add_level(name, elevation=e2 + 3000.0 * i)
    return s


def _view(s, level):
    """Apply a plan view of *level* whose range excludes adjacent floors."""
    e = s._level_manager.get(level).elevation
    s._level_manager.apply_to_scene(s, active_level=level,
                                    view_height=e + 1200.0,
                                    view_depth=e - 300.0)


def _wall(s, p1, p2, base="Level 1", top="Level 2", th=200.0):
    w = WallSegment(QPointF(*p1), QPointF(*p2), thickness_mm=th)
    w._base_level, w._top_level = base, top
    s.addItem(w)
    s._walls.append(w)
    # precondition for the literal mm coordinates below: default calibration
    # (ScaleManager.paper_to_scene = paper_mm * px_per_mm(1) * drawing_scale)
    assert abs(w.half_thickness_scene() - th / 2.0) < 1e-9
    return w


def _on_segment(pt, a, b, tol=1e-3):
    dx, dy = b.x() - a.x(), b.y() - a.y()
    L = math.hypot(dx, dy)
    if L == 0.0:
        return False
    t = ((pt.x() - a.x()) * dx + (pt.y() - a.y()) * dy) / L
    d = abs((pt.x() - a.x()) * dy - (pt.y() - a.y()) * dx) / L
    return d <= tol and -tol <= t <= L + tol


def _stroked(wall, pt):
    return any(_on_segment(pt, a, b) for a, b in wall.outline().stroke_segments)


class TestPerLevelJoins:
    def test_offlevel_wall_never_joins(self, qapp):
        s = _ms()
        upper = _wall(s, (0, 0), (2000, 0), "Level 3", "Level 4")
        lower = _wall(s, (2000, 0), (2000, 1500), "Level 1", "Level 2")
        _view(s, "Level 3")
        assert not lower.isVisible() and upper.isVisible()   # precondition
        o = upper.outline()
        assert o.solid[1] is False
        p1l, p1r, p2r, p2l = o.quad
        end_mid = QPointF((p2l.x() + p2r.x()) / 2, (p2l.y() + p2r.y()) / 2)
        assert _stroked(upper, end_mid)                       # end edge drawn

    def test_both_visible_still_join(self, qapp):
        """Positive control: a view range spanning both walls joins them."""
        s = _ms()
        upper = _wall(s, (0, 0), (2000, 0), "Level 1", "Level 4")
        lower = _wall(s, (2000, 0), (2000, 1500), "Level 1", "Level 2")
        _view(s, "Level 1")
        assert upper.isVisible() and lower.isVisible()
        assert upper.outline().solid[1] is True

    def test_shaft_tee_breaks_only_where_visible(self, qapp):
        s = _ms()
        shaft = _wall(s, (0, 0), (4000, 0), "Level 1", "Level 5")
        tee = _wall(s, (2000, 0), (2000, 2000), "Level 3", "Level 4", th=150.0)
        near_face_at_tee = QPointF(2000, 100)      # shaft left face, y=+100
        _view(s, "Level 3")
        assert shaft.isVisible() and tee.isVisible()
        assert not _stroked(shaft, near_face_at_tee)   # T-break on L3
        _view(s, "Level 1")
        assert shaft.isVisible() and not tee.isVisible()
        assert _stroked(shaft, near_face_at_tee)       # continuous on L1


class TestOutlineCache:
    def test_tee_union_end_reaches_host_centerline(self, qapp):
        s = _ms()
        host = _wall(s, (0, 0), (4000, 0))
        stub = _wall(s, (2000, 0), (2600, 1500))
        o = stub.outline_geometry()
        assert o.solid[0] is True                       # coped body
        ys = sorted(round(o.union_body.at(i).y(), 6)
                    for i in range(o.union_body.count()))
        assert ys[0] == pytest.approx(0.0, abs=1e-6)    # union end on y=0
        assert min(o.body.at(i).y()
                   for i in range(o.body.count())) == pytest.approx(100.0)

    def test_alignment_set_after_construction_rebuilds(self, qapp):
        """D3: the _alignment property setter invalidates (placement and
        from_dict assign it after __init__)."""
        s = _ms()
        w = _wall(s, (0, 0), (3000, 0))
        before = w.path().boundingRect()
        w._alignment = "Left"
        after = w.path().boundingRect()
        assert after.top() == pytest.approx(0.0, abs=1e-6)
        assert before.top() < -1.0

    def test_removed_neighbour_releases_join(self, qapp):
        s = _ms()
        a = _wall(s, (0, 0), (2000, 0))
        b = _wall(s, (2000, 0), (2000, 1500))
        assert a.outline().solid[1] is True
        s._walls.remove(b)
        s.removeItem(b)                         # Model_Space delete order
        assert a.outline().solid[1] is False
        assert len(a.outline().caps) == 2

    def test_unjoined_overlap_strokes_full_body(self, qapp):
        """AC1: crossing walls that do not join each stroke their full body."""
        s = _ms()
        a = _wall(s, (0, 0), (4000, 0))
        b = _wall(s, (2000, -2000), (2000, 2000))
        for w in (a, b):
            total = sum(math.hypot(q.x() - p.x(), q.y() - p.y())
                        for p, q in w.outline().stroke_segments)
            assert total == pytest.approx(2 * 4000 + 2 * 200, abs=1e-6)


# -- G1 / G2 pixel guards (AC1) ------------------------------------------------

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from firepro3d.wall import ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT, FILL_SOLID

_PX_PER_MM = 0.25            # 200 mm wall = 50 px; cosmetic pen = 1 px
_SKIP_MM = 40.0              # stay clear of the outer outline near seam ends
_PROBE_MM = 5.0              # outward step that decides "interior seam"
_VERTEX_CLEAR_MM = 8.0       # > the 1-px (4 mm) read window around a sample
# Explicit-Butt L at Right alignment: the bodies only touch along an edge
# (the butt wall hangs off the mitered wall's face), so there is no overlap
# and thus no interior seam to sample.
_NO_OVERLAP = {("L-butt", ALIGN_RIGHT)}


def _render(scene, rect):
    img = QImage(int(rect.width() * _PX_PER_MM),
                 int(rect.height() * _PX_PER_MM), QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, img.width(), img.height()), rect,
                 Qt.AspectRatioMode.IgnoreAspectRatio)
    p.end()
    return img


def _px(img, rect, pt):
    return (int((pt.x() - rect.x()) * _PX_PER_MM),
            int((pt.y() - rect.y()) * _PX_PER_MM))


def _is_line_red(c: QColor) -> bool:
    return c.red() > 150 and c.green() < 110 and c.blue() < 110


def _poly_contains(poly, pt):
    from PyQt6.QtGui import QPainterPath
    path = QPainterPath()
    path.addPolygon(poly)
    path.closeSubpath()
    return path.contains(pt)


def _edge_crossings(bodies):
    """Points where an edge of one body crosses an edge of another (the
    corners of the union outline that are not body vertices)."""
    from firepro3d.wall_outline import intersect_lines
    out = []
    for i, a in enumerate(bodies):
        for j in range(i + 1, len(bodies)):
            b = bodies[j]
            for k in range(a.count()):
                p1, p2 = a.at(k), a.at((k + 1) % a.count())
                for m in range(b.count()):
                    q1, q2 = b.at(m), b.at((m + 1) % b.count())
                    x = intersect_lines(p1, p2, q1, q2)
                    if x is None:
                        continue
                    if (_on_segment(x, p1, p2, 1e-6)
                            and _on_segment(x, q1, q2, 1e-6)):
                        out.append(x)
    return out


def _seam_samples(walls):
    """Interior seam points from BODIES only (not from stroke logic): a body
    edge point whose outward neighbourhood lies inside another wall's body
    is inside the junction.  Points near any edge end are skipped."""
    out = []
    bodies = [w.outline_geometry().body for w in walls]
    # A body vertex (any wall) is where a legitimate stroke may end; a sample
    # within the 3x3-pixel read window (_VERTEX_CLEAR_MM) of one would read
    # that stroke, not a seam.
    verts = [b.at(k) for b in bodies for k in range(b.count())]
    verts += _edge_crossings(bodies)       # where two bodies' edges cross
    for i, body in enumerate(bodies):
        n = body.count()
        for k in range(n):
            p, q = body.at(k), body.at((k + 1) % n)
            dx, dy = q.x() - p.x(), q.y() - p.y()
            L = math.hypot(dx, dy)
            if L < 2 * _SKIP_MM:
                continue
            for s in range(1, 20):
                t = s / 20.0
                if t * L < _SKIP_MM or (1 - t) * L < _SKIP_MM:
                    continue
                pt = QPointF(p.x() + dx * t, p.y() + dy * t)
                if any(math.hypot(pt.x() - v.x(), pt.y() - v.y())
                       < _VERTEX_CLEAR_MM for v in verts):
                    continue
                nx, ny = dy / L, -dx / L           # one side ...
                a = QPointF(pt.x() + nx * _PROBE_MM, pt.y() + ny * _PROBE_MM)
                b = QPointF(pt.x() - nx * _PROBE_MM, pt.y() - ny * _PROBE_MM)
                outward = b if _poly_contains(body, a) else a
                if any(_poly_contains(bodies[j], outward)
                       for j in range(len(bodies)) if j != i):
                    out.append(pt)
    return out


def _junction_case(s, case, align):
    th = 200.0
    def w(p1, p2, **kw):
        wall = _wall(s, p1, p2, th=kw.get("th", th))
        wall._colour = "#ff0000"
        wall._alignment = align
        if "j1" in kw:
            wall._join_mode_pt1 = kw["j1"]
        return wall
    if case == "L":
        return [w((0, 0), (3000, 0)), w((3000, 0), (3000, 2500))]
    if case == "L-butt":
        return [w((0, 0), (3000, 0)), w((3000, 0), (3000, 2500), j1="Butt")]
    if case == "T":
        return [w((0, 0), (5000, 0)), w((2500, 0), (2500, 2500))]
    if case == "3way":
        return [w((-3000, 0), (0, 0)), w((0, 0), (0, 2500)),
                w((0, 0), (2000, -2000))]
    if case == "4way":
        return [w((0, 0), far) for far in
                ((3000, 0), (0, 3000), (-3000, 0), (0, -3000))]
    if case == "failed-tee":   # 10 deg stub: cope beyond MAX_MITER -> butt end in host
        a = math.radians(10.0)
        return [w((0, 0), (6000, 0)),
                w((2500, 0), (2500 + 3000 * math.cos(a), 3000 * math.sin(a)))]
    raise ValueError(case)


_CASES = ["L", "L-butt", "T", "3way", "4way", "failed-tee"]
_ALIGNS = [ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT]


@pytest.mark.parametrize("align", _ALIGNS)
@pytest.mark.parametrize("case", _CASES)
def test_junction_seam_has_no_outline_pixels(qapp, case, align):
    """G1: every joined junction paints as one body -- no outline pixel on
    any interior seam (real paint() through scene.render)."""
    s = _ms()
    walls = _junction_case(s, case, align)
    samples = _seam_samples(walls)
    if (case, align) in _NO_OVERLAP:
        assert not samples, "scenario unexpectedly overlaps"
        return
    assert samples, "scenario produced no interior seam to check"
    rect = QRectF(-4000, -4000, 11000, 8000)
    img = _render(s, rect)
    bad = []
    for pt in samples:
        x, y = _px(img, rect, pt)
        if any(_is_line_red(img.pixelColor(x + dx, y + dy))
               for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
            bad.append((round(pt.x()), round(pt.y())))
    assert not bad, f"{case}/{align}: outline drawn on seam at {bad[:5]}"


def test_differing_fills_meet_without_overlap(qapp):
    """G2 (D7): three differently coloured solid fills at a pie junction --
    each slice shows only its own colour (no stacked overlap, no line)."""
    s = _ms()
    cols = ["#ff0000", "#00c000", "#0000ff"]
    walls = [_wall(s, (-3000, 0), (0, 0)), _wall(s, (0, 0), (0, 2500)),
             _wall(s, (0, 0), (2000, -2000))]
    for wall, col in zip(walls, cols):
        wall._colour = col
        wall._fill_mode = FILL_SOLID
        wall._display_color = ""            # "" = No stroke: fill only
        wall.update()
    rect = QRectF(-4000, -4000, 8000, 8000)
    img = _render(s, rect)
    for wall in walls:
        o = wall.outline_geometry()
        end = 0 if math.hypot(wall.pt1.x(), wall.pt1.y()) < 1 else 1
        a, b = (o.quad[0], o.quad[1]) if end == 0 else (o.quad[3], o.quad[2])
        hub = o.wedge[end][0]
        probe = QPointF((a.x() + b.x() + hub.x()) / 3, (a.y() + b.y() + hub.y()) / 3)
        mid = QPointF((wall.pt1.x() + wall.pt2.x()) / 2 + wall._centerline_offset().x(),
                      (wall.pt1.y() + wall.pt2.y()) / 2 + wall._centerline_offset().y())
        ref = img.pixelColor(*_px(img, rect, mid))
        got = img.pixelColor(*_px(img, rect, probe))
        assert abs(ref.red() - got.red()) <= 6, wall
        assert abs(ref.green() - got.green()) <= 6, wall
        assert abs(ref.blue() - got.blue()) <= 6, wall


def test_hatch_flows_across_t_junction(qapp, shipped_hatches):
    """G1 positive half: with section hatch on, hatch strokes exist on both
    sides of the T seam (the seam is not a hatch-free gap).  The shipped
    hatch blocks are loaded through the real registry path (without them
    paint draws a flat tone, not strokes)."""
    from firepro3d.wall import FILL_HATCH
    s = _ms()
    shipped_hatches(s)
    host = _wall(s, (0, 0), (5000, 0))
    stub = _wall(s, (2500, 0), (2500, 2500))
    for wall in (host, stub):
        wall._colour = "#ff0000"
        wall._fill_mode = FILL_HATCH
        wall.update()
    rect = QRectF(1500, -1000, 2000, 2000)
    img = _render(s, rect)
    def red_in(x0, y0, x1, y1):
        return any(_is_line_red(img.pixelColor(*_px(img, rect, QPointF(x, y))))
                   for x in range(int(x0), int(x1), 4)
                   for y in range(int(y0), int(y1), 4))
    assert red_in(2420, 20, 2580, 95)      # host side, under the stub
    assert red_in(2420, 105, 2580, 180)    # stub side, above the seam


def test_butt_l_union_keeps_both_bodies(qapp):
    """Qt's path clipper drops the long wall's body from the cluster union in
    one operand order when an explicit-Butt wall end lies on the mitered
    wall's face (Left alignment, float-noisy coordinates from real walls):
    the mitered wall must still stroke its far face and not the hidden
    miter diagonal."""
    s = _ms()
    w0, w1 = _junction_case(s, "L-butt", ALIGN_LEFT)
    o = w0.outline()
    assert any(_on_segment(QPointF(1000, 200), a, b)
               for a, b in o.stroke_segments)          # far face kept
    assert not _stroked(w0, QPointF(2900, 100))        # miter diagonal hidden


def _snapshot(wall):
    """Body, union body and stroke segments of the wall's cached outline."""
    def pts(poly):
        return [(round(poly.at(k).x(), 6), round(poly.at(k).y(), 6))
                for k in range(poly.count())]
    o = wall.outline()
    segs = [tuple(round(c, 6) for c in (a.x(), a.y(), b.x(), b.y()))
            for a, b in o.stroke_segments]
    return pts(o.body), pts(o.union_body), segs


@pytest.mark.parametrize("attr, value", [("_join_mode_pt1", "Butt"),
                                         ("_thickness_mm", 400.0)])
def test_direct_attribute_write_refreshes_partner_outline(qapp, attr, value):
    """F1(a): a direct write of a geometry input on a joined wall refreshes
    the PARTNER's cached outline (no reliance on the paint-time self-heal on
    the partner's own key, which does not see the other wall's change)."""
    s = _ms()
    a = _wall(s, (0, 0), (3000, 0))
    b = _wall(s, (3000, 0), (3000, 2500))
    before = _snapshot(a)
    setattr(b, attr, value)
    cached_snap = _snapshot(a)
    a._rebuild_outline()
    a._outline.stroke_segments = None
    fresh = _snapshot(a)
    assert cached_snap == fresh, "partner outline stale after direct write"
    assert fresh != before, "scenario: the write must change the partner"
