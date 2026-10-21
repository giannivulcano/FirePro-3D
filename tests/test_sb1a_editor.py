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
