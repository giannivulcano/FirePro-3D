"""Posted-event offset-grip drag of a real DimensionAnnotation == legacy
apply_grip outcome; one undo per gesture; Esc restores; snap parity (grid
fallback).

U3 migration of DimensionAnnotation onto manip_handles(). A single round offset
grip (the draggable reposition affordance — round per the gridline bubble-standoff
precedent); apply_grip(0) changes the perpendicular offset distance. Zero special
drag semantics (no Ctrl-constrain, no sibling propagation). Serialization is via
network_codec (no to_dict), so apply-parity is asserted on _offset_dist."""
from PyQt6.QtCore import QPointF, QEvent, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from firepro3d.annotations import DimensionAnnotation
from firepro3d.manip_handle import GripHandle
from firepro3d.manip_math import HandleRole


def _make_dim():
    # Horizontal measurement line -> perpendicular (offset) axis is vertical.
    return DimensionAnnotation(QPointF(0, 0), QPointF(100, 0))


def test_dimension_manip_handles_shape(qapp):
    dm = _make_dim()
    assert len(dm.grip_points()) == 1                 # single offset grip
    hs = dm.manip_handles()
    assert len(hs) == 1
    assert type(hs[0]) is GripHandle
    assert hs[0].index == 0
    assert hs[0].role is HandleRole.GRIP
    assert hs[0].circular is True                     # reposition affordance -> round
    assert hs[0].scene_position(None) == dm.grip_points()[0]


def test_offset_grip_apply_matches_legacy(qapp):
    """The migrated live-apply drag mutation == calling apply_grip directly."""
    target = QPointF(50, 40)
    legacy = _make_dim()
    legacy.apply_grip(0, target)                      # legacy path

    migrated = _make_dim()
    h = migrated.manip_handles()[0]

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
    h.on_drag(m, target, Qt.KeyboardModifier.NoModifier)
    assert abs(migrated._offset_dist - legacy._offset_dist) < 1e-6
    assert migrated.grip_points()[0] == legacy.grip_points()[0]


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


def test_posted_drag_changes_offset(qapp):
    """End-to-end: a posted drag on the offset grip moves it along the
    perpendicular, routed through the manipulator (no legacy path)."""
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    dm = _make_dim()
    scene.addItem(dm)
    m = SelectionManipulator(scene)
    dm.setSelected(True)
    qapp.processEvents()
    start = QPointF(dm.grip_points()[0])
    end = QPointF(start.x(), start.y() + 30)          # drag straight along perp
    _post_drag(view, scene, [start, QPointF(start.x(), start.y() + 15), end])
    qapp.processEvents()
    moved = dm.grip_points()[0]
    assert abs(moved.y() - end.y()) < 1e-6            # grip rode the drag
    assert abs(moved.x() - start.x()) < 1e-6          # x unchanged (perp-only)


def test_one_commit_per_gesture(qapp):
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    calls = []
    dm = _make_dim(); scene.addItem(dm)
    m = SelectionManipulator(scene, commit_hook=lambda mode: calls.append(mode))
    dm.setSelected(True); qapp.processEvents()
    start = QPointF(dm.grip_points()[0])
    _post_drag(view, scene, [start, QPointF(start.x(), start.y() + 15),
                             QPointF(start.x(), start.y() + 30)])
    qapp.processEvents()
    assert calls == ["grip"]                          # exactly one commit


def test_esc_restores_and_no_commit(qapp):
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    calls = []
    dm = _make_dim(); scene.addItem(dm)
    before = dm._offset_dist
    m = SelectionManipulator(scene, commit_hook=lambda mode: calls.append(mode))
    dm.setSelected(True); qapp.processEvents()
    start = QPointF(dm.grip_points()[0])
    h = dm.manip_handles()[0]
    m._begin_handle(h, start, start)
    end = QPointF(start.x(), start.y() + 30)
    m._update(end, Qt.KeyboardModifier.NoModifier, end)
    assert abs(dm._offset_dist - before) > 1e-6       # mutated live
    m.cancel_drag()
    assert abs(dm._offset_dist - before) < 1e-6       # restored exactly
    assert calls == []                                # no undo entry on cancel
