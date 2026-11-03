"""SB4d P4 probe (d): the paper drop path and the browser drag flag the
one-sheet rule (D4) hooks into, pinned on shipped code before it is changed."""
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtWidgets import QDialog

from firepro3d.paper_space import SheetViewPropertiesDialog
from firepro3d.project_browser import ProjectBrowser
from tests._sb4d_helpers import (add_sheet, dispose, drop_leaf, find_leaf,
                                 paper_view, plan_scene)


def test_p4_a_browser_detail_drop_reaches_dropevent_before_its_dialog(qapp, monkeypatch):
    """A real QDropEvent built from the browser leaf's own mimeData reaches
    PaperGraphicsView.dropEvent and decodes to the properties dialog -- the
    refusal must sit before that dialog. A cancelled dialog places nothing."""
    ms, sec, det, tabs = plan_scene()
    try:
        det.create_detail("Detail 1", QRectF(0.0, 0.0, 4000.0, 3000.0))
        browser = ProjectBrowser()
        browser.refresh_details(det.detail_names)
        sheet = add_sheet(ms, "FP-1.0")
        view, _ps = paper_view(ms, sec, det, sheet)
        seen = []

        def _exec(dlg):
            seen.append(dlg)
            return QDialog.DialogCode.Rejected
        monkeypatch.setattr(SheetViewPropertiesDialog, "exec", _exec)
        drop_leaf(view, browser, "detail", "Detail 1")
        assert len(seen) == 1
        assert sheet.sheet_views == []
    finally:
        dispose(ms, sec, tabs)


def test_p4_b_clearing_the_leaf_drag_flag_reaches_the_tree_model(qapp):
    """QAbstractItemView.startDrag only drags indexes whose model flags carry
    ItemIsDragEnabled; a QTreeWidgetItem flag edit is what the model reports."""
    browser = ProjectBrowser()
    browser.refresh_details(["Detail 1"])
    leaf = find_leaf(browser, "detail", "Detail 1")
    idx = browser._tree.indexFromItem(leaf)
    assert browser._tree.model().flags(idx) & Qt.ItemFlag.ItemIsDragEnabled
    leaf.setFlags(leaf.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
    assert not (browser._tree.model().flags(idx) & Qt.ItemFlag.ItemIsDragEnabled)
