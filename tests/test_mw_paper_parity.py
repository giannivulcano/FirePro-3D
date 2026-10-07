"""MW-1 / MW-4 paper parity -- cosmetic canvas pens that survive into a paper
pass plot at the frozen pre-MW mapping, never the Model weight factor."""
import fitz
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d import paper_display as pd
from firepro3d.model_space import Model_Space
from tests.test_lt1_block_paper import _export

# Pre-MW (base 8c3e3577) paper widths of an unweighted raw-PDF underlay child:
# pt -> mm x 6 px/mm (> 1.25 px, so no snap), floored at 1 px.
_BASE_1PT = 1.0 * 25.4 / 72.0 * 6.0       # 2.1167 px
_BASE_2PT = 2.0 * 25.4 / 72.0 * 6.0       # 4.2333 px


def _pdf_underlay_scene(y0=0.0):
    from firepro3d.underlay import Underlay
    sc = Model_Space()
    rec = Underlay(type="pdf", path="x.pdf")                # unweighted layers
    g, _ = sc._build_batched_underlay_group([
        {"kind": "line", "x1": -400, "y1": y0, "x2": 400, "y2": y0, "layer": "A", "width": 1.0},
        {"kind": "line", "x1": -400, "y1": y0 + 300, "x2": 400, "y2": y0 + 300,
         "layer": "A", "width": 2.0}], rec)
    sc.underlays.append((rec, g))
    return sc, g


def _paper_widths(factor):
    from firepro3d.underlay_freeze import _UnderlayPathItem
    pd.set_model_weight_factor(factor)
    sc, g = _pdf_underlay_scene()
    try:
        items = [it for it in g.childItems() if isinstance(it, _UnderlayPathItem)]
        saved = pd.apply_paper_overrides(sc, QRectF(-500, -500, 1000, 1000), paper_scale=50.0)
        try:
            return sorted((round(it.pen().widthF(), 4), it.pen().isCosmetic()) for it in items)
        finally:
            pd.restore_model_display(saved)
    finally:
        sc.cleanup()


def test_unweighted_pdf_underlay_paper_widths_ignore_the_factor(qapp):
    a, b = _paper_widths(8.0), _paper_widths(16.0)
    assert a == b
    assert a == [(round(_BASE_1PT, 4), True), (round(_BASE_2PT, 4), True)]


def _export_widths(tmp_path, factor, name):
    pd.set_model_weight_factor(factor)
    sc, _g = _pdf_underlay_scene()
    try:
        pdf = _export(tmp_path, sc, 0.02, name)
    finally:
        sc.cleanup()
    doc = fitz.open(str(pdf))
    try:
        return sorted((round(d["width"] or 0.0, 4), tuple(round(v, 2) for v in d["rect"]))
                      for d in doc[0].get_drawings() if "s" in (d.get("type") or ""))
    finally:
        doc.close()


def test_pdf_export_with_unweighted_underlay_is_factor_independent(qapp, tmp_path):
    a = _export_widths(tmp_path, 8.0, "f8.pdf")
    b = _export_widths(tmp_path, 16.0, "f16.pdf")
    assert a and a == b


def _primitive_paper_image(factor):
    from firepro3d import geometry_2d as g
    pd.set_model_weight_factor(factor)
    sc = Model_Space()
    try:
        for it in (g.EllipseItem(QPointF(0, 0), 60, 30, 0),
                   g.RegularPolygonItem(QPointF(200, 0), 6, 50),
                   g.SplineItem([QPointF(0, 150), QPointF(60, 210), QPointF(120, 140)])):
            it.style["weight"] = "Thick"
            it.style["colour"] = "#ff00ff"
            sc.addItem(it)
        crop = QRectF(-100, -100, 400, 400)
        img = QImage(400, 400, QImage.Format.Format_ARGB32)
        img.fill(QColor(255, 255, 255))
        p = QPainter(img)
        sc.render(p, QRectF(0, 0, 400, 400), crop)       # a model paint first
        p.end()
        saved = pd.apply_paper_overrides(sc, crop, paper_scale=1.0)
        try:
            img.fill(QColor(255, 255, 255))
            p = QPainter(img)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            sc.render(p, QRectF(0, 0, 400, 400), crop)
            p.end()
        finally:
            pd.restore_model_display(saved)
        return img
    finally:
        sc.cleanup()


def test_uncategorised_primitives_plot_factor_independent(qapp):
    # Ellipse / Polygon / Spline have no paper category: their canvas pen
    # survives into the pass. Their paper render must not follow the factor.
    a, b = _primitive_paper_image(8.0), _primitive_paper_image(16.0)
    assert any(a.pixelColor(x, y) != QColor(255, 255, 255)
               for x in range(0, 400, 2) for y in range(0, 400, 2))
    assert a == b
