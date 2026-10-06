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


def _st(b):
    return (b.isEnabled(), b.isChecked())


def test_linetype_button_follows_redo_tab_switch_and_close(mw, qapp):
    """G6 M4 / A9: redo, a two-editor tab switch and editor close."""
    btns = _buttons(_group(_page(mw, PAGE), "Definition"))
    lt, tile = btns["Linetype"], btns["Pattern Tile"]
    mgr = mw.block_editor_manager
    a = mgr.open_new()
    qapp.processEvents()
    b = None
    try:
        assert a.toggle_capability("repeat")
        qapp.processEvents()
        a.editor_scene.undo()
        qapp.processEvents()
        assert _st(lt) == (True, False)
        a.editor_scene.redo()
        qapp.processEvents()
        assert a.editor_scene.block_repeat is not None
        assert _st(lt) == (True, True)
        b = mgr.open_new()
        qapp.processEvents()
        assert _st(lt) == (True, False) and _st(tile) == (True, False)
        assert b.toggle_capability("tile")
        qapp.processEvents()
        assert _st(lt) == (True, False) and _st(tile) == (True, True)
        mw.central_tabs.setCurrentWidget(a)
        qapp.processEvents()
        assert _st(lt) == (True, True) and _st(tile) == (True, False)
        mw.central_tabs.setCurrentWidget(b)
        qapp.processEvents()
        assert _st(lt) == (True, False) and _st(tile) == (True, True)
        mgr.close(b)
        b = None
        qapp.processEvents()
        assert mw.central_tabs.currentWidget() is a
        assert _st(lt) == (True, True) and _st(tile) == (True, False)
        mgr.close(a)
        a = None
        qapp.processEvents()
        assert _st(lt) == (False, False) and _st(tile) == (False, False)
    finally:
        for w in (b, a):
            if w is not None:
                mgr.close(w)
        qapp.processEvents()
