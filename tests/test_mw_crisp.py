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
    assert len(s.joints) == 1 and s.joints[0] == QPointF(10, 10)
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


def test_dashed_pen_mixed_path_draws_unsplit(qapp):
    img = QImage(60, 60, QImage.Format.Format_ARGB32); img.fill(QColor(0, 0, 0))
    painter = QPainter(img)
    pen = QPen(QColor(255, 255, 255), 1, Qt.PenStyle.DashLine); pen.setCosmetic(True)
    p = QPainterPath(QPointF(5, 5)); p.lineTo(50, 5); p.lineTo(50, 50); p.lineTo(5, 30)
    s = cs.split_axis(p, QTransform())
    cs.stroke(painter, p, pen, s)              # must not raise; draws whole path
    painter.end()
    assert any(img.pixelColor(x, 5).red() for x in range(5, 50))


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


def _hline(sc, y, weight, colour="#ffffff"):
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
                         QColor("#ffffff"), bg)
    assert (full, partial) == (n, 0)


def test_g1_override_and_thin_lines_change_painted_rows(be):
    v, sc = be
    pd.set_project_line_weights([pd.LineWeightDef("Thin", 0.35, 5)])
    y = boundary_y(v, 40.0)
    _hline(sc, y, "Thin")
    img, dpr = grab(v)
    dev = v.viewportTransform().map(QPointF(_X, y))
    bg = img.pixelColor(int(dev.x() * dpr), int((dev.y() + 60) * dpr))
    assert rows(column_profile(img, dpr, int(dev.x()), dev.y()), QColor("#ffffff"), bg) == (5, 0)
    pd.set_thin_lines(True)
    img, dpr = grab(v)
    assert rows(column_profile(img, dpr, int(dev.x()), dev.y()), QColor("#ffffff"), bg) == (1, 0)


def test_g2_diagonal_stays_antialiased(be):
    v, sc = be
    ln = LineItem(QPointF(-100, -100), QPointF(100, 0))
    ln.style["weight"] = "Thinnest"; ln.style["colour"] = "#ffffff"
    sc.addItem(ln); sc._draw_lines.append(ln)
    img, dpr = grab(v)
    # Several columns along the diagonal (off the x = 0 axis): one column
    # can land the line on a single whole pixel, so count over all of them.
    partial = 0
    for sx in (30.0, 33.0, 36.0, 41.0, 47.0):
        dev = v.viewportTransform().map(QPointF(sx, -100.0 + (sx + 100.0) * 0.5))
        bg = img.pixelColor(int(dev.x() * dpr), int((dev.y() + 80) * dpr))
        partial += rows(column_profile(img, dpr, int(dev.x()), dev.y()),
                        QColor("#ffffff"), bg)[1]
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
    assert rows(column_profile(img, dpr, int(dev.x()), dev.y()), QColor("#ffffff"), bg) == (2, 0)


# ---------------------------------------------------------------- B4 blocks
def test_g2_block_op_is_n_full_rows(be):
    from firepro3d.block_definition import BlockDefinition
    v, sc = be
    prim = LineItem(QPointF(-150, 0), QPointF(150, 0))
    prim.style["weight"] = "Thick"; prim.style["colour"] = "#ffffff"
    d = BlockDefinition.new(name="B", library="L", series="S",
                            primitives=[prim.to_dict()], origin=(0.0, 0.0))
    sc.register_block_definition(d)
    y = boundary_y(v, 40.0) + 0.5
    sc.place_block_instance(d.id, (0.0, y))        # real placement path
    img, dpr = grab(v)
    dev = v.viewportTransform().map(QPointF(_X, y))
    bg = img.pixelColor(int(dev.x() * dpr), int((dev.y() + 60) * dpr))
    assert rows(column_profile(img, dpr, int(dev.x()), dev.y()), QColor("#ffffff"), bg) == (4, 0)


# ---------------------------------------------------------------- B5 text
def test_g2_text_frame_edge_is_n_full_rows(be):
    from firepro3d.text_item import TextAnnotationData, TextItem
    v, sc = be
    # Wide padding keeps the glyphs' AA rows out of the edge's column profile.
    t = TextItem(TextAnnotationData(text="HELLO", border=True, border_weight="Thinner",
                                    color="#ffffff", cell_padding_mm=8.0))
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
                         QColor("#ffffff"), bg)
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
