"""SB4d guards 6 + 7 (D4): the Sheet slot is blank when unplaced and follows
place / remove; a detail / section view lives on one sheet (second drop
refused with a notice, browser leaf not draggable); plans stay
multi-placeable; a legacy two-placement file loads as-is and cites the
first sheet in sheet order."""
import json

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtWidgets import QDialog

from firepro3d.paper_space import SheetViewData, SheetViewPropertiesDialog
from firepro3d.project_browser import ProjectBrowser
from tests._sb4d_helpers import (add_sheet, dispose, drop_leaf, find_leaf,
                                 head_def, paper_view, plan_scene)


def test_guard7_sheet_slot_follows_place_and_remove(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        head_def(ms, "Detail", texts=(("Mark", -2.0), ("Sheet", 9.0)))   # Sheet text OUTSIDE the circle
        m = det.create_detail("Detail 1", QRectF(0.0, 0.0, 4000.0, 3000.0))
        sheet = add_sheet(ms, "FP-2.0")
        _view, ps = paper_view(ms, sec, det, sheet)
        assert m.bubble.host_values({"Sheet"})["Sheet"].raw is None
        unplaced_bottom = m.bubble.mapRectToScene(m.bubble.boundingRect()).bottom()
        ps.add_viewport(SheetViewData("detail", "Detail 1", "", 0.02, 20.0, 20.0, 100.0, 80.0))
        assert m.bubble.host_values({"Sheet"})["Sheet"].text == "FP-2.0"
        placed_bottom = m.bubble.mapRectToScene(m.bubble.boundingRect()).bottom()
        assert placed_bottom > unplaced_bottom + 100.0          # the head re-shaped round the number
        ps.undo_stack.undo()                                     # removal
        assert m.bubble.host_values({"Sheet"})["Sheet"].raw is None
        assert m.bubble.mapRectToScene(m.bubble.boundingRect()).bottom() == pytest.approx(unplaced_bottom)
    finally:
        dispose(ms, sec, tabs)


@pytest.mark.parametrize("role", ["detail", "section"])
def test_guard6_second_drop_is_refused_with_a_notice(qapp, monkeypatch, role):
    ms, sec, det, tabs = plan_scene()
    try:
        if role == "detail":
            det.create_detail("Detail 1", QRectF(0.0, 0.0, 4000.0, 3000.0))
            name = "Detail 1"
        else:
            name = sec.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0)).name
        add_sheet(ms, "FP-1.0", [(role, name)])
        second = add_sheet(ms, "FP-2.0")
        browser = ProjectBrowser()
        browser.refresh_details(det.detail_names)
        browser.refresh_sections(sec.section_names)
        view, _ps = paper_view(ms, sec, det, second)
        opened, msgs = [], []
        monkeypatch.setattr(SheetViewPropertiesDialog, "exec",
                            lambda dlg: opened.append(dlg) or QDialog.DialogCode.Accepted)
        monkeypatch.setattr(ms, "_show_status", lambda m, timeout=5000: msgs.append(m))
        drop_leaf(view, browser, role, name)
        assert opened == [] and second.sheet_views == []
        assert msgs == [f"{name} is already placed on sheet FP-1.0 - "
                        f"a {role} view can be placed on one sheet only."]
    finally:
        dispose(ms, sec, tabs)


def test_guard6_plans_stay_multi_placeable(qapp, monkeypatch):
    ms, sec, det, tabs = plan_scene()
    try:
        add_sheet(ms, "FP-1.0", [("plan", "Plan: Level 1")])
        second = add_sheet(ms, "FP-2.0")
        browser = ProjectBrowser(level_manager=ms._level_manager)
        view, _ps = paper_view(ms, sec, det, second)
        monkeypatch.setattr(SheetViewPropertiesDialog, "exec", lambda dlg: QDialog.DialogCode.Accepted)
        drop_leaf(view, browser, "plan", "Level 1")
        assert [sv.source_view_name for sv in second.sheet_views] == ["Plan: Level 1"]
    finally:
        dispose(ms, sec, tabs)


def test_guard6_placed_detail_and_section_leaves_are_not_draggable(qapp):
    browser = ProjectBrowser()
    browser.refresh_details(["Detail 1", "Detail 2"])
    browser.refresh_sections(["Section 1"])
    placed = {("detail", "Detail 1"), ("section", "Section 1")}
    browser.set_placed_views(placed)

    def drag(role, name):
        return bool(find_leaf(browser, role, name).flags() & Qt.ItemFlag.ItemIsDragEnabled)
    assert not drag("detail", "Detail 1") and not drag("section", "Section 1")
    assert drag("detail", "Detail 2")
    assert find_leaf(browser, "detail", "Detail 1").font(0).italic()
    browser.refresh_details(["Detail 1", "Detail 2"])            # a rebuild keeps the rule
    assert not drag("detail", "Detail 1") and drag("detail", "Detail 2")
    browser.set_placed_views(set())
    assert drag("detail", "Detail 1")


def test_guard6_legacy_two_placement_file_loads_and_cites_the_first_sheet(qapp, tmp_path):
    ms, sec, det, tabs = plan_scene()
    try:
        det.create_detail("Detail 1", QRectF(0.0, 0.0, 4000.0, 3000.0))
        ms._sheets.clear()
        add_sheet(ms, "FP-3.0", [("detail", "Detail 1")])
        add_sheet(ms, "FP-1.0", [("detail", "Detail 1")])        # a pre-SB4d second placement
        path = tmp_path / "legacy.fp3d"
        ms.save_to_file(str(path))
    finally:
        dispose(ms, sec, tabs)
    ms2, sec2, det2, tabs2 = plan_scene()
    try:
        head_def(ms2, "Detail", texts=(("Mark", -2.0), ("Sheet", 2.0)))
        ms2.load_from_file(str(path))
        assert [s.number for s in ms2._sheets] == ["FP-3.0", "FP-1.0"]
        assert all(len(s.sheet_views) == 1 for s in ms2._sheets)          # loaded as-is
        m = det2.get_marker("Detail 1")
        assert m.bubble.host_values({"Sheet"})["Sheet"].text == "FP-3.0"
    finally:
        dispose(ms2, sec2, tabs2)


def test_renaming_a_placed_detail_keeps_its_sheet_binding_and_the_one_sheet_rule(qapp, monkeypatch):
    """VC9 I2: set_property("Name") moves the sheet binding + manager key (like
    rename_section); the Sheet slot still cites the sheet, a second drop of the
    new name is still refused, and undoing the rename restores name + binding."""
    ms, sec, det, tabs = plan_scene()
    try:
        head_def(ms, "Detail", texts=(("Mark", -2.0), ("Sheet", 9.0)))
        m = det.create_detail("Detail 1", QRectF(0.0, 0.0, 4000.0, 3000.0))
        first = add_sheet(ms, "A-501", [("detail", "Detail 1")])
        second = add_sheet(ms, "A-502")
        assert m.bubble.host_values({"Sheet"})["Sheet"].text == "A-501"
        ms.push_undo_state()
        m.set_property("Name", "Stair Detail")
        ms.push_undo_state()                                     # the PropertyManager's post-action step
        assert m.bubble.host_values({"Sheet"})["Sheet"].text == "A-501"
        assert first.sheet_views[0].source_view_name == "Stair Detail"
        assert det.detail_names == ["Stair Detail"] and det.get_marker("Stair Detail") is m

        browser = ProjectBrowser()
        browser.refresh_details(det.detail_names)
        browser.set_placed_views({(sv.source_view_type, sv.source_view_name) for sv in first.sheet_views})
        view, _ps = paper_view(ms, sec, det, second)
        msgs = []
        monkeypatch.setattr(SheetViewPropertiesDialog, "exec", lambda dlg: QDialog.DialogCode.Accepted)
        monkeypatch.setattr(ms, "_show_status", lambda msg, timeout=5000: msgs.append(msg))
        assert not (find_leaf(browser, "detail", "Stair Detail").flags() & Qt.ItemFlag.ItemIsDragEnabled)
        drop_leaf(view, browser, "detail", "Stair Detail")
        assert second.sheet_views == []
        assert msgs == ["Stair Detail is already placed on sheet A-501 - "
                        "a detail view can be placed on one sheet only."]

        ms.undo()
        assert m.name == "Detail 1" and det.detail_names == ["Detail 1"]
        assert first.sheet_views[0].source_view_name == "Detail 1"
        assert m.bubble.host_values({"Sheet"})["Sheet"].text == "A-501"
        ms.redo()
        assert m.name == "Stair Detail" and first.sheet_views[0].source_view_name == "Stair Detail"

        det.create_detail("Other", QRectF(9000.0, 0.0, 1000.0, 1000.0))
        m.set_property("Name", "Other")                          # a duplicate name is refused
        assert m.name == "Stair Detail"
    finally:
        dispose(ms, sec, tabs)
