"""G12 perf guard (HF4 AC9 / D-A25): hover <= 50 ms per move on ~500 primitives.

Run standalone: venv/Scripts/python.exe -m pytest tests/test_pick_region_perf.py -m perf -q -s
Raw timings are appended to tests/_perf_pick_region.txt (interleaved runs, VC perf rule).
"""
import os
import time

import pytest
from PyQt6.QtCore import QPointF

from tests._snap_polish_helpers import close_view, make_view, move

BAR_MS = 50.0
OUT = os.path.join(os.path.dirname(__file__), "_perf_pick_region.txt")


def _grid_lines(scene):
    from firepro3d.geometry_2d import LineItem
    items = []
    for r in range(20):
        for c in range(25):
            x, y = c * 20.0, r * 20.0
            items.append(LineItem(QPointF(x, y), QPointF(x + 20.0, y)))
    for c in range(26):
        items.append(LineItem(QPointF(c * 20.0, 0), QPointF(c * 20.0, 400.0)))
    for it in items:
        scene.addItem(it)
    return len(items)


def _circles_cut(scene):
    from firepro3d.geometry_2d import CircleItem, LineItem
    n = 0
    for k in range(50):
        cx, cy = (k % 10) * 100.0, (k // 10) * 100.0
        for it in (CircleItem(QPointF(cx, cy), 40.0),
                   LineItem(QPointF(cx - 50, cy), QPointF(cx + 50, cy)),
                   LineItem(QPointF(cx, cy - 50), QPointF(cx, cy + 50))):
            scene.addItem(it); n += 1
    return n


@pytest.mark.perf
@pytest.mark.parametrize("shape,build,probe", [
    ("a-grid", _grid_lines, QPointF(210.0, 210.0)),
    ("b-circles", _circles_cut, QPointF(215.0, 215.0)),
])
def test_hover_per_move_under_bar(qapp, shape, build, probe):
    view, scene = make_view(role="block_editor", scale=1.0, mode=None)
    try:
        n = build(scene)
        assert n >= 150
        scene.set_mode("pick_region")
        t0 = time.perf_counter()
        move(view, probe)                                   # builds the window
        build_ms = (time.perf_counter() - t0) * 1000.0
        samples = []
        for i in range(20):
            pt = QPointF(probe.x() + (i % 5) * 0.5, probe.y() + (i % 3) * 0.5)
            t1 = time.perf_counter()
            scene._pick_region_hover(pt)
            samples.append((time.perf_counter() - t1) * 1000.0)
        samples.sort()
        median = samples[len(samples) // 2]
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(f"{shape}\tn={n}\tbuild_ms={build_ms:.1f}\tmedian_ms={median:.2f}\tmax_ms={samples[-1]:.2f}\n")
        print(f"\n{shape}: n={n} build={build_ms:.1f}ms median={median:.2f}ms max={samples[-1]:.2f}ms")
        assert scene._pick_region_preview is not None and scene._pick_region_preview[2] is True
        assert median <= BAR_MS
    finally:
        close_view(view, scene)
