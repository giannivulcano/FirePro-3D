"""LevelDialog chrome (view-relationships section 12.4 Chrome; ui-design-system
HouseDialog consumer; mockup docs/mockups/level-manager-tuner.html, approved 2026-10-30)
under the real house dialog stylesheet."""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (QComboBox, QDialogButtonBox, QFrame, QLabel, QLineEdit,
                             QPushButton, QToolButton)

from firepro3d.level_dialog import LevelDialog
from firepro3d.level_manager import LevelManager
from firepro3d.level_widget import _COL_ELEV, _COL_NUM
from firepro3d.theme import M


def _shown(qapp):
    dlg = LevelDialog(LevelManager())
    dlg.show()
    QTest.qWaitForWindowExposed(dlg)
    qapp.processEvents()
    return dlg


def test_level_dialog_is_a_house_dialog_with_a_close_only_footer(qapp):
    dlg = _shown(qapp)
    try:
        assert dlg.property("houseDialog") is True
        assert dlg._titlebar.objectName() == "shellHeader"
        assert dlg._shell_title_lbl.text() == "Level Manager"
        assert dlg.findChild(QFrame, "dialogBody") is not None
        footer = dlg.findChild(QFrame, "footerBar")
        assert [b.text() for b in footer.findChildren(QPushButton)] == ["Close"]
        assert dlg._footer_box.button(QDialogButtonBox.StandardButton.Cancel) is None
        assert dlg.size() == QSize(*M.LEVEL_DLG_SIZE)
        assert not hasattr(dlg, "populate")                       # the unused forwarder is gone
        assert dlg.findChildren(QComboBox) == []                   # no View Level combo
        assert [l for l in dlg.findChildren(QLabel) if l.text() == "Levels"] == []
        for sig in ("activeLevelChanged", "levelsChanged", "duplicateLevel",
                    "levelRenamed", "levelsRemoved"):
            assert hasattr(dlg, sig)
    finally:
        dlg.close()


def test_level_table_uses_the_mockup_metrics_under_the_house_qss(qapp):
    dlg = _shown(qapp)
    try:
        t = dlg.widget.table
        assert t.objectName() == "levelTable"
        assert t.columnCount() == 3                                # section 12.4 Columns
        assert [t.horizontalHeaderItem(c).text() for c in range(3)] == ["Name", "Number", "Elevation"]
        assert t.horizontalHeader().isSortIndicatorShown() is False  # accent caret only, no native arrow
        assert dlg.minimumSize() == QSize(*M.LEVEL_DLG_MIN)
        assert t.rowHeight(0) == M.LEVEL_ROW_H
        assert t.columnWidth(_COL_NUM) == M.LEVEL_COL_NUMBER_W
        assert t.columnWidth(_COL_ELEV) == M.LEVEL_COL_ELEV_W
        glyphs = [b for b in dlg.findChildren(QToolButton) if b.property("glyph") is True]
        assert [b.toolTip() for b in glyphs] == ["Add level", "Delete level(s)", "Select a single level to duplicate"]
        dlg.widget._select_level("Level 1")                      # one row -> Duplicate becomes available
        assert [b.toolTip() for b in glyphs] == ["Add level", "Delete level(s)", "Duplicate level"]
        assert all(b.size() == QSize(M.GLYPH_BTN_PX, M.GLYPH_BTN_PX) for b in glyphs)
        assert dlg.widget.layout().spacing() == M.LEVEL_TOOLBAR_TOP
        assert dlg._body_outer.contentsMargins().left() == M.DIALOG_BODY_MARGIN[0]
    finally:
        dlg.close()


def test_close_button_accepts(qapp):
    dlg = _shown(qapp)
    footer = dlg.findChild(QFrame, "footerBar")
    footer.findChildren(QPushButton)[0].click()
    assert dlg.result() == dlg.DialogCode.Accepted


def test_enter_in_a_cell_editor_commits_and_delete_only_edits_text(qapp):
    """P1 (the neutral Close is never the default button) + the Delete-key EditingState
    branch, as behaviour: Return in the Name editor renames and leaves the dialog open;
    Delete inside the editor edits the text and deletes no level (probe (n))."""
    from firepro3d.level_widget import _COL_NAME
    dlg = _shown(qapp)
    try:
        lm, w = dlg.widget.manager, dlg.widget
        row = next(r for r in range(w.table.rowCount())
                   if w.table.item(r, _COL_NAME).data(Qt.ItemDataRole.UserRole) == "Level 2")
        w.table.editItem(w.table.item(row, _COL_NAME))
        qapp.processEvents()
        editor = w.table.findChild(QLineEdit)
        editor.selectAll()
        QTest.keyClicks(editor, "Mezz")
        QTest.keyClick(editor, Qt.Key.Key_Delete)
        assert [l.name for l in lm.levels] == ["Level 1", "Level 2", "Level 3"]
        QTest.keyClick(editor, Qt.Key.Key_Return)
        qapp.processEvents()
        assert [l.name for l in lm.levels] == ["Level 1", "Mezz", "Level 3"]
        assert dlg.isVisible() and dlg.result() == 0
    finally:
        dlg.close()
