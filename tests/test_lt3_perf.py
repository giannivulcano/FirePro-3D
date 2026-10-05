"""LT3-11 G-perf -- 200 linetyped block instances paint within 2x Continuous.

Run standalone: ``pytest tests/test_lt3_perf.py -m perf -s``.
"""
import time

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d import linetype_render
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.lt3_support import hidden

pytestmark = pytest.mark.perf
_W, _H = 1600, 900
_CROP = QRectF(0, 0, 50000, 6000)       # ~31 mm/px: Hidden period ~29 px, above LOD


def _scene(dashed: bool):
    """200 placed instances of a block of 10 parallel 2000 mm lines."""
    ms = Model_Space()
    lid = hidden(ms)
    prims = []
    for k in range(10):
        ln = LineItem(QPointF(0, k * 50), QPointF(2000, k * 50))
        if dashed:
            ln.style["linetype"] = lid
        prims.append(ln.to_dict())
    d = BlockDefinition.new(name="B", library="L", series="S",
                            primitives=prims, origin=(0.0, 0.0))
    ms.register_block_definition(d)
    for i in range(200):
        ms.place_block_instance(d.id, ((i % 20) * 2500.0, (i // 20) * 600.0),
                                level=ms.active_level)
    return ms


def _render(ms, img):
    img.fill(QColor("#000000"))
    p = QPainter(img)
    t0 = time.perf_counter()
    ms.render(p, QRectF(0, 0, _W, _H), _CROP)
    dt = time.perf_counter() - t0
    p.end()
    return dt


def _frame_ms(ms, reps=5):
    """Best of *reps* renders into 1600x900 px, in ms."""
    img = QImage(_W, _H, QImage.Format.Format_ARGB32)
    return min(_render(ms, img) for _ in range(reps)) * 1000


def _span_profile(ms):
    """(has_gap_row, has_solid_row) over the first instance's pixel span
    (x 0..2000 mm = 0..64 px), measured on the real rendered pixels."""
    img = QImage(_W, _H, QImage.Format.Format_ARGB32)
    _render(ms, img)
    gap = solid = False
    for y in range(_H):
        lit = [img.pixelColor(x, y).lightness() > 40 for x in range(2, 62)]
        if all(lit):
            solid = True
        elif any(lit) and not all(lit) and sum(lit) < len(lit) - 4:
            gap = True
    return gap, solid


def test_lt3_linetyped_within_2x_continuous(qapp):
    plain, dashed = _scene(False), _scene(True)
    assert len(plain._block_instances) == 200
    assert len(dashed._block_instances) == 200

    linetype_render._EXPAND.clear()
    _frame_ms(plain, reps=1)
    assert len(linetype_render._EXPAND) == 0, "plain scene must not expand"
    _frame_ms(dashed, reps=1)                          # warm the expansion cache
    assert len(linetype_render._EXPAND) > 0, "dashed scene never expanded"

    gap_d, _ = _span_profile(dashed)
    _, solid_p = _span_profile(plain)
    assert gap_d, "dashed scene shows no gaps -- bench is measuring Continuous"
    assert solid_p, "plain scene shows no solid line -- not Continuous"

    a, b = _frame_ms(plain), _frame_ms(dashed)
    print(f"plain {a:.1f} ms, dashed {b:.1f} ms, ratio {b / a:.2f}")
    assert b <= 2.0 * a + 1.0, (a, b)
