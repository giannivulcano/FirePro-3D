"""Build + Editor ribbon tabs (editor-build design §1; AC1-AC3, guards T1/T2).

Real MainWindow, shown, under the LIVE app QSS + font (VC3).
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QToolButton

from firepro3d import snap_engine
from tests._mainwindow_helpers import dispose_main_window


@pytest.fixture(scope="module")
def mw(qapp, tmp_path_factory):
    import os
    from firepro3d import theme as th
    prev_qss, prev_font = qapp.styleSheet(), qapp.font()
    prev_appdata = os.environ.get("APPDATA")
    os.environ["APPDATA"] = str(tmp_path_factory.mktemp("appdata"))
    th.apply_app_font(qapp)
    qapp.setStyleSheet(th.build_app_qss(th.detect()))
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    import main as main_mod
    from firepro3d.view_3d import View3D
    main_mod.View3D = View3D
    w = main_mod.MainWindow()
    w.resize(1400, 850)
    w.show()
    QTest.qWaitForWindowExposed(w)
    QTest.qWait(200)
    yield w
    dispose_main_window(w)
    snap_engine.SNAP_TOLERANCE_PX = saved_tol
    qapp.setStyleSheet(prev_qss)
    qapp.setFont(prev_font)
    if prev_appdata is None:
        os.environ.pop("APPDATA", None)
    else:
        os.environ["APPDATA"] = prev_appdata


def _editors(w):
    from firepro3d.block_editor import BlockEditorWidget
    return [w.central_tabs.widget(i) for i in range(w.central_tabs.count())
            if isinstance(w.central_tabs.widget(i), BlockEditorWidget)]


def _plan_index(w):
    for i in range(w.central_tabs.count()):
        if w.central_tabs.tabText(i).startswith("Plan: "):
            return i
    raise AssertionError("no plan tab")


@pytest.fixture(autouse=True)
def _clean(mw, qapp):
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    mw.ribbon._tab_bar.setCurrentIndex(0)
    qapp.processEvents()
    yield
    for e in _editors(mw):
        mw.block_editor_manager.close(e)
    mw.scene.clearSelection()
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    qapp.processEvents()


def _titles(w):
    tb = w.ribbon._tab_bar
    return [tb.tabText(i) for i in range(tb.count())]


def _page(w, title):
    tb = w.ribbon._tab_bar
    for i in range(tb.count()):
        if tb.tabText(i) == title:
            return w.ribbon._stack.widget(i)
    return None


def _groups(page):
    """``[(TITLE, RibbonGroup)]`` in on-page (layout) order."""
    from firepro3d.ribbon_bar import RibbonGroup
    from PyQt6.QtWidgets import QLabel
    out = []
    lay = page._layout
    for i in range(lay.count()):
        g = lay.itemAt(i).widget()
        if isinstance(g, RibbonGroup):
            out.append((g.findChildren(QLabel)[0].text(), g))
    return out


def _group(page, title):
    for t, g in _groups(page):
        if t == title.upper():
            return g
    raise AssertionError(title)


def _buttons(group):
    return {b.text(): b for b in group.findChildren(QToolButton)}


def _remove(w, *items):
    w.scene.clearSelection()
    for it in items:
        try:
            w.scene.removeItem(it)
        except Exception:
            pass


def _plan_wall(w):
    from firepro3d.wall import WallSegment
    wall = WallSegment(QPointF(0, 0), QPointF(1000, 0))
    w.scene.addItem(wall)
    return (wall,)


def _plan_pipe(w):
    pipe = w.scene.add_pipe(w.scene.add_node(0, -800), w.scene.add_node(1000, -800))
    return (pipe, pipe.node1, pipe.node2)


# ── T2: selection never inserts or switches a ribbon tab (AC2, G4/G6) ────────

@pytest.mark.parametrize("make", ["wall", "pipe"])
def test_plan_selection_inserts_no_tab_and_keeps_the_current_tab(mw, qapp, monkeypatch, make):
    inserted = []
    real_insert = mw.ribbon.insert_page
    monkeypatch.setattr(mw.ribbon, "insert_page",
                        lambda *a, **k: inserted.append(a) or real_insert(*a, **k))
    tb = mw.ribbon._tab_bar
    tb.setCurrentIndex(2)                                   # Sprinkler Systems
    qapp.processEvents()
    before = _titles(mw)
    items = _plan_wall(mw) if make == "wall" else _plan_pipe(mw)
    try:
        items[0].setSelected(True)
        qapp.processEvents()
        assert inserted == []
        assert _titles(mw) == before
        assert tb.currentIndex() == 2
        mw.scene.clearSelection()                            # deselect: still no move
        qapp.processEvents()
        assert _titles(mw) == before and tb.currentIndex() == 2
    finally:
        _remove(mw, *items)
        qapp.processEvents()


def test_block_editor_selection_inserts_no_tab(mw, qapp, monkeypatch):
    from firepro3d.geometry_2d import LineItem
    inserted = []
    real_insert = mw.ribbon.insert_page
    monkeypatch.setattr(mw.ribbon, "insert_page",
                        lambda *a, **k: inserted.append(a) or real_insert(*a, **k))
    ed = mw.block_editor_manager.open_new()
    qapp.processEvents()
    tb = mw.ribbon._tab_bar
    cur, before = tb.currentIndex(), _titles(mw)
    ln = LineItem(QPointF(0, 0), QPointF(100, 0))
    ed.editor_scene.addItem(ln)
    ed.editor_scene._draw_lines.append(ln)
    ln.setSelected(True)
    qapp.processEvents()
    assert inserted == [] and _titles(mw) == before and tb.currentIndex() == cur
