"""G9 -- MW-13 perf: pan/zoom paint ms/frame vs base (A/B, 1.25x bar).

Run standalone, one at a time:
    ./venv/Scripts/python.exe -m pytest tests/test_mw_perf.py -m perf -s
A/B: copy this file into a worktree at the base commit and run it there
first; pass that run's printed medians as MW_BASE_MS_PRIMS / MW_BASE_MS_PDF
to the HEAD run. MW_PDF = the user's heavy PDF underlay (vector import).
First paint (the one-time crisp split, H-MW-f) is reported, not gated.
Views fit with KeepAspectRatio, as every app fit does (model_view).
Weights use the pre-MW factory names, which resolve at base and (by MW-6)
at HEAD, so both runs draw the same named weights.
"""
import os
import random
import statistics
import time

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication, QGraphicsPathItem
from PyQt6.QtTest import QTest

from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View

pytestmark = pytest.mark.perf
_FRAMES = 40
_NAMES = ["Very Light", "Light", "Medium", "Heavy", "Very Heavy"]


def _paint_ms(v):
    t0 = time.perf_counter()
    v.viewport().repaint()
    QApplication.processEvents()
    return (time.perf_counter() - t0) * 1000.0


def _frames_ms(v):
    out = []
    for k in range(_FRAMES):
        f = 1.03 if k % 2 else 1 / 1.03
        v.scale(f, f)
        out.append(_paint_ms(v))
    return statistics.median(out)


def _view(sc):
    v = Model_View(sc)
    v.resize(1400, 900)
    v.show()
    QTest.qWaitForWindowExposed(v)
    return v


def _check(label, env, ms):
    base = os.environ.get(env)
    print(f"\nG9 {label}: median {ms:.2f} ms/frame"
          + (f" (base {float(base):.2f}, ratio {ms / float(base):.2f}, bar 1.25)"
             if base else " (no base given: report only)"))
    if base:
        assert ms <= 1.25 * float(base), (label, ms, base)


def test_g9_two_thousand_mixed_primitives(qapp):
    random.seed(7)
    sc = Model_Space()
    for i in range(2000):
        x, y = random.uniform(-5000, 5000), random.uniform(-5000, 5000)
        if i % 3 == 0:
            a, b = QPointF(x, y), QPointF(x + 400, y + 250)          # diagonal
        elif i % 2:
            a, b = QPointF(x, y), QPointF(x + 400, y)                # horizontal
        else:
            a, b = QPointF(x, y), QPointF(x, y + 400)                # vertical
        ln = LineItem(a, b)
        ln.style["weight"] = _NAMES[i % 5]
        sc.addItem(ln)
        sc._draw_lines.append(ln)
    assert len(sc._draw_lines) == 2000                                 # composition
    v = _view(sc)
    v.fitInView(sc.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
    first = _paint_ms(v)
    ms = _frames_ms(v)
    print(f"\nG9 prims first paint {first:.1f} ms")
    _check("prims", "MW_BASE_MS_PRIMS", ms)
    v.close()
    sc.cleanup()


def test_g9_heavy_pdf_underlay(qapp):
    path = os.environ.get("MW_PDF")
    if not path:
        pytest.skip("set MW_PDF to the user's heavy PDF underlay")
    from firepro3d.underlay import Underlay
    sc = Model_Space()
    sc.import_pdf(path, page=0,
                  _record=Underlay(type="pdf", path=path, import_mode="vectors"),
                  import_mode="vectors")
    end = time.time() + 180
    while not sc.underlays and time.time() < end:
        QApplication.processEvents()
        time.sleep(0.05)
    assert sc.underlays, "vector import produced no underlay"
    _rec, group = sc.underlays[-1]
    paths = [c for c in group.childItems() if isinstance(c, QGraphicsPathItem)]
    els = sum(p.path().elementCount() for p in paths)
    assert len(paths) > 10 and els > 100_000, (len(paths), els)        # composition
    v = _view(sc)
    v.fitInView(group.sceneBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
    first = _paint_ms(v)
    ms = _frames_ms(v)
    print(f"\nG9 pdf: {len(paths)} path items, {els} elements; first paint {first:.1f} ms")
    _check("pdf", "MW_BASE_MS_PDF", ms)
    v.close()
    sc.cleanup()
