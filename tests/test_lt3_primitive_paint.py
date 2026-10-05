"""LT3-6/7 + G1/G2/G-canvas (Block Editor half) -- raw primitives draw dashed."""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.lt3_support import hidden


def _editor():
    ms = Model_Space(scene_role="block_editor")
    return ms, hidden(ms)


def _render(ms, rect, w=400, h=40):
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, w, h), rect)
    p.end()
    return img


def _row(img, y):
    return [QColor(img.pixel(x, y)).lightness() > 128 for x in range(img.width())]


def _line(ms, lt, a, b):
    ln = LineItem(QPointF(*a), QPointF(*b))
    ln.style["linetype"] = lt
    ms.addItem(ln)
    return ln


def test_block_editor_draws_real_size_dashes(qapp):
    ms, lid = _editor()
    _line(ms, lid, (0, 0), (36, 0))
    row = _row(_render(ms, QRectF(0, -2, 40, 4)), 20)       # 10 px per mm
    # Hidden 6/3 at 1:1 -> lit 0-60 px, dark 60-90, lit 90-150 ...
    assert all(row[5:55]) and not any(row[65:85]) and all(row[95:145])


def test_g1_collinear_pieces_match_one_line(qapp):
    # Hidden 6/3: ink 0-6, 9-15, 18-24, 27-33, 36. The split leaves a real gap
    # at 15..18 mm, which is already a pattern gap -> rasters must be identical.
    ms1, l1 = _editor()
    _line(ms1, l1, (0, 0), (36, 0))
    ms2, l2 = _editor()
    _line(ms2, l2, (15, 0), (0, 0))              # drawn reversed
    _line(ms2, l2, (18, 0), (36, 0))             # gapped, drawn forward
    r1 = _row(_render(ms1, QRectF(0, -2, 40, 4)), 20)
    r2 = _row(_render(ms2, QRectF(0, -2, 40, 4)), 20)
    assert r1 == r2


def test_g1_off_grid_split_matches_one_line(qapp):
    """D-L9 axis phase: a split at 16 mm (not a period multiple, not a dash
    edge) still reproduces the single line -- a start-anchored phase would
    restart the reversed and the forward piece at their own ends."""
    ms1, l1 = _editor()
    _line(ms1, l1, (0, 0), (36, 0))
    ms2, l2 = _editor()
    _line(ms2, l2, (16, 0), (0, 0))              # drawn reversed, ends at 16
    _line(ms2, l2, (16, 0), (36, 0))             # abutting, drawn forward
    r1 = _row(_render(ms1, QRectF(0, -2, 40, 4)), 20)
    r2 = _row(_render(ms2, QRectF(0, -2, 40, 4)), 20)
    assert not any(r1[155:175])                   # the 15.5..17.5 mm gap is real
    assert r1 == r2


def test_continuous_unchanged_and_lod_solid(qapp):
    ms, lid = _editor()
    _line(ms, lid, (0, 0), (3600, 0))
    row = _row(_render(ms, QRectF(0, -200, 4000, 400)), 20)   # 0.1 px/mm: period 0.9 px
    assert all(row[5:355])                        # LOD -> solid


def test_selected_dashed_highlight_follows_dashes(qapp):
    ms, lid = _editor()
    ln = _line(ms, lid, (0, 0), (36, 0))
    ln.setSelected(True)
    row = _row(_render(ms, QRectF(0, -2, 40, 4)), 20)
    assert not any(row[65:85])                    # gap stays dark when selected
    assert all(row[5:55])                         # dash still lit


def test_g2_trim_keeps_surviving_dashes(qapp):
    ms, lid = _editor()
    full = _line(ms, lid, (0, 0), (36, 0))
    before = _row(_render(ms, QRectF(0, -2, 40, 4)), 20)
    full.set_length(20.0)                          # in-place trim of the far end
    after = _row(_render(ms, QRectF(0, -2, 40, 4)), 20)
    assert not any(after[65:85])                   # still dashed (not solid)
    assert after[:195] == before[:195]
    assert not any(after[205:])                    # the trimmed tail is gone


def test_g2_real_trim_tool_keeps_surviving_dashes(qapp):
    """G2 through the real two-phase Trim tool (scene_tools._handle_trim_click)."""
    from tests._snap_polish_helpers import click, close_view, make_view
    view, scene = make_view(scale=1.0, mode=None)
    try:
        lid = hidden(scene, size="model")          # factor 1 on the plan canvas
        ln = _line(scene, lid, (0, 0), (36, 0))
        scene._draw_lines.append(ln)
        edge = LineItem(QPointF(20, -100), QPointF(20, 100))
        scene.addItem(edge)
        scene._draw_lines.append(edge)
        before = _row(_render(scene, QRectF(0, -2, 40, 4)), 20)
        scene.set_mode("trim")
        click(view, QPointF(20, 80))               # cutting edge
        click(view, QPointF(30, 0))                # remove the far piece
        assert abs(ln.line().p2().x() - 20.0) < 1e-6   # really trimmed
        after = _row(_render(scene, QRectF(0, -2, 40, 4)), 20)
        assert not any(after[65:85])               # still dashed (not solid)
        assert after[:195] == before[:195]
        assert not any(after[215:])
    finally:
        close_view(view, scene)


def test_g2_real_trim_near_end_keeps_surviving_dashes(qapp):
    """G2 through the real Trim tool removing the NEAR piece: pt1 moves to the
    cut, and the surviving dashes stay on the axis rhythm (D-L9)."""
    from tests._snap_polish_helpers import click, close_view, make_view
    view, scene = make_view(scale=1.0, mode=None)
    try:
        lid = hidden(scene, size="model")          # factor 1 on the plan canvas
        ln = _line(scene, lid, (0, 0), (36, 0))
        scene._draw_lines.append(ln)
        edge = LineItem(QPointF(20, -100), QPointF(20, 100))
        scene.addItem(edge)
        scene._draw_lines.append(edge)
        before = _row(_render(scene, QRectF(0, -2, 40, 4)), 20)
        scene.set_mode("trim")
        click(view, QPointF(20, 80))               # cutting edge
        click(view, QPointF(10, 0))                # remove the near piece
        assert abs(ln.line().p1().x() - 20.0) < 1e-6   # start really moved
        after = _row(_render(scene, QRectF(0, -2, 40, 4)), 20)
        assert not any(after[245:265])             # 24..27 mm axis gap stays dark
        assert after[205:360] == before[205:360]
        assert not any(after[15:195])              # the near piece is gone (x<15 px: origin cross)
    finally:
        close_view(view, scene)


def _all_primitives():
    from firepro3d.geometry_2d import (ArcItem, CircleItem, EllipseItem, PolylineItem,
                                       RectangleItem, RegularPolygonItem, SplineItem)
    pl = PolylineItem(QPointF(-15, -15))
    for p in ((15, -15), (15, 10), (-10, 15)):
        pl.append_point(QPointF(*p))
    rect = RectangleItem(QPointF(-12, -8), QPointF(12, 8))
    rect.set_angle(30.0)                          # rotation baked as data
    return {
        "line": LineItem(QPointF(-15, -10), QPointF(15, 12)),
        "polyline": pl,
        "rect": rect,
        "circle": CircleItem(QPointF(0, 0), 14.0),
        "arc": ArcItem(QPointF(0, 0), 14.0, 20.0, 250.0),
        "polygon": RegularPolygonItem(QPointF(0, 0), 6, 14.0),
        "ellipse": EllipseItem(QPointF(0, 0), 16.0, 9.0, 25.0),
        "spline": SplineItem([QPointF(-15, 0), QPointF(-5, 15), QPointF(5, -15),
                              QPointF(15, 0)]),
    }


def _lit(ms):
    img = _render(ms, QRectF(-20, -20, 40, 40), 400, 400)
    return {(x, y) for y in range(400) for x in range(400)
            if QColor(img.pixel(x, y)).lightness() > 128}


import pytest  # noqa: E402


@pytest.mark.parametrize("kind", ["line", "polyline", "rect", "circle", "arc",
                                  "polygon", "ellipse", "spline"])
def test_every_styled_primitive_draws_dashes_on_its_stroke(qapp, kind):
    """H3-f: all 8 paint()s route through paint_stroke; dashes lie on the
    plain stroke (rotated Rect included) and leave real gaps."""
    ms_c = Model_Space(scene_role="block_editor")
    ms_c.addItem(_all_primitives()[kind])
    solid = _lit(ms_c)
    ms_d, lid = _editor()
    it = _all_primitives()[kind]
    it.style["linetype"] = lid
    ms_d.addItem(it)
    dashed = _lit(ms_d)
    assert solid and dashed
    assert len(dashed) < 0.85 * len(solid)        # gaps (Hidden = 6/9 ink)
    near = {(x + dx, y + dy) for x, y in solid for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    off = dashed - near                           # 1 px AA rasterisation slack
    assert len(off) <= 0.02 * len(dashed), len(off)   # on the plain stroke


# -- seam guard gaps (LT3-5 / LT3-6 / G2 Break) ---------------------------------

def test_plan_raw_line_dashes_at_drawing_scale(qapp):
    """LT3-5 plan canvas, RAW primitive: a loose plan line given Hidden through
    the real panel pick dashes at printed mm x drawing_scale x zoom
    (6 mm x 100 = 600 mm = 60 px at 0.1 px/mm).

    The line is added directly: the draw tools refuse on the plan and Explode
    is Block-Editor-only (containment C1), so no UI path creates one -- the
    item is the session-only loose plan geometry (C8) the seam review probed.
    """
    from tests._snap_polish_helpers import close_view, make_view
    view, scene = make_view(role="plan", scale=0.1, mode=None)
    try:
        hidden(scene)
        ln = LineItem(QPointF(-1500, 1000), QPointF(1500, 1000))
        scene.addItem(ln)
        scene._draw_lines.append(ln)
        ln.set_property("Linetype", "Hidden")
        assert ln.style["linetype"] != "continuous"
        assert scene.scale_manager.drawing_scale == 100.0
        img = _render(scene, QRectF(-2000, -2000, 4000, 4000), 400, 400)
        row = _row(img, 300)
        runs, start = [], None
        for x, on in enumerate(row + [False]):
            if on and start is None:
                start = x
            if not on and start is not None:
                runs.append(x - start)
                start = None
        inner = runs[1:-1]
        assert inner and all(abs(r - 60) <= 2 for r in inner), runs
    finally:
        close_view(view, scene)


def _parity_pair(make):
    """(continuous item, Hidden item), each alone in a Block Editor scene."""
    out = []
    for styled in (False, True):
        ms, lid = _editor()
        it = make()
        if styled:
            it.style["linetype"] = lid
        ms.addItem(it)
        out.append((ms, it))
    return out


@pytest.mark.parametrize("kind", ["line", "circle", "rect"])
def test_halo_snap_and_shape_stay_on_the_continuous_base(qapp, kind):
    """LT3-6: HALO trace, shape() and snap candidates of a linetyped item equal
    the Continuous item's -- including a cursor over a dash GAP."""
    from firepro3d.halo import halo_scene_path
    from firepro3d.snap_engine import SnapEngine
    from PyQt6.QtGui import QTransform
    from firepro3d.geometry_2d import CircleItem, RectangleItem
    make = {"line": lambda: LineItem(QPointF(0, 0), QPointF(36, 0)),
            "circle": lambda: CircleItem(QPointF(0, 0), 14.0),
            "rect": lambda: RectangleItem(QPointF(0, 0), QPointF(36, 18))}[kind]
    (ms_c, c), (ms_h, h) = _parity_pair(make)
    assert halo_scene_path(h) == halo_scene_path(c)
    assert h.shape() == c.shape()
    probes = [QPointF(7.5, 0.3), QPointF(16.5, -0.2), QPointF(18.0, 0.0),
              QPointF(36.0, 0.2), QPointF(14.0, 0.1), QPointF(0.0, 14.2),
              QPointF(36.2, 9.0)]
    for cur in probes:
        rc = SnapEngine().find(cur, ms_c, QTransform())
        rh = SnapEngine().find(cur, ms_h, QTransform())
        key = lambda r: None if r is None else (r.snap_type, round(r.point.x(), 6),
                                                round(r.point.y(), 6))
        assert key(rh) == key(rc), cur


def test_g2_real_break_tool_keeps_surviving_dashes(qapp):
    """G2 through the real two-click Break tool (_press_break): the pieces
    either side of the cut keep the uncut line's dash pixels."""
    from tests._snap_polish_helpers import click, close_view, make_view
    view, scene = make_view(role="block_editor", scale=10.0, mode=None)
    try:
        lid = hidden(scene)
        ln = _line(scene, lid, (0, 0), (36, 0))
        scene._draw_lines.append(ln)
        before = _row(_render(scene, QRectF(0, -2, 40, 4)), 20)
        scene.set_mode("break")
        click(view, QPointF(30, 0))                # pick the line
        click(view, QPointF(16, 0))                # first break point
        click(view, QPointF(20.5, 0))              # second break point
        scene.set_mode("select")                   # (break mode renders blank)
        a, b = sorted(scene._draw_lines, key=lambda i: i.line().p1().x())
        cut0, cut1 = a.line().p2().x(), b.line().p1().x()
        assert 15.0 < cut0 < 17.0 and 19.5 < cut1 < 21.5, (cut0, cut1)
        after = _row(_render(scene, QRectF(0, -2, 40, 4)), 20)
        lo, hi = int(cut0 * 10) - 3, int(cut1 * 10) + 3
        assert after[:lo] == before[:lo]
        assert after[hi:360] == before[hi:360]
        assert not any(after[245:265])             # an axis gap stays dark
    finally:
        close_view(view, scene)
