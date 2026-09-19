"""Ribbon roster + File-group recompaction + TopTabs styling (chrome revamp Task 4).

Drives the real MainWindow ribbon. Reuses the session-scoped ``qapp`` fixture.
"""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QLabel, QToolButton
from firepro3d import snap_engine
from firepro3d import theme as th
from firepro3d.ribbon_bar import RibbonGroup, RibbonButton, RibbonSmallButton

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import, required before MainWindow()
_main_module.View3D = View3D
from main import MainWindow


@pytest.fixture(scope="module")
def main_window(qapp):
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    saved_hyst = snap_engine.SNAP_HYSTERESIS_PX
    win = MainWindow()
    win.show()
    yield win
    win.close()
    win.deleteLater()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol
    snap_engine.SNAP_HYSTERESIS_PX = saved_hyst


# ── helpers ──────────────────────────────────────────────────────────────────

def _page_by_title(mw, title):
    tb = mw.ribbon._tab_bar
    for i in range(tb.count()):
        if tb.tabText(i) == title:
            return mw.ribbon._stack.widget(i)
    return None


def _group_label(g):
    lbls = g.findChildren(QLabel)
    return lbls[0].text() if lbls else ""


def manage_group_titles(mw):
    page = _page_by_title(mw, "Manage")
    return [_group_label(g).title() for g in page.findChildren(RibbonGroup)]


def _file_group(mw):
    page = _page_by_title(mw, "Manage")
    for g in page.findChildren(RibbonGroup):
        if _group_label(g).upper() == "FILE":
            return g
    return None


def file_group_button_texts(mw):
    g = _file_group(mw)
    return {b.text().replace("\n", " ") for b in g.findChildren(QToolButton)}


# ── roster ───────────────────────────────────────────────────────────────────

def test_manage_tab_groups(main_window):
    assert manage_group_titles(main_window) == ["File", "Settings", "Display"]


def test_file_group_has_recent_and_no_save(main_window):
    names = file_group_button_texts(main_window)
    assert "Save As" in names and "Recent" in names
    assert "Save" not in names   # Save moved to the header rail


def test_file_group_is_compact_stack_plus_recent(main_window):
    g = _file_group(main_window)
    small = {b.text().replace("\n", " ") for b in g.findChildren(RibbonSmallButton)}
    assert {"New", "Open", "Save As"} <= small
    large = {b.text().replace("\n", " ") for b in g.findChildren(RibbonButton)}
    assert "Recent" in large   # Recent is a large menu button


# ── TopTabs styling ──────────────────────────────────────────────────────────

def test_ribbon_qss_selected_tab_accent_underline(qapp):
    t = th.detect()
    qss = th.build_ribbon_qss(t)
    assert f"border-bottom: 2px solid {t.accent}" in qss   # accent underline
    assert f"border-bottom: 1px solid {t.line_strong}" in qss  # full-width divider


# ── behaviour parity (Option A preserved) ────────────────────────────────────

def test_contextual_tab_insert_remove(main_window):
    rb = main_window.ribbon
    n = rb._tab_bar.count()
    rb.insert_page("Modify | Rectangle", 1, contextual=True)
    assert rb._tab_bar.count() == n + 1
    rb.remove_page(1)
    assert rb._tab_bar.count() == n
