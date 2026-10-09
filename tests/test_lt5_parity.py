"""LT5 E1 -- legacy drawings render identically (Q3 / design E1).

Parity guard (VC3 maint): golden recorded at base cbe41a15 (LT5_RECORD=1
prints the repr) and must pass at base and at every LT5 commit. Scope: the
geometry strokes only -- PDF drawings strictly inside the viewport box (the
viewport border, title block and sheet chrome fall out) and canvas pixels
outside a box around the scene origin marker (WM2 polish note (c)).
"""
import hashlib
import os

import fitz
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import ArcItem, LineItem, PolylineItem, SplineItem
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
from tests.lt3_support import hidden
from tests.test_lt1_block_paper import _VP_W, _VP_X, _VP_Y, _export

PT = 25.4 / 72.0
_ORIGIN_BOX = 12            # px half-size masked around the crop centre

# Recorded at base cbe41a15 with LT5_RECORD=1.
_GOLDEN = ((1280, '3a220c6422e028f4'), (1219, '6a80ca84e977427a'),
           (6, '2a1780a8c661fd5f'))


def _items(u, lid):
    """Open Line / dashed Line / Polyline / Arc / Spline, *u* mm per unit."""
    def P(x, y):
        return QPointF(x * u, y * u)
    solid = LineItem(P(-1500, -1200), P(1500, -1200))
    dashed = LineItem(P(-1500, -800), P(1500, -800))
    dashed.style["linetype"] = lid
    poly = PolylineItem(P(-1500, -300))
    for x, y in ((-500, -300), (-500, 300), (500, 300)):
        poly.append_point(P(x, y))
    arc = ArcItem(P(900, -100), 500 * u, 30.0, 200.0)
    spline = SplineItem([P(-1500, 700), P(-700, 1200), P(0, 700),
                         P(700, 1200), P(1500, 800)])
    return [solid, dashed, poly, arc, spline]


def _plan():
    """Plan: one placed block holding the five strokes + a nested block."""
    ms = Model_Space()
    lid = hidden(ms)
    inner = BlockDefinition.new(
        name="Inner", library="L", series="S", origin=(0.0, 0.0),
        primitives=[LineItem(QPointF(-300, 0), QPointF(300, 0)).to_dict()])
    nested = {"type": "block_instance", "block_id": inner.id,
              "pos": [-900.0, 1600.0], "rotation": 30.0}
    host = BlockDefinition.new(
        name="Host", library="L", series="S", origin=(0.0, 0.0),
        primitives=[it.to_dict() for it in _items(1.0, lid)] + [nested])
    for d in (inner, host):
        ms.register_block_definition(BlockDefinition.from_dict(d.to_dict()))
    ms.place_block_instance(host.id, (0.0, 0.0), level=ms.active_level)
    return ms


def _editor():
    """Block Editor: the same strokes as raw primitives at 1/10 size."""
    ms = Model_Space(scene_role="block_editor")
    lid = hidden(ms)
    for it in _items(0.1, lid):
        ms.addItem(it)
    return ms


def _render(ms, crop):
    img = QImage(400, 400, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, 400, 400), crop)
    p.end()
    return img


def _canvas_sig(img):
    """(lit count, sha) of every pixel outside the origin-marker box."""
    c = 200
    px = [img.pixel(x, y) & 0xFFFFFF for y in range(400) for x in range(400)
          if not (abs(x - c) <= _ORIGIN_BOX and abs(y - c) <= _ORIGIN_BOX)]
    h = hashlib.sha256(repr(px).encode()).hexdigest()[:16]
    return sum(1 for v in px if v), h


def _pt(v):
    if hasattr(v, "x0"):                                  # fitz.Rect
        return (round(v.x0, 2), round(v.y0, 2), round(v.x1, 2), round(v.y1, 2))
    if hasattr(v, "x"):                                   # fitz.Point
        return (round(v.x, 2), round(v.y, 2))
    return repr(v)


def _pdf_sig(pdf):
    """(n strokes, sha) of the stroked drawings strictly inside the viewport."""
    lo_x, hi_x = (_VP_X + 0.5) / PT, (_VP_X + _VP_W - 0.5) / PT
    lo_y, hi_y = (_VP_Y + 0.5) / PT, (_VP_Y + _VP_W - 0.5) / PT
    doc = fitz.open(str(pdf))
    try:
        sig = []
        for d in doc[0].get_drawings():
            if "s" not in (d.get("type") or ""):
                continue
            r = d["rect"]
            if not (lo_x < r.x0 and r.x1 < hi_x and lo_y < r.y0 and r.y1 < hi_y):
                continue
            sig.append((round(d["width"], 4),
                        tuple((it[0],) + tuple(_pt(v) for v in it[1:])
                              for it in d["items"])))
    finally:
        doc.close()
    sig.sort()
    return len(sig), hashlib.sha256(repr(sig).encode()).hexdigest()[:16]


def test_e1_legacy_strokes_match_base_golden(qapp, tmp_path):
    save_paper_color_mode(PaperColorMode.BW)
    plan = _canvas_sig(_render(_plan(), QRectF(-2000, -2000, 4000, 4000)))
    editor = _canvas_sig(_render(_editor(), QRectF(-200, -200, 400, 400)))
    pdf = _pdf_sig(_export(tmp_path, _plan(), 0.02, "e1.pdf"))
    sig = (plan, editor, pdf)
    assert plan[0] > 0 and editor[0] > 0 and pdf[0] > 5   # really drew
    if os.environ.get("LT5_RECORD"):
        print("GOLDEN", repr(sig))
        return
    assert sig == _GOLDEN
