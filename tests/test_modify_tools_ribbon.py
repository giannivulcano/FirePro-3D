"""D1: Block Editor page carries Edit + Modify groups acting on the editor scene.

Governing spec: docs/specs/scene-tools.md D1 (surface) / D3 (select-first).
"""
from __future__ import annotations

import json
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QToolButton

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
_main_module.View3D = View3D
from firepro3d import snap_engine
from main import MainWindow


@pytest.fixture(scope="module")
def _main_window_singleton(qapp, tmp_path_factory):
    """Module-scoped MainWindow (same pattern as test_ribbon_contextual.py).

    The autosave path is redirected to a temp dir so a real recovery file on
    this machine can't pop the modal "Recover Unsaved Work" dialog when a test
    pumps events (``_check_recovery`` runs on a 500 ms single-shot).
    """
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
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
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


@pytest.fixture
def main_window(_main_window_singleton):
    """Per-test view of the shared MainWindow."""
    yield _main_window_singleton


def _buttons(page):
    return {b.text().replace("\n", " "): b for b in page.findChildren(QToolButton)}


def test_modify_group_builder_has_four_tools(main_window):
    from firepro3d.ribbon_bar import RibbonPage
    page = RibbonPage()
    main_window.build_modify_group(page, main_window._active_scene)
    names = set(_buttons(page))
    assert {"Move", "Rotate", "Offset", "Array"} <= names


def test_edit_group_buttons_route_to_scene_getter(main_window, monkeypatch):
    from firepro3d.ribbon_bar import RibbonPage

    class _Ctl:
        def __init__(self): self.calls = []
        def start(self, tool): self.calls.append(tool); return True

    class _FakeScene:
        def __init__(self): self._modify_ctl = _Ctl()
        def delete_selected_items(self): self._modify_ctl.calls.append("delete")

    fake = _FakeScene()
    page = RibbonPage()
    main_window.build_edit_group(page, lambda: fake)
    b = _buttons(page)
    for label, tool in (("Copy", "copy"), ("Cut", "cut"), ("Paste", "paste"),
                        ("Duplicate", "duplicate"), ("Delete", "delete")):
        b[label].click()
    assert fake._modify_ctl.calls == ["copy", "cut", "paste", "duplicate", "delete"]  # [RED]


def test_tooltips_show_shift_keys(main_window):
    from firepro3d.ribbon_bar import RibbonPage
    page = RibbonPage()
    main_window.build_modify_group(page, main_window._active_scene)
    main_window.build_edit_group(page, main_window._active_scene)
    b = _buttons(page)
    for label, key in (("Move", "Shift+M"), ("Rotate", "Shift+R"),
                       ("Offset", "Shift+O"), ("Array", "Shift+A"),
                       ("Copy", "Shift+C"), ("Cut", "Shift+X"),
                       ("Paste", "Shift+V"), ("Duplicate", "Shift+D")):
        assert key in b[label].toolTip(), label
    assert b["Delete"].toolTip()


def _group_title(b):
    from firepro3d.ribbon_bar import RibbonGroup, _VLabel
    w = b
    while w is not None and not isinstance(w, RibbonGroup):
        w = w.parentWidget()
    assert w is not None, "button not inside a RibbonGroup"
    return w.findChild(_VLabel).text()


def test_block_editor_page_edit_modify_end_to_end(main_window, qapp):
    """Real path: open the Block Editor; its page carries Edit + Modify; the
    selection-needing buttons follow the editor scene's selection; clicking
    Move with a selected line enters "move" on the EDITOR scene (not plan)."""
    from firepro3d.geometry_2d import LineItem
    main_window.scene.clearSelection()
    main_window._open_block_editor()
    qapp.processEvents()
    ed = main_window._active_editor_widget()
    try:
        assert ed is not None
        btns = main_window._be_modify_buttons
        edit = {"Copy", "Cut", "Paste", "Duplicate", "Delete"}
        modify = {"Move", "Rotate", "Offset", "Array"}
        assert set(btns) == edit | modify
        for label, b in btns.items():
            assert _group_title(b) == ("EDIT" if label in edit else "MODIFY"), label
            assert b.toolTip(), label
            assert not b.icon().isNull(), label

        editor = main_window._active_scene()
        assert editor is ed.editor_scene and editor is not main_window.scene
        editor.clearSelection()
        qapp.processEvents()
        for label in ("Copy", "Cut", "Duplicate", "Delete", "Move", "Rotate", "Array"):
            assert not btns[label].isEnabled(), label
        # Paste follows the clipboard payload (D5 / I1), refreshed on change.
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText("")
        qapp.processEvents()
        assert not btns["Paste"].isEnabled()
        QApplication.clipboard().setText(json.dumps(
            {"fp3d_clipboard": 1, "base": [0, 0], "scene_role": "block_editor",
             "items": [LineItem(QPointF(0, 0), QPointF(1, 0)).to_dict()]}))
        qapp.processEvents()
        assert btns["Paste"].isEnabled()
        assert btns["Offset"].isEnabled()

        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        editor.addItem(line)
        line.setSelected(True)
        qapp.processEvents()
        assert btns["Move"].isEnabled()             # [RED]
        btns["Move"].click()
        assert editor.mode == "move"
        assert main_window.scene.mode != "move"
        editor.set_mode(None)
    finally:
        if ed is not None:
            ed._modified = False
            main_window.block_editor_manager.close(ed)
            qapp.processEvents()
