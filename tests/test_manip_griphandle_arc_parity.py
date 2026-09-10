"""Posted-event grip drag of a real ArcItem == legacy apply_grip outcome; one
undo per gesture; Esc restores; snap parity (grid fallback).

U3 migration of ArcItem onto manip_handles(). Mirrors the SplineItem parity
file; the arc's grips (centre/start/end) have no special drag semantics (the
legacy grip path explicitly excludes arc from Ctrl-constrain) and all render
round per the house rule (centre = move grip; start/end = geometric endpoints)."""
import math

from PyQt6.QtCore import QPointF, QEvent, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from firepro3d.construction_geometry import ArcItem
from firepro3d.manip_handle import GripHandle
from firepro3d.manip_math import HandleRole


def _make_arc():
    # centre (0,0), radius 50, start 0deg, span 90deg (Y-up CCW+):
    #   grip 0 = centre (0, 0)
    #   grip 1 = start  (50, 0)
    #   grip 2 = end    (~0, -50)
    return ArcItem(QPointF(0, 0), 50.0, 0.0, 90.0)


def test_arc_manip_handles_shape():
    a = _make_arc()
    hs = a.manip_handles()
    assert len(hs) == 3                               # centre + start + end
    assert all(isinstance(h, GripHandle) for h in hs)
    assert [h.index for h in hs] == [0, 1, 2]
    assert all(h.role is HandleRole.GRIP for h in hs)
    # house rule: centre (move) + start/end (endpoints) all render round
    assert all(h.circular is True for h in hs)
    # each rides its grip point
    for i, h in enumerate(hs):
        assert h.scene_position(None) == a.grip_points()[i]


def test_end_grip_apply_matches_legacy():
    """The migrated live-apply drag mutation == calling apply_grip directly.
    Grip 2 (end) exercises the span-angle branch of apply_grip."""
    legacy = _make_arc()
    legacy.apply_grip(2, QPointF(0, 50))              # legacy path (end -> span)

    migrated = _make_arc()
    h = migrated.manip_handles()[2]

    class _Scene:
        _tools = None
        _grip_item = None
        _grip_dragging = False
        def get_effective_position(self, p): return QPointF(p)
    class _M:
        _commit_hook = None
        def scene(self_m): return sc
        def _reflow_live(self_m): pass
    sc = _Scene()
    m = _M()
    h.on_press(m)
    h.on_drag(m, QPointF(0, 50), Qt.KeyboardModifier.NoModifier)
    assert migrated.to_dict() == legacy.to_dict()


def _post_drag(view, scene, path):
    """Post press->moves->release through the viewport (real event dispatch)."""
    from PyQt6.QtWidgets import QApplication
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


def test_posted_drag_moves_start_grip(qapp):
    """End-to-end: a posted drag on the start grip (index 1) moves it, routed
    through the manipulator (no legacy path). apply_grip stores radius+angle and
    reprojects, so the grip lands exactly at the dragged point."""
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    a = _make_arc()
    scene.addItem(a)
    m = SelectionManipulator(scene)
    a.setSelected(True)
    qapp.processEvents()
    # start grip at (50, 0) -> drag to (80, 20)
    _post_drag(view, scene, [QPointF(50, 0), QPointF(65, 10), QPointF(80, 20)])
    qapp.processEvents()
    moved = a.grip_points()[1]
    assert abs(moved.x() - 80) < 1e-6
    assert abs(moved.y() - 20) < 1e-6
    # the centre is untouched by a start-grip drag
    assert a.grip_points()[0] == QPointF(0, 0)


def test_one_commit_per_gesture(qapp):
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    calls = []
    a = _make_arc(); scene.addItem(a)
    m = SelectionManipulator(scene, commit_hook=lambda mode: calls.append(mode))
    a.setSelected(True); qapp.processEvents()
    _post_drag(view, scene, [QPointF(50, 0), QPointF(65, 10), QPointF(80, 20)])
    qapp.processEvents()
    assert calls == ["grip"]                          # exactly one commit


def test_esc_restores_and_no_commit(qapp):
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    calls = []
    a = _make_arc(); scene.addItem(a)
    before = a.to_dict()
    m = SelectionManipulator(scene, commit_hook=lambda mode: calls.append(mode))
    a.setSelected(True); qapp.processEvents()
    # press + move (mutates the end grip), then cancel via the manipulator (Esc)
    h = a.manip_handles()[2]
    m._begin_handle(h, QPointF(0, -50), QPointF(0, -50))
    m._update(QPointF(0, 50), Qt.KeyboardModifier.NoModifier, QPointF(0, 50))
    assert a._span_deg != 90.0                        # mutated live
    m.cancel_drag()
    assert a.to_dict() == before                       # restored exactly
    assert calls == []                                 # no undo entry on cancel
