"""MW-7 / H-MW-f -- crisp axis-split (module level + G2 on QImage)."""
import math

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QTransform

from firepro3d import crisp_stroke as cs


def _img_rows(w, y, *, path=None, aa=True):
    img = QImage(60, 40, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, aa)
    pen = QPen(QColor(255, 255, 255), w)
    pen.setCosmetic(True)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    if path is None:
        path = QPainterPath(QPointF(5, y)); path.lineTo(QPointF(55, y))
    cs.stroke(p, path, pen, cs.split_axis(path, p.worldTransform()))
    p.end()
    return [img.pixelColor(30, r).red() for r in range(40) if img.pixelColor(30, r).red()]


@pytest.mark.parametrize("w", [1, 2, 3, 4, 5, 6])
@pytest.mark.parametrize("y", [20.0, 20.5, 20.3])
def test_g2_axis_line_is_n_full_rows_any_y(qapp, w, y):
    assert _img_rows(w, y) == [255] * w


def test_split_classifies_axis_diagonal_curve(qapp):
    p = QPainterPath(QPointF(0, 0))
    p.lineTo(10, 0); p.lineTo(10, 10)          # axis run
    p.lineTo(20, 20)                           # diagonal
    p.cubicTo(25, 25, 30, 20, 35, 20)          # curve
    s = cs.split_axis(p, QTransform())
    assert s.axis.elementCount() == 3 and not s.all_axis
    assert s.joint_points.count() == 1 and s.joint_points.at(0) == QPointF(10, 10)
    assert not s.other.isEmpty()


def test_rotation_reclassifies(qapp):
    p = QPainterPath(QPointF(0, 0)); p.lineTo(10, 10)
    assert not cs.split_axis(p, QTransform()).all_axis
    assert cs.split_axis(p, QTransform().rotate(45)).all_axis


def test_cache_ignores_zoom_but_not_rotation(qapp):
    c = cs.SplitCache()
    p = QPainterPath(QPointF(0, 0)); p.lineTo(10, 0)
    a = c.get(p, QTransform().scale(2, 2))
    assert c.get(p, QTransform().scale(7, 7)) is a
    assert c.get(p, QTransform().rotate(30)) is not a


def test_orthogonal_poses_share_one_split_key(qapp):
    # A signed permutation 2x2 classifies exactly as the identity does.
    k = cs.xf_key(QTransform())
    for xf in (QTransform().rotate(90), QTransform().rotate(180),
               QTransform().scale(-3, 3), QTransform(0, 2, 2, 0, 5, 7)):
        assert cs.xf_key(xf) == k
    assert cs.xf_key(QTransform().rotate(30)) != k
    assert cs.xf_key(QTransform().scale(2, 1)) != k      # non-uniform: own key


def _dash_render(path, w, *, split):
    """*path* stroked by a cosmetic DashLine pen on an AA painter: through
    ``cs.stroke`` (split=True) or a plain ``drawPath`` (split=False)."""
    img = QImage(80, 80, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0))
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(255, 255, 255), w, Qt.PenStyle.DashLine)
    pen.setCosmetic(True)
    if split:
        cs.stroke(painter, path, pen, cs.split_axis(path, painter.worldTransform()))
    else:
        painter.setPen(pen)
        painter.drawPath(path)
    painter.end()
    return img


@pytest.mark.parametrize("w", [1, 2])
def test_d4_dashed_pen_mixed_path_draws_exactly_unsplit(qapp, w):
    # Delta 4: Qt restarts the dash pattern per subpath, so a dashed pen on a
    # mixed (axis + diagonal) path must draw byte-identical to a plain stroke.
    p = QPainterPath(QPointF(5, 5.3)); p.lineTo(60, 5.3); p.lineTo(60, 60); p.lineTo(5, 35)
    assert _dash_render(p, w, split=True) == _dash_render(p, w, split=False)


def test_d4_dashed_pen_all_axis_path_does_split(qapp):
    # ... and an all-axis dashed path IS split: aliased, so a 2 px dash at
    # y = 20.5 is two full rows where the plain AA stroke smears into three.
    p = QPainterPath(QPointF(5, 20.5)); p.lineTo(75, 20.5)
    col = lambda img: [img.pixelColor(x, r).red() for r in range(40)
                       for x in (6,) if img.pixelColor(x, r).red()]
    assert col(_dash_render(p, 2, split=False)) == [127, 255, 127]
    assert col(_dash_render(p, 2, split=True)) == [255, 255]


def test_closed_mixed_subpath_records_closing_joint(qapp):
    # Closed triangle with one axis edge: the axis run meets the diagonal run
    # at BOTH ends -- the closing vertex is a joint too.
    p = QPainterPath(QPointF(0, 0)); p.lineTo(10, 0); p.lineTo(5, 8); p.closeSubpath()
    s = cs.split_axis(p, QTransform())
    pts = s.joint_points
    assert sorted((pts.at(k).x(), pts.at(k).y()) for k in range(pts.count())) == \
        [(0.0, 0.0), (10.0, 0.0)]


def _pair(path, w, *, cap=Qt.PenCapStyle.FlatCap, join=None, aa=True,
          cosmetic=True, size=80, offset=(10.5, 10.5)):
    """(split render, plain render) of *path*: ``cs.stroke`` with its split
    vs a plain ``drawPath`` with the same pen and AA hint."""
    out = []
    for split in (True, False):
        img = QImage(size, size, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0))
        pa = QPainter(img)
        pa.setRenderHint(QPainter.RenderHint.Antialiasing, aa)
        pa.translate(*offset)
        pen = QPen(QColor(255, 255, 255), w)
        pen.setCosmetic(cosmetic)
        pen.setCapStyle(cap)
        if join is not None:
            pen.setJoinStyle(join)
        if split:
            cs.stroke(pa, path, pen, cs.split_axis(path, pa.worldTransform()))
        else:
            pa.setPen(pen)
            pa.drawPath(path)
        pa.end()
        out.append(img)
    return out


def test_closing_joint_leaves_no_notch(qapp):
    # w = 4 FlatCap closed triangle: the closing vertex (40, 0) -- device
    # (50.5, 10.5) -- is a run boundary (axis edge -> closing diagonal). Two
    # flat caps there leave a wedge the plain stroke's join covers (e.g.
    # (51, 10): plain 147, caps only 6); the joint dot must fill it. Region:
    # right of the axis edge's end, so its AA-vs-aliased fringe is excluded.
    p = QPainterPath(QPointF(0, 0)); p.lineTo(40, 0); p.lineTo(20, 30); p.closeSubpath()
    a, b = _pair(p, 4)
    notch = [(x, y) for x in range(50, 57) for y in range(6, 15)
             if b.pixelColor(x, y).red() >= 128
             and a.pixelColor(x, y).red() < b.pixelColor(x, y).red() - 60]
    assert notch == []


def test_closed_subpath_starting_inside_a_run_keeps_its_join(qapp):
    # Chamfered square starting at its top-left corner (inside the axis run
    # that wraps through the start): the outer corner is a real miter join,
    # lit like the plain stroke -- not two flat caps leaving it dark.
    p = QPainterPath(QPointF(0, 0))
    p.lineTo(40, 0); p.lineTo(50, 10); p.lineTo(50, 50); p.lineTo(0, 50); p.closeSubpath()
    a, b = _pair(p, 4, join=Qt.PenJoinStyle.MiterJoin)
    # Outer corner region (the start vertex is device (10.5, 10.5)): every
    # pixel the plain stroke lights fully is lit fully by the split one (the
    # AA fringe pixels differ by design -- the axis run is aliased).
    gap = [(x, y) for x in range(6, 14) for y in range(6, 14)
           if b.pixelColor(x, y).red() >= 200 and a.pixelColor(x, y).red() < 200]
    assert b.pixelColor(9, 9).red() >= 200 and gap == []


def _mixed():
    p = QPainterPath(QPointF(5, 20.3)); p.lineTo(40, 20.3); p.lineTo(70, 55); p.lineTo(70, 75)
    return p


@pytest.mark.parametrize("aa", [True, False])
def test_stroke_restores_the_aa_hint(qapp, aa):
    img = QImage(80, 80, QImage.Format.Format_ARGB32); img.fill(QColor(0, 0, 0))
    pa = QPainter(img)
    pa.setRenderHint(QPainter.RenderHint.Antialiasing, aa)
    pen = QPen(QColor(255, 255, 255), 4); pen.setCosmetic(True)
    seen = []
    for path in (_mixed(), QPainterPath(QPointF(5, 5.5))):
        if path.elementCount() == 1:
            path.lineTo(70, 5.5)                 # all-axis branch too
        cs.stroke(pa, path, pen, cs.split_axis(path, pa.worldTransform()))
        seen.append(pa.testRenderHint(QPainter.RenderHint.Antialiasing))
    pa.end()                                     # before asserting (live painter)
    assert seen == [aa, aa]


def test_aliased_painter_keeps_other_runs_aliased(qapp):
    # The split never ADDS antialiasing: on an aliased painter the diagonal
    # run stays aliased -- the image holds only ink and background.
    a, _b = _pair(_mixed(), 3, aa=False, offset=(0, 0))
    vals = {a.pixelColor(x, y).red() for x in range(80) for y in range(80)}
    assert vals == {0, 255}


def test_non_cosmetic_pen_draws_unsplit(qapp):
    a, b = _pair(_mixed(), 3, cosmetic=False, offset=(0, 0))
    assert a == b


def test_paper_pass_draws_unsplit(qapp, monkeypatch):
    # Inside a paper pass (apply_paper_overrides .. restore) the cosmetic
    # canvas split is bypassed: byte-identical to a plain drawPath.
    from firepro3d import paper_display as pdm
    monkeypatch.setattr(pdm, "_THIN_SUSPEND", 1)        # the pass's own counter
    assert pdm.paper_pass_active()
    a, b = _pair(_mixed(), 3, offset=(0, 0))
    assert a == b


# ---------------------------------------------------------------- B2 views
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

from firepro3d import paper_display as pd
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.scale_manager import ScaleManager
from tests.mw_support import boundary_y, column_profile, grab, rows


@pytest.fixture
def be(qapp):
    sc = Model_Space(scene_role="block_editor")
    sc.scale_manager = ScaleManager()
    sc.constraint_ctl.show_status = False       # tint is Group C's concern
    v = Model_View(sc)
    v.resize(800, 600); v.show(); QTest.qWaitForWindowExposed(v)
    v.resetTransform(); v.centerOn(0, 0)
    sc.set_mode("select"); QApplication.processEvents()
    yield v, sc
    sc.clearSelection(); sc.cleanup(); v.close(); v.deleteLater()
    QApplication.processEvents()


# Sample off x = 0: the Block Editor paints its Y axis through the origin
# column (over the stroke), so a probe there reads the axis, not the line.
_X = 60.0
# Saturated ink: never confusable with a light or dark theme background.
INK = "#ff00ff"


def _hline(sc, y, weight, colour=INK):
    ln = LineItem(QPointF(-150, y), QPointF(150, y))
    ln.style["weight"] = weight
    ln.style["colour"] = colour
    sc.addItem(ln); sc._draw_lines.append(ln)
    return ln


@pytest.mark.parametrize("half", [0.0, 0.5])
@pytest.mark.parametrize("weight,n", [("Thinnest", 1), ("Thinner", 2), ("Thin", 3),
                                      ("Thick", 4), ("Thickest", 6)])
def test_g1_g2_factory_weights_paint_n_full_rows(be, half, weight, n):
    v, sc = be
    y = boundary_y(v, 40.0) + half
    _hline(sc, y, weight)
    img, dpr = grab(v)
    dev = v.viewportTransform().map(QPointF(_X, y))
    bg = img.pixelColor(int(dev.x() * dpr), int((dev.y() + 60) * dpr))
    full, partial = rows(column_profile(img, dpr, int(dev.x()), dev.y()),
                         QColor(INK), bg)
    assert (full, partial) == (n, 0)


def test_g1_override_and_thin_lines_change_painted_rows(be):
    v, sc = be
    pd.set_project_line_weights([pd.LineWeightDef("Thin", 0.35, 5)])
    y = boundary_y(v, 40.0)
    _hline(sc, y, "Thin")
    img, dpr = grab(v)
    dev = v.viewportTransform().map(QPointF(_X, y))
    bg = img.pixelColor(int(dev.x() * dpr), int((dev.y() + 60) * dpr))
    assert rows(column_profile(img, dpr, int(dev.x()), dev.y()), QColor(INK), bg) == (5, 0)
    pd.set_thin_lines(True)
    img, dpr = grab(v)
    assert rows(column_profile(img, dpr, int(dev.x()), dev.y()), QColor(INK), bg) == (1, 0)


def test_g2_diagonal_stays_antialiased(be):
    v, sc = be
    ln = LineItem(QPointF(-100, -100), QPointF(100, 0))
    ln.style["weight"] = "Thinnest"; ln.style["colour"] = INK
    sc.addItem(ln); sc._draw_lines.append(ln)
    img, dpr = grab(v)
    # Several columns along the diagonal (off the x = 0 axis): one column
    # can land the line on a single whole pixel, so count over all of them.
    partial = 0
    for sx in (30.0, 33.0, 36.0, 41.0, 47.0):
        dev = v.viewportTransform().map(QPointF(sx, -100.0 + (sx + 100.0) * 0.5))
        bg = img.pixelColor(int(dev.x() * dpr), int((dev.y() + 80) * dpr))
        partial += rows(column_profile(img, dpr, int(dev.x()), dev.y()),
                        QColor(INK), bg)[1]
    assert partial >= 1          # AA edge pixels exist


# ---------------------------------------------------------------- B3 dashes
@pytest.mark.parametrize("half", [0.0, 0.5])
def test_g2_linetyped_dash_is_n_full_rows(be, half):
    # An even (2 px) AA stroke is already crisp ON a boundary; half a pixel
    # off it smears -- so both positions are probed.
    from tests.lt3_support import make_linetype
    v, sc = be
    d = make_linetype(dashes=((0.0, 30.0),), length=45.0)
    sc.register_block_definition(d)
    y = boundary_y(v, 40.0) + half
    ln = _hline(sc, y, "Thinner")
    ln.style["linetype"] = d.id
    img, dpr = grab(v)
    # Inside a dash: the rhythm is origin-anchored, dashes span -135..-105.
    dev = v.viewportTransform().map(QPointF(-120.0, y))
    bg = img.pixelColor(int(dev.x() * dpr), int((dev.y() + 60) * dpr))
    assert rows(column_profile(img, dpr, int(dev.x()), dev.y()), QColor(INK), bg) == (2, 0)


# ---------------------------------------------------------------- B4 blocks
def test_g2_block_op_is_n_full_rows(be):
    from firepro3d.block_definition import BlockDefinition
    v, sc = be
    prim = LineItem(QPointF(-150, 0), QPointF(150, 0))
    prim.style["weight"] = "Thick"; prim.style["colour"] = INK
    d = BlockDefinition.new(name="B", library="L", series="S",
                            primitives=[prim.to_dict()], origin=(0.0, 0.0))
    sc.register_block_definition(d)
    y = boundary_y(v, 40.0) + 0.5
    sc.place_block_instance(d.id, (0.0, y))        # real placement path
    img, dpr = grab(v)
    dev = v.viewportTransform().map(QPointF(_X, y))
    bg = img.pixelColor(int(dev.x() * dpr), int((dev.y() + 60) * dpr))
    assert rows(column_profile(img, dpr, int(dev.x()), dev.y()), QColor(INK), bg) == (4, 0)


# ---------------------------------------------------------------- B5 text
def test_g2_text_frame_edge_is_n_full_rows(be):
    from firepro3d.text_item import TextAnnotationData, TextItem
    v, sc = be
    # Wide padding keeps the glyphs' AA rows out of the edge's column profile.
    t = TextItem(TextAnnotationData(text="HELLO", border=True, border_weight="Thinner",
                                    color=INK, cell_padding_mm=8.0))
    sc.addItem(t); sc._texts.append(t)
    t.setPos(20.0, 20.0)                    # clear of the x = 0 / y = 0 axes
    QApplication.processEvents()
    # Land the top edge half a pixel off a device boundary (a 2 px AA stroke
    # there smears into 3 partial rows).
    top = t.mapRectToScene(t._frame_path().boundingRect()).top()
    t.moveBy(0.0, boundary_y(v, top) + 0.5 - top)
    QApplication.processEvents()
    r = t.mapRectToScene(t._frame_path().boundingRect())
    img, dpr = grab(v)
    dev = v.viewportTransform().map(QPointF(r.center().x(), r.top()))
    bg = img.pixelColor(int(dev.x() * dpr), int((dev.y() - 30) * dpr))
    full, partial = rows(column_profile(img, dpr, int(dev.x()), dev.y(), span=3),
                         QColor(INK), bg)
    assert (full, partial) == (2, 0)


# ---------------------------------------------------------------- B6 underlays
def test_g6_pdf_widths_paint_whole_px(qapp):
    from firepro3d.model_space import _pdf_width_to_px
    pts = {0.18: 1.0, 0.25: 2.0, 0.35: 3.0}
    for mm, px in pts.items():
        assert _pdf_width_to_px(mm * 72.0 / 25.4) == px


def test_g6_underlay_axis_stroke_is_n_full_rows(qapp):
    from firepro3d.underlay import Underlay
    sc = Model_Space()
    v = Model_View(sc); v.resize(800, 600); v.show(); QTest.qWaitForWindowExposed(v)
    v.resetTransform(); v.centerOn(0, 0); QApplication.processEvents()
    try:
        rec = Underlay(type="dxf", path="x.dxf", line_weight_name="Thinner")
        group, _ = sc._build_batched_underlay_group(       # adds itself to the scene
            [{"kind": "line", "x1": -150, "y1": 40, "x2": 150, "y2": 40, "layer": "A"}], rec)
        sc.underlays.append((rec, group))
        # Land the line exactly half a pixel off a boundary, whatever the
        # builder's coordinate mapping (move the group, not the geometry).
        line_y = group.sceneBoundingRect().center().y()
        y = boundary_y(v, line_y) + 0.5
        group.moveBy(0.0, y - line_y)
        QApplication.processEvents()
        img, dpr = grab(v)
        dev = v.viewportTransform().map(QPointF(_X, y))
        bg = img.pixelColor(int(dev.x() * dpr), int((dev.y() + 60) * dpr))
        ink = img.pixelColor(int(dev.x() * dpr), int(math.floor(dev.y()) * dpr))
        full, partial = rows(column_profile(img, dpr, int(dev.x()), dev.y()), ink, bg)
        assert (full, partial) == (2, 0)
    finally:
        sc.cleanup(); v.close(); v.deleteLater(); QApplication.processEvents()


# ------------------------------------------------- review round: more views
from tests.mw_support import boundary_x, row_profile


@pytest.mark.parametrize("half", [0.0, 0.5])
def test_g2_vertical_line_is_n_full_columns(be, half):
    v, sc = be
    x = boundary_x(v, 60.0) + half
    ln = LineItem(QPointF(x, -150), QPointF(x, -20))      # clear of y = 0 axis
    ln.style["weight"] = "Thinner"; ln.style["colour"] = INK
    sc.addItem(ln); sc._draw_lines.append(ln)
    img, dpr = grab(v)
    dev = v.viewportTransform().map(QPointF(x, -80.0))
    bg = img.pixelColor(int((dev.x() + 60) * dpr), int(dev.y() * dpr))
    assert rows(row_profile(img, dpr, dev.x(), int(dev.y())), QColor(INK), bg) == (2, 0)


def test_g2_rotated_rect_edge_classified_in_rotated_frame(be):
    from firepro3d.geometry_2d import RectangleItem
    v, sc = be

    def make(dy):
        r = RectangleItem(QPointF(30, 30 + dy), QPointF(90, 60 + dy))
        r.style["weight"] = "Thick"; r.style["colour"] = INK
        r.set_angle(90)                      # data rotation (bake-at-rest)
        rc = r.rect()                        # mapToScene applies the rotation
        pts = [r.mapToScene(q) for q in (rc.topLeft(), rc.topRight(),
                                          rc.bottomRight(), rc.bottomLeft())]
        return r, pts

    # The local VERTICAL sides become the scene-horizontal edges; land the
    # top one half a pixel off a device boundary (a 4 px AA smear position).
    _r, pts = make(0.0)
    top = min(q.y() for q in pts)
    r, pts = make(boundary_y(v, top) + 0.5 - top)
    sc.addItem(r); sc._draw_rects.append(r)
    top = min(q.y() for q in pts)
    xs = [q.x() for q in pts if abs(q.y() - top) < 1e-6]
    assert len(xs) == 2 and abs(xs[0] - xs[1]) > 20      # a real horizontal edge
    img, dpr = grab(v)
    dev = v.viewportTransform().map(QPointF(sum(xs) / 2.0, top))
    bg = img.pixelColor(int(dev.x() * dpr), int((dev.y() - 30) * dpr))
    assert rows(column_profile(img, dpr, int(dev.x()), dev.y(), span=4),
                QColor(INK), bg) == (4, 0)


def test_g2_rotated_rect_30_edges_stay_antialiased(be):
    # Local edges are axis-aligned in the item frame; at 30 deg they are
    # diagonals in the painter's world frame and must stay AA (classification
    # reads the rotated world transform, not the local rect).
    from firepro3d.geometry_2d import RectangleItem
    v, sc = be
    r = RectangleItem(QPointF(30, 30), QPointF(130, 90))
    r.style["weight"] = "Thinnest"; r.style["colour"] = INK
    r.set_angle(30)
    sc.addItem(r); sc._draw_rects.append(r)
    rc = r.rect()
    a, b = r.mapToScene(rc.topLeft()), r.mapToScene(rc.topRight())
    img, dpr = grab(v)
    partial = 0
    for k in range(2, 19):
        q = a + (b - a) * (k / 20.0)
        dev = v.viewportTransform().map(q)
        bg = img.pixelColor(int(dev.x() * dpr), int((dev.y() + 80) * dpr))
        partial += rows(column_profile(img, dpr, int(dev.x()), dev.y(), span=3),
                        QColor(INK), bg)[1]
    assert partial >= 5


def test_unstyled_reference_line_stays_unsplit(be):
    # MW-7 scope: only weight-mapped strokes go crisp. A reference line
    # (unstyled, fixed 1 px dashed) half-covering two rows keeps its AA.
    from firepro3d.geometry_2d import ReferenceLineItem
    v, sc = be
    y = boundary_y(v, 40.0) + 0.3
    ln = ReferenceLineItem(QPointF(20, y), QPointF(150, y), color=INK)
    sc.addItem(ln)
    img, dpr = grab(v)
    partial = 0
    for sx in range(25, 145, 3):          # dashes + gaps: sum over columns
        dev = v.viewportTransform().map(QPointF(float(sx), y))
        bg = img.pixelColor(int(dev.x() * dpr), int((dev.y() + 60) * dpr))
        partial += rows(column_profile(img, dpr, int(dev.x()), dev.y(), span=3),
                        QColor(INK), bg)[1]
    assert partial >= 10


# --------------------------------------------- quality round: paper gate
def test_paper_pass_never_populates_an_underlay_split(qapp):
    # A sheet / PDF render before any model paint must not pay a first split
    # it never uses: the gate runs BEFORE cache.get (stroke_cached).
    from PyQt6.QtCore import QRectF
    from firepro3d.underlay import Underlay
    from firepro3d.underlay_freeze import _UnderlayPathItem
    sc = Model_Space()
    try:
        rec = Underlay(type="dxf", path="x.dxf")        # unweighted: stays cosmetic
        group, _ = sc._build_batched_underlay_group(
            [{"kind": "line", "x1": -150, "y1": 40, "x2": 150, "y2": 40, "layer": "A"},
             {"kind": "line", "x1": 150, "y1": 40, "x2": 200, "y2": 90, "layer": "A"}],
            rec)
        sc.underlays.append((rec, group))
        items = [it for it in group.childItems() if isinstance(it, _UnderlayPathItem)]
        assert items
        crop = QRectF(-500, -500, 1000, 1000)
        saved = pd.apply_paper_overrides(sc, crop, paper_scale=1.0)
        try:
            assert pd.paper_pass_active()
            assert any(it.pen().isCosmetic() for it in items)   # would split on canvas
            img = QImage(400, 400, QImage.Format.Format_ARGB32)
            img.fill(QColor(255, 255, 255))           # paper (B&W plots black)
            p = QPainter(img)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            sc.render(p, QRectF(0, 0, 400, 400), crop)
            p.end()
        finally:
            pd.restore_model_display(saved)
        assert any(img.pixelColor(x, y) != QColor(255, 255, 255)
                   for x in range(400) for y in range(400))     # the pass painted it
        assert all(it._mw_split_cache._split is None for it in items)
    finally:
        sc.cleanup()


def test_dash_split_lru_keeps_one_split_per_pose(qapp):
    # A shared block expansion drawn by instances at two rotations keeps both
    # splits (no per-paint recompute when the poses alternate).
    from firepro3d import linetype_render as lr
    dash = QPainterPath(QPointF(0, 0)); dash.lineTo(10, 0)
    a = lr._dash_split(dash, QTransform())
    b = lr._dash_split(dash, QTransform().rotate(30))
    assert lr._dash_split(dash, QTransform()) is a
    assert lr._dash_split(dash, QTransform().rotate(30)) is b
