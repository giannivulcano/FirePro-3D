"""BlockOpenDialog — the Block Editor tab's Open… picker (block-system.md).

Runs under the LIVE app QSS + font, against a real ``Model_Space`` holding one
project definition and a temp block library holding one library-only block
(written with the same ``block_library.save_to_library`` the Manager uses).
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem


@pytest.fixture()
def live_env(qapp):
    from firepro3d import theme as th
    prev_qss = qapp.styleSheet()
    prev_font = qapp.font()
    th.apply_app_font(qapp)
    qapp.setStyleSheet(th.build_app_qss(th.detect()))
    yield th
    qapp.setStyleSheet(prev_qss)
    qapp.setFont(prev_font)


def _defn(name, library="Lib", series="Ser"):
    prims = [LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict()]
    return BlockDefinition.new(name=name, library=library, series=series,
                               primitives=prims, origin=(0.0, 0.0))


@pytest.fixture()
def env(qapp, live_env, tmp_path):
    from firepro3d import block_library
    from firepro3d.model_space import Model_Space
    scene = Model_Space()
    proj = _defn("Riser Detail", "ProjLib", "ProjSer")
    scene.register_block_definition(proj)
    # The project block also lives in the library: it must list ONCE, as project.
    block_library.save_to_library(proj, root=str(tmp_path))
    lib_only = _defn("Valve Tag", "Standard", "Valves")
    block_library.save_to_library(lib_only, root=str(tmp_path))
    yield scene, proj, lib_only, str(tmp_path)


def _dialog(env):
    from firepro3d.block_open_dialog import BlockOpenDialog
    scene, _proj, _lib, root = env
    dlg = BlockOpenDialog(scene, None, root=root)
    dlg.show()
    QTest.qWaitForWindowExposed(dlg)
    return dlg


def _tree_shape(item):
    return (item.text(0), [_tree_shape(item.child(i)) for i in range(item.childCount())])


def _roots(dlg):
    t = dlg._tree
    return [t.topLevelItem(i) for i in range(t.topLevelItemCount())]


def _find_leaf(dlg, name):
    stack = list(_roots(dlg))
    while stack:
        it = stack.pop()
        if it.childCount() == 0 and it.text(0) == name:
            return it
        stack.extend(it.child(i) for i in range(it.childCount()))
    raise AssertionError(name)


def _visible_leaves(dlg):
    out = []
    stack = list(_roots(dlg))
    while stack:
        it = stack.pop()
        if it.isHidden():
            continue
        if it.childCount() == 0:
            out.append(it.text(0))
        stack.extend(it.child(i) for i in range(it.childCount()))
    return sorted(out)


def test_tree_lists_project_then_library_series(env):
    dlg = _dialog(env)
    try:
        shape = [_tree_shape(r) for r in _roots(dlg)]
        assert shape == [
            ("Project", [("Riser Detail", [])]),
            ("Library", [("Standard", [("Valves", [("Valve Tag", [])])])]),
        ]
    finally:
        dlg.close()


def test_search_hides_non_matching_leaves_and_empty_folders(env):
    dlg = _dialog(env)
    try:
        QTest.keyClicks(dlg._search, "valve")
        assert _visible_leaves(dlg) == ["Valve Tag"]
        project_root = _roots(dlg)[0]
        assert project_root.text(0) == "Project" and project_root.isHidden()
        assert not _roots(dlg)[1].isHidden()
        dlg._search.clear()
        assert _visible_leaves(dlg) == ["Riser Detail", "Valve Tag"]
        QTest.keyClicks(dlg._search, "zzz-nothing")
        assert _visible_leaves(dlg) == []
        assert all(r.isHidden() for r in _roots(dlg))
    finally:
        dlg.close()


def test_open_library_only_block_loads_it_into_the_project(env):
    scene, _proj, lib_only, _root = env
    dlg = _dialog(env)
    try:
        assert lib_only.id not in scene._block_definitions
        dlg._tree.setCurrentItem(_find_leaf(dlg, "Valve Tag"))
        QTest.mouseClick(dlg._open_btn, Qt.MouseButton.LeftButton)
        assert dlg.result() == dlg.DialogCode.Accepted
        assert dlg.chosen_id() == lib_only.id
        assert lib_only.id in scene._block_definitions
        assert scene._block_definitions[lib_only.id].name == "Valve Tag"
    finally:
        dlg.close()


def test_open_disabled_until_leaf_and_double_click_accepts(env):
    _scene, proj, _lib, _root = env
    dlg = _dialog(env)
    try:
        assert not dlg._open_btn.isEnabled()
        dlg._tree.setCurrentItem(_roots(dlg)[0])          # a folder row
        assert not dlg._open_btn.isEnabled()
        leaf = _find_leaf(dlg, "Riser Detail")
        dlg._tree.setCurrentItem(leaf)
        assert dlg._open_btn.isEnabled()
        rect = dlg._tree.visualItemRect(leaf)
        # A real double-click is press/release then DblClick/release; QTest's
        # mouseDClick alone skips the press the item view keys activation on.
        vp = dlg._tree.viewport()
        QTest.mouseClick(vp, Qt.MouseButton.LeftButton, pos=rect.center())
        QTest.mouseDClick(vp, Qt.MouseButton.LeftButton, pos=rect.center())
        assert dlg.result() == dlg.DialogCode.Accepted
        assert dlg.chosen_id() == proj.id
    finally:
        dlg.close()


# ── empty state (review Minor 2) ─────────────────────────────────────────────

def _assert_empty_shown(dlg, text):
    from firepro3d import theme as th
    from firepro3d.block_open_dialog import BlockOpenDialog  # noqa: F401
    lbl = dlg._empty_lbl
    assert lbl.isVisible() and not dlg._tree.isVisible()
    assert lbl.text() == text
    assert lbl.font().pointSizeF() == th.M.BLOCK_OPEN_EMPTY_PT
    assert lbl.palette().color(lbl.foregroundRole()).name().lower() == \
        th.detect().muted.lower()


def test_empty_state_when_there_are_no_blocks(qapp, live_env, tmp_path):
    from firepro3d.block_open_dialog import BlockOpenDialog, EMPTY_NO_BLOCKS
    from firepro3d.model_space import Model_Space
    dlg = BlockOpenDialog(Model_Space(), None, root=str(tmp_path / "empty_lib"))
    dlg.show()
    QTest.qWaitForWindowExposed(dlg)
    try:
        _assert_empty_shown(dlg, EMPTY_NO_BLOCKS)
        assert not dlg._open_btn.isEnabled()
    finally:
        dlg.close()


def test_empty_state_when_search_matches_nothing(env):
    from firepro3d.block_open_dialog import EMPTY_NO_MATCH
    dlg = _dialog(env)
    try:
        assert dlg._tree.isVisible() and not dlg._empty_lbl.isVisible()
        QTest.keyClicks(dlg._search, "zzz-nothing")
        _assert_empty_shown(dlg, EMPTY_NO_MATCH)
        dlg._search.clear()
        assert dlg._tree.isVisible() and not dlg._empty_lbl.isVisible()
    finally:
        dlg.close()


# ── failed library load (review Minor 3c) ────────────────────────────────────

def test_failed_library_load_does_not_accept(env, monkeypatch):
    from firepro3d.blocks_browser import _ROLE_PATH
    scene, _proj, lib_only, _root = env
    msgs = []
    monkeypatch.setattr("firepro3d.themed_message.themed_info",
                        lambda parent, title, text: msgs.append((parent, title, text)))
    dlg = _dialog(env)
    try:
        leaf = _find_leaf(dlg, "Valve Tag")
        with open(leaf.data(0, _ROLE_PATH), "w", encoding="utf-8") as fh:
            fh.write("{ not json")                       # corrupt .fpdb
        dlg._tree.setCurrentItem(leaf)
        QTest.mouseClick(dlg._open_btn, Qt.MouseButton.LeftButton)
        assert dlg.result() != dlg.DialogCode.Accepted
        assert dlg.isVisible()
        assert dlg.chosen_id() is None
        assert lib_only.id not in scene._block_definitions
        assert len(msgs) == 1 and msgs[0][0] is dlg and msgs[0][1] == "Load block"
        assert "Valve Tag" in msgs[0][2]
    finally:
        dlg.close()
