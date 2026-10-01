"""Project Browser 3D Model leaf (view-3d.md I3; project-browser.md)."""
from __future__ import annotations

from PyQt6.QtCore import Qt


def _browser(qapp):
    from firepro3d.project_browser import ProjectBrowser
    from firepro3d.level_manager import LevelManager
    return ProjectBrowser(level_manager=LevelManager())


def test_3d_leaf_is_first_top_level_item(qapp):
    from firepro3d.project_browser import _ROLE_TYPE
    b = _browser(qapp)
    top = b._tree.topLevelItem(0)
    assert top.text(0) == "3D Model"
    assert top.data(0, _ROLE_TYPE) == "view3d"
    assert b._tree.topLevelItem(1).text(0) == "2D Model"
    assert top.childCount() == 0


def test_activating_3d_leaf_emits_activate3DView(qapp):
    b = _browser(qapp)
    got = []
    ms = []
    b.activate3DView.connect(lambda: got.append(1))
    b.activateModelSpace.connect(lambda: ms.append(1))
    b._on_item_activated(b._tree.topLevelItem(0), 0)
    assert got == [1]
    assert ms == []          # must not also route to the 2D Model


def test_3d_leaf_context_menu_open_emits_activate3DView(qapp, monkeypatch):
    from PyQt6.QtWidgets import QMenu
    b = _browser(qapp)
    b.resize(300, 400)
    b.show()
    qapp.processEvents()
    top = b._tree.topLevelItem(0)
    pos = b._tree.visualItemRect(top).center()
    assert b._tree.itemAt(pos) is top
    labels = []

    def _fake_exec(menu, *_a, **_k):
        acts = [a for a in menu.actions() if not a.isSeparator()]
        labels.extend(a.text() for a in acts)
        for a in acts:
            if a.text() == "Open":
                a.trigger()
        return None

    monkeypatch.setattr(QMenu, "exec", _fake_exec)
    got = []
    b.activate3DView.connect(lambda *a: got.append(1))
    b._on_context_menu(pos)
    b.close()
    assert labels == ["Open"]
    assert got == [1]


def test_3d_leaf_is_not_a_drag_payload(qapp):
    b = _browser(qapp)
    top = b._tree.topLevelItem(0)
    assert top.text(0) == "3D Model"
    assert not (top.flags() & Qt.ItemFlag.ItemIsDragEnabled)
    assert not b._tree.mimeData([top]).formats()
