"""Bug guard: no ribbon group label may be clipped (todo 2026-09-30).

The live app runs in Arial (theme.apply_app_font); the default test font
(Segoe UI) happened to make THERMAL RADIATION fit exactly, masking the clip.
Ground truth = rendered pixels: the label's ink must not touch either end.
"""
from __future__ import annotations

import pytest
from PyQt6.QtGui import QColor
from firepro3d import theme as th
from firepro3d import snap_engine
from firepro3d.ribbon_bar import RibbonGroup, _VLabel

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import, required before MainWindow()
_main_module.View3D = View3D
from main import MainWindow


@pytest.fixture(scope="module")
def arial_window(qapp):
    old_font = qapp.font()
    th.apply_app_font(qapp)
    saved = (snap_engine.SNAP_TOLERANCE_PX, snap_engine.SNAP_HYSTERESIS_PX)
    win = MainWindow()
    win.resize(1920, 1080)
    win.show()
    qapp.processEvents()
    yield win
    win.close()
    win.deleteLater()
    snap_engine.SNAP_TOLERANCE_PX, snap_engine.SNAP_HYSTERESIS_PX = saved
    qapp.setFont(old_font)


def _ink_rows(stack, lbl):
    """Label-local y rows that carry text ink (colour far from the surface)."""
    img = stack.grab().toImage()
    bg = QColor(th.detect().surface)
    top = lbl.mapTo(stack, lbl.rect().topLeft())
    rows = set()
    for y in range(lbl.height()):
        for x in range(lbl.width()):
            c = img.pixelColor(top.x() + x, top.y() + y)
            if (abs(c.red() - bg.red()) + abs(c.green() - bg.green())
                    + abs(c.blue() - bg.blue())) > 90:
                rows.add(y)
    return rows


def test_no_group_label_is_clipped(arial_window, qapp):
    rb = arial_window.ribbon
    checked = 0
    for i in range(rb._tab_bar.count()):
        rb._tab_bar.setCurrentIndex(i)
        qapp.processEvents()
        page = rb._stack.widget(i)
        for g in page.findChildren(RibbonGroup):
            lbl = g.findChild(_VLabel)
            rows = _ink_rows(rb._stack, lbl)
            assert rows, f"{lbl.text()}: no ink rendered"
            assert min(rows) >= 1 and max(rows) <= lbl.height() - 2, (
                f"{lbl.text()!r} clipped: ink rows {min(rows)}..{max(rows)} "
                f"in a {lbl.height()}px label")
            checked += 1
    assert checked >= 10


def test_long_label_wraps_to_two_lines(qapp):
    old_font = qapp.font()
    th.apply_app_font(qapp)
    try:
        lbl = _VLabel("THERMAL RADIATION")
        f = lbl.font()
        f.setPointSizeF(th.M.RIBBON_VLABEL_PT)
        lbl.setFont(f)
        assert lbl._lines() == ["THERMAL", "RADIATION"]
        assert _VLabel("FILE")._lines() == ["FILE"]
    finally:
        qapp.setFont(old_font)
