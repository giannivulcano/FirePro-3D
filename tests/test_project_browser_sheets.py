"""Browser sheet tree: pure push, number-keyed rows, reorder computation,
in-place placed-views italics (project-browser.md multi-sheet deltas)."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt

from firepro3d.project_browser import ProjectBrowser, _ROLE_TYPE, _ROLE_NAME


@pytest.fixture()
def browser(qapp):
    b = ProjectBrowser()
    yield b
    b.deleteLater()


def _sheet_rows(b):
    root = b._paper_root
    return [(root.child(i).data(0, _ROLE_NAME), root.child(i).text(0))
            for i in range(root.childCount())]


def test_set_sheets_number_keyed_display(browser):
    browser.set_sheets([("FP-1.0", "FP-1.0 - Plans"),
                        ("FP-2.0", "FP-2.0 - Details")])
    assert _sheet_rows(browser) == [("FP-1.0", "FP-1.0 - Plans"),
                                    ("FP-2.0", "FP-2.0 - Details")]
    assert browser._paper_root.child(0).data(0, _ROLE_TYPE) == "sheet"


def test_no_default_phantom_sheet(browser):
    """Pure push: the tree starts empty under Paper Space (D2 resolution)."""
    assert browser._paper_root.childCount() == 0
    assert not hasattr(browser, "_create_new_sheet"), \
        "optimistic local append must be deleted"


def test_create_signal_is_parameterless_and_does_not_mutate(browser):
    hits = []
    browser.createPaperSheet.connect(lambda: hits.append(1))
    browser.createPaperSheet.emit()
    assert hits == [1]
    assert browser._paper_root.childCount() == 0, "tree never self-mutates"


def test_sheet_selected_signal_on_single_click_selection(browser):
    browser.set_sheets([("FP-1.0", "FP-1.0 - A"), ("FP-2.0", "FP-2.0 - B")])
    got = []
    browser.sheetSelected.connect(got.append)
    browser._tree.setCurrentItem(browser._paper_root.child(1))
    assert got == ["FP-2.0"]


def test_reorder_computation_insert_before_target(browser):
    browser.set_sheets([("1", "1 - a"), ("2", "2 - b"), ("3", "3 - c")])
    got = []
    browser.sheetOrderChanged.connect(got.append)
    browser._on_sheet_dropped("3", "1")     # drop 3 onto 1 → before 1
    assert got == [["3", "1", "2"]]


def test_reorder_computation_append_on_root_drop(browser):
    browser.set_sheets([("1", "1 - a"), ("2", "2 - b"), ("3", "3 - c")])
    got = []
    browser.sheetOrderChanged.connect(got.append)
    browser._on_sheet_dropped("1", "")      # no target row → append
    assert got == [["2", "3", "1"]]


def test_reorder_noop_emits_nothing(browser):
    browser.set_sheets([("1", "1 - a"), ("2", "2 - b")])
    got = []
    browser.sheetOrderChanged.connect(got.append)
    browser._on_sheet_dropped("2", "")      # 2 is already last
    assert got == []


def test_sheet_mime_payload(browser):
    browser.set_sheets([("FP-1.0", "FP-1.0 - A")])
    mime = browser._tree.mimeData([browser._paper_root.child(0)])
    assert mime.hasFormat("application/x-firepro3d-sheet")
    raw = bytes(mime.data("application/x-firepro3d-sheet")).decode("utf-8")
    assert raw == "FP-1.0"


def test_placed_views_italicize_in_place(browser):
    from firepro3d.level_manager import LevelManager
    lm = LevelManager()
    browser.set_level_manager(lm)           # populates Plans from real levels
    plans = browser._plans_root
    assert plans.childCount() >= 1
    name = plans.child(0).data(0, _ROLE_NAME)
    browser.set_placed_views({("plan", f"Plan: {name}")})
    assert plans.child(0).font(0).italic() is True
    browser.set_placed_views(set())
    assert plans.child(0).font(0).italic() is False


def test_placed_views_cover_elevations(browser):
    elev = browser._elev_root
    browser.set_placed_views({("elevation", "North")})
    fonts = {elev.child(i).data(0, _ROLE_NAME): elev.child(i).font(0).italic()
             for i in range(elev.childCount())}
    assert fonts["North"] is True and fonts["South"] is False
