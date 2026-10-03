"""G12 (D-A35): 200 hatched placed instances cost <= 0.15 ms extra each.

Bar amended 2026-10-02 (user ruling): absolute per-instance overhead
(hatched - plain <= 30 ms for 200 instances), not a ratio to the unfilled
frame - the ratio got harder whenever plain blocks got faster.

Run standalone: ``pytest tests/test_hatch_perf.py -m perf -s``.
"""
import statistics
import time

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d import hatch_render as hr
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import RectangleItem
from firepro3d.model_space import Model_Space

pytestmark = pytest.mark.perf
_RECT = QRectF(-1250, -1250, 50000, 25000)
_G12_BUDGET_MS = 30.0   # 200 instances x 0.15 ms (D-A35, amended 2026-10-02)


def _scene(filled):
    """Build 200 placed instances of a 2000x1000 mm rect (hatched if *filled*)."""
    sc = Model_Space(scene_role="block_editor")
    r = RectangleItem(QPointF(0, 0), QPointF(2000, 1000))
    if filled:
        r.fill_type, r.fill_pattern = "hatch", "diagonal"
        r._display_fill_color, r.fill_opacity = "#000000", 1.0
    d = BlockDefinition.new(name="B", library="L", series="S",
                            primitives=[r.to_dict()], origin=(0, 0))
    sc.register_block_definition(d)
    for i in range(20):
        for j in range(10):
            sc.place_block_instance(d.id, (i * 2500.0, j * 2500.0))
    return sc


def _frame_ms(sc):
    """Median of 5 renders of the whole layout into 1000x500 px, in ms."""
    img = QImage(1000, 500, QImage.Format.Format_RGB32)
    times = []
    for _ in range(5):
        img.fill(QColor("white"))
        p = QPainter(img)
        t0 = time.perf_counter()
        sc.render(p, QRectF(0, 0, 1000, 500), _RECT)
        times.append(time.perf_counter() - t0)
        p.end()
    return statistics.median(times) * 1000


def test_g12_200_hatched_instances_within_per_instance_budget(qapp):
    plain, hatched = _scene(False), _scene(True)
    assert len(hatched._block_instances) == 200
    _frame_ms(hatched)                               # warm the lattice cache
    hr.STATS["stamped_cells"] = 0
    t_hatch = _frame_ms(hatched)
    stamped = hr.STATS["stamped_cells"]
    assert stamped > 200 * 5, "bench never stamped — LOD toned it"
    t_plain = _frame_ms(plain)
    print(f"plain {t_plain:.1f} ms, hatched {t_hatch:.1f} ms, "
          f"ratio {t_hatch / t_plain:.2f}, stamped {stamped}")
    assert t_hatch - t_plain <= _G12_BUDGET_MS, "hatch overhead over budget"
