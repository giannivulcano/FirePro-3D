"""Proves the GripHandle live-apply lifecycle admits all four per-item drag
semantics (Ctrl point-transform, sibling apply_grip, post-apply propagation,
constraint-solver pass) WITHOUT building wall/gridline in this PR."""
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.manip_handle import GripHandle
from firepro3d.selection_manipulator import SelectionManipulator


class _Item:
    def __init__(self, pts):
        self._pts = list(pts)
        self.applied = []

    def grip_points(self):
        return list(self._pts)

    def apply_grip(self, index, pos):
        self.applied.append((index, pos))
        self._pts[index] = pos

    def manip_translate(self, dx, dy):        # so the manipulator wraps it
        self._pts = [QPointF(p.x() + dx, p.y() + dy) for p in self._pts]

    def manip_bounds(self):                   # so _reflow_live can compute frame
        from PyQt6.QtCore import QRectF
        xs = [p.x() for p in self._pts]
        ys = [p.y() for p in self._pts]
        return QRectF(min(xs), min(ys), max(xs) - min(xs) or 1.0, max(ys) - min(ys) or 1.0)


class _FakeScene(QGraphicsScene):
    """Scene stub exposing the grip-snap + solver seam GripHandle uses."""
    def __init__(self):
        super().__init__()
        self._grip_item = None
        self._grip_dragging = False
        self.eff_calls = []
        self.solved = []

        class _Tools:
            def __init__(self, s): self._s = s
            def _solve_constraints(self, item=None): self._s.solved.append(item)
        self._tools = _Tools(self)

    def get_effective_position(self, pos):
        self.eff_calls.append((self._grip_item, self._grip_dragging, pos))
        return QPointF(pos)   # identity snap for the stub


def _mk(scene):
    m = SelectionManipulator(scene)
    return m


def test_on_drag_calls_apply_grip_through_effective_position(qapp):
    scene = _FakeScene()
    item = _Item([QPointF(0, 0), QPointF(10, 0)])
    m = _mk(scene)
    m._items = [item]                          # wrap directly for the unit
    h = GripHandle(item, 1)
    m._active_handle = h
    h.on_press(m)
    assert scene._grip_dragging is True and scene._grip_item is item
    h.on_drag(m, QPointF(25, 0), Qt.KeyboardModifier.NoModifier)
    assert item.applied[-1] == (1, QPointF(25, 0))    # via get_effective_position
    # Snap parity by construction: the borrowed flags were set when the scene's
    # grip-snap authority ran (item excluded as source, grip_dragging True).
    assert scene.eff_calls[-1] == (item, True, QPointF(25, 0))
    assert scene.solved[-1] is item                    # solver pass ran
    h.on_cancel(m)
    assert scene._grip_dragging is False               # state cleared


def test_admits_ctrl_point_transform_and_sibling_and_propagation(qapp):
    """A subclass overriding the two hook points reaches real geometry —
    proves the framework admits Ctrl-constrain, parallel-delta, propagation."""
    scene = _FakeScene()
    a = _Item([QPointF(0, 0), QPointF(10, 0)])
    b = _Item([QPointF(0, 5), QPointF(10, 5)])
    m = _mk(scene)
    m._items = [a]

    class _SemanticGrip(GripHandle):
        def _transform_point(self, m, pt, mods):        # Ctrl-constrain hook
            return QPointF(pt.x(), 0.0) if mods else pt
        def _after_apply(self, m, applied_pt):          # sibling/propagation hook
            b.apply_grip(self.index, QPointF(applied_pt))

    h = _SemanticGrip(a, 1)
    m._active_handle = h
    h.on_press(m)
    h.on_drag(m, QPointF(25, 99), Qt.KeyboardModifier.ControlModifier)
    assert a.applied[-1] == (1, QPointF(25, 0))         # Ctrl flattened y
    assert b.applied[-1] == (1, QPointF(25, 0))         # propagation reached b
    h.on_cancel(m)
