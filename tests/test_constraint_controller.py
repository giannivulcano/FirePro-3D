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
    (H) may legitimately shrink.

    Rewritten in fix round A (VC5): D34 (translate, then resize) made the
    original scenario TRANSLATE the free rect instead of shrinking it, so the
    rect's bottom is now held on the X axis (H(bl/br, origin)) -- shrinking
    is the only way for it to follow, which is the D29 contract under test."""
    sc = _scene()
    r = _rect(sc, (0, -100), (100, 0))
    ln = _line(sc, (200, -100), (300, -100))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": r._uid, "h": "bl"}, {"ref": "origin"}])
    ctl.add("horizontal", [{"uid": r._uid, "h": "br"}, {"ref": "origin"}])
    ctl.add("horizontal", [{"uid": r._uid, "h": "tr"}, {"uid": ln._uid, "h": "p1"}])
    assert r.rect().height() == pytest.approx(100.0, abs=1e-6)
    msgs = _status(sc)
    with ctl.edit([ln]):
        ln.translate(0, 30)
    tr = r.grip_points()[2]
    assert abs(tr.y() - ln._pt1.y()) < 1e-6
    assert tr.y() > -100.0 + 1.0                          # the rect followed
    assert 1.0 < r.rect().height() < 100.0 - 1.0          # ... by shrinking
    assert r.grip_points()[6].y() == pytest.approx(0.0, abs=1e-6)   # bottom held
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


def _collapsing_pair(sc):
    """CS2 (D37 retired the persistently conflicted rect as an edit blocker):
    L (0,0)-(100,0) Horizontal, L.p1 Vertical to the origin, L.p2 Vertical to
    M.p1 -- all satisfied. Moving / scaling [L, M] so L.p2's goal lands on
    L.p1's X can only be solved by shrinking L to a point (D36): an EDIT-time
    conflict, so the whole commit rolls back."""
    L = _line(sc, (0, 0), (100, 0))
    M = _line(sc, (100, 50), (200, 50))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": L._uid, "h": "edge"}])
    ctl.add("vertical", [{"uid": L._uid, "h": "p1"}, {"ref": "origin"}])
    ctl.add("vertical", [{"uid": L._uid, "h": "p2"}, {"uid": M._uid, "h": "p1"}])
    assert ctl.red == set()
    return L, M


def _grips(it):
    return [(p.x(), p.y()) for p in it.grip_points()]


def test_rolled_back_move_restores_every_moved_item(qapp):
    """I1: Move [L, M, free line] fails (D36 edit-time collapse) -> the WHOLE
    move is undone (the status says the change was not applied), the free
    line included."""
    from firepro3d.constraint_controller import CONFLICT_STATUS
    sc = _scene()
    L, M = _collapsing_pair(sc)
    free = _line(sc, (300, 300), (400, 300))
    l0, m0, f0 = _grips(L), _grips(M), _grips(free)
    msgs = _status(sc)
    sc._selected_items = [L, M, free]
    sc.move_items(QPointF(-100, 10))
    assert _grips(L) == l0 and _grips(M) == m0
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
    # D37/D38 (CS2): all three are admitted; the one whose admission broke the
    # rect's group (b2, list order) is red and sits out of active().
    assert len(sc.constraint_ctl.constraints) == 3
    assert sc.constraint_ctl.red == {"b2"}
    assert [c.id for c in sc.constraint_ctl.active()] == ["a", "b1"]


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
    L, M = _collapsing_pair(sc)
    l0 = _grips(L)
    msgs = _status(sc)
    sc._scale_base = QPointF(200, 0)
    sc._selected_items = [L, M]
    sc._modify_ctl.commit_scale(2.0)
    QApplication.processEvents()
    assert _grips(L) == l0
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


# ── fix round A (VC9 F1): Explode / emptied-text removal cascade (§8) ──────

def _nested_instance(sc, pos=(50.0, 30.0)):
    from firepro3d.block_definition import BlockDefinition
    d = BlockDefinition.new(name="n", library="L", series="S", origin=(0, 0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(10, 0)).to_dict()])
    sc.register_block_definition(d)
    return sc.place_block_instance(d.id, pos)


def test_exploding_a_constrained_nested_instance_cascades_its_constraints(qapp):
    """§8: Explode drops the constraints on the exploded instance's ``ins``
    in the SAME undo step, with the status "N constraint(s) removed"; undo
    brings the instance AND a live (not "Unsupported") constraint back."""
    from PyQt6.QtWidgets import QGraphicsView
    from firepro3d import constraint_paint as cp
    sc = _scene()
    sc.push_undo_state()
    inst = _nested_instance(sc)
    ln = _line(sc, (0, 0), (100, 10))
    ctl = sc.constraint_ctl
    c = ctl.add("horizontal", [{"uid": inst._uid, "h": "ins"}, {"uid": ln._uid, "h": "p1"}])
    assert c is not None
    view = QGraphicsView(sc)
    msgs = _status(sc)
    sc.clearSelection()
    inst.setSelected(True)
    new = sc.explode_selected_blocks()                    # the real Explode entry
    assert new and inst.scene() is None
    assert ctl.constraints == []                                         # [RED]
    assert ctl.constraints_on(ln) == []
    assert ctl.to_records() == []
    ctl.show_all = True                        # D32: every glyph would show
    assert cp.glyph_layouts(view, ctl) == []
    ctl.show_all = False
    assert "1 constraint removed" in msgs
    assert sc._undo_stack[-1]["constraints"] == []        # cascade inside the step
    sc.undo()
    (back,) = sc._block_instances
    assert back._uid == inst._uid
    assert [ctl.kind_text(x) for x in ctl.constraints] == ["Horizontal"]
    assert [x.id for x in ctl.active()] == [c.id]
    sc.redo()
    assert sc._block_instances == [] and ctl.constraints == []


def test_emptying_a_constrained_text_in_place_cascades_its_constraints(qapp):
    """§8 delete: a text emptied in its inline session is deleted -- its
    constraints cascade in that one undo step; undo restores both."""
    from firepro3d.text_item import TextAnnotationData, TextItem
    sc = _scene()
    sc.push_undo_state()
    d = TextAnnotationData(text="Hi", x=0.0, y=40.0, height_mm=40.0, wrap_width_mm=600.0)
    t = TextItem(d)
    sc.addItem(t); sc._texts.append(t); t._apply_format()
    ln = _line(sc, (100, 0), (200, 0))
    ctl = sc.constraint_ctl
    c = ctl.add("horizontal", [{"uid": t._uid, "h": "ins"}, {"uid": ln._uid, "h": "p1"}])
    assert c is not None
    n = len(sc._undo_stack)
    sc._text_edit_ctl.begin(t)
    t.setPlainText("   ")
    sc.commit_text_edit()
    assert sc._texts == []
    assert len(sc._undo_stack) == n + 1
    assert ctl.constraints == [] and ctl.constraints_on(ln) == []        # [RED]
    assert sc._undo_stack[-1]["constraints"] == []
    sc.undo()
    assert len(sc._texts) == 1
    assert [x.id for x in ctl.active()] == [c.id]


# ── fix round A (VC9 F5): inert records on adapter-less primitives (§6.4) ──

def test_an_inert_record_on_a_spline_survives_save_and_reopen(qapp):
    """AC7: a newer build's record on a spline (no adapter in v1) is inert,
    and Save writes it back verbatim -- through a reopen and a second Save."""
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.block_editor import BlockEditorWidget
    from firepro3d.geometry_2d import SplineItem
    project = Model_Space()
    sp = SplineItem([QPointF(0, 0), QPointF(10, 10), QPointF(20, 0), QPointF(30, 10)])
    ln = LineItem(QPointF(0, 50), QPointF(100, 50))
    rec = {"id": "c-sp", "type": "tangent_spline_future",
           "refs": [{"uid": sp._uid, "h": "curve"}, {"uid": ln._uid, "h": "edge"}],
           "future": {"k": 1}}
    defn = BlockDefinition.new(name="B", library="L", series="S", origin=(0, 0),
                               primitives=[sp.to_dict(), ln.to_dict()], constraints=[rec])
    project.register_block_definition(defn)
    w = BlockEditorWidget(project)
    w.seed_from_definition(defn)
    ctl = w.editor_scene.constraint_ctl
    assert [c.inert for c in ctl.constraints] == [True]
    w._edit_block_id = defn.id
    w.commit_block("B", "L", "S")
    assert project.get_block_definition(defn.id).constraints == [rec]    # [RED]
    w2 = BlockEditorWidget(project)                     # reopen + save again
    w2.seed_from_definition(project.get_block_definition(defn.id))
    w2._edit_block_id = defn.id
    w2.commit_block("B", "L", "S")
    assert project.get_block_definition(defn.id).constraints == [rec]


# ── fix round A (VC9 F4, D34): translate, then resize, then rotate ─────────

def test_adding_horizontal_to_a_rect_corner_translates_the_rect(qapp):
    """D34: H(rect.br, line.p1) on an axis-aligned 200x100 rect keeps its
    size and angle -- the rect and the line end meet halfway (both translate)."""
    sc = _scene()
    r = _rect(sc, (0, 0), (200, 100))
    ln = _line(sc, (-300, 0), (-400, 50))
    sc.constraint_ctl.add("horizontal", [{"uid": r._uid, "h": "br"}, {"uid": ln._uid, "h": "p1"}])
    assert r.rect().width() == pytest.approx(200.0, abs=1e-6)
    assert r.rect().height() == pytest.approx(100.0, abs=1e-6)          # [RED]
    assert abs(math.remainder(r._angle, 360.0)) < math.degrees(1e-6)
    br = r.grip_points()[4]
    assert br.y() == pytest.approx(ln._pt1.y(), abs=1e-6)
    assert br.y() == pytest.approx(50.0, abs=0.5)                        # halfway
    assert r.grip_points()[0].x() == pytest.approx(0.0, abs=1e-6)        # pure translate


# ── fix round A (VC9 F2): a constrained rotated-rect grip drag tracks ──────

def _drag_rect_corner(qapp, constrained):
    """Drag the 200x100 @30 deg rect's ``br`` grip through the REAL
    manipulator + RectGripHandle path. Returns (cursor, br, tl0, tl, pivot,
    press-time centre)."""
    v, sc = _shown_editor(qapp)
    try:
        sc._snap_enabled = False                          # cursor == drag point
        r = _rect(sc, (0, 0), (200, 100))
        r.set_angle(30.0, None)
        tl = r.grip_points()[0]
        ln = _line(sc, (tl.x() - 300, tl.y()), (tl.x() - 400, tl.y() + 50))
        if constrained:
            assert sc.constraint_ctl.add(
                "horizontal", [{"uid": r._uid, "h": "br"}, {"uid": ln._uid, "h": "p1"}])
        r.setSelected(True)
        qapp.processEvents()
        tl0, br0 = QPointF(r.grip_points()[0]), QPointF(r.grip_points()[4])
        c0 = QPointF(r.grip_points()[8])
        m = sc._live_manip()
        h = r.manip_handles()[4]
        m._begin_handle(h, br0, QPointF(v.mapFromScene(br0)))
        cur = br0
        for k in range(1, 6):
            cur = QPointF(br0.x() + 10 * k, br0.y() + 7 * k)
            m._update(cur, Qt.KeyboardModifier.NoModifier, QPointF(v.mapFromScene(cur)))
        m._finish(cur, Qt.KeyboardModifier.NoModifier)
        br, tl1 = QPointF(r.grip_points()[4]), QPointF(r.grip_points()[0])
        if constrained:
            assert abs(br.y() - ln._pt1.y()) < 1e-6        # the constraint held
        return cur, br, tl0, tl1, r._pivot, c0
    finally:
        _close(v, sc)


# ── fix round A (D33): polygon vertex / edge handles in the solver ─────────

def _polygon(sc, **kw):
    from firepro3d.geometry_2d import RegularPolygonItem
    p = RegularPolygonItem(QPointF(0, 0), **kw)
    sc.addItem(p); sc._draw_polygons.append(p)
    return p


def test_build_cache_never_serves_a_changed_polygon(qapp):
    """D18 build cache: a polygon side-count change is a structural miss;
    an unchanged sketch reuses the System with x re-read."""
    sc = _scene()
    p = _polygon(sc, sides=5, radius_mm=40.0)
    ln = _line(sc, (0, 100), (50, 120))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": p._uid, "h": "v0"}, {"uid": ln._uid, "h": "p1"}])
    s1, slots, _b = ctl._build(ctl.active())
    ln.translate(0.0, 7.0)
    s1b, _sl, _b = ctl._build(ctl.active())
    off = slots[ln._uid][2]
    assert s1b is s1 and s1.x[off + 1] == pytest.approx(ln._pt1.y())   # x re-read
    p._sides = 7
    s2, _sl, _b = ctl._build(ctl.active())
    assert s2 is not s1


def test_polygon_handles_are_pick_candidates(qapp):
    from firepro3d.constraint_controller import PickState
    sc = _scene()
    p = _polygon(sc, sides=5, radius_mm=40.0, rotation_deg=10.0)
    names = {(k, r.get("h")) for k, r, _a, _b in PickState(sc.constraint_ctl,
                                                            "horizontal")._candidates()
             if r.get("uid") == p._uid}
    assert names == ({("point", "center")} | {("point", f"v{i}") for i in range(5)}
                     | {("edge", f"s{i}") for i in range(5)})


@pytest.mark.parametrize("inscribed", [True, False])
def test_horizontal_on_a_polygon_edge_levels_it_by_rotating(qapp, inscribed):
    """D33 + D28: nothing but a rotation levels an edge (a translate can't;
    shrinking R to 0 collapses, D29) -- R and the centre stay."""
    sc = _scene()
    p = _polygon(sc, sides=6, radius_mm=50.0, rotation_deg=15.0, inscribed=inscribed)
    c = sc.constraint_ctl.add("horizontal", [{"uid": p._uid, "h": "s0"}])
    assert c is not None
    g = p.grip_points()
    assert g[1].y() == pytest.approx(g[2].y(), abs=1e-6)                # v0, v1 level
    assert p._radius_mm == pytest.approx(50.0, abs=1e-6)
    assert (p._center.x(), p._center.y()) == pytest.approx((0.0, 0.0), abs=1e-6)
    assert abs(math.remainder(p._rotation_deg - 15.0, 360.0)) > 1.0      # it rotated


def test_horizontal_between_a_polygon_vertex_and_a_line_end_translates(qapp):
    """D34: the polygon meets the line end by moving (R and rotation kept)."""
    sc = _scene()
    p = _polygon(sc, sides=6, radius_mm=50.0, rotation_deg=15.0)
    ln = _line(sc, (200, 100), (300, 100))
    v2 = QPointF(p.grip_points()[3])
    sc.constraint_ctl.add("horizontal", [{"uid": p._uid, "h": "v2"}, {"uid": ln._uid, "h": "p1"}])
    assert p.grip_points()[3].y() == pytest.approx(ln._pt1.y(), abs=1e-6)
    assert p._radius_mm == pytest.approx(50.0, abs=1e-6)
    assert p._rotation_deg == pytest.approx(15.0, abs=1e-6)
    assert p._center.x() == pytest.approx(0.0, abs=1e-6)
    assert ln._pt1.y() == pytest.approx((v2.y() + 100.0) / 2.0, abs=0.5)   # met halfway


@pytest.mark.parametrize("constrained", [False, True])
def test_a_constrained_rotated_rect_grip_drag_tracks_the_cursor(qapp, constrained):
    """VC9 F2: with H(br, line.p1) the drag behaves like the free one -- the
    corner tracks, the opposite corner stays, and the solver never re-writes
    the dragged rect (its ~1e-9 pin leakage is below the write tolerance), so
    the press-time pivot pin survives exactly as in a free drag (§5.3)."""
    cur, br, tl0, tl, pivot, c0 = _drag_rect_corner(qapp, constrained)
    assert math.dist(_xy(cur), _xy(br)) <= 0.5                          # [RED]
    assert math.dist(_xy(tl0), _xy(tl)) <= 0.5            # the opposite corner stays
    assert pivot is not None and math.dist(_xy(pivot), _xy(c0)) < 1e-9


def _xy(p):
    return (p.x(), p.y())


def _self_constrained_rect_drag(qapp, steps):
    """H(tl, br) on a rotated rect, then drag ``br`` (real manipulator path)
    to the same end point in *steps* frames. Returns the final grips."""
    v, sc = _shown_editor(qapp)
    try:
        sc._snap_enabled = False
        r = _rect(sc, (0, 0), (200, 100))
        r.set_angle(30.0, None)
        assert sc.constraint_ctl.add("horizontal", [{"uid": r._uid, "h": "tl"},
                                                    {"uid": r._uid, "h": "br"}])
        r.setSelected(True)
        qapp.processEvents()
        br0 = QPointF(r.grip_points()[4])
        m = sc._live_manip()
        m._begin_handle(r.manip_handles()[4], br0, QPointF(v.mapFromScene(br0)))
        for k in range(1, steps + 1):
            cur = QPointF(br0.x() + 40.0 * k / steps, br0.y() + 25.0 * k / steps)
            m._update(cur, Qt.KeyboardModifier.NoModifier, QPointF(v.mapFromScene(cur)))
        m._finish(cur, Qt.KeyboardModifier.NoModifier)
        g = r.grip_points()
        assert abs(g[0].y() - g[4].y()) < 1e-6              # the constraint held
        return [_xy(p) for p in g]
    finally:
        _close(v, sc)


def test_a_rect_drag_the_solver_rotates_is_path_independent(qapp):
    """VC9 F2 (material write-back): when the solve really rotates the dragged
    rect each frame (its own H(tl, br)), the write canonicalises its pivot;
    the grip must re-apply every frame from its press-time pose, so the
    result depends on the end point only, not on the frames taken."""
    one, six = _self_constrained_rect_drag(qapp, 1), _self_constrained_rect_drag(qapp, 6)
    assert max(math.dist(p, q) for p, q in zip(one, six)) < 1e-6         # [RED]


# ── CS2 D36: an edge the solve collapses to zero length is a conflict ───────

def _status_log(sc):
    log = []
    sc._show_status = lambda m, t=0: log.append(m)
    return log


def test_d36_h_then_v_on_one_line_is_a_conflict_line_holds(qapp):
    sc = _scene()
    log = _status_log(sc)
    ln = _line(sc, (0, 0), (100, 30))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    v = ctl.add("vertical", [{"uid": ln._uid, "h": "edge"}])
    assert v is not None                                   # D9 admitted
    assert (ln._pt1.x(), ln._pt1.y(), ln._pt2.x(), ln._pt2.y()) == pytest.approx(
        (0.0, 15.0, 100.0, 15.0), abs=1e-6)                # held, not a point
    assert "Over-constrained: the change was not applied" in log


def test_d36_polyline_segment_collapse_is_a_conflict(qapp):
    from firepro3d.geometry_2d import PolylineItem
    sc = _scene()
    pl = PolylineItem(QPointF(0, 0))
    for q in (QPointF(100, 30), QPointF(200, 0)):
        pl.append_point(q)
    sc.addItem(pl); sc._polylines.append(pl)
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": pl._uid, "h": "s0"}])
    ctl.add("vertical", [{"uid": pl._uid, "h": "s0"}])
    p0, p1 = pl._points[0], pl._points[1]
    assert abs(p1.x() - p0.x()) > 1.0                       # s0 not collapsed


def test_d36_already_zero_length_line_is_not_a_collapse(qapp):
    sc = _scene()
    ln = _line(sc, (10, 10), (10, 10))
    c = sc.constraint_ctl.add("vertical", [{"uid": ln._uid, "h": "edge"}])
    assert c is not None and c.id not in sc.constraint_ctl.red


# ── CS2 D37/D38: red constraints sit out; attribution = admission ──────────

def _top_left_y(r):
    import numpy as np
    from firepro3d.sketch_adapters import adapter_for
    ad = adapter_for(r)
    x = np.array(ad.read(r), float)
    return float(ad.points(r, 0)["tl"].eval(x)[0][1])


def test_d38_newly_added_conflict_is_red_earlier_one_not(qapp):
    sc = _scene()
    r = _rect(sc, (0, 0), (100, 50))
    ctl = sc.constraint_ctl
    h = ctl.add("horizontal", [{"uid": r._uid, "h": "top"}])
    v = ctl.add("vertical", [{"uid": r._uid, "h": "top"}])
    assert ctl.red == {v.id}
    assert h.id not in ctl.red
    assert [c.id for c in ctl.active()] == [h.id]


def test_d37_connected_geometry_stays_editable_after_a_red_admit(qapp):
    sc = _scene()
    r = _rect(sc, (0, 0), (100, 50))
    ln = _line(sc, (200, 0), (300, 10))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": r._uid, "h": "top"}])
    ctl.add("horizontal", [{"uid": r._uid, "h": "tl"}, {"uid": ln._uid, "h": "p1"}])
    ctl.add("vertical", [{"uid": r._uid, "h": "top"}])           # red
    before = (ln._pt1.x(), ln._pt1.y())
    with ctl.edit([ln]):
        ln._pt1 = QPointF(200, 40)
        ln.setLine(200, 40, 300, 10)
    assert (ln._pt1.x(), ln._pt1.y()) != before                  # the edit applied
    assert ln._pt1.y() == pytest.approx(_top_left_y(r), abs=1e-6)   # H tl~p1 honoured


def test_d37_deleting_the_conflict_partner_rejoins_the_red_one(qapp):
    """H(L) + V(L.p1, M.p1) + V(L.p2, M.p1): the last can only collapse L
    (D36) -> red. Deleting V(L.p1, M.p1) makes it satisfiable: the structural
    commit's re-check re-admits it and applies it."""
    sc = _scene()
    L = _line(sc, (0, 0), (100, 30))
    M = _line(sc, (40, 100), (140, 100))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": L._uid, "h": "edge"}])
    v1 = ctl.add("vertical", [{"uid": L._uid, "h": "p1"}, {"uid": M._uid, "h": "p1"}])
    v2 = ctl.add("vertical", [{"uid": L._uid, "h": "p2"}, {"uid": M._uid, "h": "p1"}])
    assert ctl.red == {v2.id}
    assert L._pt2.x() != pytest.approx(M._pt1.x(), abs=1e-3)     # not applied yet
    ctl.delete([v1.id])                                          # structural commit
    assert ctl.red == set()
    assert L._pt2.x() == pytest.approx(M._pt1.x(), abs=1e-6)     # V now applied
    assert L._pt1.y() == pytest.approx(L._pt2.y(), abs=1e-6)     # H still holds


def test_d37_a_geometry_edit_never_rejoins_a_red_one(qapp):
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 30))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    v = ctl.add("vertical", [{"uid": ln._uid, "h": "edge"}])
    with ctl.edit([ln]):
        ln._pt2 = QPointF(150, 15)
        ln.setLine(ln._pt1.x(), ln._pt1.y(), 150, 15)
    assert ctl.red == {v.id}


def test_d38_red_rederived_on_load_in_list_order(qapp):
    sc = _scene()
    ln = _line(sc, (0, 15), (100, 15))
    ctl = sc.constraint_ctl
    h = ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    v = ctl.add("vertical", [{"uid": ln._uid, "h": "edge"}])
    recs = ctl.to_records()
    ctl.reset()
    assert ctl.red == set()
    ctl.load(recs)
    assert ctl.red == {v.id} and h.id not in ctl.red
    assert (ln._pt1.x(), ln._pt1.y(), ln._pt2.x()) == pytest.approx((0.0, 15.0, 100.0))


def test_d38_undo_restore_rederives_red(qapp):
    sc = _scene()
    ln = _line(sc, (0, 15), (100, 15))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    v = ctl.add("vertical", [{"uid": ln._uid, "h": "edge"}])
    snap = ctl.capture()
    ctl.red.clear()
    ctl.restore(snap)
    assert ctl.red == {v.id}


def test_suppress_clears_red_and_reenable_reattributes(qapp):
    sc = _scene()
    ln = _line(sc, (0, 15), (100, 15))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    v = ctl.add("vertical", [{"uid": ln._uid, "h": "edge"}])
    ctl.set_enabled(v.id, False)
    assert v.id not in ctl.red
    ctl.set_enabled(v.id, True)
    assert v.id in ctl.red


def test_d42_redundant_add_posts_status_and_still_admits(qapp):
    sc = _scene()
    log = _status_log(sc)
    ln = _line(sc, (0, 0), (100, 30))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    c2 = ctl.add("horizontal", [{"uid": ln._uid, "h": "p1"}, {"uid": ln._uid, "h": "p2"}])
    assert c2 is not None and c2.id not in ctl.red
    assert c2.id in ctl.diagnostics().redundant
    assert "Redundant constraint: already implied by others" in log


# ── CS2 diagnostics cache (§7.4, D39/D41) ───────────────────────────────────

def test_item_states_free_defined_conflict(qapp):
    sc = _scene()
    a = _line(sc, (10, 5), (60, 40))
    b = _line(sc, (0, 100), (50, 120))                       # untouched
    ctl = sc.constraint_ctl
    O = {"ref": "origin"}
    ctl.add("horizontal", [{"uid": a._uid, "h": "p1"}, O])
    ctl.add("vertical", [{"uid": a._uid, "h": "p1"}, O])     # p1 pinned at the origin
    ctl.add("horizontal", [{"uid": a._uid, "h": "edge"}])    # p2.y = 0, p2.x free
    d = ctl.diagnostics()
    assert d.state(a._uid) == "free" and d.item_dof[a._uid] == 1
    assert d.state(b._uid) == "free" and d.item_dof[b._uid] == 4   # unconstrained
    r = _rect(sc, (300, 0), (400, 50))
    ctl.add("horizontal", [{"uid": r._uid, "h": "top"}])
    ctl.add("vertical", [{"uid": r._uid, "h": "top"}])             # red
    assert ctl.diagnostics().state(r._uid) == "conflict"


def test_fully_defined_text_ins_at_origin(qapp):
    from firepro3d.text_item import TextAnnotationData, TextItem
    sc = _scene()
    t = TextItem(TextAnnotationData(text="A", x=30.0, y=40.0, height_mm=20.0))
    sc.addItem(t); sc._texts.append(t)
    ctl = sc.constraint_ctl
    O = {"ref": "origin"}
    ctl.add("horizontal", [{"uid": t._uid, "h": "ins"}, O])
    ctl.add("vertical", [{"uid": t._uid, "h": "ins"}, O])
    assert ctl.diagnostics().state(t._uid) == "defined"
    assert ctl.sketch_state() == ("Fully defined", "defined")


def test_line_both_ends_to_origin_collapses_red(qapp):
    sc = _scene()
    a = _line(sc, (10, 5), (60, 40))
    ctl = sc.constraint_ctl
    O = {"ref": "origin"}
    ctl.add("horizontal", [{"uid": a._uid, "h": "p1"}, O])
    ctl.add("vertical", [{"uid": a._uid, "h": "p1"}, O])
    ctl.add("horizontal", [{"uid": a._uid, "h": "p2"}, O])
    v = ctl.add("vertical", [{"uid": a._uid, "h": "p2"}, O])       # D36: collapse -> red
    assert ctl.red == {v.id}
    assert ctl.diagnostics().state(a._uid) == "conflict"


def test_diagnostics_cached_until_a_commit(qapp):
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 30))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    d1 = ctl.diagnostics()
    assert ctl.diagnostics() is d1                          # no commit -> same object
    ctl.add("vertical", [{"uid": ln._uid, "h": "p1"}, {"ref": "origin"}])
    assert ctl.diagnostics() is not d1


def test_new_unconstrained_item_invalidates_the_cache(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    d1 = ctl.diagnostics()
    ln = _line(sc, (0, 0), (100, 30))
    d2 = ctl.diagnostics()
    assert d2 is not d1 and d2.state(ln._uid) == "free" and d2.dof == 4


def test_sketch_state_text(qapp):
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 30))
    ctl = sc.constraint_ctl
    assert ctl.sketch_state() == ("Under-defined · 4 DOF", "free")
    ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    ctl.add("vertical", [{"uid": ln._uid, "h": "edge"}])      # red
    assert ctl.sketch_state() == ("Over-constrained", "conflict")


def test_d41_element_footer_is_the_element_state(qapp):
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 30))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    spec = ctl.panel_rows(ln)
    assert spec["footer"] == "Under-defined · 3 DOF"
    assert spec["footer_state"] == "free"


def test_panel_row_state_for_red_and_redundant(qapp):
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 30))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    ctl.add("horizontal", [{"uid": ln._uid, "h": "p1"}, {"uid": ln._uid, "h": "p2"}])  # amber
    ctl.add("vertical", [{"uid": ln._uid, "h": "edge"}])                                # red
    states = [r["state"] for r in ctl.panel_rows(ln)["rows"]]
    assert states == ["", "warn", "danger"]


# ── CS2 D42: D30 copy rule for Vertical ─────────────────────────────────────

@pytest.mark.parametrize("kw, kept", [
    ({}, True),                                                    # translate-only
    ({"rotation_deg": 180.0}, True),
    ({"rotation_deg": 90.0}, False),                               # no H<->V swap
    ({"mirror_axis": (QPointF(200, -500), QPointF(200, 500))}, True),
    ({"mirror_axis": (QPointF(0, 0), QPointF(100, 100))}, False),  # 45 deg
])
def test_d30_vertical_copy_rule(qapp, kw, kept):
    sc = _scene()
    ln = _line(sc, (0, 0), (0, 100))
    ctl = sc.constraint_ctl
    ctl.add("vertical", [{"uid": ln._uid, "h": "edge"}])
    recs = ctl.internal_records([ln])
    cp_ = _line(sc, (50, 0), (50, 100))
    ctl.paste_records(recs, {ln._uid: cp_._uid}, **kw)
    assert [c.type for c in ctl.constraints_on(cp_)] == (["vertical"] if kept else [])


# ── CS2 review I-1 / I-2 / m-1: red derivation must never leave an active
#    constraint unsatisfied, and only a real cascade re-checks red ─────────

def _sat(ctl):
    """Every ACTIVE constraint holds at the committed geometry (the D37
    invariant): max |residual| over aliases / fixes / rows."""
    import numpy as np
    cons = ctl.active()
    if not cons:
        return 0.0
    sys_, _slots, _w = ctl._build(cons)
    x = sys_.x
    r = [abs(x[i] - x[j]) for i, j, _c in sys_.aliases]
    r += [abs(x[i] - v) for i, v, _c in sys_.fixes]
    r += [abs(row.fn(x)[0]) for row in sys_.rows]
    return float(max(r)) if r else 0.0


def test_review_i1_undo_restore_never_activates_an_unapplied_red(qapp):
    sc = _scene()
    L = _line(sc, (0, 0), (100, 0))
    sc.push_undo_state()
    ctl = sc.constraint_ctl
    v = ctl.add("vertical", [{"uid": L._uid, "h": "edge"}])     # collapse -> red
    assert ctl.red == {v.id}
    with ctl.edit([L]):                                         # D37: no re-check
        L._pt2 = QPointF(10, 80)
        L.setLine(0, 0, 10, 80)
    sc.push_undo_state()
    M = _line(sc, (300, 0), (400, 0))
    sc.push_undo_state()
    sc.undo()                                                   # unrelated step
    ctl = sc.constraint_ctl
    L2 = next(i for i in sc._draw_lines if i._uid == L._uid)
    assert _sat(ctl) <= 1e-6                                    # [RED before fix]
    assert v.id in ctl.red                                      # still red, as live
    assert (L2._pt2.x(), L2._pt2.y()) == pytest.approx((10.0, 80.0))


def test_review_i1_paste_keeps_a_red_source_constraint_red(qapp):
    sc = _scene()
    L = _line(sc, (0, 0), (100, 0))
    ctl = sc.constraint_ctl
    v = ctl.add("vertical", [{"uid": L._uid, "h": "edge"}])     # red
    with ctl.edit([L]):
        L._pt2 = QPointF(10, 80)
        L.setLine(0, 0, 10, 80)
    recs = ctl.internal_records([L])
    C = _line(sc, (200, 0), (210, 80))                          # the copy
    ctl.paste_records(recs, {L._uid: C._uid})
    copied = [c for c in ctl.constraints_on(C)]
    assert len(copied) == 1 and copied[0].id in ctl.red        # [RED before fix]
    assert _sat(ctl) <= 1e-6


def test_review_i2_removing_an_unrelated_item_does_not_move_geometry(qapp):
    sc = _scene()
    L = _line(sc, (0, 0), (100, 0))
    other = _line(sc, (300, 300), (400, 300))
    ctl = sc.constraint_ctl
    v = ctl.add("vertical", [{"uid": L._uid, "h": "edge"}])     # red
    with ctl.edit([L]):
        L._pt2 = QPointF(10, 80)
        L.setLine(0, 0, 10, 80)
    before = _grips(L)
    assert ctl.on_items_removed([other]) == 0                   # nothing cascaded
    assert _grips(L) == before                                  # [RED before fix]
    assert v.id in ctl.red


def test_review_m1_non_participating_item_has_no_state_footer(qapp):
    from firepro3d.geometry_2d import SplineItem
    sc = _scene()
    sp = SplineItem([QPointF(0, 0), QPointF(50, 40), QPointF(100, 0), QPointF(150, 30)])
    sc.addItem(sp); sc._draw_splines.append(sp)
    assert sc.constraint_ctl.item_state_text(getattr(sp, "_uid", None)) == ("", "")


# ── CS3 Coincident (controller) ──────────────────────────────────────────────

def _circle(sc, c, r):
    from firepro3d.geometry_2d import CircleItem
    it = CircleItem(QPointF(*c), r)
    sc.addItem(it); sc._draw_circles.append(it)
    return it


def _arc(sc, c, r, s, span):
    from firepro3d.geometry_2d import ArcItem
    it = ArcItem(QPointF(*c), r, s, span)
    sc.addItem(it); sc._draw_arcs.append(it)
    return it


def _cross(a, b, p):
    """Signed distance of *p* from the infinite line a->b (mm)."""
    dx, dy = b.x() - a.x(), b.y() - a.y()
    return ((p.x() - a.x()) * dy - (p.y() - a.y()) * dx) / math.hypot(dx, dy)


def test_coincident_joins_two_line_ends_least_change(qapp):
    sc = _scene()
    a = _line(sc, (-100, 0), (-10, 4)); b = _line(sc, (10, -4), (100, 0))
    c = sc.constraint_ctl.add("coincident", [{"uid": a._uid, "h": "p2"},
                                             {"uid": b._uid, "h": "p1"}])
    assert c is not None and c.id not in sc.constraint_ctl.red
    assert (a._pt2.x(), a._pt2.y()) == pytest.approx((0.0, 0.0), abs=1e-6)
    assert (b._pt1.x(), b._pt1.y()) == pytest.approx((0.0, 0.0), abs=1e-6)


def test_coincident_point_to_origin(qapp):
    sc = _scene()
    a = _line(sc, (5, 7), (80, 40))
    sc.constraint_ctl.add("coincident", [{"uid": a._uid, "h": "p1"}, {"ref": "origin"}])
    assert (a._pt1.x(), a._pt1.y()) == pytest.approx((0.0, 0.0), abs=1e-6)


def test_point_on_circle_and_arc_curve_handles(qapp):
    sc = _scene()
    circ = _circle(sc, (0, 0), 50)
    arc = _arc(sc, (200, 0), 40, 10.0, 60.0)
    ln = _line(sc, (80, 0), (150, 30))
    ctl = sc.constraint_ctl
    assert ctl.add("point_on_curve", [{"uid": ln._uid, "h": "p1"},
                                      {"uid": circ._uid, "h": "curve"}]) is not None
    p, c = ln._pt1, circ._center
    assert math.hypot(p.x() - c.x(), p.y() - c.y()) == pytest.approx(circ._radius, abs=1e-6)
    assert ctl.add("point_on_curve", [{"uid": ln._uid, "h": "p2"},
                                      {"uid": arc._uid, "h": "curve"}]) is not None
    p, c = ln._pt2, arc._center
    assert math.hypot(p.x() - c.x(), p.y() - c.y()) == pytest.approx(arc._radius, abs=1e-6)
    assert ctl.red == set()


def test_point_on_edge_is_the_infinite_line(qapp):
    sc = _scene()
    base = _line(sc, (0, 0), (10, 0))
    ln = _line(sc, (60, 9), (90, 40))
    sc.constraint_ctl.add("point_on_curve", [{"uid": ln._uid, "h": "p1"},
                                             {"uid": base._uid, "h": "edge"}])
    # Least change moves both; the point lands on base's INFINITE line,
    # well beyond the segment's end (no segment bound).
    assert _cross(base._pt1, base._pt2, ln._pt1) == pytest.approx(0.0, abs=1e-6)
    assert ln._pt1.x() > max(base._pt1.x(), base._pt2.x()) + 20.0


@pytest.mark.parametrize("axis,coord", [("x_axis", "y"), ("y_axis", "x")])
def test_point_on_axis(qapp, axis, coord):
    sc = _scene()
    ln = _line(sc, (20, 30), (90, 60))
    sc.constraint_ctl.add("point_on_curve", [{"uid": ln._uid, "h": "p1"}, {"ref": axis}])
    assert getattr(ln._pt1, coord)() == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("refs", [
    lambda ln, arc: [{"uid": ln._uid, "h": "p1"}, {"uid": ln._uid, "h": "edge"}],
    lambda ln, arc: [{"uid": arc._uid, "h": "end"}, {"uid": arc._uid, "h": "curve"}],
    lambda ln, arc: [{"ref": "origin"}, {"ref": "x_axis"}],
], ids=["line_end_on_own_edge", "arc_end_on_own_curve", "origin_on_axis"])
def test_identically_satisfied_point_on_curve_is_refused(qapp, refs):
    from firepro3d.constraint_controller import TRIVIAL_STATUS
    sc = _scene()
    ln = _line(sc, (0, 0), (50, 20)); arc = _arc(sc, (0, 0), 30, 0.0, 90.0)
    msgs = []
    sc._show_status = lambda m, *a, **k: msgs.append(m)
    assert sc.constraint_ctl.add("point_on_curve", refs(ln, arc)) is None
    assert sc.constraint_ctl.constraints == []
    assert msgs[-1] == TRIVIAL_STATUS


def test_polyline_vertex_on_a_non_adjacent_own_segment_is_admitted(qapp):
    from firepro3d.geometry_2d import PolylineItem
    sc = _scene()
    pl = PolylineItem(QPointF(0, 0))
    for p in ((100, 0), (100, 50), (30, 20)):
        pl.append_point(QPointF(*p))
    sc.addItem(pl); sc._polylines.append(pl)
    c = sc.constraint_ctl.add("point_on_curve", [{"uid": pl._uid, "h": "v3"},
                                                 {"uid": pl._uid, "h": "s0"}])
    assert c is not None and sc.constraint_ctl.red == set()
    v = pl._points
    assert _cross(v[0], v[1], v[3]) == pytest.approx(0.0, abs=1e-6)


def test_coincident_two_ends_of_one_line_is_red_and_held(qapp):
    """D29/D36: collapsing the line is a conflict (admitted, red, held)."""
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 30))
    c = sc.constraint_ctl.add("coincident", [{"uid": ln._uid, "h": "p1"},
                                             {"uid": ln._uid, "h": "p2"}])
    assert c is not None and sc.constraint_ctl.red == {c.id}
    assert (ln._pt2.x(), ln._pt2.y()) == pytest.approx((100.0, 30.0), abs=1e-9)


def test_coincident_triangle_third_is_redundant(qapp):
    sc = _scene()
    a = _line(sc, (0, 0), (10, 0)); b = _line(sc, (10, 0), (20, 5)); c = _line(sc, (10, 0), (5, 9))
    ctl = sc.constraint_ctl
    ctl.add("coincident", [{"uid": a._uid, "h": "p2"}, {"uid": b._uid, "h": "p1"}])
    ctl.add("coincident", [{"uid": b._uid, "h": "p1"}, {"uid": c._uid, "h": "p1"}])
    third = ctl.add("coincident", [{"uid": a._uid, "h": "p2"}, {"uid": c._uid, "h": "p1"}])
    assert third.id in ctl.diagnostics().redundant
    assert ctl.red == set()


def test_rotated_and_mirrored_copies_keep_coincident(qapp):
    sc = _scene()
    a = _line(sc, (0, 0), (10, 0)); b = _line(sc, (10, 0), (20, 5))
    ctl = sc.constraint_ctl
    ctl.add("coincident", [{"uid": a._uid, "h": "p2"}, {"uid": b._uid, "h": "p1"}])
    ctl.add("point_on_curve", [{"uid": b._uid, "h": "p2"}, {"uid": a._uid, "h": "edge"}])
    recs = ctl.internal_records([a, b])
    a2 = _line(sc, (0, 0), (0, 10)); b2 = _line(sc, (0, 10), (-5, 20))
    ctl.paste_records(recs, {a._uid: a2._uid, b._uid: b2._uid}, rotation_deg=37.0)
    a3 = _line(sc, (0, 0), (10, 0)); b3 = _line(sc, (10, 0), (20, -5))
    ctl.paste_records(recs, {a._uid: a3._uid, b._uid: b3._uid},
                      mirror_axis=(QPointF(0, 0), QPointF(3, 1)))
    for x in (a2, a3):
        assert sorted(c.type for c in ctl.constraints_on(x)) == ["coincident", "point_on_curve"]


# ── CS3 D17: refuse Move / Rotate / Scale of fully defined geometry ──────────

def _text(sc, x, y):
    from firepro3d.text_item import TextAnnotationData, TextItem
    t = TextItem(TextAnnotationData(text="A", x=x, y=y, height_mm=20.0))
    sc.addItem(t); sc._texts.append(t)
    return t


def _grounded_text(sc):
    t = _text(sc, 30.0, 40.0)
    assert sc.constraint_ctl.add("coincident", [{"uid": t._uid, "h": "ins"},
                                                {"ref": "origin"}]) is not None
    assert sc.constraint_ctl.item_state_text(t._uid)[1] == "defined"
    return t


def test_move_items_refuses_a_fully_defined_selection(qapp):
    from firepro3d.constraint_controller import GROUNDED_STATUS
    sc = _scene()
    t = _grounded_text(sc)
    msgs = []
    sc._show_status = lambda m, *a, **k: msgs.append(m)
    sc._selected_items = [t]
    assert sc.move_items(QPointF(25, 0)) is False
    assert (t.pos().x(), t.pos().y()) == pytest.approx((0.0, 0.0), abs=1e-9)
    assert msgs[-1] == GROUNDED_STATUS


@pytest.mark.parametrize("mode", ["move", "rotate", "scale"])
def test_tool_entry_refused_on_fully_defined_selection(qapp, mode):
    sc = _scene()
    t = _grounded_text(sc)
    t.setSelected(True)
    sc.set_mode(mode)
    assert sc.mode != mode


def test_partly_grounded_selection_still_moves(qapp):
    sc = _scene()
    ln = _line(sc, (0, 0), (100, 0))
    sc.constraint_ctl.add("coincident", [{"uid": ln._uid, "h": "p1"}, {"ref": "origin"}])
    ln.setSelected(True)
    sc.set_mode("move")
    assert sc.mode == "move"
    sc._selected_items = [ln]
    assert sc.move_items(QPointF(0, 10)) is not False
    assert (ln._pt1.x(), ln._pt1.y()) == pytest.approx((0.0, 0.0), abs=1e-6)
    assert ln._pt2.y() == pytest.approx(10.0, abs=1e-6)


def test_rotate_commit_refuses_and_pushes_no_undo(qapp):
    sc = _scene()
    t = _grounded_text(sc)
    sc.push_undo_state()
    n = len(sc._undo_stack)
    angle0 = t._angle
    sc._selected_items = [t]
    sc._rotate_pivot = QPointF(100, 100)
    assert sc._modify_ctl.commit_rotate(45.0) is False
    assert len(sc._undo_stack) == n
    assert (t.pos().x(), t.pos().y()) == pytest.approx((0.0, 0.0), abs=1e-9)
    assert t._angle == angle0


def test_d4_migrated_definition_with_coincident_to_origin_opens_satisfied(qapp):
    """D4 seam (closed CS3): migrate THEN load + solve keeps an origin-tied
    constraint satisfied (p1 sat on the old origin)."""
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.block_editor import BlockEditorWidget
    project = Model_Space()
    ln = LineItem(QPointF(10, 20), QPointF(110, 70))       # p1 on the OLD origin
    defn = BlockDefinition.new(
        name="B", library="L", series="S", primitives=[ln.to_dict()],
        origin=(10.0, 20.0),
        constraints=[{"id": "c-o", "type": "coincident",
                      "refs": [{"uid": ln._uid, "h": "p1"}, {"ref": "origin"}]}])
    project.register_block_definition(defn)
    w = BlockEditorWidget(project)
    w.seed_from_definition(defn)
    sc = w.editor_scene
    (l,) = sc._draw_lines
    assert (l._pt1.x(), l._pt1.y()) == pytest.approx((0.0, 0.0), abs=1e-9)
    assert (l._pt2.x(), l._pt2.y()) == pytest.approx((100.0, 50.0), abs=1e-9)
    assert sc.constraint_ctl.red == set()
    assert [c.id for c in sc.constraint_ctl.active()] == ["c-o"]
