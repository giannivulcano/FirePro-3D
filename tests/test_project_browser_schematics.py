"""SV1 Task 4 -- Project Browser Schematics root (D-S4, D-S16; G6 widget half)."""
from PyQt6.QtCore import QPoint

from firepro3d.mime_types import MIME_VIEW
from firepro3d.project_browser import _ROLE_NAME, _ROLE_TYPE, ProjectBrowser


def _rows():
    return [("id1", "Riser A", ""), ("id2", "Hanger", "Typicals"),
            ("id3", "Trim", "Typicals")]


def _leaf(pb, block_id):
    stack = [pb._schem_root]
    while stack:
        it = stack.pop()
        if it.data(0, _ROLE_TYPE) == "schematic" and it.data(0, _ROLE_NAME) == block_id:
            return it
        stack.extend(it.child(i) for i in range(it.childCount()))
    return None


def test_root_has_its_own_role_and_no_stub(qapp):
    pb = ProjectBrowser()
    assert pb._schem_root.data(0, _ROLE_TYPE) == "schematic_root"
    assert "Schematics" not in pb._MS_STUBS
    hits = []
    pb.activateModelSpace.connect(lambda: hits.append(1))
    pb._on_item_activated(pb._schem_root, 0)
    assert hits == []                       # no longer routes to the plan


def test_refresh_schematics_builds_series_and_leaves(qapp):
    pb = ProjectBrowser()
    pb.refresh_schematics(_rows())
    root = pb._schem_root
    texts = [root.child(i).text(0) for i in range(root.childCount())]
    assert texts == ["Typicals", "Riser A"]  # series first, then loose leaves
    series = root.child(0)
    assert series.data(0, _ROLE_TYPE) == "schematic_series"
    assert [series.child(i).text(0) for i in range(series.childCount())] == \
        ["Hanger", "Trim"]
    assert _leaf(pb, "id1").text(0) == "Riser A"
    pb.refresh_schematics([("id1", "Riser B", "")])
    assert root.childCount() == 1 and root.child(0).text(0) == "Riser B"


def test_leaf_activation_emits_id(qapp):
    pb = ProjectBrowser()
    pb.refresh_schematics(_rows())
    got = []
    pb.activateSchematic.connect(got.append)
    pb._on_item_activated(_leaf(pb, "id2"), 0)
    assert got == ["id2"]


def test_leaf_drag_emits_schematic_view_payload(qapp):
    import json
    from PyQt6.QtCore import Qt
    pb = ProjectBrowser()
    pb.refresh_schematics(_rows())
    leaf = _leaf(pb, "id2")                            # under a Series row
    assert leaf.flags() & Qt.ItemFlag.ItemIsDragEnabled
    mime = pb._tree.mimeData([leaf])
    payload = json.loads(bytes(mime.data(MIME_VIEW)).decode("utf-8"))
    assert payload == {"view_type": "schematic", "view_name": "id2"}
    series = pb._schem_root.child(0)
    assert not (series.flags() & Qt.ItemFlag.ItemIsDragEnabled)


def test_placed_italics_follow_set_placed_views_and_survive_refresh(qapp):
    pb = ProjectBrowser()
    pb.refresh_schematics(_rows())
    pb.set_placed_views({("schematic", "id2")})
    assert _leaf(pb, "id2").font(0).italic()
    assert not _leaf(pb, "id1").font(0).italic()
    pb.refresh_schematics(_rows())                     # rebuild keeps italics
    assert _leaf(pb, "id2").font(0).italic()
    pb.set_placed_views(set())
    assert not _leaf(pb, "id2").font(0).italic()


def test_context_menu_actions(qapp, monkeypatch):
    from PyQt6.QtWidgets import QMenu
    pb = ProjectBrowser()
    pb.refresh_schematics(_rows())
    captured = []
    monkeypatch.setattr(QMenu, "exec",
                        lambda self, *a: captured.append(
                            [x.text() for x in self.actions()]))
    for item in (pb._schem_root, _leaf(pb, "id1")):
        monkeypatch.setattr(pb._tree, "itemAt", lambda pos, it=item: it)
        pb._on_context_menu(QPoint(0, 0))
    assert captured == [["New Schematic…"], ["Open", "Rename…", "Delete"]]


def test_menu_signals(qapp):
    pb = ProjectBrowser()
    got = []
    pb.createSchematic.connect(lambda: got.append("new"))
    pb.renameSchematic.connect(lambda i: got.append(("ren", i)))
    pb.deleteSchematic.connect(lambda i: got.append(("del", i)))
    pb.createSchematic.emit()
    pb.renameSchematic.emit("id1")
    pb.deleteSchematic.emit("id1")
    assert got == ["new", ("ren", "id1"), ("del", "id1")]
