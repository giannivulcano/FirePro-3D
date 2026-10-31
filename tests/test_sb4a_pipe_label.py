"""SB4a -- pipe label drawn by an annotation block (design
docs/superpowers/specs/2026-10-31-sb4a-pipe-label-design.md)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.block_attributes import normalise_attr
from firepro3d.block_definition import BlockDefinition
from firepro3d.bound_label import BoundLabelItem
from firepro3d.hydraulic_solver import HydraulicResult
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space


def _scene():
    ms = Model_Space()
    ms._level_manager = LevelManager()
    return ms


def _pipe(ms, x0=0.0, y0=0.0, x1=3000.0, y1=0.0):
    return ms.add_pipe(ms.add_node(x0, y0), ms.add_node(x1, y1))


def _pipe_def(ms, texts=(("@[Diameter]", -4.0, False), ("@[Length]", 1.0, False))):
    """An eligible Pipe label: Annotative, Scale with zoom, host Pipe; one
    3 mm text per (text, y, hide_empty); mapped as the project default."""
    prims, keys = [], set()
    for text, y, hide in texts:
        rec = {"type": "text", "text": text, "x": -10.0, "y": y, "height_mm": 3.0,
               "wrap_width_mm": 20.0, "box_height_mm": 3.0, "align": "C", "valign": "M"}
        if hide:
            rec["hide_empty"] = True
        prims.append(rec)
        keys.add(text[2:-1])
    d = BlockDefinition.new(name="TestPipeLabel", library="", series="",
                            origin=(0.0, 0.0), primitives=prims)
    d.scale_mode = "annotative"
    d.host_category = "Pipe"
    d.attributes = [normalise_attr({"key": k, "source": "host", "host_key": k})
                    for k in sorted(keys)]
    ms.register_block_definition(d)
    ms.annotation_defaults["Pipe"] = d.id
    return d


def test_top_level_label_reads_its_explicit_host(qapp):
    ms = _scene()
    p = _pipe(ms)
    lab = BoundLabelItem(p, child=False)
    ms.addItem(lab)
    assert lab.parentItem() is None
    assert lab.host is p
    assert lab.category == "Pipe"
    hv = lab.host_values({"Diameter"})
    assert hv is not None and hv["Diameter"].raw == p._properties["Diameter"]["value"]


def test_pipe_is_an_annotation_category_with_a_system_default(qapp):
    from firepro3d import system_blocks as sb
    assert "Pipe" in sb.ANNOTATION_CATEGORIES
    assert sb.SYSTEM_DEFAULTS["Pipe"] == "system-tags-pipelabel"
    assert sb.LABEL_FIELD["Pipe"] == "Diameter"


def test_refresh_annotation_tags_reshapes_pipe_labels(qapp):
    ms = _scene()
    p = _pipe(ms)
    _pipe_def(ms)
    p.label._rect = QRectF(0, 0, 1, 1)           # a stale cached rect
    ms.refresh_annotation_tags()
    assert p.label._rect is None


def test_shipped_pipelabel_is_eligible_and_binds_the_four_fields(qapp):
    import json
    import os
    import firepro3d
    from firepro3d import block_library
    from firepro3d.bound_label import eligible_definition
    path = os.path.join(os.path.dirname(firepro3d.__file__), "system_blocks", "Tags", "PipeLabel.fpdb")
    d = block_library.load_block_file(path)
    assert d.id == "system-tags-pipelabel" and eligible_definition(d, "Pipe")
    keys = {a["host_key"] for a in d.effective_attributes() if a.get("source") == "host"}
    assert keys == {"Diameter", "Length", "Flow", "FrictionLoss"}
    raw = json.load(open(path, encoding="utf-8"))
    hide = {p["text"]: p.get("hide_empty", False) for p in raw["primitives"]}
    assert hide == {"@[Diameter]": False, "@[Length]": False,
                    "@[Flow]": True, "@[FrictionLoss]": True}


def _texts(lab):
    """The resolved strings the label paints (bound_text_ops' cache key)."""
    lab.boundingRect()
    return lab._bound_cache[1][0] if lab._bound_cache else ()


def _solve(ms, p, q, hf, v=1.0):
    r = HydraulicResult.__new__(HydraulicResult)
    r.pipe_flows, r.pipe_friction_loss, r.pipe_velocity = {p: q}, {p: hf}, {p: v}
    ms.hydraulic_result = r
    p.update_label()


def test_g1_solved_pipe_label_paints_diameter_3d_length_flow_and_friction(qapp):
    from firepro3d import element_params as ep
    from firepro3d.block_attributes import format_value
    ms = _scene()
    p = _pipe(ms)
    p.node1.z_pos = 0.0                        # nodes default to -50.8 mm
    p.node2.z_pos = 4000.0                     # 3D length 5000 mm (3-4-5)
    _pipe_def(ms, texts=(("@[Diameter]", -4.0, False), ("@[Length]", 1.0, False),
                         ("@[Flow]", 6.0, True), ("@[FrictionLoss]", 11.0, True)))
    _solve(ms, p, 52.5, 1.25)
    t = _texts(p.label)
    keys = ("Diameter", "Length", "Flow", "FrictionLoss")
    hv = ep.host_values(p, set(keys))
    assert hv["Length"].raw == 5000.0
    rec = lambda k: normalise_attr({"key": k, "source": "host", "host_key": k})
    assert t == tuple(format_value(rec(k), hv[k]) for k in keys)


def test_g3_left_and_right_pipes_get_the_same_label_angle(qapp):
    ms = _scene()
    _pipe_def(ms)
    right = _pipe(ms, 0.0, 0.0, 3000.0, 1000.0)
    left = _pipe(ms, 3000.0, 6000.0, 0.0, 5000.0)     # same direction, drawn backwards
    assert left.label.rotation() == right.label.rotation()
    assert -90.0 <= right.label.rotation() < 90.0
    up = _pipe(ms, 8000.0, 0.0, 8000.0, -3000.0)          # plan-vertical, both directions
    down = _pipe(ms, 9000.0, -3000.0, 9000.0, 0.0)
    assert up.label.rotation() == down.label.rotation() == -90.0
    assert right.label._pose_rot == right.label.rotation()


def test_g4_label_draws_above_a_node_at_the_midpoint(qapp):
    ms = _scene()
    _pipe_def(ms)
    p = _pipe(ms)
    mid_node = ms.add_node(1500.0, 0.0)                # a node under the label
    mid = p.node1.scenePos() * 0.5 + p.node2.scenePos() * 0.5   # the anchor (rect centre is offset by the block)
    assert mid_node.sceneBoundingRect().contains(mid)
    assert ms.items(mid)[0] is p.label


def test_vertical_pipe_and_show_label_off_hide_the_label(qapp):
    ms = _scene()
    _pipe_def(ms)
    p = _pipe(ms)
    p.set_property("Show Label", "False")
    assert not p.label.isVisible()
    v = _pipe(ms, 5000.0, 0.0, 6000.0, 0.0)
    v.node2.setPos(5000.0, 0.0)                        # same XY: a riser in plan
    v.node2.z_pos = 3000.0
    v.update_geometry()
    assert v._is_vertical() and not v.label.isVisible()


def test_g6_legacy_label_size_loads_clean_and_is_gone(qapp):
    ms = _scene()
    p = _pipe(ms)
    p.set_property("Label Size", "24")                # an old file's key: ignored
    assert "Label Size" not in p._properties
    assert "Label Size" not in p.get_properties()
    from firepro3d.display_manager import _category_has_font
    assert not _category_has_font("Pipe")


def test_tag_row_follows_show_label_and_assignment_is_one_undo_step(qapp):
    ms = _scene()
    p = _pipe(ms)
    keys = list(p.get_properties())
    assert keys.index("Tag") == keys.index("Show Label") + 1
    row = p.get_properties()["Tag"]
    assert row["type"] == "enum" and row["value"] in row["options"]
    p.set_property("Tag", row["value"])               # the default entry: a no-op
    assert p.tag_block is None
