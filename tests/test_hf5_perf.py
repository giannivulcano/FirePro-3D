"""HF5 VC9 I1: one Fill Types tab edit refreshes the picker fast.

Perf bench (``-m perf``, excluded from the default gate) on two scenes. The
Model tab's per-row Section pickers retired with the Section column (materials
M5, M6), so the bench times the one picker left: the Materials tab's Fill Type
selector, which the Fill Types tab's ``edited`` refreshes. The structural icon
guards (one build per type per refresh, rename rebuild, memo keeps live looks)
retired with ``DisplayManager._type_icons`` they pinned; the Materials tab has
no icon memo yet (filed follow-up), so it has none to pin.
"""
import statistics
import time
from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from firepro3d import display_manager as dm
from firepro3d import fill_types as ft
from firepro3d.fill_layers import BackgroundLayer, FillLayers, PatternLayer

_LOG = Path(__file__).resolve().parent.parent / ".todo" / "perf_hf5_tab.log"
_BAR_MS = 50.0
_REPS = 5


def _scene(ms, n_walls: int, n_types: int):
    """*n_walls* walls + *n_types* Fill Types in the project table."""
    from firepro3d.wall import WallSegment
    have = len(ft.project_table().all())
    for i in range(max(0, n_types - have)):
        ft.project_table().add(ft.FillType(f"t{i}", f"T{i}", FillLayers(
            BackgroundLayer("#808080", 1.0), PatternLayer("diagonal", "#000000"))))
    for i in range(n_walls):
        w = WallSegment(QPointF(0, i * 500.0), QPointF(2000, i * 500.0))
        ms._walls.append(w)
        ms.addItem(w)
    assert len(ft.project_table().all()) == n_types
    assert len(ms._walls) == n_walls


def _open(ms):
    t0 = time.perf_counter()
    d = dm.DisplayManager(ms)
    open_s = time.perf_counter() - t0
    tab = next(d._tabs.widget(i) for i in range(d._tabs.count())
               if d._tabs.tabText(i) == "Fill Types")
    return d, tab, open_s


def _selectors(d):
    return [d._mat_tab.section_selector()]


@pytest.mark.perf
@pytest.mark.parametrize("n_walls,n_types", [(300, 8), (20, 40)])
def test_tab_edit_refreshes_pickers_within_bar(qapp, model_space, n_walls, n_types):
    _scene(model_space, n_walls, n_types)
    # Drain Qt's queued item polish (wall visibility -> outline rejoin) so rep0
    # times the edit, not scene setup (HF5 VC9 first-edit debug).
    QApplication.processEvents()
    d, tab, open_s = _open(model_space)
    try:
        d.show()                                          # real env: pickers visible
        QApplication.processEvents()
        sels = _selectors(d)
        assert len(sels) == 1                             # the Materials tab's picker
        assert all(s.count() >= n_types for s in sels)
        tab.select_name("T0")
        QApplication.processEvents()
        samples = []
        for k in range(_REPS):
            col = "#%02x0000" % (40 + k * 20)
            t0 = time.perf_counter()
            tab.set_background(True, col, 0.5)            # the real edit path
            QApplication.processEvents()
            samples.append((time.perf_counter() - t0) * 1000.0)
        med = statistics.median(samples)
        _LOG.parent.mkdir(exist_ok=True)
        with open(_LOG, "a", encoding="ascii") as f:
            for k, ms_ in enumerate(samples):
                f.write(f"scene={n_walls}w x {n_types}t rep={k} edit_ms={ms_:.1f}\n")
            f.write(f"scene={n_walls}w x {n_types}t median_ms={med:.1f} "
                    f"dm_open_s={open_s:.3f} bar_ms={_BAR_MS}\n")
        assert med <= _BAR_MS, f"median {med:.1f} ms > {_BAR_MS} ms ({samples})"
        assert samples[0] <= _BAR_MS, f"first edit {samples[0]:.1f} ms > {_BAR_MS} ms"
    finally:
        d.reject()
