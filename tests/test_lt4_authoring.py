"""LT4 rows ⇄ geometry, Weight row, Continuous lock, grow-to-fit (A1-A3)."""
from PyQt6.QtCore import QPointF

from firepro3d import linetype_authoring as la
from firepro3d import stroke_style as ss
from firepro3d.block_editor import BlockEditorWidget
from firepro3d.geometry_2d import CircleItem, LineItem
from firepro3d.linetype_render import LinetypeDef
from firepro3d.model_space import Model_Space
from tests.lt3_support import hidden


def _lt_editor(*lines, length=9.0):
    proj = Model_Space()
    w = BlockEditorWidget(proj)
    for a, b in lines:
        w._add_primitive(LineItem(QPointF(a, 0), QPointF(b, 0)))
    sc = w.editor_scene
    sc.set_block_capability(("repeat", {"length": length, "size": "drafting"}))
    return proj, w, sc


def _axis(sc):
    return sorted((round(min(l._pt1.x(), l._pt2.x()), 6),
                   round(max(l._pt1.x(), l._pt2.x()), 6)) for l in sc._draw_lines)


def test_a1_edit_ripples_moves_in_place_one_undo(qapp):
    proj, w, sc = _lt_editor((0, 6))
    circle = CircleItem(QPointF(8, 5), 1.0)
    w._add_primitive(circle)
    sc.push_undo_state()
    first = sc._draw_lines[0]
    circle_before = circle.to_dict()
    n = len(sc._undo_stack)
    la.apply_pattern_rows(sc, [("dash", 8.0), ("gap", 2.0), ("dot", 0.0), ("gap", 1.0)])
    assert _axis(sc) == [(0.0, 8.0), (10.0, 10.0)]
    assert sc._draw_lines[0] is first                      # in place (Q10)
    assert sc.block_repeat["length"] == 11.0               # period = sum
    assert circle.to_dict() == circle_before and circle in sc._draw_circles   # untouched (Q9)
    assert len(sc._undo_stack) == n + 1                    # one step
    sc.undo()
    assert _axis(sc) == [(0.0, 6.0)] and sc.block_repeat["length"] == 9.0


def test_a1_reorder_and_remove(qapp):
    _, _, sc = _lt_editor((0, 6))
    la.apply_pattern_rows(sc, [("gap", 3.0), ("dash", 6.0)])
    assert _axis(sc) == [(3.0, 9.0)]
    la.apply_pattern_rows(sc, [("dot", 0.0), ("gap", 2.0)])
    assert _axis(sc) == [(0.0, 0.0)]


def test_a1_invalid_rows_refused(qapp):
    _, _, sc = _lt_editor((0, 6))
    n = len(sc._undo_stack)
    assert la.apply_pattern_rows(sc, [("gap", 3.0)]) is False
    assert _axis(sc) == [(0.0, 6.0)] and len(sc._undo_stack) == n


def test_a2_rows_match_the_renderer_reading(qapp):
    _, w, sc = _lt_editor((0, 6), (8, 9), (11, 11), length=12.0)
    rows = la.current_rows(sc)
    defn = w.editor_scene.capability_frame_item().scratch_definition()
    lt = LinetypeDef.from_block(defn)
    from firepro3d.linetype_pattern import rows_from_reading
    assert rows == rows_from_reading(lt.dashes, lt.dots, lt.period)
    assert rows == [("dash", 6.0), ("gap", 2.0), ("dash", 1.0), ("gap", 2.0),
                    ("dot", 0.0), ("gap", 1.0)]


def test_a2_overlap_is_unrepresentable(qapp):
    _, _, sc = _lt_editor((0, 6), (4, 8))
    assert la.current_rows(sc) is None


def test_a2_draw_past_end_grows_in_the_same_step(qapp):
    _, w, sc = _lt_editor((0, 6))
    w._add_primitive(LineItem(QPointF(7, 0), QPointF(12, 0)))
    n = len(sc._undo_stack)
    sc.push_undo_state()                                   # the draw's commit
    assert sc.block_repeat["length"] == 12.0
    assert len(sc._undo_stack) == n + 1                    # one step, not two
    sc.undo()
    assert sc.block_repeat["length"] == 9.0


def test_weight_row_sets_every_dash(qapp):
    _, _, sc = _lt_editor((0, 6), (7, 8))
    la.set_pattern_weight(sc, "Heavy")
    assert {l.style["weight"] for l in sc._draw_lines} == {"Heavy"}
    assert la.pattern_weight(sc) == "Heavy"
    sc._draw_lines[0].style["weight"] = "Light"
    assert la.pattern_weight(sc) is None                    # mixed


def test_a3_lock_on_commit_and_new_draw_takes_linetype_weight(qapp):
    proj, w, sc = _lt_editor((0, 6))
    lt_id = hidden(proj)
    la.set_pattern_weight(sc, "Medium")
    ss.set_current(linetype=lt_id, weight="Heavy")
    try:
        line = LineItem(QPointF(0, 5), QPointF(4, 5))
        ss.apply_current(line, sc)                          # the draw-tool stamp
        assert line.style["linetype"] == ss.CONTINUOUS
        assert line.style["weight"] == "Medium"
        assert ss.current_style()["linetype"] == lt_id      # current untouched
    finally:
        ss.reset_current()


# ── A3 lock through the real commit paths (H4-d: paste / import / explode) ──

def test_a3_paste_commit_is_continuous(qapp):
    proj, w, sc = _lt_editor((0, 6))
    lt_id = hidden(proj)
    src = LineItem(QPointF(0, 5), QPointF(4, 5))
    src.style["linetype"] = lt_id
    circ = CircleItem(QPointF(3, 3), 1.0)
    circ.style["linetype"] = lt_id
    sc._paste_payload = {"items": [src.to_dict(), circ.to_dict()]}
    before = set(sc._draw_lines + sc._draw_circles)
    n = len(sc._undo_stack)
    sc._modify_ctl.commit_paste(QPointF(0, 0))              # the real paste commit
    new = [it for it in sc._draw_lines + sc._draw_circles if it not in before]
    assert len(sc._undo_stack) == n + 1
    assert len(new) == 2
    assert {it.style["linetype"] for it in new} == {ss.CONTINUOUS}


def test_a3_editor_import_is_continuous(qapp):
    """The Block-Editor import geoms carry no linetype (geometry_import makes
    default-styled primitives); the imported lines land Continuous."""
    from types import SimpleNamespace
    proj, w, sc = _lt_editor((0, 6))
    hidden(proj)
    p = SimpleNamespace(geom_list=[{"kind": "line", "x1": 0, "y1": 4,
                                    "x2": 5, "y2": 4}],
                        scale=1.0, base_x=0.0, base_y=0.0, rotation=0.0,
                        insert_at_origin=True)
    before = set(sc._draw_lines)
    w.import_with_params(p)                                 # the real import entry
    new = [l for l in sc._draw_lines if l not in before]
    assert len(new) == 1 and new[0].style["linetype"] == ss.CONTINUOUS


def test_a3_explode_of_a_hidden_block_is_continuous(qapp):
    from firepro3d.block_definition import BlockDefinition
    proj, w, sc = _lt_editor((0, 6))
    lt_id = hidden(proj)
    ul = LineItem(QPointF(0, 3), QPointF(5, 3))
    ul.style["linetype"] = lt_id
    sym = BlockDefinition.new(name="Sym", library="L", series="S",
                              origin=(0, 0), primitives=[ul.to_dict()])
    proj.register_block_definition(sym)
    inst = sc.place_block_instance(sym.id, (0.0, 0.0))
    sc.push_undo_state()
    sc.clearSelection()
    inst.setSelected(True)
    new = sc.explode_selected_blocks()                      # one undo step
    lines = [it for it in new if isinstance(it, LineItem)]
    assert len(lines) == 1
    assert lines[0].style["linetype"] == ss.CONTINUOUS


# ── LT4-8: a ripple-violated constraint is red live == restored ────────────

def test_a1_ripple_violated_constraint_is_red_live_and_restored(qapp):
    _, _, sc = _lt_editor((0, 6))
    ctl = sc.constraint_ctl
    a = sc._draw_lines[0]
    ctl.add("dim_distance", [{"uid": a._uid, "h": "p1"},
                             {"uid": a._uid, "h": "p2"}], value=6.0)
    cid = ctl.constraints[-1].id
    sc.push_undo_state()
    assert cid not in ctl.red
    assert la.apply_pattern_rows(sc, [("dash", 8.0), ("gap", 1.0)])
    assert _axis(sc) == [(0.0, 8.0)]                        # not snapped back
    assert cid in ctl.red                                   # live
    sc.undo()
    assert _axis(sc) == [(0.0, 6.0)] and cid not in ctl.red
    sc.redo()
    assert _axis(sc) == [(0.0, 8.0)] and cid in ctl.red     # restored == live


def test_apply_rows_without_an_editor_refuses_before_mutating(qapp):
    sc = Model_Space(scene_role="block_editor")
    a = LineItem(QPointF(0, 0), QPointF(6, 0))
    sc.addItem(a)
    sc._draw_lines.append(a)
    sc.set_block_capability(("repeat", {"length": 9.0, "size": "drafting"}))
    assert sc._tile_editor is None
    n = len(sc._undo_stack)
    assert la.apply_pattern_rows(
        sc, [("dash", 4.0), ("gap", 1.0), ("dot", 0.0), ("gap", 1.0)]) is False
    assert _axis(sc) == [(0.0, 6.0)]                        # nothing moved
    assert sc.block_repeat["length"] == 9.0 and len(sc._undo_stack) == n

