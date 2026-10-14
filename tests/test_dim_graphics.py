"""CS4b dim graphics (parametric-constraint-system.md D60-D66): layout in
viewport px on a real shown view, signed offset, hit test, terminator."""
import json
import math
import os

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d import constants as K
from firepro3d import dim_graphics as dg
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View


@pytest.fixture
def view(qapp):
    """A shown Block Editor view at 1 px / mm (scene y down = screen down)."""
    sc = Model_Space(scene_role="block_editor")
    v = Model_View(sc)
    v.resize(800, 600)
    v.show()
    QTest.qWaitForWindowExposed(v)
    v.resetTransform()
    v.centerOn(100, 0)
    QApplication.processEvents()
    yield v
    sc.cleanup()
    v.close()
    v.deleteLater()
    QApplication.processEvents()


def _vp(v, x, y):
    return QPointF(v.mapFromScene(QPointF(x, y)))


def test_signed_offset_is_along_the_left_normal():
    a, b = QPointF(0, 0), QPointF(100, 0)
    assert dg.unit_normal(a, b) == pytest.approx((0.0, 1.0))
    assert dg.signed_offset(a, b, QPointF(50, 20)) == pytest.approx(20.0)
    assert dg.signed_offset(a, b, QPointF(50, -20)) == pytest.approx(-20.0)
    assert dg.unit_normal(a, a) is None


def test_offset_of_reads_only_a_numeric_offset():
    assert dg.offset_of({"offset": -12.5}) == -12.5
    assert dg.offset_of(None) is None
    assert dg.offset_of({"offset": [3, 4]}) is None          # the old reserved shape
    assert dg.offset_of({"offset": True}) is None
    assert dg.with_offset(None, 4) == {"offset": 4.0}


def test_layout_puts_the_dim_line_at_the_offset_with_witness_lines(view):
    v = view
    g = dg.layout_dim(v, QPointF(0, 0), QPointF(200, 0), -30.0, "200", tlen=7.5)
    A0, B0 = _vp(v, 0, 0), _vp(v, 200, 0)
    assert (g.a.x(), g.a.y()) == pytest.approx((A0.x(), A0.y() - 30), abs=1e-6)
    assert (g.b.x(), g.b.y()) == pytest.approx((B0.x(), B0.y() - 30), abs=1e-6)
    (w1s, w1e), (w2s, w2e) = g.witness
    assert (w1s.y(), w1e.y()) == pytest.approx((A0.y() - 3, A0.y() - 34), abs=1e-6)
    assert w1s.x() == pytest.approx(A0.x()) and w2s.x() == pytest.approx(B0.x())
    assert g.inside
    (ta, ua), (tb, ub) = g.terms
    assert ua == pytest.approx((-1.0, 0.0)) and ub == pytest.approx((1.0, 0.0))
    assert g.label.center.y() < g.a.y()                       # text outside (above)
    assert g.label.center.x() == pytest.approx((A0.x() + B0.x()) / 2, abs=1e-6)


def test_zero_offset_draws_no_witness_lines(view):
    g = dg.layout_dim(view, QPointF(0, 0), QPointF(200, 0), 0.0, "200", tlen=7.5)
    assert g.witness == []


def test_short_dim_puts_terminators_outside_pointing_in(view):
    v = view
    g = dg.layout_dim(v, QPointF(0, 0), QPointF(10, 0), -20.0, "10", tlen=7.5)
    assert not g.inside
    (ta, ua), (tb, ub) = g.terms
    assert ua == pytest.approx((1.0, 0.0)) and ub == pytest.approx((-1.0, 0.0))
    assert g.label.center.x() > g.b.x() + K.DIM_SHORT_LEADER_PX


def test_auto_offset_sits_away_from_the_item_centre(view):
    v = view
    A0 = _vp(v, 0, 0)
    g = dg.layout_dim(v, QPointF(0, 0), QPointF(200, 0), None, "200",
                      away=QPointF(100, 50), tlen=7.5)            # centre below
    assert g.a.y() == pytest.approx(A0.y() - K.DIM_AUTO_OFFSET_PX)
    g2 = dg.layout_dim(v, QPointF(0, 0), QPointF(200, 0), None, "200",
                       away=QPointF(100, 0), tlen=7.5)            # undecided -> up
    assert g2.a.y() == pytest.approx(A0.y() - K.DIM_AUTO_OFFSET_PX)


def test_hit_dim_takes_the_dim_line_not_a_witness_line(view):
    v = view
    g = dg.layout_dim(v, QPointF(0, 0), QPointF(200, 0), -30.0, "200", tlen=7.5)
    on_line = QPointF(g.a.x() + 20, g.a.y() + 1)
    on_witness = QPointF(g.witness[0][0].x(), (g.witness[0][0].y() + g.a.y()) / 2)
    assert dg.hit_dim(g, on_line)
    assert dg.hit_dim(g, g.label.center)
    assert not dg.hit_dim(g, on_witness)


# -- D61 terminator -----------------------------------------------------------

from PyQt6.QtCore import QSettings  # noqa: E402
from PyQt6.QtGui import QColor, QImage, QPainter  # noqa: E402


def _write_end(name, pts, closed=True):
    """A real End Types end block file (the LT5 capability) in the isolated
    End Types folder; returns its path."""
    from firepro3d.app_data import end_types_dir
    d = end_types_dir()
    os.makedirs(d, exist_ok=True)
    rec = {"schema": 1, "id": f"end{abs(hash(name)) % 10**8:08d}", "version": 1,
           "name": name, "library": "System", "series": "End Types",
           "scale_mode": "real_size", "origin": [0.0, 0.0], "attributes": [],
           "primitives": [{"type": "polyline", "points": pts, "closed": closed,
                           "uid": f"u{abs(hash(name)) % 10**8:08d}",
                           "fill": {"type": "solid"}}],
           "end": {"trim": 0.0}}
    path = os.path.join(d, f"{name}.fpdb")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rec, fh)
    return path


@pytest.fixture
def arrow_end(qapp):
    path = _write_end("Arrow", [[0.0, 0.0], [-3.0, -0.5], [-3.0, 0.5]])
    yield path
    os.remove(path)


def _ink_extent(img, bg):
    xs, ys = [], []
    for x in range(img.width()):
        for y in range(img.height()):
            if img.pixelColor(x, y) != bg:
                xs.append(x)
                ys.append(y)
    return (min(xs), max(xs), min(ys), max(ys)) if xs else None


def _footprint(ed):
    img = QImage(60, 30, QImage.Format.Format_ARGB32)
    bg = QColor("white")
    img.fill(bg)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    dg.paint_terminator(p, QPointF(40.0, 15.0), (1.0, 0.0), QColor("black"), ed)
    p.end()
    return _ink_extent(img, bg)


def test_terminator_is_the_named_end_type_at_2_5_px_per_mm(arrow_end):
    ed = dg.terminator_def()
    assert ed is not None and ed.bounds == pytest.approx((-3.0, -0.5, 0.0, 0.5))
    assert dg.terminator_length_px(ed) == pytest.approx(7.5)
    x0, x1, y0, y1 = _footprint(ed)
    assert 31 <= x0 <= 34 and 39 <= x1 <= 41          # 7.5 px long, tip at x=40
    assert (y1 - y0 + 1) <= 5                          # ~2.5 px wide (+AA, 1 px outline)


def test_missing_end_type_falls_back_to_the_3_to_1_triangle(qapp):
    QSettings("GV", "FirePro3D").setValue(K.DIM_TERMINATOR_KEY, "No Such End")
    try:
        assert dg.terminator_def() is None
        assert dg.terminator_length_px(None) == pytest.approx(7.5)
        x0, x1, y0, y1 = _footprint(None)
        assert 31 <= x0 <= 34 and 39 <= x1 <= 41
        assert (y1 - y0 + 1) <= 5
    finally:
        QSettings("GV", "FirePro3D").remove(K.DIM_TERMINATOR_KEY)


def test_angular_readout_arc_draws_the_terminator(qapp):
    """A big square end named Arrow shows at the arc's ends (D61)."""
    from firepro3d import theme as th
    from firepro3d.readout_paint import ReadoutLayout, paint_readout
    path = _write_end("Arrow", [[0, -3], [-6, -3], [-6, 3], [0, 3]])
    try:
        img = QImage(300, 300, QImage.Format.Format_ARGB32)
        bg = QColor("white")
        img.fill(bg)
        p = QPainter(img)
        lay = ReadoutLayout("", QPointF(-100, -100), 0.0, 0.0, 0.0, True,
                            arc_center=QPointF(150, 150), arc_radius_px=100.0,
                            start_deg=0.0, span_deg=90.0)
        paint_readout(p, lay, th.detect(), color=QColor("black"))
        p.end()
        # 0 deg end: tip at (250, 150), outward = screen down -> a 15x15 px
        # square spans y in [135, 150] beside x 242..258. The old 7x5 arrow
        # never reached 7 px off the arc.
        dark = sum(1 for x in range(243, 258) for y in range(136, 149)
                   if img.pixelColor(x, y) != bg)
        assert dark > 100
    finally:
        os.remove(path)
