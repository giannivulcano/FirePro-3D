"""Posted-event vertex-grip drag of a real PolylineItem == legacy apply_grip
outcome; one undo per gesture; Esc restores; snap parity (grid fallback).

U3 migration of PolylineItem onto manip_handles(). Mirrors the CircleItem
parity file (test_manip_griphandle_parity.py); polyline vertices have no
special drag semantics (no Ctrl-constrain, no move-centre grip)."""
from PyQt6.QtCore import QPointF, QEvent, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from firepro3d.construction_geometry import PolylineItem
from firepro3d.manip_handle import GripHandle
from firepro3d.manip_math import HandleRole


def _make_polyline():
    pl = PolylineItem(QPointF(0, 0))
    pl.append_point(QPointF(100, 0))
    pl.append_point(QPointF(100, 100))
    return pl


def test_polyline_manip_handles_shape():
    pl = _make_polyline()
    hs = pl.manip_handles()
    assert len(hs) == 3                               # one per vertex
    assert all(isinstance(h, GripHandle) for h in hs)
    assert [h.index for h in hs] == [0, 1, 2]
    assert all(h.role is HandleRole.GRIP for h in hs)
    # house rule: vertex grips render round (disc); polyline has only vertices
    assert all(h.circular is True for h in hs)
    # each rides its grip point
    for i, h in enumerate(hs):
        assert h.scene_position(None) == pl.grip_points()[i]


def test_vertex_grip_apply_matches_legacy():
    """The migrated live-apply drag mutation == calling apply_grip directly (the
    legacy mutation) to the same point."""
    legacy = _make_polyline()
    legacy.apply_grip(1, QPointF(150, 30))            # legacy path

    migrated = _make_polyline()
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
    h.on_drag(m, QPointF(150, 30), Qt.KeyboardModifier.NoModifier)
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


def test_posted_drag_moves_vertex(qapp):
    """End-to-end: a posted drag on vertex 1 moves that vertex, routed through
    the manipulator (no legacy path)."""
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    pl = _make_polyline()
    scene.addItem(pl)
    m = SelectionManipulator(scene)
    pl.setSelected(True)
    qapp.processEvents()
    # vertex 1 at (100, 0) -> drag to (140, 20)
    _post_drag(view, scene, [QPointF(100, 0), QPointF(120, 10), QPointF(140, 20)])
    qapp.processEvents()
    moved = pl.grip_points()[1]
    assert abs(moved.x() - 140) < 1e-6
    assert abs(moved.y() - 20) < 1e-6
    # the other vertices are untouched
    assert pl.grip_points()[0] == QPointF(0, 0)
    assert pl.grip_points()[2] == QPointF(100, 100)


def test_one_commit_per_gesture(qapp):
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    calls = []
    pl = _make_polyline(); scene.addItem(pl)
    m = SelectionManipulator(scene, commit_hook=lambda mode: calls.append(mode))
    pl.setSelected(True); qapp.processEvents()
    _post_drag(view, scene, [QPointF(100, 0), QPointF(120, 10), QPointF(140, 20)])
    qapp.processEvents()
    assert calls == ["grip"]                          # exactly one commit


def test_esc_restores_and_no_commit(qapp):
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    calls = []
    pl = _make_polyline(); scene.addItem(pl)
    before = pl.to_dict()
    m = SelectionManipulator(scene, commit_hook=lambda mode: calls.append(mode))
    pl.setSelected(True); qapp.processEvents()
    # press + move (mutates), then cancel via the manipulator (Esc path)
    h = pl.manip_handles()[1]
    m._begin_handle(h, QPointF(100, 0), QPointF(100, 0))
    m._update(QPointF(140, 20), Qt.KeyboardModifier.NoModifier, QPointF(140, 20))
    assert abs(pl.grip_points()[1].x() - 140) < 1e-6  # mutated live
    m.cancel_drag()
    assert pl.to_dict() == before                      # restored exactly
    assert calls == []                                 # no undo entry on cancel
