"""SB1b G3 / G7 / G2 browser half -- Blocks browser System tier (D10, D13)."""
import os
import uuid

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d import block_library as bl
from firepro3d.block_definition import BlockDefinition
from firepro3d.blocks_browser import BlocksBrowser, SYSTEM_ROW_TIP
from tests._mainwindow_helpers import dispose_main_window


def _mk_user_library(*libs):
    for lib in libs:
        os.makedirs(os.path.join(bl.block_library_dir(), lib, "Set"))


def _top_texts(b):
    t = b._tree
    return [t.topLevelItem(i).text(0) for i in range(t.topLevelItemCount())]


def _system_leaf(b, name="Diagonal"):
    lib = b._tree.topLevelItem(0)
    ser = lib.child(0)
    return next(ser.child(i) for i in range(ser.childCount())
                if ser.child(i).text(0) == name)


def test_g7_shown_browser_pins_system_with_padlock(
        model_space, qapp, real_system_library):
    _mk_user_library("Beta", "Alpha")
    b = BlocksBrowser(model_space)
    b.show()
    assert QTest.qWaitForWindowExposed(b)
    assert _top_texts(b) == ["System", "", "Alpha", "Beta"]   # "" = separator
    sys_row = b._tree.topLevelItem(0)
    assert not sys_row.icon(0).isNull()
    assert sys_row.toolTip(0) == SYSTEM_ROW_TIP
    assert _system_leaf(b).toolTip(0) == SYSTEM_ROW_TIP
    assert b._tree.topLevelItem(2).toolTip(0) == ""            # user rows: none
    sep = b._tree.topLevelItem(1)
    assert not (sep.flags() & Qt.ItemFlag.ItemIsSelectable)
    assert b._tree.itemWidget(sep, 0) is not None              # the drawn rule
    b.close()


def test_g7_no_system_row_without_system_blocks(model_space, qapp):
    _mk_user_library("Alpha")
    b = BlocksBrowser(model_space)
    assert _top_texts(b) == ["Alpha"]                          # no separator


def test_g7_refresh_keeps_collapsed_state_across_separator(
        model_space, qapp, real_system_library):
    _mk_user_library("Alpha")
    b = BlocksBrowser(model_space)
    b._tree.topLevelItem(2).setExpanded(False)                 # Alpha
    b.refresh()
    assert _top_texts(b) == ["System", "", "Alpha"]
    assert not b._tree.topLevelItem(2).isExpanded()
    assert b._tree.topLevelItem(0).isExpanded()


def test_g3_edit_block_on_system_leaf_requests_duplicate(
        model_space, qapp, real_system_library):
    b = BlocksBrowser(model_space)
    got, edits = [], []
    b.duplicateRequested.connect(lambda bid, path: got.append((bid, path)))
    b.editRequested.connect(edits.append)
    menu = b._build_context_menu(_system_leaf(b))
    labels = [a.text() for a in menu.actions()]
    assert labels == ["Edit Block", "Duplicate to library..."]
    menu.actions()[0].trigger()
    assert edits == [] and got[0][0] == "builtin-hatch-diagonal"
    assert "builtin-hatch-diagonal" not in model_space._block_definitions  # not embedded


def test_g3_embedded_system_leaf_still_duplicates(
        model_space, qapp, real_system_library):
    path = os.path.join(real_system_library, "Hatches", "Diagonal.fpdb")
    model_space.load_blocks_from_files([path])
    b = BlocksBrowser(model_space)
    got = []
    b.duplicateRequested.connect(lambda bid, p: got.append(bid))
    b._build_context_menu(_system_leaf(b)).actions()[0].trigger()
    assert got == ["builtin-hatch-diagonal"]


def test_g3_user_leaf_menu_unchanged(model_space, qapp, real_system_library):
    d = BlockDefinition.new(name="Mine", library="Fire", series="Valves",
                            primitives=[{"type": "draw_line", "pt1": [0, 0],
                                         "pt2": [10, 0], "color": "#ffffff",
                                         "lineweight": 1.0}], origin=(0.0, 0.0))
    model_space.register_block_definition(d)
    b = BlocksBrowser(model_space)
    t = b._tree
    fire = next(t.topLevelItem(i) for i in range(t.topLevelItemCount())
                if t.topLevelItem(i).text(0) == "Fire")
    leaf = fire.child(0).child(0)
    assert [a.text() for a in b._build_context_menu(leaf).actions()] == ["Edit Block"]


def _write_copy(src):
    """What run_duplicate_dialog does after OK, minus the dialog (covered by
    tests/test_system_library_duplicate.py)."""
    copy = BlockDefinition.from_dict(src.to_dict())
    copy.id, copy.version, copy.base_version = uuid.uuid4().hex, 1, None
    copy.name, copy.library, copy.series = f"{src.name} copy", "Mine", "Set"
    return bl.save_to_library(copy)


@pytest.fixture(scope="module")
def _main_window_singleton(qapp, tmp_path_factory):
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
        dispose_main_window(win)


def test_g2_main_window_duplicate_opens_the_copy(
        qapp, _main_window_singleton, real_system_library, monkeypatch):
    from firepro3d import block_editor as be
    win = _main_window_singleton
    seen = []

    def _dup(scene, src, parent, **k):
        seen.append(src.id)
        return _write_copy(src)
    monkeypatch.setattr(be, "run_duplicate_dialog", _dup)
    win.blocks_browser.refresh()
    QApplication.processEvents()
    mgr = win.block_editor_manager
    w = None
    try:
        leaf = _system_leaf(win.blocks_browser)
        win.blocks_browser._build_context_menu(leaf).actions()[1].trigger()
        QApplication.processEvents()
        assert seen == ["builtin-hatch-diagonal"]
        w = next(x for x in mgr._open.values()
                 if x._edit_block_id and x._edit_block_id != "builtin-hatch-diagonal")
        defn = win.scene.get_block_definition(w._edit_block_id)
        assert defn.name == "Diagonal copy" and not bl.is_system_block(defn.id)
        assert win.central_tabs.indexOf(w) >= 0
        # the shipped block itself was not loaded into the project
        assert "builtin-hatch-diagonal" not in win.scene._block_definitions
    finally:
        if w is not None:
            w._modified = False
            mgr.close(w)
            win.scene._block_definitions.pop(w._edit_block_id, None)
        win.scene.blockDefinitionsChanged.emit()
        QApplication.processEvents()


def test_g2_main_window_cancelled_duplicate_changes_nothing(
        qapp, _main_window_singleton, real_system_library, monkeypatch):
    from firepro3d import block_editor as be
    win = _main_window_singleton
    monkeypatch.setattr(be, "run_duplicate_dialog", lambda *a, **k: None)
    before = (set(win.scene._block_definitions), dict(win.block_editor_manager._open))
    win.blocks_browser.refresh()
    leaf = _system_leaf(win.blocks_browser)
    win.blocks_browser._build_context_menu(leaf).actions()[1].trigger()
    QApplication.processEvents()
    assert (set(win.scene._block_definitions),
            dict(win.block_editor_manager._open)) == before
