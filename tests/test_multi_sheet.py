"""Multi-sheet integration: round-trip, active-sheet rules, legacy load.

Headline regression: pre-fix, save collapsed scene._sheets to [active] and
load kept only _sheets[0] — extra sheets silently vanished.
"""
from __future__ import annotations

import json

import pytest

from firepro3d.paper_space import PaperSpaceWidget, Sheet, SheetManager
from firepro3d.project_browser import _ROLE_NAME


@pytest.fixture()
def mw(qapp):
    import main as main_mod
    from firepro3d.view_3d import View3D
    main_mod.View3D = View3D
    w = main_mod.MainWindow()
    yield w
    w._modified = False
    w.close()


def test_three_sheet_round_trip(mw, tmp_path):
    """Save → load → save keeps all sheets intact (headline bug).

    The headline regression: extra sheets silently vanished on save (collapsed
    to [active]) or load (kept only _sheets[0]).  The round-trip stability
    check compares structural identity (number, name, sheet_views, annotations,
    revisions) but not title_block_fields — those are re-enriched by the live
    titleblock template on every load, which is expected/pre-existing behaviour.
    """
    s2 = mw.sheet_mgr.create()
    s3 = mw.sheet_mgr.create()
    s2.name, s3.name = "Details", "Cover"
    path = str(tmp_path / "multi.fpd")
    mw._current_file = path
    mw.save_file()
    sheets1 = json.load(open(path, encoding="utf-8"))["sheets"]
    assert len(sheets1) == 3, "save must persist ALL sheets, not just active"

    mw._load_project(path)
    assert [s.number for s in mw.sheet_mgr.sheets] == \
        [d["number"] for d in sheets1], "load must keep every sheet, in order"

    mw._current_file = path
    mw.save_file()
    sheets2 = json.load(open(path, encoding="utf-8"))["sheets"]
    assert len(sheets2) == 3, "second save must still persist all three sheets"

    def _structural(sheets):
        return [
            {k: s[k] for k in ("number", "name", "sheet_views", "annotations", "revisions")}
            for s in sheets
        ]

    assert _structural(sheets1) == _structural(sheets2), (
        "round-trip must be structurally stable (number/name/views/annotations/revisions)"
    )


def test_manager_wraps_scene_list_after_load(mw, tmp_path):
    """sheet_mgr must operate on the SAME list scene_io persists."""
    path = str(tmp_path / "p.fpd")
    mw._current_file = path
    mw.save_file()
    mw._load_project(path)
    assert mw.sheet_mgr.sheets is mw.scene._sheets
    assert mw._sheet is mw.sheet_mgr.sheets[0], "active = first on load"


def test_active_sheet_rules(mw):
    first = mw._sheet
    s2 = mw.sheet_mgr.create()
    mw._switch_sheet(s2)
    assert mw._sheet is s2, "create-then-switch makes the new sheet active"
    neighbor = mw.sheet_mgr.delete(s2)
    assert neighbor is first


def test_legacy_single_sheet_load_intact(mw, tmp_path):
    """A pre-feature single-sheet .fpd opens with its one sheet untouched."""
    mw._sheet.title_block_fields["Title"] = "Legacy Title"
    path = str(tmp_path / "legacy.fpd")
    mw._current_file = path
    mw.save_file()
    mw._load_project(path)
    assert len(mw.sheet_mgr.sheets) == 1
    assert mw._sheet.title_block_fields["Title"] == "Legacy Title"


def test_new_file_resets_to_single_default(mw, tmp_path):
    mw.sheet_mgr.create()
    assert len(mw.sheet_mgr.sheets) == 2
    mw._modified = False          # suppress the save prompt
    mw.new_file()
    assert len(mw.sheet_mgr.sheets) == 1
    assert mw.sheet_mgr.sheets is mw.scene._sheets
    assert mw._sheet is mw.sheet_mgr.sheets[0]


def test_sheet_no_auto_field(qapp):
    """§19.7: 'Sheet No' resolves to Sheet.number and always wins."""
    from firepro3d.paper_space import build_field_values
    sheet = Sheet.create_default()
    sheet.number = "FP-7.0"
    sheet.title_block_fields["Sheet No"] = "OVERRIDE-ME"   # sheet field loses
    vals = build_field_values(sheet, {})
    assert vals["Sheet No"] == "FP-7.0"


def test_sheet_no_sample_parity(qapp):
    """DD-13: editor sample keyset must include the new auto key."""
    from firepro3d.titleblock_editor import _SAMPLE_VALUES
    assert "Sheet No" in _SAMPLE_VALUES and _SAMPLE_VALUES["Sheet No"]


# ---------------------------------------------------------------------------
# Task 5: browser-push + orchestration tests
# ---------------------------------------------------------------------------

def _browser_rows(mw):
    from firepro3d.project_browser import _ROLE_NAME
    root = mw.project_browser._paper_root
    return [(root.child(i).data(0, _ROLE_NAME), root.child(i).text(0))
            for i in range(root.childCount())]


def test_browser_reflects_sheet_list_on_startup(mw):
    rows = _browser_rows(mw)
    assert rows == [("FP-1.0", "FP-1.0 - Fire Suppression Layout")]


def test_create_flow_end_to_end(mw):
    """Browser signal → MainWindow creates → pushed back → active + dirty."""
    mw._modified = False
    mw.project_browser.createPaperSheet.emit()
    assert len(mw.sheet_mgr.sheets) == 2
    assert mw._sheet is mw.sheet_mgr.sheets[-1], "new sheet becomes active"
    assert _browser_rows(mw)[-1][0] == mw._sheet.number
    assert mw._modified is True


def test_reorder_flow_and_reconcile(mw):
    mw.project_browser.createPaperSheet.emit()
    nums = [s.number for s in mw.sheet_mgr.sheets]
    mw._modified = False
    mw.project_browser.sheetOrderChanged.emit(list(reversed(nums)))
    assert [s.number for s in mw.sheet_mgr.sheets] == list(reversed(nums))
    assert [r[0] for r in _browser_rows(mw)] == list(reversed(nums))
    assert mw._modified is True
    # Garbage order (not a permutation) → data untouched, tree reconciled
    mw._modified = False
    mw.project_browser.sheetOrderChanged.emit(["bogus"])
    assert [r[0] for r in _browser_rows(mw)] == list(reversed(nums))
    assert mw._modified is False


def test_activate_switches_scene_to_sheet(mw):
    mw.project_browser.createPaperSheet.emit()
    target = mw.sheet_mgr.sheets[0]
    mw._activate_paper_sheet(target.number)
    assert mw._sheet is target
    assert mw.paper_space_widget._sheet is target
    assert mw.paper_space_widget.paper_scene._sheet is target


def test_undo_stack_clears_on_sheet_switch(mw):
    from firepro3d.paper_space import TextAnnotationData
    from firepro3d.paper_commands import AddTextAnnotationCommand
    scene = mw.paper_space_widget.paper_scene
    scene.undo_stack.push(
        AddTextAnnotationCommand(scene, TextAnnotationData(text="x", x=5, y=5)))
    assert scene.undo_stack.count() == 1
    s2 = mw.sheet_mgr.create()
    mw._switch_sheet(s2)
    assert scene.undo_stack.count() == 0, "grill: undo history dies on switch"


def test_delete_confirms_and_activates_neighbor(mw, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    s2 = mw.sheet_mgr.create()
    mw._switch_sheet(s2)
    # Decline → nothing happens
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    mw._delete_sheet(s2.number)
    assert len(mw.sheet_mgr.sheets) == 2
    # Accept → deleted, neighbor active
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    mw._delete_sheet(s2.number)
    assert len(mw.sheet_mgr.sheets) == 1
    assert mw._sheet is mw.sheet_mgr.sheets[0]


def test_delete_last_sheet_blocked(mw):
    assert len(mw.sheet_mgr.sheets) == 1
    mw._delete_sheet(mw._sheet.number)      # must not raise, must not delete
    assert len(mw.sheet_mgr.sheets) == 1


def test_placed_views_recomputed_on_paper_modified(mw):
    from firepro3d.paper_space import SheetViewData
    mw._sheet.sheet_views.append(SheetViewData(
        source_view_type="elevation", source_view_name="North",
        title="North Elevation", scale=100.0, x=10, y=10, w=100, h=100))
    mw._on_paper_modified()
    elev = mw.project_browser._elev_root
    fonts = {elev.child(i).data(0, 0x0101): elev.child(i).font(0).italic()
             for i in range(elev.childCount())}
    assert fonts["North"] is True


# ---------------------------------------------------------------------------
# Task 6: SheetProperties adapter + panel fallback + Esc + browser selection
# ---------------------------------------------------------------------------

def test_sheet_properties_adapter_validation(qapp):
    from firepro3d.paper_space import SheetProperties
    lst = [Sheet.create_default()]
    s2 = Sheet.create_default()
    s2.number = "FP-2.0"
    lst.append(s2)
    mgr = SheetManager(lst)
    changes, rejects = [], []
    props = SheetProperties(s2, mgr,
                            on_change=lambda: changes.append(1),
                            on_reject=rejects.append)
    form = props.get_properties()
    assert form["Sheet Number"]["value"] == "FP-2.0"
    assert form["Sheet Name"]["type"] == "string"
    assert form["Paper Size"]["type"] == "label"
    # collision rejected, number kept, on_reject fired
    props.set_property("Sheet Number", "FP-1.0")
    assert s2.number == "FP-2.0" and rejects and not changes
    # valid renumber commits + notifies
    props.set_property("Sheet Number", "FP-9.0")
    assert s2.number == "FP-9.0" and changes == [1]
    # name edit
    props.set_property("Sheet Name", "Cover")
    assert s2.name == "Cover" and changes == [1, 1]
    # no-op emits nothing
    props.set_property("Sheet Name", "Cover")
    assert changes == [1, 1]
    # blank name rejected with feedback, kept
    props.set_property("Sheet Name", "   ")
    assert s2.name == "Cover" and len(rejects) == 2


def test_panel_shows_sheet_props_on_empty_selection(mw):
    from firepro3d.paper_space import SheetProperties
    mw._activate_paper_sheet()              # paper tab current
    mw.paper_space_widget.paper_scene.clearSelection()
    mw.update_paper_property_manager()
    targets = mw.prop_manager._targets
    assert len(targets) == 1 and isinstance(targets[0], SheetProperties)


def test_escape_on_paper_tab_falls_back_to_sheet_props(mw):
    from firepro3d.paper_space import SheetProperties
    mw._activate_paper_sheet()
    mw._on_escape()                          # empty selection: stays on sheet props
    assert isinstance(mw.prop_manager._targets[0], SheetProperties)


def test_browser_sheet_click_populates_panel_with_that_sheet(mw):
    from firepro3d.paper_space import SheetProperties
    s2 = mw.sheet_mgr.create()
    mw._push_sheet_list()
    root = mw.project_browser._paper_root
    mw.project_browser._tree.setCurrentItem(root.child(1))   # fires sheetSelected
    t = mw.prop_manager._targets[0]
    assert isinstance(t, SheetProperties) and t._sheet is s2


def test_renumber_refreshes_tab_title_and_browser(mw):
    mw._activate_paper_sheet()
    props = mw._sheet_props_adapter(mw._sheet)
    props.set_property("Sheet Number", "FP-77.0")
    idx = mw.central_tabs.indexOf(mw.paper_space_widget)
    assert mw.central_tabs.tabText(idx).startswith("FP-77.0")
    root = mw.project_browser._paper_root
    assert root.child(0).data(0, _ROLE_NAME) == "FP-77.0"
    assert mw._modified is True


def test_delete_nonactive_sheet_resets_stale_panel_adapter(mw, monkeypatch):
    """Deleting a browser-selected non-active sheet must not leave its
    adapter live in the panel (edits would write to a detached Sheet)."""
    from PyQt6.QtWidgets import QMessageBox
    from firepro3d.paper_space import SheetProperties
    s2 = mw.sheet_mgr.create()          # active = s2 after create
    mw._switch_sheet(mw.sheet_mgr.sheets[0])   # make FP-1.0 active
    mw._activate_paper_sheet()          # paper tab current
    mw._on_browser_sheet_selected(s2.number)   # panel shows s2 (non-active)
    assert mw.prop_manager._targets[0]._sheet is s2
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    mw._delete_sheet(s2.number)
    t = mw.prop_manager._targets[0]
    assert isinstance(t, SheetProperties) and t._sheet is mw._sheet, \
        "panel must fall back to the active sheet after the delete"


def test_browser_sheet_click_ignored_in_add_text_mode(mw):
    mw._activate_paper_sheet()
    mw.paper_space_widget.set_add_text_mode(True)
    template_target = mw.prop_manager._targets[0]
    mw._on_browser_sheet_selected(mw._sheet.number)
    assert mw.prop_manager._targets[0] is template_target, \
        "add-text template must keep the panel"
    mw.paper_space_widget.set_add_text_mode(False)


# ---------------------------------------------------------------------------
# Task 7: uniform paper size across all sheets (spec §19.1)
# ---------------------------------------------------------------------------

def test_paper_size_change_applies_to_all_sheets(mw):
    s2 = mw.sheet_mgr.create()

    class R:
        paper_size = "ANSI B"
        orientation = "portrait"

    # ANSI B native is landscape (431.8 × 279.4); "portrait" is non-native
    # so stored value must be "portrait" (non-empty).
    mw._apply_paper_size_result(R())
    assert all(s.paper_size == "ANSI B" for s in mw.sheet_mgr.sheets)
    assert all(s.orientation == "portrait" for s in mw.sheet_mgr.sheets)

    # Requesting the native orientation stores "" for all sheets.
    class RNative:
        paper_size = "ANSI B"
        orientation = "landscape"

    mw._apply_paper_size_result(RNative())
    assert all(s.paper_size == "ANSI B" for s in mw.sheet_mgr.sheets)
    assert all(s.orientation == "" for s in mw.sheet_mgr.sheets)


def test_ribbon_paper_size_change_dirties_when_only_nonactive_change(mw):
    """Active sheet already at target size: setter no-ops, but non-active
    sheets still mutate — the project must dirty (§19.3 bytes rule).

    _change_paper_with_warning takes a str arg and has no dialog of its own
    (the menu lambda fires the dialog choice; this method is called after the
    user selects a size).  No monkeypatch needed.
    """
    s2 = mw.sheet_mgr.create()
    active_size = mw._sheet.paper_size      # e.g. "ANSI D"
    # craft mixed state: s2 has a different size so set_paper_all will mutate it
    other_size = next(s for s in ("ANSI A", "ANSI B", "ANSI C", "ANSI D", "ANSI E")
                      if s != active_size)
    s2.paper_size = other_size              # non-active sheet diverges
    mw._modified = False
    # Call the ribbon handler with the *active* size → active-sheet setter no-ops
    # but set_paper_all still normalises s2.
    mw._change_paper_with_warning(active_size)
    assert s2.paper_size == active_size, "non-active sheet must be normalised"
    assert mw._modified is True, "mutation of non-active sheet must dirty the project"
