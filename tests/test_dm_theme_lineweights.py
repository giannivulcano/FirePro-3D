"""DM chrome revision, Line Weights tab (AC4): table look + house glyph buttons."""
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QToolButton

from firepro3d.theme import detect
from tests._dm_theme_helpers import dispose_dm, mw, open_dm, table_px  # noqa: F401

_LEFT = Qt.MouseButton.LeftButton


def test_line_weights_table_look_and_glyph_buttons_act(mw):
    dlg = open_dm(mw)
    try:
        dlg._tabs.setCurrentIndex(2)
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        tbl = dlg._lw_table
        assert table_px(tbl) == detect().table.lower()
        row0 = tbl.visualItemRect(tbl.item(0, 0))
        vp = tbl.viewport()
        assert vp.grab().toImage().pixelColor(vp.width() - 5, row0.bottom()).name() == detect().line.lower()
        add, rem = dlg._lw_add_btn, dlg._lw_remove_btn
        assert isinstance(add, QToolButton) and add.property("glyph") is True
        assert isinstance(rem, QToolButton) and rem.property("glyph") is True
        n = len(dlg._lw_defs)
        QTest.mouseClick(add, _LEFT)                    # real click path -> _on_lw_add
        assert len(dlg._lw_defs) == n + 1
    finally:
        dispose_dm(dlg)
