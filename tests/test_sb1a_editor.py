"""SB1a: Block Editor authoring (S4; A6, A7, AC6, AC7, AC9)."""
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QTabWidget

from firepro3d.block_attributes import normalise_attr
from firepro3d.block_editor import BlockEditorManager
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _text(text, **kw):
    d = {"type": "text", "text": text, "x": 0.0, "y": 0.0, "height_mm": 5.0}
    d.update(kw)
    return d


def _attr(key, **kw):
    return normalise_attr({"key": key, **kw})


def _line():
    return LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict()


def _editor(project=None):
    project = project or Model_Space()
    mgr = BlockEditorManager(QTabWidget(), project)
    return project, mgr.open_new()


def test_meta_round_trips_commit_and_undo(qapp):
    project, w = _editor()
    w.seed_from_dicts([_line(), _text("@[Mark]")])
    sc = w.editor_scene
    assert sc.block_meta == {"attributes": [], "host_category": "", "scale_mode": "real_size"}
    sc.set_block_meta({"attributes": [_attr("Mark", default="A1")],
                       "host_category": "Rooms", "scale_mode": "annotative"})
    sc.undo()
    assert sc.block_meta["attributes"] == []
    sc.redo()
    assert sc.block_meta["attributes"] == [_attr("Mark", default="A1")]
    defn = w.commit_block("B", "L", "S")
    assert defn.attributes == [_attr("Mark", default="A1")]
    assert defn.host_category == "Rooms" and defn.scale_mode == "annotative"
    # re-open seeds the meta back
    mgr2 = BlockEditorManager(QTabWidget(), project)
    w2 = mgr2.open_for_definition(defn.id)
    w2.seed_from_definition(defn)
    assert w2.editor_scene.block_meta["attributes"] == [_attr("Mark", default="A1")]
    assert w2.editor_scene.block_meta["scale_mode"] == "annotative"


def test_edit_commit_rebuilds_placed_and_nesting_instances(qapp):
    """The child ``attributes`` setter has no cascade of its own: the commit's
    set_primitives + registry invalidate make placed instances re-resolve."""
    project, w = _editor()
    w.seed_from_dicts([_line(), _text("@[Mark]")])
    w.editor_scene.set_block_meta({"attributes": [_attr("Mark", default="A1")]})
    defn = w.commit_block("B", "L", "S")
    inst = project.place_block_instance(defn.id, (0.0, 0.0), rotation=0.0)
    parent = project.commit_block_definition(
        block_id=None, name="P", library="L", series="S", origin=(0.0, 0.0),
        primitives=[{"type": "block_instance", "block_id": defn.id, "pos": [0.0, 0.0]}],
        place_instance=False)
    assert [a["key"] for a in parent.effective_attributes()] == ["Mark"]
    w.editor_scene.set_block_meta({"attributes": [_attr("Mark", default="A1"),
                                                  _attr("Area", default="9")]})
    w.commit_block("B", "L", "S")
    assert [a["key"] for a in defn.attributes] == ["Mark", "Area"]
    assert [a["key"] for a in parent.effective_attributes()] == ["Mark", "Area"]


def test_block_view_rows(qapp):
    project, w = _editor()
    w.seed_from_dicts([_line()])
    from firepro3d.block_properties_info import BlockPropertiesInfo
    info = BlockPropertiesInfo(w.editor_scene, "B", editor=w)
    props = info.get_properties()
    assert props["Attributes"]["type"] == "header"
    assert props["Count"]["value"] == "0"
    assert props["Edit attributes"]["type"] == "button"
    assert props["Host category"] == {"type": "string", "value": ""}
    assert props["Scale mode"]["type"] == "enum" and props["Scale mode"]["value"] == "Real size"
    info.set_property("Scale mode", "Annotative")
    info.set_property("Host category", "Rooms")
    assert w.editor_scene.block_meta["scale_mode"] == "annotative"
    assert w.editor_scene.block_meta["host_category"] == "Rooms"


def test_block_view_rows_absent_for_schematic(qapp):
    from firepro3d.block_properties_info import BlockPropertiesInfo
    project = Model_Space()
    w = BlockEditorManager(QTabWidget(), project).open_new(kind="schematic")
    w.seed_from_dicts([_line()])
    props = BlockPropertiesInfo(w.editor_scene, "S", editor=w).get_properties()
    for k in ("Attributes", "Count", "Edit attributes", "Host category", "Scale mode"):
        assert k not in props


def test_rename_cascades_and_delete_refused(qapp):
    from firepro3d.block_attributes_editor import AttributesEditorDialog
    from firepro3d.text_item import TextItem
    project, w = _editor()
    w.seed_from_dicts([_line(), _text("@[Mark]-@[Mark]"), _text("@[Other]")])
    sc = w.editor_scene
    sc.set_block_meta({"attributes": [_attr("Mark"), _attr("Other"), _attr("Unused")]})
    dlg = AttributesEditorDialog(w)
    assert dlg.table.rowCount() == 3
    dlg.set_cell(0, "key", "Tag")              # rename Mark -> Tag
    dlg.remove_row(2)                           # Unused: not referenced -> allowed
    n = len(sc._undo_stack)
    assert dlg.try_accept() is True
    texts = sorted(t._data.text for t in sc.items() if isinstance(t, TextItem))
    assert texts == ["@[Other]", "@[Tag]-@[Tag]"]
    assert [a["key"] for a in sc.block_meta["attributes"]] == ["Tag", "Other"]
    assert len(sc._undo_stack) == n + 1         # one editor undo step
    # that one step undoes both the meta and the text rewrite
    sc.undo()
    assert [a["key"] for a in sc.block_meta["attributes"]] == ["Mark", "Other", "Unused"]
    assert sorted(t._data.text for t in sc.items() if isinstance(t, TextItem)) == \
        ["@[Mark]-@[Mark]", "@[Other]"]
    sc.redo()
    # delete of a referenced key is refused
    dlg2 = AttributesEditorDialog(w)
    dlg2.remove_row(1)                          # Other -- referenced by one text
    assert dlg2.try_accept() is False
    assert "used by 1 text field" in dlg2.message()
    assert [a["key"] for a in sc.block_meta["attributes"]] == ["Tag", "Other"]
    # duplicate / empty key refused inline
    dlg3 = AttributesEditorDialog(w)
    dlg3.add_row()
    dlg3.set_cell(2, "key", "Tag")
    assert dlg3.try_accept() is False and "duplicate" in dlg3.message().lower()
    dlg3.set_cell(2, "key", "")
    assert dlg3.try_accept() is False and "empty" in dlg3.message()


def test_reorder_rows(qapp):
    from firepro3d.block_attributes_editor import AttributesEditorDialog
    project, w = _editor()
    w.seed_from_dicts([_line()])
    sc = w.editor_scene
    sc.set_block_meta({"attributes": [_attr("A"), _attr("B")]})
    dlg = AttributesEditorDialog(w)
    dlg.table.setCurrentCell(0, 0)
    dlg._move(1)
    assert dlg.try_accept() is True
    assert [a["key"] for a in sc.block_meta["attributes"]] == ["B", "A"]
