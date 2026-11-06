"""Notes on schematics, Part 3: a Printed schematic drops at extent / text_scale,
clamped to the sheet (N17). Drives the real browser leaf, drop event and dialog."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication, QDialog

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.paper_space import (MARGIN, INNER_MARGIN, PaperGraphicsView, PaperScene, Sheet,
                                   SheetViewPropertiesDialog, ViewResolver, sheet_page_mm)
from firepro3d.project_browser import ProjectBrowser
from firepro3d.schematic_scene import SchematicSceneManager
from tests._sb4d_helpers import drop_leaf


class _PlanStub:
    _views: dict = {}

    def get(self, name):
        return None


class _DetailStub:
    detail_names: list = []

    def get_marker(self, name):
        return None


def _drop(monkeypatch, width, sizing=None, scale=None, height=1000.0):
    """Drop a *width* x *height* mm schematic. Returns the viewport data, its extent."""
    proj = Model_Space()
    d = BlockDefinition.new(
        name="Riser", library="", series="", origin=(0.0, 0.0), kind="schematic",
        primitives=[LineItem(QPointF(0, 0), QPointF(width, height)).to_dict()])
    d.text_sizing, d.text_scale = sizing, scale
    proj.register_block_definition(d)
    mgr = SchematicSceneManager(proj)
    res = ViewResolver(proj, _PlanStub(), _DetailStub(), None, schematic_scenes=mgr)
    sheet = Sheet.create_default()
    proj._sheets = [sheet]
    ps = PaperScene(sheet, res)
    view = PaperGraphicsView(ps)
    view.resize(900, 700)
    browser = ProjectBrowser()
    browser.refresh_schematics([(d.id, d.name, "")])
    monkeypatch.setattr(SheetViewPropertiesDialog, "exec",
                        lambda dlg: QDialog.DialogCode.Accepted)
    try:
        drop_leaf(view, browser, "schematic", d.id)
        assert len(sheet.sheet_views) == 1
        return sheet.sheet_views[0], mgr.extent(d.id), sheet
    finally:
        browser.deleteLater()
        view.deleteLater()
        ps.deleteLater()
        QApplication.processEvents()


def test_a_printed_schematic_drops_at_extent_over_scale(qapp, monkeypatch):
    data, ext, _s = _drop(monkeypatch, 4000.0, "printed", 20.0)
    assert data.scale == 0.0                                # NTS default stands
    assert (data.w, data.h) == pytest.approx((ext.width() / 20.0, ext.height() / 20.0))


def test_it_opens_matching_the_editor(qapp, monkeypatch):
    """The NTS fit of that box is 1 / N, so k = 1: nothing moves in the print."""
    data, ext, _s = _drop(monkeypatch, 4000.0, "printed", 20.0)
    assert min(data.w / ext.width(), data.h / ext.height()) == pytest.approx(1 / 20.0)


def test_an_old_schematic_still_drops_at_one_to_one(qapp, monkeypatch):
    data, ext, _s = _drop(monkeypatch, 300.0, height=200.0)
    assert (data.w, data.h) == pytest.approx((ext.width(), ext.height()))


def test_a_large_printed_schematic_clamps_to_the_sheet(qapp, monkeypatch):
    data, ext, sheet = _drop(monkeypatch, 90000.0, "printed", 10.0)
    pw, _ph = sheet_page_mm(sheet)
    want_w = pw - 2 * (MARGIN + INNER_MARGIN)
    assert data.w == pytest.approx(want_w)
    assert data.h == pytest.approx(want_w * ext.height() / ext.width())
