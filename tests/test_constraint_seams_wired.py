"""Guard: every geometry edit routes through the ConstraintController seams
(parametric-constraint-system.md §8; CS1 Task 8).

The CS1 Task-8 controller is a no-op skeleton, so its seams have no observable
geometry effect yet. This guard swaps ``scene.constraint_ctl`` for a recorder
and drives the REAL edit paths (a posted-event grip drag on a shown view,
``move_items``, ``commit_rotate``, delete, undo) to prove each one calls its
seam — and in the order the solver needs: the edit context exits (solve)
after the mutation and before the undo snapshot.
"""
from __future__ import annotations

import contextlib

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView

from firepro3d.geometry_2d import LineItem

_SENTINEL = {"id": "c-sentinel", "type": "horizontal"}


class _RecCtl:
    """Records every seam call (and the geometry seen at edit exit)."""

    def __init__(self):
        self.events: list = []

    @contextlib.contextmanager
    def edit(self, items):
        items = list(items)
        self.events.append(("edit_enter", items))
        yield
        self.events.append(("edit_exit", items,
                            [list(it.grip_points()) for it in items]))

    def begin_drag(self, item):
        self.events.append(("begin_drag", item))

    def drag(self, item, grip_index):
        self.events.append(("drag", item, grip_index,
                            QPointF(item.grip_points()[grip_index])))

    def end_drag(self):
        self.events.append(("end_drag",))

    def cancel_drag(self):
        self.events.append(("cancel_drag",))

    def on_items_removed(self, items):
        self.events.append(("removed", list(items)))
        return 0

    def capture(self):
        self.events.append(("capture",))
        return [dict(_SENTINEL)]

    def restore(self, records):
        self.events.append(("restore", records))

    def kinds(self):
        return [e[0] for e in self.events]


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
        enter = [e for e in rec.events if e[0] == "edit_enter"]
        exit_ = [e for e in rec.events if e[0] == "edit_exit"]
        assert len(enter) == 1 and enter[0][1] == [ln]
        # The mutation happened INSIDE the context (seen moved at exit).
        assert exit_[0][2][0][0] == QPointF(10, 5)
    finally:
        sc.cleanup()


def test_commit_rotate_enters_edit_before_undo_push(qapp):
    sc, rec, ln = _editor_scene()
    try:
        sc._selected_items = [ln]
        sc._rotate_pivot = QPointF(0, 0)
        assert sc._modify_ctl.commit_rotate(90.0) is True
        k = rec.kinds()
        enter = [e for e in rec.events if e[0] == "edit_enter"]
        assert len(enter) == 1 and enter[0][1] == [ln]
        exit_ = next(e for e in rec.events if e[0] == "edit_exit")
        end = exit_[2][0][-1]
        assert abs(end.x()) < 1e-6 and abs(abs(end.y()) - 100) < 1e-6  # rotated inside
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
