"""EmptyCanvasPlaceholder under the LIVE app QSS + font (view-3d.md I5)."""
from __future__ import annotations

import pytest
from PyQt6.QtTest import QTest


@pytest.fixture()
def live_env(qapp):
    from firepro3d import theme as th
    prev_qss = qapp.styleSheet()
    prev_font = qapp.font()
    th.apply_app_font(qapp)
    qapp.setStyleSheet(th.build_app_qss(th.detect()))
    yield th
    qapp.setStyleSheet(prev_qss)
    qapp.setFont(prev_font)


def _placeholder(th):
    from firepro3d.canvas_placeholder import EmptyCanvasPlaceholder
    p = EmptyCanvasPlaceholder()
    p.resize(900, 500)
    p.set_rail_height(26)
    p.set_active_level("Level 2")
    p.show()
    QTest.qWaitForWindowExposed(p)
    return p


def test_text_sizes_survive_an_app_qss_reapply(live_env):
    th = live_env
    p = _placeholder(th)
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        app.setStyleSheet(th.build_app_qss(th.detect()))   # theme-switch path
        QTest.qWait(50)
        assert p._title.font().pointSizeF() == th.M.EMPTY_CANVAS_TITLE_PT
        assert p._title.font().bold()
        assert p._hint.font().pointSizeF() == th.M.EMPTY_CANVAS_HINT_PT
    finally:
        p.close()


def test_buttons_labels_tooltips_and_signals(live_env):
    p = _placeholder(live_env)
    try:
        got = []
        p.open3DRequested.connect(lambda: got.append("3d"))
        p.openPlanRequested.connect(lambda: got.append("plan"))
        assert p._btn_3d.text() == "3D Model" and p._btn_3d.toolTip()
        assert p._btn_plan.text() == "Plan: Level 2" and p._btn_plan.toolTip()
        assert p._btn_3d.width() >= live_env.M.EMPTY_CANVAS_BTN_MIN_W
        assert p._btn_plan.width() >= live_env.M.EMPTY_CANVAS_BTN_MIN_W
        p._btn_3d.click()
        p._btn_plan.click()
        assert got == ["3d", "plan"]
    finally:
        p.close()


def test_rail_height_follows_setter(live_env):
    p = _placeholder(live_env)
    try:
        assert p._rail.height() == 26
        p.set_rail_height(31)
        QTest.qWait(20)
        assert p._rail.height() == 31
    finally:
        p.close()


def test_pane_paints_the_plan_canvas_surface_token(live_env):
    """The empty pane matches the plan canvas colour (``surface``) — user
    request at the 2026-09-30 smoke; the live plan viewport samples surface."""
    th = live_env
    p = _placeholder(th)
    try:
        img = p.grab().toImage()
        got = img.pixelColor(5, img.height() - 5).name()
        assert got == th.detect().surface.lower()
    finally:
        p.close()
