"""Posted-event control-point-grip drag of a real SplineItem == legacy
apply_grip outcome; one undo per gesture; Esc restores; snap parity (grid
fallback).

U3 migration of SplineItem onto manip_handles(). Mirrors the PolylineItem parity
file; spline control points have no special drag semantics (no Ctrl-constrain,
no move-centre grip) and all render round (they are the spline's vertices)."""
from PyQt6.QtCore import QPointF, QEvent, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from firepro3d.construction_geometry import SplineItem
from firepro3d.manip_handle import GripHandle
from firepro3d.manip_math import HandleRole


def _make_spline():
    return SplineItem([QPointF(0, 0), QPointF(50, 0),
                       QPointF(100, 50), QPointF(150, 0)])


def test_spline_manip_handles_shape():
    s = _make_spline()
    hs = s.manip_handles()
    assert len(hs) == 4                               # one per control point
    assert all(isinstance(h, GripHandle) for h in hs)
    assert [h.index for h in hs] == [0, 1, 2, 3]
    assert all(h.role is HandleRole.GRIP for h in hs)
    # house rule: control points are vertices -> round
    assert all(h.circular is True for h in hs)
    # each rides its grip point
    for i, h in enumerate(hs):
        assert h.scene_position(None) == s.grip_points()[i]


def test_control_point_grip_apply_matches_legacy():
    """The migrated live-apply drag mutation == calling apply_grip directly."""
    legacy = _make_spline()
    legacy.apply_grip(1, QPointF(60, 40))             # legacy path

    migrated = _make_spline()
    h = migrated.manip_handles()[1]

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
    h.on_drag(m, QPointF(60, 40), Qt.KeyboardModifier.NoModifier)
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


def test_posted_drag_moves_control_point(qapp):
    """End-to-end: a posted drag on control point 1 moves it, routed through the
    manipulator (no legacy path)."""
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    s = _make_spline()
    scene.addItem(s)
    m = SelectionManipulator(scene)
    s.setSelected(True)
    qapp.processEvents()
    # control point 1 at (50, 0) -> drag to (70, 30)
    _post_drag(view, scene, [QPointF(50, 0), QPointF(60, 15), QPointF(70, 30)])
    qapp.processEvents()
    moved = s.grip_points()[1]
    assert abs(moved.x() - 70) < 1e-6
    assert abs(moved.y() - 30) < 1e-6
    # the other control points are untouched
    assert s.grip_points()[0] == QPointF(0, 0)
    assert s.grip_points()[3] == QPointF(150, 0)


def test_one_commit_per_gesture(qapp):
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    calls = []
    s = _make_spline(); scene.addItem(s)
    m = SelectionManipulator(scene, commit_hook=lambda mode: calls.append(mode))
    s.setSelected(True); qapp.processEvents()
    _post_drag(view, scene, [QPointF(50, 0), QPointF(60, 15), QPointF(70, 30)])
    qapp.processEvents()
    assert calls == ["grip"]                          # exactly one commit


def test_esc_restores_and_no_commit(qapp):
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    calls = []
    s = _make_spline(); scene.addItem(s)
    before = s.to_dict()
    m = SelectionManipulator(scene, commit_hook=lambda mode: calls.append(mode))
    s.setSelected(True); qapp.processEvents()
    # press + move (mutates), then cancel via the manipulator (Esc path)
    h = s.manip_handles()[1]
    m._begin_handle(h, QPointF(50, 0), QPointF(50, 0))
    m._update(QPointF(70, 30), Qt.KeyboardModifier.NoModifier, QPointF(70, 30))
    assert abs(s.grip_points()[1].x() - 70) < 1e-6    # mutated live
    m.cancel_drag()
    assert s.to_dict() == before                       # restored exactly
    assert calls == []                                 # no undo entry on cancel
