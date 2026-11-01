"""paint_halo_paths == per-path paint_halo_path loop (L1068 pens-once)."""
from PyQt6.QtGui import QImage, QPainter, QPainterPath

from firepro3d import theme as th
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


def test_batch_matches_per_path_loop(qapp):
    t = th.detect()
    ref = _render(lambda pt: [paint_halo_path(pt, p, t) for p in _paths()])
    got = _render(lambda pt: paint_halo_paths(pt, _paths(), t))
    assert any(got.pixelColor(x, 60).alpha() > 0 for x in range(200))   # drew something
    # Same-colour src-over commutes; only 8-bit rounding differs where up
    # to ~10 glow layers of crossing paths stack (measured max 3).
    assert _max_diff(ref, got) <= 3
