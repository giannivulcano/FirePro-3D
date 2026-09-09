"""Posted-event grip drag of a real CircleItem == legacy apply_grip outcome;
one undo per gesture; Esc restores; snap parity (grid fallback)."""
from PyQt6.QtCore import QPointF, QEvent, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from firepro3d.construction_geometry import CircleItem
from firepro3d.manip_handle import GripHandle


def test_circle_manip_handles_shape():
    c = CircleItem(QPointF(0, 0), 50)
    hs = c.manip_handles()
    assert len(hs) == 5
    assert all(isinstance(h, GripHandle) for h in hs)
    assert [h.index for h in hs] == [0, 1, 2, 3, 4]
    # each rides its grip point
    from firepro3d.manip_math import HandleRole
    assert hs[1].scene_position(None) == c.grip_points()[1]
    assert hs[0].role is HandleRole.GRIP


def test_radius_grip_apply_matches_legacy():
    """The migrated drag mutation == calling apply_grip directly (the legacy
    mutation) to the same point."""
    legacy = CircleItem(QPointF(0, 0), 50)
    legacy.apply_grip(1, QPointF(80, 0))          # legacy path

    migrated = CircleItem(QPointF(0, 0), 50)
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
    h.on_press(m); h.on_drag(m, QPointF(80, 0), Qt.KeyboardModifier.NoModifier)
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


def test_posted_drag_moves_radius_grip(qapp):
    """End-to-end: a posted drag on the right radius grip resizes the circle,
    routed through the manipulator (no legacy path)."""
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    c = CircleItem(QPointF(0, 0), 50)
    scene.addItem(c)
    m = SelectionManipulator(scene)
    c.setSelected(True)
    qapp.processEvents()
    # right grip at (50, 0) -> drag to (90, 0)
    _post_drag(view, scene, [QPointF(50, 0), QPointF(70, 0), QPointF(90, 0)])
    qapp.processEvents()
    assert abs(c._radius - 90) < 1e-6


def test_one_commit_per_gesture(qapp):
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    calls = []
    c = CircleItem(QPointF(0, 0), 50); scene.addItem(c)
    m = SelectionManipulator(scene, commit_hook=lambda mode: calls.append(mode))
    c.setSelected(True); qapp.processEvents()
    _post_drag(view, scene, [QPointF(50, 0), QPointF(70, 0), QPointF(90, 0)])
    qapp.processEvents()
    assert calls == ["grip"]          # exactly one commit, mode "grip"


def test_esc_restores_and_no_commit(qapp):
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    calls = []
    c = CircleItem(QPointF(0, 0), 50); scene.addItem(c)
    before = c.to_dict()
    m = SelectionManipulator(scene, commit_hook=lambda mode: calls.append(mode))
    c.setSelected(True); qapp.processEvents()
    # press + move (mutates), then cancel via the manipulator (Esc path)
    h = c.manip_handles()[1]
    m._begin_handle(h, QPointF(50, 0), QPointF(50, 0))
    m._update(QPointF(90, 0), Qt.KeyboardModifier.NoModifier, QPointF(90, 0))
    assert abs(c._radius - 90) < 1e-6         # mutated live
    m.cancel_drag()
    assert c.to_dict() == before              # restored exactly
    assert calls == []                        # no undo entry on cancel
