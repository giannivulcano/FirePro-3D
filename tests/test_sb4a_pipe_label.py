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
    # Ground truth (VC3): the label's local +x axis, mapped to the scene, runs
    # along the pipe and reads left to right -- whichever way the pipe was drawn.
    for pipe, (dx, dy) in ((right, (3000.0, 1000.0)), (left, (-3000.0, -1000.0))):
        lab = pipe.label
        ax = lab.mapToScene(QPointF(1.0, 0.0)) - lab.mapToScene(QPointF(0.0, 0.0))
        ux, uy = (dx, dy) if dx > 0 else (-dx, -dy)       # the pipe line, pointing +x
        assert ax.x() * uy - ax.y() * ux == pytest.approx(0.0, abs=1e-6 * abs(ux))   # parallel
        assert ax.x() * ux + ax.y() * uy > 0.0                                       # reads left to right
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


def test_tag_row_follows_show_label_and_default_entry_assignment_is_a_no_op(qapp):
    ms = _scene()
    p = _pipe(ms)
    keys = list(p.get_properties())
    assert keys.index("Tag") == keys.index("Show Label") + 1
    row = p.get_properties()["Tag"]
    assert row["type"] == "enum" and row["value"] in row["options"]
    p.set_property("Tag", row["value"])               # the default entry: a no-op
    assert p.tag_block is None


def test_g5_tag_block_round_trips_the_file_codec(qapp):
    from firepro3d.network_codec import serialize_pipe
    ms = _scene()
    p = _pipe(ms)
    d = _pipe_def(ms)
    p._tag_block = d.id
    ids = {p.node1: 0, p.node2: 1}
    rec = serialize_pipe(p, ids)
    assert rec["tag_block"] == d.id
    p._tag_block = None
    assert "tag_block" not in serialize_pipe(p, ids)        # sparse


@pytest.mark.parametrize("bad", ["", None, 7, ["x"]])
def test_g5_garbage_tag_block_loads_as_none(qapp, bad):
    from firepro3d.network_codec import deserialize_pipe, serialize_pipe
    ms = _scene()
    p = _pipe(ms)
    d = _pipe_def(ms)
    p._tag_block = d.id
    rec = serialize_pipe(p, {p.node1: 0, p.node2: 1})
    rec["tag_block"] = bad
    q = deserialize_pipe(ms, rec, {0: p.node1, 1: p.node2})
    assert q.tag_block is None


def test_g5_tag_row_pick_is_one_undo_step(qapp):
    ms = _scene()
    p = _pipe(ms)
    d = _pipe_def(ms)
    ms.push_undo_state()                                # the seed a new / opened file has
    opts = p.get_properties()["Tag"]["options"]
    pick = next(o for o in opts if o.startswith("TestPipeLabel"))
    n = len(ms._undo_stack)
    p.set_property("Tag", pick)
    assert len(ms._undo_stack) == n + 1                 # ONE step (Room SB3b G3 pattern)
    assert p.tag_block == d.id
    ms.undo()
    p2 = ms.sprinkler_system.pipes[0]
    assert p2.tag_block is None
    ms.redo()
    assert ms.sprinkler_system.pipes[0].tag_block == d.id


# ---- Task 9: paper pass (D10; G7, AC7) ----
from tests.test_sb3_paper import TAG_MM, _export, _text_height  # noqa: E402


@pytest.mark.parametrize("scale", [0.02, 0.005])          # 1:50, 1:200
def test_g7_pdf_pipe_label_cap_height_is_the_authored_mm(qapp, tmp_path, scale):
    from tests.paper_mode_shim import set_paper_mode
    set_paper_mode("bw")
    ms = _scene()
    p = _pipe(ms, -1.0e6, 0.0, 1.0e6, 0.0)                 # nodes far outside the viewport
    p.set_property("Mark", "H")                             # cap-height glyph, no ascender
    _pipe_def(ms, texts=(("@[Mark]", -1.5, False),))
    p.update_label()
    h = _text_height(_export(tmp_path, ms, scale, f"p{int(1 / scale)}.pdf"))
    assert abs(h - TAG_MM) < 0.3, h
    assert p.label._paper_scale is None                     # restored after the pass


def test_ac7_dm_pipe_colour_does_not_tint_the_label(qapp):
    from firepro3d.display_manager import _apply_pipe
    ms = _scene()
    p = _pipe(ms)
    _pipe_def(ms)
    before = [op.colour for op in p.label._ops(1.0)]
    _apply_pipe(p, "#ff00ff", 1.0, 100, True)
    assert [op.colour for op in p.label._ops(1.0)] == before


# ── VC9 fix round ────────────────────────────────────────────────────────────

def _alt_def(ms):
    d = BlockDefinition.new(name="AltPipeLabel", library="", series="", origin=(0.0, 0.0),
                            primitives=[{"type": "text", "text": "@[Diameter]", "x": -10.0,
                                         "y": -4.0, "height_mm": 3.0, "wrap_width_mm": 20.0,
                                         "box_height_mm": 3.0, "align": "C", "valign": "M"}])
    d.scale_mode = "annotative"
    d.host_category = "Pipe"
    d.attributes = [normalise_attr({"key": "Diameter", "source": "host", "host_key": "Diameter"})]
    ms.register_block_definition(d)
    return d


def _tagged_pipe(ms, **kw):
    _pipe_def(ms)
    alt = _alt_def(ms)
    p = _pipe(ms, **kw)
    pick = next(o for o in p.get_properties()["Tag"]["options"] if o.startswith("AltPipeLabel"))
    p.set_property("Tag", pick)
    assert p.tag_block == alt.id
    return p, alt


def test_vc9_i1_horizontal_split_keeps_the_per_pipe_tag(qapp):
    ms = _scene()
    p, alt = _tagged_pipe(ms)
    ms.split_pipe(p, QPointF(1500.0, 0.0))
    pipes = list(ms.sprinkler_system.pipes)
    assert len(pipes) == 2
    assert [q.tag_block for q in pipes] == [alt.id, alt.id]
    assert all(q.label.definition().id == alt.id for q in pipes)


def test_vc9_i1_vertical_split_keeps_the_per_pipe_tag(qapp):
    ms = _scene()
    p, alt = _tagged_pipe(ms)
    p.node2.setPos(0.0, 0.0)                           # same XY: a riser
    p.node2.z_pos = 3000.0
    p.update_geometry()
    assert p._is_vertical()
    ms._split_vertical_pipe(p, 1500.0, p) if hasattr(ms, "_split_vertical_pipe") \
        else ms.pipe_network._split_vertical_pipe(p, 1500.0, p)
    pipes = list(ms.sprinkler_system.pipes)
    assert len(pipes) == 2
    assert [q.tag_block for q in pipes] == [alt.id, alt.id]


@pytest.mark.parametrize("z_mm", [0.0, 25000.0])
def test_vc9_i2_label_paints_above_its_pipe_and_a_node_after_the_level_z_pass(qapp, z_mm):
    ms = _scene()
    _pipe_def(ms)
    p = _pipe(ms)
    mid_node = ms.add_node(1500.0, 0.0)
    for n in (p.node1, p.node2, mid_node):
        n.z_pos = z_mm
    ms._level_manager.apply_to_scene(ms)
    assert p.label.zValue() > p.zValue()
    assert p.label.zValue() > mid_node.zValue()
    mid = p.node1.scenePos() * 0.5 + p.node2.scenePos() * 0.5
    assert ms.items(mid)[0] is p.label


def test_vc9_m3_reprepare_annotative_resizes_pipe_labels(qapp):
    from firepro3d.annotative import reprepare_annotative
    from firepro3d.bound_label import PEN_MARGIN
    ms = _scene()
    _pipe_def(ms)
    p = _pipe(ms)
    h = p.label.boundingRect().height() - 2 * PEN_MARGIN
    ms.scale_manager.drawing_scale = 2 * ms.scale_manager.drawing_scale
    reprepare_annotative(ms)
    assert p.label.boundingRect().height() - 2 * PEN_MARGIN == pytest.approx(2 * h, rel=1e-6)


def test_vc9_m7_ac9_pipe_shorter_than_its_label_is_still_labelled(qapp):
    ms = _scene()
    _pipe_def(ms)
    p = _pipe(ms, 0.0, 0.0, 40.0, 0.0)                  # 40 mm: far shorter than the label
    assert p.label.isVisible()
    assert p.label.paints()
