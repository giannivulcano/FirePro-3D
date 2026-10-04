"""LT1-4 -- .fpdb files bundle the weights they use; project wins (guard T4)."""
import json

from firepro3d import block_library
from firepro3d import paper_display as pd
from firepro3d.block_definition import BlockDefinition
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import LineWeightDef
from firepro3d.text_item import TextAnnotationData, TextItem


def _text_def(weight, name="Tag"):
    prim = TextItem(TextAnnotationData(text="X", border=True,
                                       border_weight=weight)).to_dict()
    return BlockDefinition.new(name=name, library="Lib", series="S",
                               primitives=[prim], origin=(0.0, 0.0))


def _project_with(name="X40", mm=0.40):
    pd.set_project_line_weights([*pd.FACTORY_LINE_WEIGHTS, LineWeightDef(name, mm)])


def _other_project(mm=None):
    if mm is None:
        pd.set_project_line_weights(list(pd.FACTORY_LINE_WEIGHTS))
    else:
        _project_with("X40", mm)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_save_writes_used_weights(qapp):
    _project_with()
    rec = _read(block_library.save_to_library(_text_def("X40")))
    assert rec["weights"] == {"X40": 0.40}


def test_load_adds_missing_weight(qapp):
    _project_with()
    path = block_library.save_to_library(_text_def("X40"))
    _other_project()
    Model_Space().load_blocks_from_files([path])
    assert pd.resolve_line_weight_mm("X40") == 0.40


def test_project_value_wins(qapp):
    _project_with()
    path = block_library.save_to_library(_text_def("X40"))
    _other_project(0.30)
    Model_Space().load_blocks_from_files([path])
    assert pd.resolve_line_weight_mm("X40") == 0.30


def test_no_text_no_weights_key(qapp):
    defn = BlockDefinition.new(name="Plain", library="Lib", series="S",
                               primitives=[], origin=(0.0, 0.0))
    rec = _read(block_library.save_to_library(defn))
    assert "weights" not in rec


def test_nested_definition_weights_bundled(qapp):
    _project_with()
    sc = Model_Space()
    inner = _text_def("X40", "Inner")
    outer = BlockDefinition.new(
        name="Outer", library="Lib", series="S", origin=(0.0, 0.0),
        primitives=[{"type": "block_instance", "block_id": inner.id,
                     "pos": [0, 0], "rotation": 0.0}])
    sc.register_block_definition(inner)
    sc.register_block_definition(outer)
    path = block_library.save_to_library(
        outer, bundled=sc.block_registry.bundle_for(outer.id))
    assert _read(path)["weights"] == {"X40": 0.40}


def test_reload_from_library_adds_missing_weight(qapp):
    _project_with()
    defn = _text_def("X40")
    block_library.save_to_library(defn)
    sc = Model_Space()
    sc.register_block_definition(BlockDefinition.from_dict(defn.to_dict()))
    _other_project()
    assert pd.resolve_line_weight_mm("X40") != 0.40
    assert sc.reload_block_definition(defn.id) is True
    assert pd.resolve_line_weight_mm("X40") == 0.40


def test_refused_load_adds_no_weights(qapp, tmp_path):
    _project_with()
    path = block_library.save_to_library(_text_def("X40"))
    _other_project()
    # name clash under a different id -> refused
    sc = Model_Space()
    sc.register_block_definition(_text_def("X40"))   # same lib/series/name, new id
    summary = sc.load_blocks_from_files([path])
    assert summary["refused"]
    assert pd.resolve_line_weight_mm("X40") != 0.40
    # unreadable file -> failed
    bad = tmp_path / "bad.fpdb"
    bad.write_text("{not json", encoding="utf-8")
    assert Model_Space().load_blocks_from_files([str(bad)])["failed"]
    assert pd.resolve_line_weight_mm("X40") != 0.40


def test_loaded_weight_drives_text_border_width(qapp):
    _project_with()
    path = block_library.save_to_library(_text_def("X40"))
    _other_project()
    Model_Space().load_blocks_from_files([path])
    item = TextItem(TextAnnotationData(text="X", border=True, border_weight="X40"))
    item._force_device_independent = True            # paper-surface text
    assert abs(item._frame_pen().widthF() - 0.40 / (item.scale() or 1.0)) < 1e-9


def test_same_version_reload_adding_weights_dirties_project(qapp):
    _project_with()
    defn = _text_def("X40")
    path = block_library.save_to_library(defn)
    sc = Model_Space()
    sc.register_block_definition(BlockDefinition.from_dict(defn.to_dict()))
    _other_project()
    sc.mark_saved()
    assert not sc.is_dirty()
    assert sc.load_blocks_from_files([path])["skipped"]        # same version
    assert pd.resolve_line_weight_mm("X40") == 0.40
    assert sc.is_dirty()


def test_load_adding_nothing_leaves_scene_clean(qapp):
    _project_with()
    defn = _text_def("X40")
    path = block_library.save_to_library(defn)
    sc = Model_Space()
    sc.register_block_definition(BlockDefinition.from_dict(defn.to_dict()))
    sc.mark_saved()
    assert sc.load_blocks_from_files([path])["skipped"]        # project has X40
    assert not sc.is_dirty()


def test_unknown_weight_name_not_fabricated(qapp):
    _project_with()
    rec = _read(block_library.save_to_library(_text_def("Nope")))
    assert "weights" not in rec
    rec = _read(block_library.save_to_library(_text_def("X40", "Two")))
    assert rec["weights"] == {"X40": 0.40}


def test_merge_repens_underlay_waiting_on_added_weight(qapp):
    """An underlay layer overriding to a name the project lacks is baked at
    the fallback width; a library load that bundles the name re-pens it."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QGraphicsPathItem
    from firepro3d.underlay import Underlay
    _project_with()
    path = block_library.save_to_library(_text_def("X40"))
    _other_project()                                       # X40 missing
    sc = Model_Space()
    rec = Underlay(type="dxf", path="x.dxf", line_weight_name="X40")
    group, _ = sc._build_batched_underlay_group(
        [{"kind": "line", "x1": 0, "y1": 0, "x2": 100, "y2": 0,
          "layer": "A"}], rec)
    sc.underlays.append((rec, group))

    def widths():
        return [c.pen().widthF() for c in group.childItems()
                if isinstance(c, QGraphicsPathItem)
                and c.pen().style() != Qt.PenStyle.NoPen]

    fallback = widths()
    assert fallback != [pd.canvas_weight_px(0.40)]
    sc.load_blocks_from_files([path])
    assert pd.resolve_line_weight_mm("X40") == 0.40
    assert widths() == [pd.canvas_weight_px(0.40)]
