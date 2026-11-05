"""SB4d D4 on the real MainWindow wiring (T16 review minors): a viewport
add / undo / redo, a sheet renumber, reorder and delete each reach
``MainWindow._on_paper_modified`` -> the browser's drag flag and the model
marker head's Sheet slot. Drives the shipped paper scene / sheet manager on
a MainWindow built by this module and disposed through dispose_main_window."""
import pytest
from PyQt6.QtCore import QRectF, Qt

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
_main_module.View3D = View3D
from main import MainWindow  # noqa: E402

from firepro3d.paper_space import SheetViewData
from tests._mainwindow_helpers import dispose_main_window
from tests._sb4d_helpers import find_leaf, head_def


@pytest.fixture(scope="module")
def win(qapp):
    w = MainWindow()
    w.show()
    yield w
    dispose_main_window(w)


LONG = "FP-123456789012345678"


def _draggable(w, name):
    leaf = find_leaf(w.project_browser, "detail", name)
    return bool(leaf.flags() & Qt.ItemFlag.ItemIsDragEnabled)


def _sheet_slot(w, marker):
    return marker.bubble.host_values({"Sheet"})["Sheet"].text or ""     # None = an empty slot


def _number_slot(marker):
    return marker.bubble.host_values({"Number"})["Number"].text or ""


def test_viewport_undo_renumber_reorder_delete_reach_the_browser_and_the_head(win, monkeypatch):
    ms = win.scene
    head_def(ms, "Detail", texts=(("Sheet", 2.0), ("Number", -2.0)))
    marker = win.detail_manager.create_detail("Detail 1", QRectF(0.0, 0.0, 4000.0, 3000.0))
    win.project_browser.refresh_details(win.detail_manager.detail_names)
    marker.refresh_heads()
    assert _draggable(win, "Detail 1") and _sheet_slot(win, marker) == ""
    assert _number_slot(marker) == ""

    sheet1 = win._sheet
    ps = win.paper_space_widget.paper_scene
    data = SheetViewData("detail", "Detail 1", "", 0.01, 20.0, 20.0, 100.0, 80.0)
    ps.add_viewport(data)                                      # undoable add -> sheetModified
    assert not _draggable(win, "Detail 1") and _sheet_slot(win, marker) == sheet1.number
    assert _number_slot(marker) == data.view_number != ""
    ps.undo_stack.undo()                                        # T16 minor 1: the flag returns through undo
    assert _draggable(win, "Detail 1") and _sheet_slot(win, marker) == ""
    assert _number_slot(marker) == ""
    ps.undo_stack.redo()
    assert not _draggable(win, "Detail 1") and _sheet_slot(win, marker) == sheet1.number
    assert _number_slot(marker) == data.view_number != ""

    cached = marker.bubble.boundingRect()                       # cache the rect under the old number
    sheet1.number = LONG                                        # T16 minor 2: renumber
    win._on_sheet_meta_changed()
    assert _sheet_slot(win, marker) == LONG
    assert _number_slot(marker) == data.view_number             # a sheet renumber leaves the view's number
    assert marker.bubble.boundingRect() != cached               # the head re-shaped, not just re-read

    win._modified = False
    win._create_sheet()
    sheet2 = win._sheet
    assert sheet2 is not sheet1 and win._modified
    win._modified = False
    win._reorder_sheets([sheet2.number, sheet1.number])         # reorder dirties the project
    assert win._modified and [s.number for s in win.sheet_mgr.sheets][0] == sheet2.number
    assert _sheet_slot(win, marker) == LONG and not _draggable(win, "Detail 1")

    monkeypatch.setattr(_main_module, "themed_confirm", lambda *a, **k: True)
    win._modified = False
    win._delete_sheet(LONG)                                 # the holder goes: the slot empties, the leaf drags again
    assert win._modified
    assert _sheet_slot(win, marker) == "" and _draggable(win, "Detail 1")
    assert _number_slot(marker) == ""
