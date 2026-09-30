"""Tab separators: accent "|" between tabs, hidden beside the selected tab (VC3 pixels).

Chrome polish 2026-09-30 — ribbon, canvas and browser (West) tab strips share
ui_kit.paint_tab_separators.
"""
from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QWidget
from firepro3d import theme as th
from firepro3d.theme import M
from firepro3d.ui_kit import LeftTabs, tab_gap_center
from firepro3d.ribbon_bar import RibbonBar


def _accent_count(img, xs, ys):
    acc = QColor(getattr(th.detect(), th.TAB_SEP_ROLE))
    n = 0
    for x in xs:
        for y in ys:
            c = img.pixelColor(x, y)
            if (abs(c.red() - acc.red()) + abs(c.green() - acc.green())
                    + abs(c.blue() - acc.blue())) < 40:
                n += 1
    return n


def _north_gap_hits(bar, i):
    img = bar.grab().toImage()
    r = bar.tabRect(i)
    c = tab_gap_center(bar, i)
    return _accent_count(img, [c], range(r.top() + 2, r.bottom() - 2))


def test_ribbon_tab_separators(qapp):
    rb = RibbonBar()
    for t in ("Manage", "Architecture", "Analyze", "Draft"):
        rb.add_page(t)
    rb.resize(800, 140)
    rb.show()
    qapp.processEvents()
    bar = rb._tab_bar
    bar.setCurrentIndex(0)
    qapp.processEvents()
    assert _north_gap_hits(bar, 1) >= M.TAB_SEP_LEN - 2      # between tabs 1 and 2
    assert _north_gap_hits(bar, 0) == 0                      # beside the selected tab


def test_canvas_tab_separators(qapp):
    import main as _main_module
    from firepro3d.view_3d import View3D
    _main_module.View3D = View3D
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QTabWidget
    bar = _main_module._CanvasTabBar(QIcon(), QIcon())
    tw = QTabWidget(objectName="centralTabs")
    tw.setTabBar(bar)
    for t in ("3D Model", "Plan: Level 1", "Plan: Level 2", "Elevation: North"):
        tw.addTab(QWidget(), t)
    tw.resize(900, 200)
    tw.show()
    qapp.processEvents()
    tw.setCurrentIndex(0)
    qapp.processEvents()
    assert _north_gap_hits(bar, 2) >= M.TAB_SEP_LEN - 2
    assert _north_gap_hits(bar, 0) == 0


def test_west_tab_separators(qapp):
    lt = LeftTabs()
    for k in ("Project", "Model", "Features", "Blocks"):
        lt.addTab(QWidget(), k)
    lt.resize(300, 500)
    lt.show()
    qapp.processEvents()
    bar = lt._bar
    bar.setCurrentIndex(0)
    qapp.processEvents()
    img = bar.grab().toImage()
    y = tab_gap_center(bar, 1)
    want = min(M.TAB_SEP_LEN, bar.width() - 4) - 2
    assert _accent_count(img, range(0, bar.width()), [y]) >= want
    y0 = tab_gap_center(bar, 0)
    assert _accent_count(img, range(2, bar.width() - 3), [y0]) == 0   # beside selected


def test_ribbon_and_canvas_tabs_share_one_height(qapp):
    """Smoke 2026-09-30: ribbon tabs 26px vs canvas tabs 31px (the 20px close
    dot pushed the canvas taller). Under the real app QSS both match."""
    import main as _main_module
    from firepro3d.view_3d import View3D
    _main_module.View3D = View3D
    from main import MainWindow
    old_font, old_ss = qapp.font(), qapp.styleSheet()
    th.apply_app_font(qapp)
    qapp.setStyleSheet(th.build_app_qss(th.detect()))
    win = MainWindow()
    try:
        win.resize(1920, 1080)
        win.show()
        qapp.processEvents()
        rt, ct = win.ribbon._tab_bar, win.central_tabs.tabBar()
        rh = {rt.tabRect(i).height() for i in range(rt.count())}
        ch = {ct.tabRect(i).height() for i in range(ct.count())}
        assert len(rh) == 1 and rh == ch, f"ribbon {rh} vs canvas {ch}"
    finally:
        win.close()
        win.deleteLater()
        qapp.setStyleSheet(old_ss)
        qapp.setFont(old_font)
