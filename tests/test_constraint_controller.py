"""ConstraintController — seams, cascade, undo, save/load, copy (spec §8).

parametric-constraint-system.md §3, §6, §7.2, §8 (CS1 Task 10). Every test
drives a real ``Model_Space(scene_role="block_editor")`` with real primitives;
the guards for the seams (typed readout, property panel, Rotate, Polar
Array, Mirror, grip cancel, New/Open, definition open) drive the real entry
paths and assert scene geometry / the undo stack.
"""
import math

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication

from firepro3d.geometry_2d import LineItem, RectangleItem, ReferenceLineItem
from firepro3d.model_space import Model_Space


def _scene():
    return Model_Space(scene_role="block_editor")


def _line(sc, a, b):
    ln = LineItem(QPointF(*a), QPointF(*b))
    sc.addItem(ln); sc._draw_lines.append(ln)
    return ln


def _rect(sc, a, b):
    r = RectangleItem(QPointF(*a), QPointF(*b))
    sc.addItem(r); sc._draw_rects.append(r)
    return r



# ── plan Step 1 ─────────────────────────────────────────────────────────────

def test_disabled_in_the_plan_scene(qapp):
    sc = Model_Space()
    ln = _line(sc, (0, 0), (10, 5))
    assert not sc.constraint_ctl.enabled
    assert sc.constraint_ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}]) is None


def test_add_horizontal_levels_a_tilted_line_both_ends_to_mean(qapp):
    """D22."""
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 30))
    c = sc.constraint_ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    assert c is not None
    assert abs(ln._pt1.y() - 15) < 1e-6 and abs(ln._pt2.y() - 15) < 1e-6
    assert ln._pt1.x() == 0 and ln._pt2.x() == 100


def test_two_point_and_origin_refs(qapp):
    sc = _scene()
    a = _line(sc, (0, 0), (10, 10)); b = _line(sc, (50, 40), (60, 50))
    sc.constraint_ctl.add("horizontal", [{"uid": a._uid, "h": "p2"}, {"uid": b._uid, "h": "p1"}])
    assert abs(a._pt2.y() - b._pt1.y()) < 1e-6
    sc.constraint_ctl.add("horizontal", [{"uid": a._uid, "h": "p1"}, {"ref": "origin"}])
    assert abs(a._pt1.y()) < 1e-6
    assert abs(a._pt2.y() - b._pt1.y()) < 1e-6          # the first still holds


def test_rotated_rect_edge_row_path(qapp):
    sc = _scene()
    r = _rect(sc, (0, 0), (80, 40))
    r.set_angle(20.0)
    sc.constraint_ctl.add("horizontal", [{"uid": r._uid, "h": "bottom"}])
    g = r.grip_points()
    assert abs(g[4].y() - g[6].y()) < 1e-6           # br / bl level
    # ... by ROTATING level, not by collapsing the width (D29).
    assert r.rect().width() == pytest.approx(80.0, abs=1e-6)
    assert r.rect().height() == pytest.approx(40.0, abs=1e-6)
    assert abs(math.remainder(r._angle, 180.0)) < 1e-6


def test_typed_edit_and_transform_honour_the_constraint(qapp):
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 0))
    sc.constraint_ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    with sc.constraint_ctl.edit([ln]):
        ln.manip_rotate(30.0, QPointF(0, 0))          # a Rotate commit
    assert abs(ln._pt1.y() - ln._pt2.y()) < 1e-6


def test_grip_drag_pins_the_dragged_end(qapp):
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 0))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    ctl.begin_drag(ln)
    ln.apply_grip(2, QPointF(100, 40))
    ctl.drag(ln, 2)
    ctl.end_drag()
    assert abs(ln._pt2.y() - 40) < 1e-3 and abs(ln._pt1.y() - 40) < 1e-3
    assert abs(ln._pt2.x() - 100) < 1e-6


def _status(sc):
    msgs = []
    sc._show_status = lambda m, *a, **k: msgs.append(m)
    return msgs


def test_conflict_holds_last_good(qapp):
    """D29: H(bottom) + H(left) is satisfiable only by collapsing the rect
    (h -> 0) -- a CONFLICT: admitted (D9), geometry held (D10), status shown."""
    from firepro3d.constraint_controller import CONFLICT_STATUS
    sc = _scene()
    r = _rect(sc, (0, 0), (80, 40))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": r._uid, "h": "bottom"}])
    before = [QPointF(p) for p in r.grip_points()]
    msgs = _status(sc)
    ctl.add("horizontal", [{"uid": r._uid, "h": "left"}])    # unsatisfiable with bottom
    assert len(ctl.constraints) == 2                          # D9 admit
    assert all(abs(a.x() - b.x()) < 1e-9 and abs(a.y() - b.y()) < 1e-9
               for a, b in zip(before, r.grip_points()))      # D10 hold last good  [RED]
    assert r.rect().height() == pytest.approx(40.0)
    assert msgs == [CONFLICT_STATUS]


def test_arc_whose_least_change_is_a_zero_span_holds(qapp):
    """D29 arc: H(start, end) on a 10..30 deg arc -- the least change collapses
    the span (or the radius); either is a collapse, so the arc holds."""
    from firepro3d.constraint_controller import CONFLICT_STATUS
    from firepro3d.geometry_2d import ArcItem
    sc = _scene()
    arc = ArcItem(QPointF(0, 0), 100.0, 10.0, 20.0)
    sc.addItem(arc); sc._draw_arcs.append(arc)
    before = (arc._center.x(), arc._center.y(), arc._radius,
              arc._start_deg, arc._span_deg)
    msgs = _status(sc)
    c = sc.constraint_ctl.add("horizontal", [{"uid": arc._uid, "h": "start"},
                                             {"uid": arc._uid, "h": "end"}])
    assert c is not None and len(sc.constraint_ctl.constraints) == 1
    assert (arc._center.x(), arc._center.y(), arc._radius,
            arc._start_deg, arc._span_deg) == before
    assert msgs == [CONFLICT_STATUS]


def test_a_solve_that_shrinks_a_size_above_its_floor_still_applies(qapp):
    """D29 is about collapse only: a rect whose top-right follows a line end
    (H) may legitimately shrink."""
    sc = _scene()
    r = _rect(sc, (0, 0), (100, 100))
    ln = _line(sc, (200, 0), (300, 0))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": r._uid, "h": "tr"}, {"uid": ln._uid, "h": "p1"}])
    msgs = _status(sc)
    with ctl.edit([ln]):
        ln.translate(0, 30)
    tr = r.grip_points()[2]
    assert abs(tr.y() - ln._pt1.y()) < 1e-6
    assert tr.y() > 29.0                                  # the rect followed
    assert 1.0 < r.rect().height() < 100.0 - 1.0          # ... partly by shrinking
    assert msgs == []


def test_failed_solve_rolls_the_edit_back_and_reports(qapp, monkeypatch):
    """D10 mechanism (the solver's non-convergence is forced, since no
    Horizontal-only sketch fails without a degenerate escape — see above):
    an edit whose solve fails is rolled back and the status bar says so."""
    from firepro3d import constraint_controller as cc
    from firepro3d.sketch_solver import SolveResult
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 0))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    msgs = []
    sc._show_status = lambda m, *a, **k: msgs.append(m)
    monkeypatch.setattr(ctl._solver, "solve",
                        lambda s, g, w, active=None: SolveResult(s.x.copy(), False, 1.0))
    with ctl.edit([ln]):
        ln.translate(0, 25)
    assert (ln._pt1.y(), ln._pt2.y()) == (0.0, 0.0)
    assert msgs == [cc.CONFLICT_STATUS]


def test_delete_entity_cascades_in_one_undo_step(qapp):
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 0))
    sc.constraint_ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    pos = sc._undo_pos
    ln.setSelected(True)
    sc.delete_selected_items()
    assert sc.constraint_ctl.constraints == []
    assert sc._undo_pos == pos + 1                    # entity + cascade: ONE step
    sc.undo()
    assert len(sc.constraint_ctl.constraints) == 1
    assert sc.constraint_ctl.constraints[0].refs[0]["uid"] == sc._draw_lines[0]._uid


def test_undo_redo_of_add_delete_and_solver_edit(qapp):
    sc = _scene()
    _line(sc, (0, 0), (100, 30))
    sc.push_undo_state()
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": sc._draw_lines[0]._uid, "h": "edge"}])
    sc.undo()
    assert ctl.constraints == [] and abs(sc._draw_lines[0]._pt2.y() - 30) < 1e-6
    sc.redo()
    assert len(ctl.constraints) == 1 and abs(sc._draw_lines[0]._pt2.y() - 15) < 1e-6
    ctl.delete([ctl.constraints[0].id])
    assert ctl.constraints == []
    sc.undo()
    assert len(ctl.constraints) == 1


def test_duplicate_copies_internal_constraints_with_new_uids(qapp):
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 0))
    sc.constraint_ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    recs = sc._clipboard_item_dicts([ln])
    new = sc.paste_items(QPointF(0, 50), data=recs,
                         constraints=sc.constraint_ctl.internal_records([ln]))
    assert len(sc.constraint_ctl.constraints) == 2
    assert new[0]._uid != ln._uid
    assert sc.constraint_ctl.constraints[1].refs[0]["uid"] == new[0]._uid


def test_copy_drops_constraints_to_outside_and_grounds(qapp):
    """§8: only constraints INTERNAL to the copied set ride the copy."""
    sc = _scene()
    a = _line(sc, (0, 0), (100, 0)); b = _line(sc, (200, 0), (300, 0))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": a._uid, "h": "p2"}, {"uid": b._uid, "h": "p1"}])
    ctl.add("horizontal", [{"uid": a._uid, "h": "p1"}, {"ref": "origin"}])
    assert ctl.internal_records([a]) == []
    assert len(ctl.internal_records([a, b])) == 1


def test_sketch_dof(qapp):
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 0))
    assert sc.constraint_ctl.sketch_dof() == 4
    sc.constraint_ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    assert sc.constraint_ctl.sketch_dof() == 3


# ── requirement 1: edit([]) is a no-op ─────────────────────────────────────

def test_empty_edit_is_a_no_op_even_on_an_unsolved_sketch(qapp):
    """Scale by 1 passes ``edit([])``: it must not solve the sketch. A
    restored (unsolved) Horizontal on a tilted line proves it — a solve would level it."""
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 30))
    sc.constraint_ctl.restore([{"id": "c1", "type": "horizontal",
                                "refs": [{"uid": ln._uid, "h": "edge"}]}])
    msgs = []
    sc._show_status = lambda m, *a, **k: msgs.append(m)
    with sc.constraint_ctl.edit([]):
        pass
    assert (ln._pt1.y(), ln._pt2.y()) == (0.0, 30.0)
    assert msgs == []


def test_scale_by_one_commit_leaves_constrained_geometry_alone(qapp):
    """The real caller: ``commit_scale(1.0)`` passes ``edit([])``."""
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 30))
    sc.constraint_ctl.restore([{"id": "c1", "type": "horizontal",
                                "refs": [{"uid": ln._uid, "h": "edge"}]}])
    sc._scale_base = QPointF(0, 0)
    sc._selected_items = [ln]
    pos = sc._undo_pos
    assert sc._modify_ctl.commit_scale(1.0) is False
    assert (ln._pt1.y(), ln._pt2.y()) == (0.0, 30.0)
    assert sc._undo_pos == pos


# ── requirement 2: New / Open reset ────────────────────────────────────────

def test_clear_scene_resets_constraint_state(qapp):
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 30))
    ctl = sc.constraint_ctl
    c = ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    ctl.selected_id = ctl.hover_id = c.id
    ctl.pick = object()
    ctl.begin_drag(ln)
    sc._clear_scene()
    assert ctl.constraints == []
    assert ctl.selected_id is None and ctl.hover_id is None and ctl.pick is None
    assert ctl._drag_snap is None and ctl._drag_ctx is None
    assert sc._undo_stack[0]["constraints"] == []        # the fresh baseline


# ── requirement 3: cancel restores every solver-written item ───────────────

def _shown_editor(qapp):
    from firepro3d.level_manager import LevelManager
    from firepro3d.model_view import Model_View
    from firepro3d.scale_manager import ScaleManager
    sc = _scene()
    sc._level_manager = LevelManager()
    sc.scale_manager = ScaleManager()
    v = Model_View(sc)
    v.resize(600, 500)
    v.show()
    v.resetTransform()
    v.centerOn(0, 0)
    qapp.processEvents()
    return v, sc


def _close(v, sc):
    sc.cleanup()
    v.close()
    v.deleteLater()
    QApplication.processEvents()


def test_grip_cancel_restores_every_item_the_solver_wrote(qapp):
    """Esc mid-drag (real GripHandle.on_cancel): the dragged line's grip is
    restored by the handle, and the OTHER line the solver moved is restored
    by the controller."""
    v, sc = _shown_editor(qapp)
    try:
        a = _line(sc, (0, 0), (100, 0)); b = _line(sc, (200, 0), (300, 0))
        sc.constraint_ctl.add("horizontal",
                              [{"uid": a._uid, "h": "p2"}, {"uid": b._uid, "h": "p1"}])
        a.setSelected(True)
        qapp.processEvents()
        m = sc._live_manip()
        h = a.manip_handles()[2]
        m._begin_handle(h, QPointF(100, 0), QPointF(100, 0))
        m._update(QPointF(100, 60), Qt.KeyboardModifier.NoModifier, QPointF(100, 60))
        assert abs(b._pt1.y() - a._pt2.y()) < 1e-6 and b._pt1.y() > 50   # solved live
        m.cancel_drag()
        assert (a._pt2.x(), a._pt2.y()) == (100.0, 0.0)
        assert (b._pt1.x(), b._pt1.y()) == (200.0, 0.0)                  # [RED]
        assert sc.constraint_ctl._drag_snap is None
    finally:
        _close(v, sc)


def test_begin_drag_discards_a_stale_session(qapp):
    """A session left open (no end/cancel) must not leak into the next drag:
    cancelling a drag of an unconstrained item restores nothing else."""
    sc = _scene()
    a = _line(sc, (0, 0), (100, 0)); free = _line(sc, (0, 500), (100, 500))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": a._uid, "h": "edge"}])
    ctl.begin_drag(a)                      # stale: never ended
    a.translate(0, 70)                     # a later, committed edit of a
    ctl.begin_drag(free)
    ctl.cancel_drag()
    assert a._pt1.y() == 70.0 and a._pt2.y() == 70.0                    # [RED]


# ── requirement 4: definition open loads constraints into the baseline ─────

def _defn_with_constraint(project, origin):
    from firepro3d.block_definition import BlockDefinition
    ln = LineItem(QPointF(10, 20), QPointF(110, 20))
    other = LineItem(QPointF(10, 80), QPointF(110, 80))
    rec = {"id": "c-h", "type": "horizontal", "refs": [{"uid": ln._uid, "h": "edge"}]}
    defn = BlockDefinition.new(name="B", library="L", series="S",
                               primitives=[ln.to_dict(), other.to_dict()],
                               origin=origin, constraints=[rec])
    project.register_block_definition(defn)
    return defn, ln._uid


@pytest.mark.parametrize("origin", [(0.0, 0.0), (10.0, 20.0)])
def test_definition_open_loads_constraints_into_the_undo_baseline(qapp, origin):
    from firepro3d.block_editor import BlockEditorWidget
    project = Model_Space()
    defn, uid = _defn_with_constraint(project, origin)
    w = BlockEditorWidget(project)
    w.seed_from_definition(defn)
    sc = w.editor_scene
    ctl = sc.constraint_ctl
    assert [c.id for c in ctl.active()] == ["c-h"]           # refs resolve post-migration
    assert not sc.can_undo()
    # An unrelated edit, then Ctrl+Z back to the baseline: the constraint stays.
    other = next(l for l in sc._draw_lines if l._uid != uid)
    sc.delete_items([other])
    sc.undo()
    assert [c.id for c in ctl.constraints] == ["c-h"]                    # [RED]


@pytest.mark.parametrize("origin", [(0.0, 0.0), (10.0, 20.0)])
def test_definition_open_solves_a_violated_saved_constraint(qapp, origin):
    """D18 "open = load + first solve": saved geometry that violates its saved
    Horizontal opens level, and that solved state IS the baseline (Ctrl+Z,
    even after an unrelated edit, never un-levels it)."""
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.block_editor import BlockEditorWidget
    project = Model_Space()
    tilted = LineItem(QPointF(10, 20), QPointF(110, 50))
    other = LineItem(QPointF(10, 200), QPointF(110, 200))
    defn = BlockDefinition.new(
        name="B", library="L", series="S",
        primitives=[tilted.to_dict(), other.to_dict()], origin=origin,
        constraints=[{"id": "c-h", "type": "horizontal",
                      "refs": [{"uid": tilted._uid, "h": "edge"}]}])
    project.register_block_definition(defn)
    w = BlockEditorWidget(project)
    msgs = []
    w.editor_scene._show_status = lambda m, *a, **k: msgs.append(m)
    w.seed_from_definition(defn)
    sc = w.editor_scene
    ln = next(l for l in sc._draw_lines if l._uid == tilted._uid)
    mean = (20 + 50) / 2.0 - origin[1]
    assert ln._pt1.y() == pytest.approx(mean, abs=1e-6)          # [RED]
    assert ln._pt2.y() == pytest.approx(mean, abs=1e-6)
    assert not sc.can_undo() and msgs == []
    sc.undo()
    assert ln._pt2.y() == pytest.approx(mean, abs=1e-6)
    sc.delete_items([next(l for l in sc._draw_lines if l._uid != tilted._uid)])
    sc.undo()
    (lv,) = [l for l in sc._draw_lines if l._uid == tilted._uid]
    assert lv._pt1.y() == pytest.approx(mean, abs=1e-6)
    assert lv._pt2.y() == pytest.approx(mean, abs=1e-6)


def test_commit_block_saves_and_reopens_constraints(qapp):
    from firepro3d.block_editor import BlockEditorWidget
    project = Model_Space()
    w = BlockEditorWidget(project)
    w.seed_from_dicts([LineItem(QPointF(0, 0), QPointF(100, 30)).to_dict()])
    sc = w.editor_scene
    (ln,) = sc._draw_lines
    sc.constraint_ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    defn = w.commit_block("B", "L", "S")
    assert defn is not None
    assert [c["refs"] for c in defn.constraints] == [[{"uid": ln._uid, "h": "edge"}]]
    w2 = BlockEditorWidget(project)
    w2.seed_from_definition(project.get_block_definition(defn.id))
    assert len(w2.editor_scene.constraint_ctl.active()) == 1
    # Edit-in-place save rewrites the list (a deleted constraint is gone).
    ctl2 = w2.editor_scene.constraint_ctl
    ctl2.delete([ctl2.constraints[0].id])
    w2._edit_block_id = defn.id
    w2.commit_block("B", "L", "S")
    assert project.get_block_definition(defn.id).constraints == []


# ── requirement 5: Rotate / Polar Array re-level a Horizontal line ─────────

def _rotated_twin_ys(p1, p2, deg, pivot=(0.0, 0.0)):
    """Ground truth: an UNCONSTRAINED twin turned by the same real call."""
    twin = LineItem(QPointF(*p1), QPointF(*p2))
    twin.manip_rotate(deg, QPointF(*pivot))
    return twin._pt1, twin._pt2


def test_rotate_commit_relevels_a_horizontal_line_to_the_mean_y(qapp):
    """§8: the rotated handles are W_EDIT goals and the constraint is hard, so
    a Rotate of a Horizontal line lands it level at the mean of the rotated
    end Ys, X kept — the intended CS1 behaviour, not an accident."""
    from tests._snap_polish_helpers import click
    v, sc = _shown_editor(qapp)
    try:
        sc.set_mode("select")
        ln = _line(sc, (0, 0), (100, 0))
        sc.constraint_ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
        t1, t2 = _rotated_twin_ys((0, 0), (100, 0), 30.0)
        assert abs(t1.y() - t2.y()) > 10                       # the twin tilts
        sc.clearSelection(); ln.setSelected(True)
        pos = sc._undo_pos
        sc._modify_ctl.start("rotate")
        click(v, QPointF(0, 0))                                # pivot
        assert sc.begin_dynamic_input() is True
        sc.dynamic_input.editor("Angle").setText("30")
        sc.dynamic_input._accept()
        mean = (t1.y() + t2.y()) / 2.0
        assert ln._pt1.y() == pytest.approx(mean, abs=1e-6)
        assert ln._pt2.y() == pytest.approx(mean, abs=1e-6)
        assert ln._pt1.x() == pytest.approx(t1.x(), abs=1e-6)
        assert ln._pt2.x() == pytest.approx(t2.x(), abs=1e-6)
        assert sc._undo_pos == pos + 1
        snap = sc._undo_stack[sc._undo_pos]["draw_lines"][0]   # solved, then pushed
        sc.undo(); sc.redo()
        (ln2,) = sc._draw_lines
        assert ln2._pt2.y() == pytest.approx(mean, abs=1e-6), snap
    finally:
        _close(v, sc)


def test_polar_array_keeps_horizontal_only_on_copies_it_preserves(qapp):
    """D30: a 6-way polar array of a Horizontal line -- the 180 deg copy keeps
    its Horizontal (a half-turn preserves it); the 60/120/240/300 deg copies
    are FREE and keep their rotated geometry (not re-levelled)."""
    from tests._snap_polish_helpers import click
    from PyQt6.QtTest import QTest
    v, sc = _shown_editor(qapp)
    try:
        sc.set_mode("select")
        ln = _line(sc, (100, 0), (150, 0))
        sc.constraint_ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
        sc.clearSelection(); ln.setSelected(True)
        assert sc._modify_ctl.start("array")
        QTest.keyClick(v.viewport(), Qt.Key.Key_Right)
        QTest.keyClick(v.viewport(), Qt.Key.Key_Right)     # Linear -> 2D -> Polar
        click(v, QPointF(0, 0))                            # centre
        assert sc.begin_dynamic_input() is True
        sc.dynamic_input.editor("Count").setText("6")
        sc.dynamic_input.editor("Total").setText("360")
        sc.dynamic_input._accept()
        assert len(sc._draw_lines) == 6
        ctl = sc.constraint_ctl
        by_angle = {}
        for k in range(1, 6):
            t1, t2 = _rotated_twin_ys((100, 0), (150, 0), 60.0 * k)
            copy = next(l for l in sc._draw_lines
                        if abs(l._pt1.x() - t1.x()) < 1e-3
                        and abs(l._pt1.y() - t1.y()) < 1e-3)
            assert copy._pt2.x() == pytest.approx(t2.x(), abs=1e-6)   # rotated,
            assert copy._pt2.y() == pytest.approx(t2.y(), abs=1e-6)   # not re-levelled  [RED]
            by_angle[60 * k] = copy
        constrained = {c.refs[0]["uid"] for c in ctl.active()}
        assert constrained == {ln._uid, by_angle[180]._uid}
        assert len(ctl.constraints) == 2
    finally:
        _close(v, sc)


# -- review round: I1-I4, D30, M1, M2 -----------------------------------------

def _conflicted_rect(sc):
    """A rect with H(bottom) + H(left): satisfiable only by collapsing (D29),
    so the second is admitted (D9) and held (D10)."""
    r = _rect(sc, (0, 0), (80, 40))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": r._uid, "h": "bottom"}])
    ctl.add("horizontal", [{"uid": r._uid, "h": "left"}])
    assert r.rect().height() == pytest.approx(40.0)
    return r


def _grips(it):
    return [(p.x(), p.y()) for p in it.grip_points()]


def test_rolled_back_move_restores_every_moved_item(qapp):
    """I1: Move [conflicted rect, free line] fails -> the WHOLE move is undone
    (the status says the change was not applied), the free line included."""
    from firepro3d.constraint_controller import CONFLICT_STATUS
    sc = _scene()
    r = _conflicted_rect(sc)
    free = _line(sc, (300, 300), (400, 300))
    r0, f0 = _grips(r), _grips(free)
    msgs = _status(sc)
    sc._selected_items = [r, free]
    sc.move_items(QPointF(10, 10))
    assert _grips(r) == r0
    assert _grips(free) == f0                                            # [RED]
    assert CONFLICT_STATUS in msgs


def test_open_solves_each_group_despite_a_conflict_elsewhere(qapp):
    """I2: an admitted conflict in one group must not block the first solve
    of another: the violated line opens level, the conflicted rect as saved."""
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 30))
    r = _rect(sc, (300, 0), (380, 40))
    r0 = _grips(r)
    sc.constraint_ctl.load([
        {"id": "a", "type": "horizontal", "refs": [{"uid": ln._uid, "h": "edge"}]},
        {"id": "b1", "type": "horizontal", "refs": [{"uid": r._uid, "h": "bottom"}]},
        {"id": "b2", "type": "horizontal", "refs": [{"uid": r._uid, "h": "left"}]}])
    assert ln._pt1.y() == pytest.approx(15.0, abs=1e-6)                 # [RED]
    assert ln._pt2.y() == pytest.approx(15.0, abs=1e-6)
    assert _grips(r) == r0
    assert len(sc.constraint_ctl.active()) == 3


def test_a_size_already_at_its_floor_is_never_driven_below_it(qapp):
    """I3: a zero-height rect tied to a line: the solve must not push h
    negative (write-back would clamp it, so written != solved). The written
    geometry satisfies the constraint."""
    sc = _scene()
    r = _rect(sc, (0, 0), (100, 0))
    ln = _line(sc, (200, 0), (300, 0))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": r._uid, "h": "tl"}, {"uid": ln._uid, "h": "p1"}])
    with ctl.edit([ln]):
        ln.translate(0, 20)
    tl = r.grip_points()[0]
    assert abs(tl.y() - ln._pt1.y()) < 1e-6                             # [RED]
    assert r.rect().height() >= 0.0


def test_an_arc_span_sign_flip_is_a_conflict(qapp):
    """I3 arc: centre and start pinned to the X axis, the end tied to a line
    end moved below the centre. With the radius stiff the only answer flips
    the span negative (40 deg -> about -6 deg, which write-back would draw as
    a 354 deg arc): a collapse, so the edit is held."""
    from firepro3d.constraint_controller import CONFLICT_STATUS
    from firepro3d.geometry_2d import ArcItem
    sc = _scene()
    arc = ArcItem(QPointF(0, 0), 100.0, 0.0, 40.0)
    sc.addItem(arc); sc._draw_arcs.append(arc)
    ey = -100.0 * math.sin(math.radians(40.0))
    ln = _line(sc, (200, ey), (300, ey))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": arc._uid, "h": "center"}, {"ref": "origin"}])
    ctl.add("horizontal", [{"uid": arc._uid, "h": "start"}, {"ref": "origin"}])
    ctl.add("horizontal", [{"uid": arc._uid, "h": "end"}, {"uid": ln._uid, "h": "p1"}])
    a0 = (arc._radius, arc._start_deg, arc._span_deg)
    l0 = _grips(ln)
    msgs = _status(sc)
    with ctl.edit([ln]):
        ln.translate(0, 10.0 - ey)                    # p1 to y = +10 (below)
    assert (arc._radius, arc._start_deg, arc._span_deg) == a0           # [RED]
    assert _grips(ln) == l0
    assert CONFLICT_STATUS in msgs


def test_add_refuses_refs_that_do_not_validate(qapp):
    """I4: single point / X-axis ground / unknown handle / same handle twice /
    unknown uid / junk -> None, list untouched, "Invalid constraint"; later
    edits of the item still work (no poisoned list)."""
    from firepro3d.constraint_controller import INVALID_STATUS
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 30))
    ctl = sc.constraint_ctl
    msgs = _status(sc)
    bad = [[{"uid": ln._uid, "h": "p1"}],
           [{"uid": ln._uid, "h": "p1"}, {"ref": "x_axis"}],
           [{"uid": ln._uid, "h": "bogus"}],
           [{"uid": ln._uid, "h": "p1"}, {"uid": ln._uid, "h": "p1"}],
           [{"uid": "nope", "h": "edge"}],
           ["junk"]]
    for refs in bad:
        assert ctl.add("horizontal", refs) is None, refs                 # [RED]
    assert ctl.constraints == []
    assert msgs == [INVALID_STATUS] * len(bad)
    with ctl.edit([ln]):
        ln.translate(5, 0)
    assert ln._pt1.x() == 5.0


def test_open_keeps_an_unknown_handle_record_inert_and_saves_it(qapp):
    """I4: a definition whose record names a handle this build does not know
    (a newer build's, or a stale v9) opens, never solves it, and saves it
    back verbatim."""
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.block_editor import BlockEditorWidget
    project = Model_Space()
    tilted = LineItem(QPointF(0, 0), QPointF(100, 30))
    rec = {"id": "c-x", "type": "horizontal", "refs": [{"uid": tilted._uid, "h": "v9"}],
           "future": {"k": 1}}
    defn = BlockDefinition.new(name="B", library="L", series="S",
                               primitives=[tilted.to_dict()], origin=(0, 0),
                               constraints=[rec])
    project.register_block_definition(defn)
    w = BlockEditorWidget(project)
    w.seed_from_definition(defn)                                         # [RED]
    sc = w.editor_scene
    (ln,) = sc._draw_lines
    assert (ln._pt1.y(), ln._pt2.y()) == (0.0, 30.0)                    # not solved
    assert sc.constraint_ctl.active() == []
    with sc.constraint_ctl.edit([ln]):
        ln.translate(0, 5)
    w._edit_block_id = defn.id
    w.commit_block("B", "L", "S")
    assert project.get_block_definition(defn.id).constraints == [rec]


def test_paste_of_a_malformed_clipboard_record_does_not_crash(qapp):
    """I4: clipboard JSON is untrusted -- malformed constraint records are
    dropped / kept inert; the paste lands and later edits work."""
    import json
    from firepro3d.constants import CLIPBOARD_FORMAT_VERSION
    sc = _scene()
    src = LineItem(QPointF(0, 0), QPointF(100, 0))
    payload = {"fp3d_clipboard": CLIPBOARD_FORMAT_VERSION, "base": [0, 0],
               "scene_role": "block_editor", "items": [src.to_dict()],
               "constraints": [{"id": "m", "type": "horizontal",
                                "refs": [{"uid": src._uid}]},
                               {"id": "n", "type": "horizontal",
                                "refs": [{"uid": src._uid, "h": "zz"}]},
                               5, "junk", {"type": "horizontal", "refs": "x"}]}
    QApplication.clipboard().setText(json.dumps(payload))
    new = sc.paste_items(QPointF(0, 50))                                 # [RED]
    assert len(new) == 1
    assert sc.constraint_ctl.active() == []
    with sc.constraint_ctl.edit(new):
        new[0].translate(1, 0)
    assert new[0]._pt1.x() == 1.0
    QApplication.clipboard().setText(json.dumps(
        {"fp3d_clipboard": CLIPBOARD_FORMAT_VERSION, "base": [0, 0],
         "scene_role": "block_editor", "items": [src.to_dict()], "constraints": 7}))
    assert len(sc.paste_items(QPointF(0, 90))) == 1


def test_conflict_status_survives_the_tools_success_message(qapp):
    """M1: a rolled-back Scale commit -- the tool posts its own status after
    the edit context exits; the conflict status must be the one left showing."""
    from firepro3d.constraint_controller import CONFLICT_STATUS
    sc = _scene()
    r = _conflicted_rect(sc)
    r0 = _grips(r)
    msgs = _status(sc)
    sc._scale_base = QPointF(0, 0)
    sc._selected_items = [r]
    sc._modify_ctl.commit_scale(2.0)
    QApplication.processEvents()
    assert _grips(r) == r0
    assert msgs and msgs[-1] == CONFLICT_STATUS                          # [RED]


def _sub_floor_item_follows(sc, item, msgs):
    """Shared body: H(item.center, line.p1) -- add and later line edits
    succeed silently although *item*'s size is already below its floor (the
    solve never moves it)."""
    ln = _line(sc, (200, 10), (300, 10))
    ctl = sc.constraint_ctl
    c = ctl.add("horizontal", [{"uid": item._uid, "h": "center"},
                               {"uid": ln._uid, "h": "p1"}])
    assert c is not None
    assert abs(item._center.y() - ln._pt1.y()) < 1e-6                   # [RED]
    for dy in (25.0, -40.0):
        with ctl.edit([ln]):
            ln.translate(0, dy)
        assert abs(item._center.y() - ln._pt1.y()) < 1e-6
    assert msgs == []


def test_a_circle_already_below_its_floor_does_not_block_its_group(qapp):
    """Re-review: CircleItem's ctor does not clamp (r = 0.5 < the 1 mm floor);
    D29 must only flag a below-floor size the solve CHANGED."""
    from firepro3d.geometry_2d import CircleItem
    sc = _scene()
    circ = CircleItem(QPointF(0, 0), 0.5)
    sc.addItem(circ); sc._draw_circles.append(circ)
    msgs = _status(sc)
    _sub_floor_item_follows(sc, circ, msgs)
    assert circ._radius == 0.5


def test_a_zero_radius_polygon_does_not_block_its_group(qapp):
    """Re-review: RegularPolygonItem defaults to radius 0.0 (< the 0.5 floor)."""
    from firepro3d.geometry_2d import RegularPolygonItem
    sc = _scene()
    poly = RegularPolygonItem(QPointF(0, 0))
    assert poly._radius_mm == 0.0
    sc.addItem(poly); sc._draw_polygons.append(poly)
    msgs = _status(sc)
    _sub_floor_item_follows(sc, poly, msgs)


def test_the_same_handle_twice_is_refused_whatever_the_extra_keys(qapp):
    """Duplicate refs compare by identity (uid, h) / ground, not whole dicts."""
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 30))
    ctl = sc.constraint_ctl
    _status(sc)
    assert ctl.add("horizontal", [{"uid": ln._uid, "h": "p1"},
                                  {"uid": ln._uid, "h": "p1", "note": 1}]) is None   # [RED]
    assert ctl.add("horizontal", [{"ref": "origin"}, {"ref": "origin", "x": 0}]) is None
    assert ctl.constraints == []


def _typed_follower(sc):
    """A 3-4-5 line (length 100) whose p2 is Horizontal to a follower's p1."""
    from firepro3d.scale_manager import ScaleManager
    sc.scale_manager = ScaleManager()
    t = _line(sc, (0, 100), (60, 180))
    f = _line(sc, (300, 180), (400, 180))
    sc.constraint_ctl.add("horizontal", [{"uid": t._uid, "h": "p2"},
                                         {"uid": f._uid, "h": "p1"}])
    return t, f


def test_panel_typed_length_is_honoured_exactly(qapp):
    """D31 (panel seam): a typed Length lands EXACTLY; the follower yields;
    the anchor p1 (unchanged by the typed setter) stays put."""
    from firepro3d.property_manager import PropertyManager
    sc = _scene()
    t, f = _typed_follower(sc)
    sc.push_undo_state()
    pm = PropertyManager()
    try:
        pm.show_properties([t])
        msgs = _status(sc)
        pm._apply_property("Length", 200.0)
        assert t.line().length() == pytest.approx(200.0, abs=1e-6)      # [RED]
        assert (t._pt1.x(), t._pt1.y()) == pytest.approx((0.0, 100.0), abs=1e-6)
        assert (t._pt2.x(), t._pt2.y()) == pytest.approx((120.0, 260.0), abs=1e-6)
        assert f._pt1.y() == pytest.approx(t._pt2.y(), abs=1e-6)       # follower yields
        assert msgs == [] or all(m != "Over-constrained: the change was not applied"
                                 for m in msgs)
    finally:
        pm.deleteLater()


def test_transform_edit_is_not_typed_and_keeps_w_edit(qapp):
    """D31 boundary: transforms stay W_EDIT (not typed) -- a Rotate of a
    Horizontal line still re-levels to the mean (both ends yield)."""
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 0))
    sc.constraint_ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    t1, t2 = _rotated_twin_ys((0, 0), (100, 0), 30.0)
    with sc.constraint_ctl.edit([ln]):
        ln.manip_rotate(30.0, QPointF(0, 0))
    mean = (t1.y() + t2.y()) / 2.0
    assert ln._pt1.y() == pytest.approx(mean, abs=1e-6)
    assert ln._pt2.y() == pytest.approx(mean, abs=1e-6)


def test_a_typed_edit_that_cannot_be_met_holds_and_reports(qapp):
    """D31 + D10: a line whose p2 is Horizontal to the origin (y fixed at 0).
    A typed Length moves p2 off y = 0 along the line; nothing can yield
    (p2's y is grounded, p1 cannot move p2), so the typed value cannot be
    honoured -> conflict: the line holds and the status says so."""
    from firepro3d.constraint_controller import CONFLICT_STATUS
    from firepro3d.property_manager import PropertyManager
    from firepro3d.scale_manager import ScaleManager
    sc = _scene()
    sc.scale_manager = ScaleManager()
    t = _line(sc, (0, 100), (60, 0))
    sc.constraint_ctl.add("horizontal", [{"uid": t._uid, "h": "p2"}, {"ref": "origin"}])
    g0 = _grips(t)
    sc.push_undo_state()
    pm = PropertyManager()
    try:
        pm.show_properties([t])
        msgs = _status(sc)
        pm._apply_property("Length", 200.0)
        QApplication.processEvents()
        assert _grips(t) == g0                                           # [RED]
        assert msgs and msgs[-1] == CONFLICT_STATUS
    finally:
        pm.deleteLater()


def test_focus_on_nothing_solves_nothing(qapp):
    """M2: a solve focused on items that carry no solver variables is a
    no-op, not a whole-sketch solve (which would re-report a held conflict)."""
    sc = _scene()
    _conflicted_rect(sc)
    assert sc.constraint_ctl._solve(focus=set()) is True                 # [RED]


# ── requirement 6: typed-edit seams solve BEFORE the undo push ─────────────

def _rect_and_follower(sc):
    """Rect (0,0)-(100,100) whose top-right is Horizontal to a line's p1."""
    r = _rect(sc, (0, 0), (100, 100))
    ln = _line(sc, (200, 0), (300, 0))
    sc.constraint_ctl.add("horizontal", [{"uid": r._uid, "h": "tr"},
                                         {"uid": ln._uid, "h": "p1"}])
    return r, ln


def test_readout_typed_edit_solves_before_the_undo_push(qapp):
    from firepro3d.scale_manager import ScaleManager
    v, sc = _shown_editor(qapp)
    try:
        sc.scale_manager = ScaleManager()
        sc.set_mode("select")
        r, ln = _rect_and_follower(sc)
        sc.clearSelection(); r.setSelected(True)
        qapp.processEvents()
        lay = next(e for e in sc.readouts.layouts(v) if e.spec.key == "height")
        sc.readouts.begin_edit(v, lay)
        pos = sc._undo_pos
        sc.readouts.hud.committed.emit({"Height": 50.0})
        tr = r.grip_points()[2]
        assert ln._pt1.y() == pytest.approx(tr.y(), abs=1e-6)
        assert ln._pt1.y() > 49.0                        # the follower moved   [RED]
        assert sc._undo_pos == pos + 1
        sc.undo(); sc.redo()                             # the pushed snapshot
        (ln2,) = sc._draw_lines
        assert ln2._pt1.y() == pytest.approx(ln._pt1.y(), abs=1e-6)
    finally:
        if sc.readouts.is_editing():
            sc.readouts.cancel_edit()
        _close(v, sc)


def test_panel_edit_solves_before_the_coalesced_undo_push(qapp):
    from firepro3d.property_manager import PropertyManager
    sc = _scene()
    r, ln = _rect_and_follower(sc)
    sc.push_undo_state()
    pm = PropertyManager()
    try:
        pm.show_properties([r])
        pos = sc._undo_pos
        pm._apply_property("Height", 50.0)
        tr = r.grip_points()[2]
        assert ln._pt1.y() == pytest.approx(tr.y(), abs=1e-6)
        assert ln._pt1.y() > 49.0
        assert sc._undo_pos == pos + 1                   # still one step
        sc.undo(); sc.redo()                             # the pushed snapshot
        (ln2,) = sc._draw_lines
        assert ln2._pt1.y() == pytest.approx(ln._pt1.y(), abs=1e-6)   # [RED]
    finally:
        pm.deleteLater()


# ── requirement 7: clipboard + Mirror ──────────────────────────────────────

def test_copy_paste_through_the_clipboard_payload_remaps(qapp):
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 0))
    sc.constraint_ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    assert sc._modify_ctl.write_clipboard([ln], QPointF(0, 0)) == 1
    payload = sc.clipboard_payload()
    assert [c["refs"] for c in payload["constraints"]] == [[{"uid": ln._uid, "h": "edge"}]]
    new = sc.paste_items(QPointF(0, 50))                 # data from the clipboard
    assert len(new) == 1 and new[0]._uid != ln._uid
    assert [c.refs[0]["uid"] for c in sc.constraint_ctl.constraints] == \
        [ln._uid, new[0]._uid]


def test_commit_paste_and_duplicate_carry_internal_constraints(qapp):
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 0))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    sc._modify_ctl.write_clipboard([ln], QPointF(0, 0))
    sc._paste_payload = sc.clipboard_payload()
    sc._modify_ctl.commit_paste(QPointF(0, 50))
    sc._selected_items = [ln]
    sc._modify_ctl.commit_duplicate(QPointF(0, 100))
    assert len(sc._draw_lines) == 3
    assert sorted(c.refs[0]["uid"] for c in ctl.constraints) == \
        sorted(l._uid for l in sc._draw_lines)


def _mirror_across(qapp, axis_p1, axis_p2, hover):
    from tests._modify_tools_helpers import ignore_os_mouse
    from tests._snap_polish_helpers import click, move
    v, sc = _shown_editor(qapp)
    ignore_os_mouse(v)
    sc.set_mode("select")
    rl = ReferenceLineItem(QPointF(*axis_p1), QPointF(*axis_p2))
    sc.addItem(rl); sc._reference_lines.append(rl)
    ln = _line(sc, (0, 0), (100, 0))
    sc.constraint_ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    sc.clearSelection(); ln.setSelected(True)
    sc._modify_ctl.start("mirror")
    move(v, QPointF(*hover)); click(v, QPointF(*hover))
    return v, sc, ln


def test_mirror_across_an_axis_aligned_axis_keeps_horizontal(qapp):
    v, sc, ln = _mirror_across(qapp, (200, -500), (200, 500), (202, 250))
    try:
        copy = next(l for l in sc._draw_lines if l is not ln)
        assert (copy._pt1.x(), copy._pt2.x()) == (400.0, 300.0)      # reflected
        assert [c.refs[0]["uid"] for c in sc.constraint_ctl.constraints] == \
            [ln._uid, copy._uid]
    finally:
        _close(v, sc)


def test_mirror_across_a_diagonal_axis_drops_horizontal(qapp):
    """CS1 rule: across a non-axis-aligned axis the reflected line is no longer
    horizontal, so the copied Horizontal is dropped (not re-solved)."""
    v, sc, ln = _mirror_across(qapp, (200, -300), (500, 0), (400, -100))
    try:
        assert len(sc._draw_lines) == 2
        copy = next(l for l in sc._draw_lines if l is not ln)
        assert abs(copy._pt1.y() - copy._pt2.y()) > 1                # tilted copy
        assert [c.refs[0]["uid"] for c in sc.constraint_ctl.constraints] == [ln._uid]
    finally:
        _close(v, sc)



# ── D18: a controller drag frame on a 200-primitive / 300-constraint sketch ─

@pytest.mark.perf
def test_d18_controller_drag_frame_bar(qapp):
    """The cached drag context (System reused, only the dragged item's
    component solved) keeps one real ``ConstraintController.drag`` frame —
    x refresh + solve + write-back + last-good — under the 8 ms bar."""
    import time
    sc = _scene()
    lines = [_line(sc, (i * 150.0, 0.0), (i * 150.0 + 100.0, 0.0)) for i in range(200)]
    ctl = sc.constraint_ctl
    recs = [{"id": f"h{i}", "type": "horizontal",
             "refs": [{"uid": ln._uid, "h": "edge"}]} for i, ln in enumerate(lines)]
    recs += [{"id": f"j{i}", "type": "horizontal",
              "refs": [{"uid": lines[i]._uid, "h": "p2"},
                       {"uid": lines[i + 1]._uid, "h": "p1"}]} for i in range(100)]
    ctl.load(recs)
    assert len(ctl.active()) == 300
    ln = lines[50]
    ctl.begin_drag(ln)
    ts = []
    for k in range(31):
        ln.apply_grip(2, QPointF(ln._pt2.x(), float(k % 7)))
        t = time.perf_counter()
        ctl.drag(ln, 2)
        ts.append((time.perf_counter() - t) * 1e3)
    ctl.end_drag()
    med = sorted(ts)[len(ts) // 2]
    print(f"controller drag frame median {med:.2f} ms")
    assert abs(lines[0]._pt1.y() - ln._pt2.y()) < 1e-6      # the chain followed
    assert med <= 8.0, f"drag frame {med:.2f} ms"
