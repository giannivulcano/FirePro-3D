"""G-LTS7 -- LTS-8 bench: zoom/pan frames with Fixed linetypes.

REPORT-ONLY (user ruling 2026-10-06): this host varies 2-4x run to run, below
the noise floor of the ratified relative bars (A/B zoom Fixed <= 1.5x Scale,
pan <= 1.1x; C <= 2x the same lines cut to the view), so the bench prints
the ratios and asserts only its own composition (dashes really drawn, 100 m
lines really windowed). As measured at the LTS build: B and C within their
bars; A zoom (2,000 short segments) ~1.6-2.7x -- filed as a follow-up under
LT8 (D-L21). Frames are interleaved Fixed / Scale, best of 15.

Run standalone: ./venv/Scripts/python.exe -m pytest tests/test_lts_perf.py -m perf -s
"""
import time

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d import linetype_render
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem, PolylineItem
from firepro3d.model_space import Model_Space
from tests.lt3_support import make_linetype

pytestmark = pytest.mark.perf
_W, _H = 1600, 900


def _frame(ms, crop):
    img = QImage(_W, _H, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    t0 = time.perf_counter()
    ms.render(p, QRectF(0, 0, _W, _H), crop)
    dt = (time.perf_counter() - t0) * 1000
    p.end()
    return dt, img


def _zoomed(crop, f):
    return QRectF(crop.center().x() - crop.width() * f / 2,
                  crop.center().y() - crop.height() * f / 2,
                  crop.width() * f, crop.height() * f)


def _paired(a, b, crops):
    """(best ms of *a*, best ms of *b*) rendering *crops* alternately, so host
    load drift hits both scenes alike (this machine varies ~30 % run to run)."""
    ta, tb = [], []
    for c in crops:
        ta.append(_frame(a, c)[0])
        tb.append(_frame(b, c)[0])
    return min(ta), min(tb)


def _has_gaps(img, y):
    lit = [img.pixelColor(x, y).lightness() > 40 for x in range(_W)]
    return 0 < sum(lit) < _W - 20


def _shape_a(screen):
    """Block Editor: 20 polylines x 100 segments = 2,000 linetyped segments."""
    ms = Model_Space(scene_role="block_editor")
    lt = make_linetype(screen=screen)
    ms.register_block_definition(lt)
    for r in range(20):
        pl = PolylineItem(QPointF(0.0, r * 20.0))
        for i in range(1, 101):
            pl.append_point(QPointF(i * 10.0, r * 20.0 + (i % 2) * 2.0))
        pl.style["linetype"] = lt.id
        ms.addItem(pl)
    return ms, QRectF(-10, -10, 1020, 420)


def _shape_b(screen):
    """Plan: 200 placed instances of a block of 10 parallel 2000 mm lines."""
    ms = Model_Space()
    lt = make_linetype(screen=screen)
    ms.register_block_definition(lt)
    prims = []
    for k in range(10):
        ln = LineItem(QPointF(0, k * 50), QPointF(2000, k * 50))
        ln.style["linetype"] = lt.id
        prims.append(ln.to_dict())
    d = BlockDefinition.new(name="B", library="L", series="S",
                            primitives=prims, origin=(0.0, 0.0))
    ms.register_block_definition(d)
    for i in range(200):
        ms.place_block_instance(d.id, ((i % 20) * 2500.0, (i // 20) * 600.0),
                                level=ms.active_level)
    return ms, QRectF(0, 0, 50000, 6000)


def _shape_c(x0=-50000.0, x1=50000.0):
    """Block Editor: 50 Fixed lines (default 100 m), zoomed in to ~20 px/mm.

    The reference cuts them to x0..x1 just covering every zoom step's view
    (the widest step is 80 mm x 1.1^9 ~ 190 mm, centred on x = 40).
    """
    ms = Model_Space(scene_role="block_editor")
    lt = make_linetype(screen="fixed")
    ms.register_block_definition(lt)
    for r in range(50):
        ln = LineItem(QPointF(x0, r * 1.0), QPointF(x1, r * 1.0))
        ln.style["linetype"] = lt.id
        ms.addItem(ln)
    return ms, QRectF(0, 0, 80, 45)                        # 20 px/mm


@pytest.mark.parametrize("shape", [_shape_a, _shape_b])
def test_lts8_zoom_and_pan_ab(qapp, shape):
    fixed, crop = shape("fixed")
    scale, _ = shape("scale")
    _, img = _frame(fixed, crop)
    ys = [y for y in range(0, _H, 3) if _has_gaps(img, y)]
    assert ys, "bench draws no dashes -- not measuring linetypes"
    # Every zoom crop is new to both scenes (a Fixed factor never repeats).
    z_f, z_s = _paired(fixed, scale, [_zoomed(crop, 1.03 ** k) for k in range(1, 16)])
    _frame(fixed, crop), _frame(scale, crop)               # warm the pan zoom
    p_f, p_s = _paired(fixed, scale, [crop.translated(crop.width() * 0.03 * k, 0)
                                      for k in range(1, 16)])
    print(f"{shape.__name__}: zoom fixed {z_f:.1f} / scale {z_s:.1f} ms "
          f"({z_f / z_s:.2f}x, bar 1.5x); pan fixed {p_f:.1f} / scale "
          f"{p_s:.1f} ms ({p_f / p_s:.2f}x, bar 1.1x)")


def test_lts8_shape_c_deep_zoom_long_lines(qapp):
    ms, crop = _shape_c()
    _, img = _frame(ms, crop)
    assert any(_has_gaps(img, y) for y in range(0, _H, 3)),         "100 m lines drew solid -- window missing"
    ref, _ = _shape_c(-60.0, 140.0)                       # cut to the view
    z, z_ref = _paired(ms, ref, [_zoomed(crop, 1.03 ** k) for k in range(1, 16)])
    print(f"shape C: zoom 100 m {z:.1f} / cut-to-view {z_ref:.1f} ms "
          f"({z / z_ref:.2f}x, bar 2x); expand cache {len(linetype_render._EXPAND)}")
