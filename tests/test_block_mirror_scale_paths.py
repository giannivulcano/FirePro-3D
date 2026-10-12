"""Mirror / scale pose through the library, copy, editor-save and tile paths
(design DD7).

Each guard drives the real entry (library save + load, the Duplicate and
Array tools on a shown view, Block Editor ``commit_block``, a pattern tile's
lattice cell) and asserts the observable pose or the compiled geometry
against hand-derived endpoints.
"""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from firepro3d import block_library
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests._modify_tools_helpers import ignore_os_mouse
from tests._snap_polish_helpers import click, close_view, make_view, move


def _line_def(ms, name, a, b):
    d = BlockDefinition.new(name=name, library="L", series="S", origin=(0.0, 0.0),
                            primitives=[LineItem(QPointF(*a), QPointF(*b)).to_dict()])
    ms.register_block_definition(d)
    return d


def _segments(ops):
    """Rounded (start, end) of every two-element op path."""
    out = []
    for op in ops:
        p = op.path
        pts = [(round(p.elementAt(i).x, 6), round(p.elementAt(i).y, 6))
               for i in range(p.elementCount())]
        out.append(tuple(pts))
    return sorted(out)


def _path_segments(path):
    """(moveTo, lineTo) pairs of a QPainterPath built from line ops."""
    pts = [(round(path.elementAt(i).x, 6), round(path.elementAt(i).y, 6))
           for i in range(path.elementCount())]
    return sorted(tuple(pts[i:i + 2]) for i in range(0, len(pts), 2))


# ── (a) .fpdb library round trip ────────────────────────────────────────────

def test_library_round_trip_keeps_nested_pose_geometry(qapp, tmp_path):
    ms = Model_Space()
    child = _line_def(ms, "C", (0, 0), (100, -40))
    rec = {"type": "block_instance", "block_id": child.id, "pos": [50.0, 10.0],
           "rotation": 0.0, "mirrored": True, "scale": 2.0}
    host = BlockDefinition.new(name="H", library="L", series="S", origin=(0.0, 0.0),
                               primitives=[rec])
    ms.register_block_definition(host)
    want = _segments(host.render_ops())
    # Hand-derived: x -> -x, x2, then + pos: (0,0)->(50,10); (100,-40)->(-150,-70).
    assert want == [((50.0, 10.0), (-150.0, -70.0))]
    path = block_library.save_to_library(host, root=str(tmp_path),
                                         bundled=ms.block_registry.bundle_for(host.id))
    fresh = Model_Space()
    fresh.load_blocks_from_files([path])
    loaded = fresh.get_block_definition(host.id)
    assert loaded is not None and loaded is not host
    assert _segments(loaded.render_ops()) == want


# ── (b) Duplicate / (c) Array of a posed instance ───────────────────────────

def _posed_view():
    view, scene = make_view(role="plan", scale=1.0)
    ignore_os_mouse(view)
    d = _line_def(scene, "L", (0, 0), (100, -40))
    inst = scene.place_block_instance(d.id, (30.0, 40.0), rotation=30.0,
                                      mirrored=True, scale=2.0, level_offset_mm=300.0)
    scene.push_undo_state()
    scene.clearSelection()
    inst.setSelected(True)
    return view, scene, inst


def _pose_parts(inst):
    return (round(inst.block_rotation(), 6), inst.block_mirrored(),
            round(inst.block_scale(), 6), inst._level_offset_mm)


def test_duplicate_keeps_the_pose(qapp):
    view, scene, inst = _posed_view()
    try:
        want = _pose_parts(inst)
        assert want == (30.0, True, 2.0, 300.0)
        x0, y0 = inst.block_pos()
        assert scene._modify_ctl.start("duplicate")
        click(view, QPointF(0, 0))
        base = QPointF(scene.node_start_pos)
        move(view, QPointF(300, 0)); click(view, QPointF(300, 0))
        (copy,) = [i for i in scene._block_instances if i is not inst]
        assert _pose_parts(copy) == want
        assert _pose_parts(inst) == want
        cx, cy = copy.block_pos()
        assert (cx, cy) == pytest.approx((x0 + 300 - base.x(), y0 - base.y()), abs=0.5)
    finally:
        close_view(view, scene)


def test_linear_array_keeps_the_pose(qapp):
    view, scene, inst = _posed_view()
    try:
        want = _pose_parts(inst)
        x0, y0 = inst.block_pos()
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(200, 0))
        assert scene.begin_dynamic_input() is True
        scene.dynamic_input.editor("Spacing").setText("500")
        scene.dynamic_input.editor("Count").setText("3")
        scene.dynamic_input._accept()
        copies = [i for i in scene._block_instances if i is not inst]
        assert len(copies) == 2
        for c in copies:
            assert (c.block_mirrored(), round(c.block_scale(), 6)) == (True, 2.0)
            assert round(c.block_rotation(), 6) == 30.0
        got = sorted(c.block_pos() for c in copies)
        assert got == pytest.approx([(x0 + 500, y0), (x0 + 1000, y0)], abs=0.01)
    finally:
        close_view(view, scene)


# ── (d) Block Editor save -> host compiled ops ──────────────────────────────

def test_editor_save_writes_the_nested_pose_and_compiles_it(qapp):
    from firepro3d.block_editor import BlockEditorWidget
    proj = Model_Space()
    b = _line_def(proj, "B", (0, 0), (100, -40))
    a = _line_def(proj, "A", (0, 0), (100, 0))
    w = BlockEditorWidget(proj, block_id=a.id)
    try:
        w.seed_from_definition(a)
        nested = w.editor_scene.place_block_instance(b.id, (300.0, 0.0))
        nested.set_property("Mirrored", True)       # the panel's checkbox value
        nested.set_property("Scale", 2.0)           # the panel's DimensionEdit value
        w.commit_block(a.name, a.library, a.series)
        (rec,) = [p for p in a.primitives if p["type"] == "block_instance"]
        assert (rec.get("mirrored"), rec.get("scale")) == (True, 2.0)
        # Hand-derived: (0,0)->(300,0); (100,-40) -> (300-200, -80).
        got = _segments(proj.get_block_definition(a.id).render_ops())
        assert got == sorted([((0.0, 0.0), (100.0, 0.0)),
                              ((300.0, 0.0), (100.0, -80.0))])
    finally:
        w.editor_scene.cleanup()
        QApplication.processEvents()


# ── (e) Pattern tile nesting a posed instance ───────────────────────────────

def test_pattern_tile_cell_mirrors_a_nested_instance(qapp):
    from firepro3d import hatch_render
    from firepro3d.block_editor import BlockEditorWidget
    from firepro3d.hatch_patterns import tile_is_valid
    proj = Model_Space()
    b = _line_def(proj, "B", (0, 0), (2, -1))
    w = BlockEditorWidget(proj)
    try:
        w._add_primitive(LineItem(QPointF(0, 0), QPointF(8, 0)))
        nested = w.editor_scene.place_block_instance(b.id, (6.0, 0.0))
        nested.set_property("Mirrored", True)
        nested.set_property("Scale", 2.0)
        assert w.toggle_pattern_tile()
        defn = w.commit_block("Tile", "L", "S")
        assert defn is not None and tile_is_valid(defn)
        strokes, _fills = hatch_render._lattice(defn, defn.tile, 1.0, 1, 1, 0)
        # Hand-derived: (0,0)->(6,0); (2,-1) -> (6-4, -2) = (2,-2).
        assert _path_segments(strokes) == sorted([((0.0, 0.0), (8.0, 0.0)),
                                                  ((6.0, 0.0), (2.0, -2.0))])
    finally:
        w.editor_scene.cleanup()
        QApplication.processEvents()
