"""Multi-sheet integration: round-trip, active-sheet rules, legacy load.

Headline regression: pre-fix, save collapsed scene._sheets to [active] and
load kept only _sheets[0] — extra sheets silently vanished.
"""
from __future__ import annotations

import json

import pytest

from firepro3d.paper_space import PaperSpaceWidget, Sheet, SheetManager


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
