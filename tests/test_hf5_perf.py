"""HF5 VC9 I1: one Fill Types tab edit refreshes every section picker fast.

Perf bench (``-m perf``, excluded from the default gate) on two scenes plus a
non-perf structural guard (one icon build per type per refresh).
"""
import statistics
import time
from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF, Qt
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
    return [x["widgets"]["section_sel"]
            for x in (*d._cat_data.values(), *d._inst_data.values())
            if x["widgets"].get("section_sel") is not None]


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
        assert len(sels) >= n_walls                       # every wall row has a picker
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


def test_one_icon_build_per_type_per_refresh(qapp, model_space, monkeypatch):
    """Cold refresh renders each distinct look once; a warm one renders none and keeps
    every entry; a tab edit of one type re-renders that type only and every
    picker shows its new look."""
    _scene(model_space, 12, 6)
    d, tab, _ = _open(model_space)
    try:
        sels = _selectors(d)
        assert len(sels) >= 12
        calls = []
        real = dm._fill_type_icon

        def counting(*a, **k):
            calls.append(1)
            return real(*a, **k)

        monkeypatch.setattr(dm, "_fill_type_icon", counting)
        d.__dict__.pop("_icon_memo", None)
        d._refresh_section_selectors()
        n_types = len(d._section_table().all())
        n_looks = len({t.layers for t in d._section_table().all()})
        assert 1 < n_looks < n_types                      # some types share a look
        assert len(calls) == n_looks, (len(calls), n_looks)
        calls.clear()
        d._refresh_section_selectors()
        assert calls == []                                # warm: nothing re-rendered
        for s in sels:                                    # every picker lists every type
            assert s.count() >= n_types
            assert all(not s.itemIcon(i).isNull() for i in range(n_types))
        mark = Qt.ItemDataRole.UserRole + 7               # survives only an in-place update
        for s in sels:
            s.setItemData(0, "kept", mark)
        tab.select_name("T0")
        tab.set_background(True, "#ff0000", 1.0)          # the real edit path
        QApplication.processEvents()
        assert len(calls) == 1, len(calls)                # only T0 re-rendered
        assert all(s.itemData(0, mark) == "kept" for s in sels)   # restyle: no rebuild
        tid = d._section_table().by_name("T0").id
        for s in sels:
            img = s.itemIcon(s.findData(tid)).pixmap(40, 20).toImage()
            px = [img.pixelColor(x, y) for x in range(2, 38, 4) for y in (3, 10, 16)]
            assert any(c.red() > 200 and c.green() < 60 and c.blue() < 60 for c in px)
    finally:
        d.reject()


def test_rename_rebuilds_pickers_and_memo_keeps_live_looks(qapp, model_space):
    """A rename keeps the id but changes the entry text, so every picker is
    rebuilt (never an in-place icon swap); looks edited away leave the memo."""
    _scene(model_space, 6, 4)
    d, tab, _ = _open(model_space)
    try:
        sels = _selectors(d)
        tab.select_name("T0")
        tid = d._section_table().by_name("T0").id
        for k in range(4):                                # four transient looks
            tab.set_background(True, "#%02x0000" % (60 + k * 40), 1.0)
        QApplication.processEvents()
        assert set(d._icon_memo) == {t.layers for t in d._section_table().all()}
        order = [t.id for t in d._section_table().all()]
        assert tab.set_name("T0 Renamed")                 # keeps its sorted place
        QApplication.processEvents()
        assert [t.id for t in d._section_table().all()] == order
        for s in sels:
            assert s.itemText(s.findData(tid)) == "T0 Renamed"
    finally:
        d.reject()
