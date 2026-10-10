"""Guard: every geometry edit routes through the ConstraintController seams
(parametric-constraint-system.md §8; CS1 Task 8).

The CS1 Task-8 controller is a no-op skeleton, so its seams have no observable
geometry effect yet. This guard swaps ``scene.constraint_ctl`` for a recorder
and drives the REAL edit paths (a posted-event grip drag on a shown view,
``move_items``, the manipulator move / resize bakes, Rotate, Flip, Scale,
Polar Array, Align, delete, undo) to prove each one calls its seam — and in
the order the solver needs: the geometry changes BETWEEN edit enter and edit
exit (the mutation is inside the context), and the exit (solve) precedes the
undo snapshot.
"""
from __future__ import annotations

import contextlib

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView

from firepro3d.geometry_2d import LineItem

_SENTINEL = {"id": "c-sentinel", "type": "horizontal"}


def _geo(it):
    """Observable geometry of *it*: grip points + manipulator bounds."""
    g = (tuple((p.x(), p.y()) for p in it.grip_points())
         if hasattr(it, "grip_points") else ())
    b = it.manip_bounds() if hasattr(it, "manip_bounds") else None
    return g, (None if b is None else (b.x(), b.y(), b.width(), b.height()))


class _RecCtl:
    """Records every seam call (and the geometry at edit enter AND exit)."""

    def __init__(self):
        self.events: list = []

    @contextlib.contextmanager
    def edit(self, items, *, typed=False, scale=None):   # typed: D31; scale: CS4 D54
        items = list(items)
        self.events.append(("edit_enter", items, [_geo(it) for it in items]))
        yield
        self.events.append(("edit_exit", items, [_geo(it) for it in items]))

    def begin_drag(self, item):
        self.events.append(("begin_drag", item))

    def drag(self, item, grip_index):
        self.events.append(("drag", item, grip_index,
                            QPointF(item.grip_points()[grip_index])))

    def end_drag(self):
        self.events.append(("end_drag",))

    def cancel_drag(self):
        self.events.append(("cancel_drag",))

    def cancel_pick(self):
        """set_mode ends any D21 pick session (not a geometry seam: unrecorded)."""

    def drag_partners(self, items):
        """D46 drag partners (watched for snap exclusion); none here (unrecorded)."""
        return []

    def refuse_grounded(self, items):
        """D17 (CS3) predicate at tool entry / commits; never refuses here
        (not a geometry seam: unrecorded)."""
        return False

    def on_items_removed(self, items):
        self.events.append(("removed", list(items)))
        return 0

    def capture(self):
        self.events.append(("capture",))
        return [dict(_SENTINEL)]

    def restore(self, records):
        self.events.append(("restore", records))

    # Copy-path surface (CS1 Task 10): copies carry no records here.
    def internal_records(self, items):
        return []

    def paste_records(self, records, uid_map, mirror_axis=None):
        self.events.append(("paste_records", list(records or [])))

    def kinds(self):
        return [e[0] for e in self.events]

    def edit_pairs(self):
        enters = [e for e in self.events if e[0] == "edit_enter"]
        exits = [e for e in self.events if e[0] == "edit_exit"]
        assert len(enters) == len(exits)
        return list(zip(enters, exits))


def _assert_mutated_inside(rec, items=None):
    """Every edit context saw its items' geometry change between enter and
    exit (the mutation ran INSIDE it), and covered *items* (when given)."""
    pairs = rec.edit_pairs()
    assert pairs, "no edit() context entered"
    for en, ex in pairs:
        assert en[1] and en[2] != ex[2], (en, ex)
    if items is not None:
        seen = [it for en, _ in pairs for it in en[1]]
        for it in items:
            assert any(s is it for s in seen), (it, seen)


def _assert_exit_before_push(rec):
    k = rec.kinds()
    last_exit = max(i for i, x in enumerate(k) if x == "edit_exit")
    first_enter = k.index("edit_enter")
    pushes = [i for i, x in enumerate(k) if x == "pushed" and i > first_enter]
    assert pushes and last_exit < pushes[0], k


def _post_drag(view, path):
    for i, pt in enumerate(path):
        vp = view.mapFromScene(pt)
        etype = (QEvent.Type.MouseButtonPress if i == 0
                 else QEvent.Type.MouseButtonRelease if i == len(path) - 1
                 else QEvent.Type.MouseMove)
        btn = Qt.MouseButton.LeftButton
        ev = QMouseEvent(etype, vp.toPointF(),
                         view.viewport().mapToGlobal(vp).toPointF(),
                         btn, btn if etype != QEvent.Type.MouseButtonRelease
                         else Qt.MouseButton.NoButton,
                         Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(view.viewport(), ev)


# ── (1) grip drag: begin_drag → drag → end_drag, end before the commit ─────

def test_grip_drag_routes_through_drag_seams(qapp):
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    rec = _RecCtl()
    scene.constraint_ctl = rec
    view = QGraphicsView(scene)
    view.resize(400, 400)
    view.show()
    qapp.processEvents()
    ln = LineItem(QPointF(0, 0), QPointF(100, 0))
    scene.addItem(ln)
    m = SelectionManipulator(  # noqa: F841 (lives on the scene)
        scene, commit_hook=lambda mode: rec.events.append(("commit", mode)))
    ln.setSelected(True)
    qapp.processEvents()
    _post_drag(view, [QPointF(100, 0), QPointF(100, 30), QPointF(100, 60)])
    qapp.processEvents()

    assert abs(ln.grip_points()[2].y() - 60) < 1e-6      # the drag really ran
    k = rec.kinds()
    assert k[0] == "begin_drag" and rec.events[0][1] is ln
    drags = [e for e in rec.events if e[0] == "drag"]
    assert drags and all(e[1] is ln and e[2] == 2 for e in drags)
    # Every live frame solves (on_drag at the mid-move point), not just release.
    assert any(abs(e[3].y() - 30) < 1e-6 for e in drags), drags
    assert abs(drags[-1][3].y() - 60) < 1e-6              # release frame solved
    assert k.count("end_drag") == 1
    # The session ends (solve final) BEFORE the commit hook pushes undo.
    assert k.index("end_drag") < k.index("commit")
    assert max(i for i, x in enumerate(k) if x == "drag") < k.index("end_drag")
    view.close()


def test_grip_cancel_routes_through_cancel_seam(qapp):
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    rec = _RecCtl()
    scene.constraint_ctl = rec
    view = QGraphicsView(scene)
    view.resize(400, 400)
    view.show()
    qapp.processEvents()
    ln = LineItem(QPointF(0, 0), QPointF(100, 0))
    scene.addItem(ln)
    m = SelectionManipulator(scene)
    ln.setSelected(True)
    qapp.processEvents()
    h = ln.manip_handles()[2]
    m._begin_handle(h, QPointF(100, 0), QPointF(100, 0))
    m._update(QPointF(100, 60), Qt.KeyboardModifier.NoModifier, QPointF(100, 60))
    m.cancel_drag()
    assert ln.grip_points()[2] == QPointF(100, 0)         # restored
    assert rec.kinds()[-1] == "cancel_drag"
    assert "end_drag" not in rec.kinds()
    view.close()


# ── Model_Space scenarios ───────────────────────────────────────────────────

def _editor_scene():
    from firepro3d.level_manager import LevelManager
    from firepro3d.model_space import Model_Space
    from firepro3d.scale_manager import ScaleManager
    sc = Model_Space(scene_role="block_editor")
    sc._level_manager = LevelManager()
    sc.scale_manager = ScaleManager()
    rec = _RecCtl()
    sc.constraint_ctl = rec
    orig_push = sc.push_undo_state

    def _push():
        orig_push()
        rec.events.append(("pushed",))
    sc.push_undo_state = _push
    ln = LineItem(QPointF(0, 0), QPointF(100, 0))
    sc.addItem(ln)
    sc._draw_lines.append(ln)
    return sc, rec, ln


def test_move_items_enters_edit_with_moved_items(qapp):
    sc, rec, ln = _editor_scene()
    try:
        sc._selected_items = [ln]
        sc.move_items(QPointF(10, 5))
        pairs = rec.edit_pairs()
        assert len(pairs) == 1 and pairs[0][0][1] == [ln]
        _assert_mutated_inside(rec, [ln])
        assert pairs[0][1][2][0][0][0] == (10.0, 5.0)      # moved at exit
    finally:
        sc.cleanup()


def test_commit_rotate_enters_edit_before_undo_push(qapp):
    sc, rec, ln = _editor_scene()
    try:
        sc._selected_items = [ln]
        sc._rotate_pivot = QPointF(0, 0)
        assert sc._modify_ctl.commit_rotate(90.0) is True
        k = rec.kinds()
        pairs = rec.edit_pairs()
        assert len(pairs) == 1 and pairs[0][0][1] == [ln]
        _assert_mutated_inside(rec, [ln])
        end = pairs[0][1][2][0][0][-1]
        assert abs(end[0]) < 1e-6 and abs(abs(end[1]) - 100) < 1e-6  # rotated
        assert k.index("edit_exit") < k.index("capture") < k.index("pushed")
    finally:
        sc.cleanup()


def test_delete_calls_on_items_removed_before_undo_push(qapp):
    sc, rec, ln = _editor_scene()
    try:
        sc.delete_items([ln])
        assert ln.scene() is None                         # really deleted
        k = rec.kinds()
        removed = [e for e in rec.events if e[0] == "removed"]
        assert len(removed) == 1 and ln in removed[0][1]
        assert k.index("removed") < k.index("capture") < k.index("pushed")
    finally:
        sc.cleanup()


def test_undo_snapshot_holds_capture_and_undo_restores_it(qapp):
    sc, rec, ln = _editor_scene()
    try:
        sc.push_undo_state()                              # baseline
        sc._selected_items = [ln]
        sc.move_items(QPointF(10, 0))
        sc.push_undo_state()
        assert sc._undo_stack[-1]["constraints"] == [_SENTINEL]
        sc.undo()
        restores = [e for e in rec.events if e[0] == "restore"]
        assert restores and restores[-1][1] == [_SENTINEL]
        # the restored scene is the baseline geometry (move undone)
        lines = sc._draw_lines
        assert len(lines) == 1 and lines[0].grip_points()[0] == QPointF(0, 0)
    finally:
        sc.cleanup()


def test_commit_reflect_flip_enters_edit_before_undo_push(qapp):
    from firepro3d.axis_picker import AxisPick
    from firepro3d.geometry_2d import ReferenceLineItem
    sc, rec, ln = _editor_scene()
    try:
        rl = ReferenceLineItem(QPointF(200, -500), QPointF(200, 500))
        sc.addItem(rl)
        sc._reference_lines.append(rl)
        sc.mode = "flip"
        sc._selected_items = [ln]
        sc._mirror_axis = AxisPick(QPointF(200, -500), QPointF(200, 500), rl, 90.0)
        assert sc._modify_ctl.commit_reflect() is True
        assert ln.grip_points()[0] == QPointF(400, 0)      # flipped in place
        _assert_mutated_inside(rec, [ln])
        _assert_exit_before_push(rec)
    finally:
        sc.cleanup()


def test_commit_scale_enters_edit_before_undo_push(qapp):
    sc, rec, ln = _editor_scene()
    try:
        sc._selected_items = [ln]
        sc._scale_base = QPointF(0, 0)
        assert sc._modify_ctl.commit_scale(2.0) is True
        assert ln.grip_points()[-1] == QPointF(200, 0)     # scaled
        _assert_mutated_inside(rec, [ln])
        _assert_exit_before_push(rec)
    finally:
        sc.cleanup()


def test_commit_array_polar_enters_edit_per_copy_before_undo_push(qapp):
    sc, rec, ln = _editor_scene()
    try:
        sc._array_variant = "polar"
        sc._array_base = QPointF(0, 0)
        sc._selected_items = [ln]
        assert sc._modify_ctl.commit_array({"count": 3, "total_deg": 360.0}) is True
        copies = [it for it in sc._draw_lines if it is not ln]
        assert len(copies) == 2
        pairs = rec.edit_pairs()
        assert len(pairs) == 2                             # one per copy
        _assert_mutated_inside(rec, copies)
        assert all(it is not ln for en, _ in pairs for it in en[1])
        _assert_exit_before_push(rec)
    finally:
        sc.cleanup()


def test_align_translates_primitive_inside_edit(qapp):
    """Align (Shift+L, reachable in the Block Editor) moves a 2D primitive
    through its translate contract — pos() stays (0,0), the internal points
    move — inside one edit() context, before its single undo step."""
    sc, rec, ref = _editor_scene()                         # ref: y = 0
    try:
        target = LineItem(QPointF(0, 50), QPointF(100, 50))
        sc.addItem(target)
        sc._draw_lines.append(target)
        sc.push_undo_state()                               # baseline
        tools = sc._tools
        tools._press_align(None, QPointF(50, 0), QPointF(50, 0), None, None, None)
        tools._press_align(None, QPointF(50, 50), QPointF(50, 50), target,
                           None, None)
        assert target.pos() == QPointF(0, 0)               # pos-identity kept
        assert target._pt1 == QPointF(0, 0) and target._pt2 == QPointF(100, 0)
        _assert_mutated_inside(rec, [target])
        _assert_exit_before_push(rec)
        sc.undo()                                          # one undoable step
        ys = sorted(it.grip_points()[0].y() for it in sc._draw_lines)
        assert ys == [0.0, 50.0]
        sc.redo()
        ys = sorted(it.grip_points()[0].y() for it in sc._draw_lines)
        assert ys == [0.0, 0.0]
    finally:
        sc.cleanup()


# ── SelectionManipulator bakes (shown Model_View) ───────────────────────────

def _wire(scene):
    rec = _RecCtl()
    scene.constraint_ctl = rec
    orig_push = scene.push_undo_state

    def _push():
        orig_push()
        rec.events.append(("pushed",))
    scene.push_undo_state = _push
    return rec


def test_manipulator_move_bake_enters_edit_before_commit(shown_model_view):
    _view, scene = shown_model_view
    rec = _wire(scene)
    a = LineItem(QPointF(0, 0), QPointF(100, 0))
    b = LineItem(QPointF(0, 100), QPointF(100, 100))
    for it in (a, b):
        scene.addItem(it)
        scene._draw_lines.append(it)
        it.setSelected(True)
    manip = scene._manipulator
    manip._snap = lambda p: p
    manip.rebake()
    start = QPointF(manip._rect.center())
    manip._begin("move", start, QPointF(0, 0))
    manip._update(start + QPointF(40, 0), Qt.KeyboardModifier.NoModifier,
                  QPointF(200, 0))
    manip._finish(start + QPointF(40, 0), Qt.KeyboardModifier.NoModifier)
    assert abs(a.grip_points()[0].x() - 40) < 1e-6           # baked
    _assert_mutated_inside(rec, [a, b])
    _assert_exit_before_push(rec)


def test_manipulator_resize_bake_enters_edit_before_commit(shown_model_view):
    """Rigid resize bake (``_bake_scale``) on a real TextItem — the
    Block-Editor primitive that is ``manip_scale``-capable."""
    from firepro3d.manip_math import HandleRole
    from firepro3d.text_item import TextAnnotationData, TextItem
    _view, scene = shown_model_view
    rec = _wire(scene)
    t = TextItem(TextAnnotationData(text="T", x=0.0, y=0.0, height_mm=20.0))
    scene.addItem(t)
    scene._texts.append(t)
    t.setSelected(True)
    manip = scene._manipulator
    manip._snap = lambda p: p
    manip.rebake()
    w0 = t.manip_bounds().width()
    r0 = QRectF(manip._rect)
    manip._begin("resize", r0.bottomRight(), QPointF(0, 0),
                 HandleRole.BOTTOM_RIGHT)
    end = r0.bottomRight() + QPointF(r0.width(), r0.height())
    manip._update(end, Qt.KeyboardModifier.NoModifier, QPointF(200, 200))
    manip._finish(end, Qt.KeyboardModifier.NoModifier)
    assert t.manip_bounds().width() > w0 * 1.5                # really resized
    _assert_mutated_inside(rec, [t])
    _assert_exit_before_push(rec)
