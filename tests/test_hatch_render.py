# tests/test_hatch_render.py
"""paint_fill: lattice in scene axes, LOD, drafting factor, IntersectClip (HD4a)."""
import math
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath
from firepro3d import hatch_patterns as hp
from firepro3d import hatch_render as hr


class _PaperCtx:
    """Stand-in for a scene inside a paper-viewport render window."""
    def __init__(self, s):
        self._hatch_paper_scale = s


def _img(w=400, h=400):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    return img


def _rect(x, y, w, h):
    p = QPainterPath()
    p.addRect(QRectF(x, y, w, h))
    return p


def _red(img, x, y):
    c = QColor(img.pixel(x, y))
    return c.red() > 200 and c.green() < 90 and c.blue() < 90


def _row_runs(img, x):
    """y of the first pixel of each red run down column x."""
    ys, prev = [], False
    for y in range(img.height()):
        r = _red(img, x, y)
        if r and not prev:
            ys.append(y)
        prev = r
    return ys


def test_horizontal_spacing_tracks_scale(qapp):
    def spacing(scale):
        img = _img()
        p = QPainter(img)
        # scene=None → model canvas: Drafting 3 mm × 1:100 = 300 units × scale
        hr.paint_fill(p, _rect(10, 10, 380, 380), scene=None,
                      tile_ref="horizontal", colour=QColor("#ff0000"),
                      origin=QPointF(0, 0), scale=scale)
        p.end()
        ys = _row_runs(img, 200)
        return sorted({b - a for a, b in zip(ys, ys[1:])})[0]
    s1, s2 = spacing(0.1), spacing(0.2)          # 1 px per unit, cosmetic 1 px pen
    assert s1 == 30 and s2 == 60


def test_clip_is_intersected_not_replaced(qapp):
    img = _img()
    p = QPainter(img)
    p.setClipRect(QRectF(0, 0, 100, 400))                  # outer crop (paper viewport)
    hr.paint_fill(p, _rect(0, 0, 400, 400), scene=_PaperCtx(1.0),
                  background=QColor("#ff0000"))
    p.end()
    assert _red(img, 50, 50) and not _red(img, 300, 50)    # H5


def test_lod_tone_when_cells_are_sub_pixel(qapp):
    img = _img()
    p = QPainter(img)
    p.scale(0.05, 0.05)                                    # 3 mm cell → 0.15 px
    hr.paint_fill(p, _rect(0, 0, 8000, 8000), scene=_PaperCtx(1.0),
                  tile_ref="diagonal", colour=QColor("#ff0000"))
    p.end()
    c = QColor(img.pixel(200, 200))
    # 35 % red over white → (255, ~166, ~166); uniform = no lines stamped.
    assert c.red() == 255 and 150 < c.green() < 180
    assert QColor(img.pixel(207, 203)) == c


def test_unknown_tile_draws_tone_not_blank(qapp):
    img = _img()
    p = QPainter(img)
    hr.paint_fill(p, _rect(0, 0, 400, 400), scene=None,
                  tile_ref="no-such-tile", colour=QColor("#ff0000"))
    p.end()
    assert QColor(img.pixel(200, 200)) != QColor("white")


def test_drafting_factor_contexts(qapp):
    from firepro3d.constants import DRAFTING_CANVAS_SCALE
    assert hr.drafting_factor(None) == DRAFTING_CANVAS_SCALE
    assert hr.drafting_factor(_PaperCtx(0.01)) == 100.0
    assert hr.drafting_factor(_PaperCtx(0.02)) == 50.0


def test_pattern_never_rotates_with_the_painter_frame(qapp):
    """to_scene rotated 30°: lines stay at 45° on screen (G3 at renderer level)."""
    from PyQt6.QtGui import QTransform
    img = _img()
    p = QPainter(img)
    rot = QTransform().rotate(30)
    p.setTransform(rot)                                    # item frame = rotated
    inv, _ = rot.inverted()
    clip = inv.map(_rect(20, 20, 360, 360))                # same screen square
    hr.paint_fill(p, clip, scene=None, tile_ref="diagonal",
                  colour=QColor("#ff0000"), scale=0.1, to_scene=rot)   # ~42 px cells
    p.end()
    lit = [(x, y) for x in range(30, 370, 2) for y in range(30, 370, 2) if _red(img, x, y)]
    along = sum(_red(img, x + 3, y - 3) for x, y in lit) / len(lit)
    assert along > 0.8
