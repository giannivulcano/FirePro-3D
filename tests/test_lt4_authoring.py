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
        pasted = LineItem(QPointF(0, 7), QPointF(4, 7))
        pasted.style["linetype"] = lt_id
        w._add_primitive(pasted)
        sc.push_undo_state()                                # paste / import / explode commit
        assert pasted.style["linetype"] == ss.CONTINUOUS
    finally:
        ss.reset_current()

