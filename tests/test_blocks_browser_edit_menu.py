"""Blocks browser right-click "Edit Block" (HF2): emits editRequested after
making the block a project definition; folders get no menu."""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication

from firepro3d import block_library
from firepro3d.block_definition import BlockDefinition
from firepro3d.blocks_browser import BlocksBrowser, _ROLE_ID


def _def(name="Edit Me", library="Fire", series="Valves"):
    return BlockDefinition.new(name=name, library=library, series=series,
                               primitives=[{"type": "draw_line", "pt1": [0, 0],
                                            "pt2": [10, 0], "color": "#ffffff",
                                            "lineweight": 1.0}],
                               origin=(0.0, 0.0))


def _leaf(browser, block_id):
    def walk(it):
        if it.data(0, _ROLE_ID) == block_id:
            return it
        for i in range(it.childCount()):
            r = walk(it.child(i))
            if r is not None:
                return r
    t = browser._tree
    for i in range(t.topLevelItemCount()):
        r = walk(t.topLevelItem(i))
        if r is not None:
            return r


def test_project_leaf_menu_emits_edit_requested(model_space, qapp, tmp_path):
    d = _def()
    model_space.register_block_definition(d)
    b = BlocksBrowser(model_space, root=str(tmp_path))
    got = []
    b.editRequested.connect(got.append)
    menu = b._build_context_menu(_leaf(b, d.id))
    assert [a.text() for a in menu.actions()] == ["Edit Block"]
    assert menu.actions()[0].statusTip() == "Open this block in a Block Editor tab"
    menu.actions()[0].trigger()
    assert got == [d.id]


def test_folder_rows_have_no_menu(model_space, qapp, tmp_path):
    model_space.register_block_definition(_def())
    b = BlocksBrowser(model_space, root=str(tmp_path))
    lib = b._tree.topLevelItem(0)
    assert b._build_context_menu(lib) is None
    assert b._build_context_menu(lib.child(0)) is None
    assert b._build_context_menu(None) is None


def test_library_only_leaf_is_loaded_then_emits(model_space, qapp, tmp_path):
    d = _def("Lib Only")
    block_library.save_to_library(d, str(tmp_path))
    b = BlocksBrowser(model_space, root=str(tmp_path))
    assert d.id not in model_space._block_definitions
    leaf = _leaf(b, d.id)
    assert leaf is not None
    seen = []
    b.editRequested.connect(
        lambda i: seen.append((i, i in model_space._block_definitions)))
    b._build_context_menu(leaf).actions()[0].trigger()
    assert seen == [(d.id, True)]


@pytest.fixture(scope="module")
def _main_window_singleton(qapp, tmp_path_factory):
    from PyQt6.QtTest import QTest
    import main as _main_module
    from firepro3d.view_3d import View3D
    _main_module.View3D = View3D
    from main import MainWindow
    recovery = str(tmp_path_factory.mktemp("autosave") / "recovery.FPD")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(MainWindow, "_autosave_path", staticmethod(lambda: recovery))
        win = MainWindow()
        win.show()
        QTest.qWaitForWindowExposed(win)
        yield win
        win._modified = False
        win.close()
        win.deleteLater()


def test_main_window_edit_block_opens_editor_tab(qapp, _main_window_singleton):
    win = _main_window_singleton
    d = _def("Tab Me")
    win.scene.register_block_definition(d)
    QApplication.processEvents()
    mgr = win.block_editor_manager
    w = None
    try:
        assert d.id not in mgr._open
        leaf = _leaf(win.blocks_browser, d.id)
        assert leaf is not None
        win.blocks_browser._build_context_menu(leaf).actions()[0].trigger()
        QApplication.processEvents()
        w = mgr._open.get(d.id)
        assert w is not None
        assert win.central_tabs.indexOf(w) >= 0
    finally:
        if w is not None:
            w._modified = False
            mgr.close(w)
        win.scene._block_definitions.pop(d.id, None)
        win.scene.blockDefinitionsChanged.emit()
        QApplication.processEvents()
