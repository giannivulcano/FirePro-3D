"""G12 (D-A25): a theme switch repaints 1,000 token items in <= 500 ms.

Metric: flushed repaint after a theme switch -- the work
``MainWindow._on_theme_bus_changed`` does per live scene, then
``processEvents`` + ``viewport().repaint()`` on a shown view. Each run first
settles the scene on the dark theme (untimed), then times dark -> light.

The bench degrades on older trees (no ``TOKEN_AUTO`` / ``refresh_token_latched``)
so the same file measures the base SHAs; ``G12_BENCH_OUT`` appends raw lines.
"""
import os
import statistics
import time

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QGraphicsView

from firepro3d import theme
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.text_item import TextAnnotationData, TextItem

try:
    from firepro3d.constants import TOKEN_AUTO as _AUTO
except ImportError:                       # pre-HF1 tree
    _AUTO = "#ffffff"

pytestmark = pytest.mark.perf
BAR_MS = 500.0
RUNS = 5


def _refresh(sc) -> None:
    """Mirror of ``MainWindow._on_theme_bus_changed`` for one scene."""
    try:
        from firepro3d.display_manager import refresh_token_latched
    except ImportError:                   # before the theme bus (HF1 T6)
        refresh_token_latched = None
    if refresh_token_latched is not None:
        refresh_token_latched(sc)
    for it in sc.items():
        fn = getattr(it, "on_theme_changed", None)
        if fn is not None:
            fn()
    sc.update()


def _definition(ms, n_lines: int) -> str:
    prims = [LineItem(QPointF(0, i * 2.0), QPointF(100, i * 2.0), _AUTO).to_dict()
             for i in range(n_lines)]
    d = BlockDefinition.new(name=f"G12_{n_lines}", library="L", series="S",
                            primitives=prims, origin=(0.0, 0.0))
    ms.register_block_definition(d)
    return d.id


def _scene_a():
    """(a) 1,000 instances of a one-line Automatic definition."""
    ms = Model_Space()
    bid = _definition(ms, 1)
    for i in range(1000):
        ms.place_block_instance(bid, ((i % 40) * 150.0, (i // 40) * 50.0))
    return ms


def _scene_b():
    """(b) 10 instances of a 100-line definition + 100 Automatic model texts."""
    ms = Model_Space()
    bid = _definition(ms, 100)
    for i in range(10):
        ms.place_block_instance(bid, (i * 150.0, 0.0))
    for i in range(100):
        t = TextItem(TextAnnotationData(text=f"T{i}", color=_AUTO))
        t.setPos((i % 10) * 150.0, 300.0 + (i // 10) * 40.0)
        ms.addItem(t)
    return ms


def _count(ms) -> tuple[int, int]:
    insts = sum(1 for it in ms.items() if type(it).__name__ == "BlockInstance")
    texts = sum(1 for it in ms.items() if isinstance(it, TextItem))
    return insts, texts


def _time_switches(ms, monkeypatch) -> list[float]:
    v = QGraphicsView(ms)
    v.resize(1200, 800)
    v.show()
    assert QTest.qWaitForWindowExposed(v)
    v.fitInView(ms.itemsBoundingRect())
    runs = []
    try:
        for _ in range(RUNS):
            monkeypatch.setattr(theme, "theme_preference", lambda: "dark")
            _refresh(ms)
            QApplication.processEvents()
            v.viewport().repaint()
            monkeypatch.setattr(theme, "theme_preference", lambda: "light")
            t0 = time.perf_counter()
            _refresh(ms)
            QApplication.processEvents()
            v.viewport().repaint()
            runs.append((time.perf_counter() - t0) * 1000.0)
    finally:
        v.close()
        v.deleteLater()
    return runs


def _record(shape: str, runs: list[float]) -> None:
    out = os.environ.get("G12_BENCH_OUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"{shape} min={min(runs):.1f} med={statistics.median(runs):.1f} "
                     f"raw={','.join(f'{r:.1f}' for r in runs)}\n")


def test_g12_shape_a(qapp, monkeypatch):
    ms = _scene_a()
    assert _count(ms) == (1000, 0)        # scene composition (perf rule)
    runs = _time_switches(ms, monkeypatch)
    _record("a", runs)
    assert min(runs) <= BAR_MS, runs


def test_g12_shape_b(qapp, monkeypatch):
    ms = _scene_b()
    assert _count(ms) == (10, 100)        # scene composition (perf rule)
    runs = _time_switches(ms, monkeypatch)
    _record("b", runs)
    assert min(runs) <= BAR_MS, runs
