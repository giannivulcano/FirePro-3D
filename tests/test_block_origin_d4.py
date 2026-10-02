"""D4 origin fixed at (0,0): migration on open, D24 bbox-centre base.

See docs/specs/parametric-constraint-system.md D4, D24 and §6.5.
"""
from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem, ReferenceLineItem
from firepro3d.model_space import Model_Space
from firepro3d.text_item import TextItem, TextAnnotationData


def _editor(proj):
    from firepro3d.block_editor import BlockEditorWidget
    return BlockEditorWidget(proj)


def _rects(defn):
    return [op.path.boundingRect() for op in defn.render_ops()]


def test_open_migrates_nonzero_origin_and_instances_render_identically(qapp):
    proj = Model_Space()
    ln = LineItem(QPointF(3000, 2000), QPointF(3100, 2000))
    defn = BlockDefinition.new(name="b", library="", series="",
                               primitives=[ln.to_dict()], origin=(3000.0, 2000.0))
    proj.register_block_definition(defn)
    before = _rects(defn)
    w = _editor(proj)
    w.seed_from_definition(defn)
    l2 = w.editor_scene._draw_lines[0]
    assert (l2._pt1.x(), l2._pt1.y()) == (0.0, 0.0)
    w._edit_block_id = defn.id
    w.commit_block("b", "", "")
    assert defn.origin == (0.0, 0.0)
    assert _rects(defn) == before


def test_migration_covers_text_and_nested_instances_and_keeps_uids(qapp):
    proj = Model_Space()
    child = BlockDefinition.new(
        name="c", library="", series="",
        primitives=[LineItem(QPointF(0, 0), QPointF(10, 0)).to_dict()],
        origin=(0.0, 0.0))
    proj.register_block_definition(child)
    ln = LineItem(QPointF(500, 400), QPointF(600, 400))
    tx = TextItem(TextAnnotationData(text="A", x=520.0, y=380.0, height_mm=10.0))
    nested = {"type": "block_instance", "block_id": child.id,
              "pos": [550.0, 450.0], "rotation": 0.0, "uid": "nested-uid-1"}
    defn = BlockDefinition.new(name="p", library="", series="",
                               primitives=[ln.to_dict(), tx.to_dict(), nested],
                               origin=(500.0, 400.0))
    proj.register_block_definition(defn)
    before = _rects(defn)
    uids_before = {d["uid"] for d in defn.primitives}
    w = _editor(proj)
    w.seed_from_definition(defn)
    sc = w.editor_scene
    assert {it._uid for it in w.gather_primitives()} == uids_before
    inst = sc._block_instances[0]
    assert inst.block_pos() == (50.0, 50.0)
    t2 = sc._texts[0]
    assert (round(t2.to_dict()["x"], 6), round(t2.to_dict()["y"], 6)) == (20.0, -20.0)
    w._edit_block_id = defn.id
    w.commit_block("p", "", "")
    assert defn.origin == (0.0, 0.0)
    assert {d["uid"] for d in defn.primitives} == uids_before
    assert _rects(defn) == before


def test_migration_is_the_undo_baseline(qapp):
    proj = Model_Space()
    ln = LineItem(QPointF(3000, 2000), QPointF(3100, 2000))
    defn = BlockDefinition.new(name="b", library="", series="",
                               primitives=[ln.to_dict()], origin=(3000.0, 2000.0))
    proj.register_block_definition(defn)
    w = _editor(proj)
    w.seed_from_definition(defn)
    assert not w.is_dirty()
    sc = w.editor_scene
    # A first user edit, then Ctrl+Z: it must step back to the MIGRATED state,
    # not to a pre-migration snapshot.
    w._add_primitive(LineItem(QPointF(0, 50), QPointF(10, 50)))
    sc.push_undo_state()
    sc.undo()
    assert len(sc._draw_lines) == 1
    l2 = sc._draw_lines[0]     # undo restore rebuilds items: re-read
    assert (l2._pt1.x(), l2._pt1.y()) == (0.0, 0.0)
    sc.undo()                  # nothing further: the migration is the baseline
    l2 = sc._draw_lines[0]
    assert (l2._pt1.x(), l2._pt1.y()) == (0.0, 0.0)


def test_create_from_selection_uses_bbox_centre_and_keeps_plan_position(qapp):
    proj = Model_Space()
    a = LineItem(QPointF(100, 100), QPointF(300, 100)); proj.addItem(a); proj._draw_lines.append(a)
    w = _editor(proj)
    w.seed_from_selection([a.to_dict()], source_items=[a])
    s = w.editor_scene._draw_lines[0]
    assert (s._pt1.x(), s._pt1.y(), s._pt2.x()) == (-100.0, 0.0, 100.0)
    defn = w.commit_block("b", "", "")
    assert defn.origin == (0.0, 0.0)
    inst = proj._block_instances[-1]
    assert inst.block_pos() == (200.0, 100.0)
    # Nothing moved visually: the instance covers the consumed source's extent.
    r = inst.geometric_rect()
    assert (r.left(), r.right(), r.top()) == (100.0, 300.0, 100.0)


def test_create_from_selection_centre_ignores_scaffolding(qapp):
    proj = Model_Space()
    a = LineItem(QPointF(100, 100), QPointF(300, 100))
    ref = ReferenceLineItem(QPointF(5000, 5000), QPointF(6000, 5000))
    w = _editor(proj)
    w.seed_from_selection([a.to_dict(), ref.to_dict()], source_items=[])
    s = w.editor_scene._draw_lines[0]
    assert (s._pt1.x(), s._pt2.x()) == (-100.0, 100.0)


def test_set_origin_is_retired(qapp):
    from firepro3d.model_space import Model_Space as MS
    assert "set_origin" not in MS._PRESS_DISPATCH
    assert "set_origin" not in MS._ALIGN_PLACEMENT_MODES
    assert not hasattr(MS, "originPicked")
    w = _editor(Model_Space())
    assert not hasattr(w, "begin_set_origin")
    assert not hasattr(w, "set_origin_point")
    assert w.origin_point() == QPointF(0.0, 0.0)
