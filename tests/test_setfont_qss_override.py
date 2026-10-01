"""Widget font sizes survive the app QSS (ui-design-system.md; architecture/theming.md).

Bug (filed 2026-09-30, chrome-polish audit): ``build_app_qss``'s global
``QWidget { font-size }`` beats a widget's ``setFont()`` size — ``ui_kit.Selector``
rendered 13 px instead of ``M.PROP_FIELD_FS`` (11 px) everywhere outside the
property panel's own field QSS, and the sprinkler tables' 8.5 pt dropped to
9.75 pt on the next ``app.setStyleSheet`` (the theme-switch path). The fix sizes
each widget in its OWN QSS, never ``setFont``.

Every guard runs under the real app QSS + app font and re-applies the app QSS
once, then asserts the RENDERED font (``QFontInfo``), not the value the code set.
"""
from __future__ import annotations

import os
import tempfile

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QFontInfo
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QTableWidget


@pytest.fixture()
def live_env(qapp):
    from firepro3d import theme as th
    prev_qss, prev_font = qapp.styleSheet(), qapp.font()
    th.apply_app_font(qapp)
    qapp.setStyleSheet(th.build_app_qss(th.detect()))
    yield th
    qapp.setStyleSheet(prev_qss)
    qapp.setFont(prev_font)


def _reapply_app_qss(th):
    """The theme-switch path: one more ``app.setStyleSheet`` while widgets live."""
    QApplication.instance().setStyleSheet(th.build_app_qss(th.detect()))
    QTest.qWait(30)


def _show(w):
    w.show()
    QTest.qWaitForWindowExposed(w)
    QTest.qWait(30)


def _db():
    from firepro3d.sprinkler_db import SprinklerDatabase
    return SprinklerDatabase(path=os.path.join(tempfile.mkdtemp(), "sprinklers.json"))


def test_selector_in_block_save_dialog_renders_prop_field_size(live_env):
    from firepro3d.block_editor import BlockSaveDialog
    from firepro3d.ui_kit import Selector
    th = live_env
    d = BlockSaveDialog(library_tree={"Lib": ["Series A"]})
    try:
        _show(d)
        _reapply_app_qss(th)
        sels = d.findChildren(Selector)
        assert len(sels) == 2, "precondition: Library + Series selectors"
        assert [QFontInfo(s.font()).pixelSize() for s in sels] == \
            [th.M.PROP_FIELD_FS] * 2
    finally:
        d.close()


def test_bare_selector_renders_prop_field_size(live_env):
    from firepro3d.ui_kit import Selector
    th = live_env
    s = Selector()
    s.addItems(["Alpha", "Beta"])
    try:
        _show(s)
        _reapply_app_qss(th)
        assert QFontInfo(s.font()).pixelSize() == th.M.PROP_FIELD_FS
    finally:
        s.close()


def test_sprinkler_manager_tables_keep_dense_size_after_qss_reapply(live_env):
    from firepro3d.sprinkler_db import SprinklerManagerDialog
    th = live_env
    dlg = SprinklerManagerDialog(_db())
    try:
        _show(dlg)
        _reapply_app_qss(th)
        tables = dlg.findChildren(QTableWidget)
        assert len(tables) == 2, "precondition: both sprinkler tables"
        assert [t.font().pointSizeF() for t in tables] == [th.M.DENSE_TABLE_PT] * 2
    finally:
        dlg.close()


def test_auto_populate_table_keeps_dense_size_after_qss_reapply(live_env):
    from firepro3d.auto_populate_dialog import AutoPopulateDialog
    from firepro3d.room import Room
    th = live_env
    room = Room(boundary=[QPointF(0, 0), QPointF(10000, 0),
                          QPointF(10000, 10000), QPointF(0, 10000)])
    dlg = AutoPopulateDialog(room=room, sprinkler_db=_db())
    try:
        _show(dlg)
        _reapply_app_qss(th)
        assert dlg._spr_table.font().pointSizeF() == th.M.DENSE_TABLE_PT
    finally:
        dlg.close()
