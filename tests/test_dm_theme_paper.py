"""DM chrome revision, Paper Space tree (AC3/AC4): real MainWindow, real QSS,
persisted paper settings are the observable (the paper renderer reads them)."""
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialogButtonBox

from firepro3d import colour_picker
from firepro3d import display_manager as dm
from firepro3d.paper_display import load_paper_categories
from tests.paper_mode_shim import set_paper_mode
from firepro3d.theme import M, detect
from firepro3d.ui_kit import EyeToggle, Swatch
from tests._dm_theme_helpers import dispose_dm, mw, open_dm, table_px  # noqa: F401

_LEFT = Qt.MouseButton.LeftButton


def test_paper_tree_table_look_and_row_height(mw):
    dlg = open_dm(mw, "paper")
    try:
        tree = dlg._ps_tree
        assert table_px(tree) == detect().table.lower()
        child = dlg._paper_cat_data["Pipe"]["tree_item"]
        assert tree.visualItemRect(child).height() == M.DM_ROW_H
    finally:
        dispose_dm(dlg)


def test_paper_colour_chip_click_persists_and_eye_cancel_restores(mw, monkeypatch):
    set_paper_mode("custom")          # colour cells are live only in Custom
    monkeypatch.setattr(colour_picker, "pick_colour", lambda *a, **k: "#00cc00")
    dlg = open_dm(mw, "paper")
    try:
        row = dlg._paper_cat_data["Pipe"]
        dlg._ps_tree.scrollToItem(row["tree_item"])
        QApplication.processEvents()
        sw, eye = row["color_btn"], row["vis"]
        assert isinstance(sw, Swatch) and isinstance(eye, EyeToggle)
        assert sw.isEnabled() and sw._label.isHidden()
        QTest.mouseClick(sw._chip, _LEFT)
        assert load_paper_categories(dlg._settings)["Pipe"]["color"] == "#00cc00"
        assert sw.hex() == "#00cc00"
        assert load_paper_categories(dlg._settings)["Pipe"]["visible"] is True
        QTest.mouseClick(eye, _LEFT)
        assert load_paper_categories(dlg._settings)["Pipe"]["visible"] is False
        cancel = dlg._footer_box.button(QDialogButtonBox.StandardButton.Cancel)
        before = load_paper_categories(dlg._settings)["Pipe"]["color"]
        assert before == "#00cc00"
        QTest.mouseClick(cancel, _LEFT)
        restored = load_paper_categories(dlg._settings)["Pipe"]
        assert restored["visible"] is True and restored["color"] != "#00cc00"   # snapshot put both back
    finally:
        dispose_dm(dlg)


def test_paper_not_applicable_cells_stay_disabled_chips(mw):
    set_paper_mode("custom")
    dlg = open_dm(mw, "paper")
    try:
        hatch = dlg._paper_cat_data["Hatch"]               # weight-only row (_LW_ONLY)
        assert isinstance(hatch["color_btn"], Swatch) and not hatch["color_btn"].isEnabled()
        assert not hatch["vis"].isEnabled() and not hatch["opacity"].isEnabled()
        assert hatch["lw_combo"].isEnabled()
        assert isinstance(hatch["fill_btn"], Swatch) and not hatch["fill_btn"].isEnabled()
    finally:
        dispose_dm(dlg)


def test_paper_section_cell_is_a_compact_chip(mw, monkeypatch):
    set_paper_mode("custom")
    monkeypatch.setattr(colour_picker, "pick_colour", lambda *a, **k: "#12ab34")
    dlg = open_dm(mw, "paper")
    try:
        row = dlg._paper_cat_data["Wall"]                  # Wall is in paper_display._HAS_SECTION
        dlg._ps_tree.scrollToItem(row["tree_item"])
        QApplication.processEvents()
        sec = row["section_btn"]
        assert isinstance(sec, Swatch) and sec._label.isHidden() and sec.isEnabled()
        QTest.mouseClick(sec._chip, _LEFT)
        assert load_paper_categories(dlg._settings)["Wall"]["section_color"] == "#12ab34"
    finally:
        dispose_dm(dlg)
