"""Header labels keep their size under the live app QSS (smoke audit 2026-09-30).

The app stylesheet's ``QWidget { font-size: 9.75pt }`` silently beats a
widget's ``setFont()`` size (bold/family survive). Dock headers and the Levels
header now own their size in their own stylesheet. These guards run under the
real app QSS and re-apply it once (a theme switch re-styles live widgets).
"""
from __future__ import annotations

import pytest
from firepro3d import theme as th
from firepro3d.theme import M


@pytest.fixture
def app_qss(qapp):
    old_ss = qapp.styleSheet()
    qapp.setStyleSheet(th.build_app_qss(th.detect()))
    yield qapp
    qapp.setStyleSheet(old_ss)


def _effective(widget, qapp):
    widget.show()
    qapp.processEvents()
    qapp.setStyleSheet(qapp.styleSheet())   # re-style, as a theme switch does
    qapp.processEvents()
    return widget.font()


def test_dock_header_keeps_its_size(app_qss):
    from firepro3d.ui_kit import dock_header
    lbl = dock_header("Browser Dock")
    f = _effective(lbl, app_qss)
    assert f.pointSizeF() == M.DOCK_HEADER_PT
    assert f.bold()


def test_levels_header_keeps_its_size(app_qss):
    from PyQt6.QtWidgets import QLabel
    from firepro3d.level_manager import LevelManager
    from firepro3d.level_widget import LevelWidget
    w = LevelWidget(LevelManager())
    hdr = next(l for l in w.findChildren(QLabel) if l.text() == "Levels")
    _effective(w, app_qss)
    f = hdr.font()
    assert f.pointSizeF() == M.DOCK_HEADER_PT
    assert f.bold()
