"""DM chrome revision AC3 + AC4 (Model tree cells): real MainWindow, real app QSS,
canvas-observable ground truth (VC3)."""
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QDialogButtonBox

from firepro3d import colour_picker
from firepro3d import display_manager as dm
from firepro3d.ui_kit import EyeToggle, Swatch
from tests._dm_theme_helpers import add_wall, dispose_dm, mw, open_dm  # noqa: F401

_LEFT = Qt.MouseButton.LeftButton


def _centre_name(sw):
    img = sw._chip.grab().toImage()
    return img.pixelColor(img.width() // 2, img.height() // 2).name()


def _show_row(dlg, key):
    item = dlg._cat_data[key]["tree_item"]
    dlg._tree.scrollToItem(item)
    QApplication.processEvents()
    return dlg._cat_data[key]["widgets"]


def test_colour_chip_click_recolours_the_wall_and_the_chip(mw, monkeypatch):
    wall = add_wall(mw)
    monkeypatch.setattr(colour_picker, "pick_colour", lambda *a, **k: "#00cc00")
    dlg = open_dm(mw)
    try:
        w = _show_row(dlg, "Wall")
        sw = w["color_btn"]
        assert isinstance(sw, Swatch) and sw._label.isHidden()
        assert dlg._tree.itemWidget(dlg._cat_data["Wall"]["tree_item"], dm._COL_COLOR) is sw
        assert sw.isVisible()
        QTest.mouseClick(sw._chip, _LEFT)
        assert wall._display_color == "#00cc00"        # canvas item's display colour
        assert sw.hex() == "#00cc00" and sw.property("_color") == "#00cc00"
        assert _centre_name(sw) == "#00cc00"           # the chip itself paints it
    finally:
        dispose_dm(dlg)


def test_fill_chip_no_fill_and_disabled_cell(mw, monkeypatch):
    wall = add_wall(mw)
    monkeypatch.setattr(colour_picker, "pick_colour", lambda *a, **k: "")     # No Fill
    dlg = open_dm(mw)
    try:
        w = _show_row(dlg, "Wall")
        fill = w["fill_btn"]
        assert isinstance(fill, Swatch) and fill.isEnabled()
        QTest.mouseClick(fill._chip, _LEFT)
        assert wall._display_fill_color == ""          # No Fill reached the canvas item
        assert fill.hex() == ""
        assert fill._chip.grab().toImage().pixelColor(4, 3).name() == "#ffffff"   # empty-chip (No-Fill) look
        pipe = _show_row(dlg, "Pipe")
        assert isinstance(pipe["fill_btn"], Swatch) and not pipe["fill_btn"].isEnabled()  # Pipe has no fill
    finally:
        dispose_dm(dlg)


def test_eye_cell_flips_wall_visibility_and_cancel_restores(mw):
    wall = add_wall(mw)
    dlg = open_dm(mw)
    try:
        w = _show_row(dlg, "Wall")
        eye = w["vis"]
        assert isinstance(eye, EyeToggle) and eye.isChecked() and wall.isVisible()
        QTest.mouseClick(eye, _LEFT)
        assert not eye.isChecked() and not wall.isVisible()
        cancel = dlg._footer_box.button(QDialogButtonBox.StandardButton.Cancel)
        QTest.mouseClick(cancel, _LEFT)
        assert wall.isVisible()                        # Cancel revert
        assert dlg.result() == QDialog.DialogCode.Rejected
    finally:
        dispose_dm(dlg)


def test_model_rows_use_the_house_row_height(mw):
    dlg = open_dm(mw)
    try:
        from firepro3d.theme import M
        grp = dlg._tree.topLevelItem(0)
        assert dlg._tree.visualItemRect(grp.child(0)).height() == M.DM_ROW_H
    finally:
        dispose_dm(dlg)
