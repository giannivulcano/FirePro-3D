"""LT4 A9: ribbon Linetype toggle follows panel, ribbon and undo (real MainWindow).

Runs in its OWN pytest process: the imported module-scoped ``mw`` fixture builds
a second MainWindow (a known chunk-crash point when combined with other files).
"""
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

from tests.test_block_editor_ribbon_tab import PAGE, _buttons, _group, _page, mw  # noqa: F401


def test_linetype_button_toggles_and_follows_panel_and_undo(mw, qapp):
    w = mw.block_editor_manager.open_new()
    qapp.processEvents()
    try:
        btns = _buttons(_group(_page(mw, PAGE), "Definition"))
        lt, tile = btns["Linetype"], btns["Pattern Tile"]
        assert lt.isCheckable() and "linetype" in lt.toolTip().lower()
        QTest.mouseClick(lt, Qt.MouseButton.LeftButton)
        qapp.processEvents()
        assert w.editor_scene.block_repeat is not None and lt.isChecked()
        assert not tile.isChecked()
        w.editor_scene.undo()
        qapp.processEvents()
        assert w.editor_scene.block_repeat is None and not lt.isChecked()
        w.toggle_capability("repeat")                      # the panel path
        qapp.processEvents()
        assert lt.isChecked()
        QTest.mouseClick(tile, Qt.MouseButton.LeftButton)  # refused: exclusive
        qapp.processEvents()
        assert not tile.isChecked() and w.editor_scene.block_tile is None
    finally:
        mw.block_editor_manager.close(w)
        qapp.processEvents()
