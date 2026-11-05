"""SB4f AC3 / AC4 / AC7 / D3: the drop dialog's Number, Show Title and Show Border
reach the viewport, a duplicate is refused at OK, the clamp holds the title."""
import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QDialog

from firepro3d.paper_space import (INNER_MARGIN, MARGIN, TITLE_H, SheetViewData,
                                   SheetViewPropertiesDialog, sheet_page_mm)
from firepro3d.project_browser import ProjectBrowser
from tests._sb4d_helpers import add_sheet, dispose, drop_leaf, paper_view, plan_scene


def _drop(ms, sec, det, monkeypatch, edit):
    """A real browser drop of a detail; *edit* fills the dialog before OK."""
    det.create_detail("Detail 1", QRectF(0.0, 0.0, 4000.0, 3000.0))
    browser = ProjectBrowser()
    browser.refresh_details(det.detail_names)
    sheet = add_sheet(ms, "FP-1.0")
    sheet.sheet_views.append(SheetViewData("plan", "Plan: Level 1", "P", 0.0, 20.0, 20.0, 50.0,
                                           40.0, view_number="1"))
    view, ps = paper_view(ms, sec, det, sheet)

    def _exec(dlg):
        edit(dlg)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(SheetViewPropertiesDialog, "exec", _exec)
    drop_leaf(view, browser, "detail", "Detail 1")
    browser.deleteLater()
    return sheet, ps


def test_dialog_values_reach_the_viewport(qapp, monkeypatch):
    ms, sec, det, tabs = plan_scene()
    try:
        def edit(dlg):
            assert dlg.get_number() == "2"           # pre-filled: lowest unused
            dlg._number_edit.setText("A5")
            dlg._title_check.setChecked(False)
            dlg._border_check.setChecked(False)
        sheet, _ps = _drop(ms, sec, det, monkeypatch, edit)
        d = sheet.sheet_views[-1]
        assert (d.view_number, d.show_title, d.show_border) == ("A5", False, False)
    finally:
        dispose(ms, sec, tabs)


def test_defaults_at_the_dialog(qapp, monkeypatch):
    ms, sec, det, tabs = plan_scene()
    try:
        sheet, _ps = _drop(ms, sec, det, monkeypatch, lambda dlg: None)
        d = sheet.sheet_views[-1]
        assert (d.view_number, d.show_title, d.show_border) == ("2", True, True)
    finally:
        dispose(ms, sec, tabs)


def test_duplicate_or_blank_at_ok_keeps_the_dialog_open(qapp):
    seen = []
    used = {"1"}
    dlg = SheetViewPropertiesDialog(
        "Plan", default_number="2",
        number_refusal=lambda n: "taken" if n in used else ("blank" if not n.strip() else None),
        notify=seen.append)
    try:
        dlg._number_edit.setText("1")
        dlg.accept()
        assert dlg.result() != QDialog.DialogCode.Accepted and seen == ["taken"]
        dlg._number_edit.setText("  ")
        dlg.accept()
        assert dlg.result() != QDialog.DialogCode.Accepted and seen == ["taken", "blank"]
        dlg._number_edit.setText("5")
        dlg.accept()
        assert dlg.result() == QDialog.DialogCode.Accepted
    finally:
        dlg.deleteLater()


@pytest.mark.parametrize("shown,extra", [(True, 7.5), (False, 0.0)])   # raw: origin 4.5 + r 3
def test_clamp_holds_the_title_on_the_sheet(qapp, monkeypatch, real_system_library, shown, extra):
    ms, sec, det, tabs = plan_scene()
    placed = []
    try:
        def edit(dlg):
            dlg._title_check.setChecked(shown)
            dlg._scale_combo.setCurrentText("1:1")   # far taller than the sheet: clamps
        det.create_detail("Detail 1", QRectF(0.0, 0.0, 60000.0, 60000.0))
        browser = ProjectBrowser()
        browser.refresh_details(det.detail_names)
        sheet = add_sheet(ms, "FP-1.0")
        view, ps = paper_view(ms, sec, det, sheet)
        monkeypatch.setattr(ps, "add_viewport", placed.append)

        def _exec(dlg):
            edit(dlg)
            return QDialog.DialogCode.Accepted
        monkeypatch.setattr(SheetViewPropertiesDialog, "exec", _exec)
        drop_leaf(view, browser, "detail", "Detail 1")
        browser.deleteLater()
        d = placed[0]
        _pw, ph = sheet_page_mm(sheet)
        limit = ph - MARGIN - INNER_MARGIN - TITLE_H
        assert d.y + d.h + extra == pytest.approx(limit, abs=1e-6)
    finally:
        dispose(ms, sec, tabs)
