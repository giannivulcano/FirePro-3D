"""LT5 B2 / E12 -- trims never re-phase dashes (Q14, D-L9, LTS-4).

``expand(..., trims=(s0, s1))`` walks the untrimmed pieces and only drops
output outside ``[s0, L - s1]``. Ground truth: the untrimmed expansion
(today's renderer) rasterised next to the trimmed one -- identical pixels
outside a mask around the trimmed-off stretches, no ink inside them -- and,
for straight pieces, exact dash intervals.
"""
import numpy as np
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen

from firepro3d import linetype_render as lr
from firepro3d import path_walk as pw
from tests.lt3_support import make_linetype

_PX = 4.0                      # px per mm
_T0, _T1 = 20.0, 25.0          # trims (mm along the path)


def _spline():
    from firepro3d.geometry_2d import SplineItem
    sp = SplineItem([QPointF(0, 0), QPointF(50, -60), QPointF(100, 0),
                     QPointF(150, -40)])
    return sp.stroke_pieces()


CASES = {
    "seg": lambda: (pw.Seg(0, 0, 100, 0),),
    "seg_reversed": lambda: (pw.Seg(100, -10, 0, -10),),   # canonical flips it
    "arc_across_0deg": lambda: (pw.Arc(0, 0, 40, 300.0, 150.0),),
    "polyline_rev_leg": lambda: (pw.Seg(0, 0, 40, 0), pw.Seg(40, 0, 10, -30)),
    "spline": _spline,
    "ellipse_arc": lambda: (pw.EllipseArc(0, 0, 40, 25, 30.0, 200.0, 250.0),),
}


def _image(paths, width_px, cap=Qt.PenCapStyle.FlatCap):
    img = QImage(900, 500, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    p.translate(300.0, 300.0)
    p.scale(_PX, _PX)
    pen = QPen(QColor("#ffffff"))
    pen.setCosmetic(True)
    pen.setWidthF(width_px)
    pen.setCapStyle(cap)
    p.setPen(pen)
    for path in paths:
        p.drawPath(path)
    p.end()
    return img


def _stretch(pieces, a, b, step=0.25):
    """Polyline through the base path between path lengths a..b (sampled
    with the pre-LT5 ``point_at_total``)."""
    path = QPainterPath()
    n = max(int((b - a) / step), 1)
    for i in range(n + 1):
        q = pw.point_at_total(pieces, a + (b - a) * i / n)
        path.moveTo(q) if i == 0 else path.lineTo(q)
    return path


def _ink(img):
    """Boolean array: True where the pixel is not black."""
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    a = np.frombuffer(bytes(ptr), np.uint32).reshape(img.height(), img.width())
    return (a & 0xFFFFFF) != 0


@pytest.mark.parametrize("name", list(CASES))
def test_e12_dashes_outside_the_trims_are_pixel_identical(qapp, name):
    pieces = CASES[name]()
    L = pw.total_length(pieces)
    lt = lr.LinetypeDef.from_block(make_linetype())            # 6 on / 3 off
    anchor = (3.7, -1.9)
    full, _ = lr.expand(pieces, lt, 1.0, anchor)               # today's walk
    cut, _ = lr.expand(pieces, lt, 1.0, anchor, trims=(_T0, _T1))
    img_full, img_cut = _image([full], 1.0), _image([cut], 1.0)
    # Mask: the trimmed-off stretches, widened 4.5 px (round caps cover the
    # cut points' raster neighbourhood).
    off = [_stretch(pieces, 0.0, _T0), _stretch(pieces, L - _T1, L)]
    mask = _image(off, 9.0, Qt.PenCapStyle.RoundCap)
    # Deep inside the trimmed-off stretches (2 mm clear of the cut points).
    deep = _image([_stretch(pieces, 0.0, _T0 - 2.0),
                   _stretch(pieces, L - _T1 + 2.0, L)], 9.0)
    f, c, m, d = _ink(img_full), _ink(img_cut), _ink(mask), _ink(deep)
    diff = np.argwhere((f != c) & ~m)
    assert diff.size == 0, diff[:5].tolist()      # (y, x) of the first diffs
    kept = int((f & ~m).sum())
    ink_full_deep, ink_cut_deep = int((f & d).sum()), int((c & d).sum())
    assert kept > 50                      # the kept span really has dashes
    assert ink_full_deep > 20             # today's walk inks the cut stretch
    assert ink_cut_deep == 0              # ... the trimmed walk never does


def _intervals(path):
    out = []
    for i in range(path.elementCount()):
        e = path.elementAt(i)
        if e.isMoveTo():
            out.append([e.x])
        else:
            out[-1].append(e.x)
    return [(round(min(s), 9), round(max(s), 9)) for s in out]


def test_e12_straight_intervals_are_the_untrimmed_ones_clipped():
    lt = lr.LinetypeDef.from_block(make_linetype())
    pcs = (pw.Seg(0, 0, 100, 0),)
    full, _ = lr.expand(pcs, lt, 1.0, (2.5, 0.0))
    cut, _ = lr.expand(pcs, lt, 1.0, (2.5, 0.0), trims=(_T0, _T1))
    exp = [(max(a, _T0), min(b, 100.0 - _T1)) for a, b in _intervals(full)
           if min(b, 100.0 - _T1) - max(a, _T0) > 1e-9]
    assert _intervals(cut) == [(round(a, 9), round(b, 9)) for a, b in exp]


def test_zero_trims_share_the_untrimmed_cache_entry():
    """Zero trims are today's call: same cache key, same cached object (the
    zero-trim arithmetic itself is guarded by E1 and tests/test_lt3_expand)."""
    lt = lr.LinetypeDef.from_block(make_linetype(dots=(7.5,)))
    pcs = _spline() + (pw.Arc(0, 0, 40, 300.0, 150.0),)
    a = lr.expand(pcs, lt, 1.0, (0.0, 0.0))
    assert lr.expand(pcs, lt, 1.0, (0.0, 0.0), trims=(0.0, 0.0)) is a
    assert lr.expand(pcs, lt, 1.0, (0.0, 0.0), trims=(-3.0, 0.0)) is a


def test_over_trim_draws_nothing_and_dots_respect_trims():
    lt = lr.LinetypeDef.from_block(make_linetype(dots=(7.5,)))
    pcs = (pw.Seg(0, 0, 50, 0),)
    dash, dot = lr.expand(pcs, lt, 1.0, (0.0, 0.0), trims=(30.0, 25.0))
    assert dash.isEmpty() and dot.isEmpty()
    _, dot = lr.expand(pcs, lt, 1.0, (0.0, 0.0), trims=(10.0, 10.0))
    xs = [dot.elementAt(i).x for i in range(dot.elementCount())
          if dot.elementAt(i).isMoveTo()]
    assert xs == pytest.approx([16.5, 25.5, 34.5])     # 7.5 + 9k inside [10, 40]


def test_trims_are_in_the_cache_key():
    lt = lr.LinetypeDef.from_block(make_linetype())
    pcs = (pw.Seg(0, 0, 60, 0),)
    a = lr.expand(pcs, lt, 1.0, (0.0, 0.0))
    b = lr.expand(pcs, lt, 1.0, (0.0, 0.0), trims=(10.0, 0.0))
    assert a is not b and a[0] != b[0]
    assert lr.expand(pcs, lt, 1.0, (0.0, 0.0), trims=(10.0, 0.0)) is b


def test_window_and_trims_compose_on_a_long_segment():
    """LTS-8 window + LT5 trims: a 20 m Seg (> LINETYPE_WINDOW_MIN_PERIODS
    periods), windows at both far ends -- every windowed+trimmed dash lies
    inside an unwindowed+trimmed one, and none crosses the trims."""
    lt = lr.LinetypeDef.from_block(make_linetype())            # 9 mm period
    L = 20000.0
    pcs = (pw.Seg(0, 0, L, 0),)
    assert L / lt.period > lr.LINETYPE_WINDOW_MIN_PERIODS      # really windowed
    whole = _intervals(lr.expand(pcs, lt, 1.0, (0.0, 0.0), trims=(_T0, _T1))[0])
    for win in ((-10.0, -10.0, 100.0, 10.0), (L - 100.0, -10.0, L + 10.0, 10.0)):
        cut = _intervals(lr.expand(pcs, lt, 1.0, (0.0, 0.0), window=win,
                                   trims=(_T0, _T1))[0])
        assert cut, win
        for a, b in cut:
            assert any(wa - 1e-6 <= a and b <= wb + 1e-6 for wa, wb in whole), (a, b)
        assert cut[0][0] >= _T0 - 1e-9
        assert cut[-1][1] <= L - _T1 + 1e-9
