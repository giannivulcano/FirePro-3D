"""paint_halo_paths == per-path paint_halo_path loop (L1068 pens-once)."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen

from firepro3d import theme as th
from firepro3d.constants import (HALO_GLOW_PX, HALO_TRACE_ALPHA,
                                 HALO_TRACE_COLOR, HALO_TRACE_WIDTH_PX)
from firepro3d.halo import paint_halo_path, paint_halo_paths


def _paths():
    out = []
    for i in range(12):
        p = QPainterPath()
        p.moveTo(10 + i * 9, 10)
        p.lineTo(60 + i * 5, 110)
        out.append(p)
    return out


def _render(fn):
    img = QImage(200, 140, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    pt = QPainter(img)
    pt.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    fn(pt)
    pt.end()
    return img


def _max_diff(a, b):
    """Largest per-channel gap on the raw premultiplied ARGB words.

    pixelColor() un-premultiplies, which blows a 1-unit rounding gap at low
    alpha up to tens of units, so compare the stored bytes instead.
    """
    m = 0
    for y in range(a.height()):
        for x in range(a.width()):
            pa, pb = a.pixel(x, y), b.pixel(x, y)
            for s in (0, 8, 16, 24):
                m = max(m, abs(((pa >> s) & 255) - ((pb >> s) & 255)))
    return m


def _frozen_per_path(pt, paths, theme):
    """The pre-L1068 paint_halo_path loop, frozen here as the look's reference.

    Independent of firepro3d.halo (which now delegates to the batch), so a
    dropped glow layer or a changed width/alpha turns the guard RED.
    """
    base = theme.color(HALO_TRACE_COLOR)
    for path in paths:
        pt.save()
        pt.setBrush(Qt.BrushStyle.NoBrush)
        strokes = []
        for i in range(4, 0, -1):
            frac = i / 4
            strokes.append((HALO_TRACE_WIDTH_PX + HALO_GLOW_PX * 2.0 * frac,
                            HALO_TRACE_ALPHA * (0.05 + 0.20 * (1.0 - frac))))
        strokes.append((HALO_TRACE_WIDTH_PX, HALO_TRACE_ALPHA))
        for w, a in strokes:
            c = QColor(base)
            c.setAlpha(max(0, min(255, int(round(a)))))
            pen = QPen(c, w)
            pen.setCosmetic(True)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pt.setPen(pen)
            pt.drawPath(path)
        pt.restore()


def test_batch_matches_frozen_per_path_loop(qapp):
    t = th.detect()
    ref = _render(lambda pt: _frozen_per_path(pt, _paths(), t))
    got = _render(lambda pt: paint_halo_paths(pt, _paths(), t))
    assert any(got.pixelColor(x, 60).alpha() > 0 for x in range(200))   # drew something
    assert _max_diff(ref, got) <= 3


def test_batch_matches_per_path_loop(qapp):
    t = th.detect()
    ref = _render(lambda pt: [paint_halo_path(pt, p, t) for p in _paths()])
    got = _render(lambda pt: paint_halo_paths(pt, _paths(), t))
    assert any(got.pixelColor(x, 60).alpha() > 0 for x in range(200))   # drew something
    # Same-colour src-over commutes; only 8-bit rounding differs where up
    # to ~10 glow layers of crossing paths stack (measured max 3).
    assert _max_diff(ref, got) <= 3
