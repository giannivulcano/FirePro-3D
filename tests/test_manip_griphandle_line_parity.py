"""Posted-event endpoint-grip drag of a real LineItem == legacy apply_grip
outcome; one undo per gesture; Esc restores; snap parity; Ctrl angle-constrain
against the opposite endpoint (EndpointGripHandle).

U3 migration of LineItem onto manip_handles(). Endpoints (0, 2) are round +
Ctrl-constrained; the midpoint (1) is square + translates the whole line."""
from PyQt6.QtCore import QPointF, QEvent, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from firepro3d.construction_geometry import LineItem
from firepro3d.manip_handle import GripHandle, EndpointGripHandle
from firepro3d.manip_math import HandleRole


def _make_line():
    return LineItem(QPointF(0, 0), QPointF(100, 0))


class _StubScene:
    """Plain-scene stand-in for direct handle-lifecycle calls (no snap)."""
    _tools = None
    _grip_item = None
    _grip_dragging = False
    def get_effective_position(self, p):
        return QPointF(p)


class _StubM:
    _commit_hook = None
    def __init__(self, sc):
        self._sc = sc
    def scene(self):
        return self._sc
    def _reflow_live(self):
        pass


def test_line_manip_handles_shape():
    ln = _make_line()
    hs = ln.manip_handles()
    assert len(hs) == 3
    assert [h.index for h in hs] == [0, 1, 2]
    assert all(h.role is HandleRole.GRIP for h in hs)
    # endpoints (0, 2) are Ctrl-constrained + round; midpoint (1) plain + square
    assert isinstance(hs[0], EndpointGripHandle) and hs[0].circular is True
    assert isinstance(hs[2], EndpointGripHandle) and hs[2].circular is True
    assert hs[0].opposite_index == 2 and hs[2].opposite_index == 0
    assert type(hs[1]) is GripHandle and hs[1].circular is False
    for i, h in enumerate(hs):
        assert h.scene_position(None) == ln.grip_points()[i]


def test_endpoint_grip_apply_matches_legacy():
    legacy = _make_line()
    legacy.apply_grip(2, QPointF(80, 40))             # legacy path

    migrated = _make_line()
    h = migrated.manip_handles()[2]
    sc = _StubScene(); m = _StubM(sc)
    h.on_press(m)
    h.on_drag(m, QPointF(80, 40), Qt.KeyboardModifier.NoModifier)
    assert migrated.to_dict() == legacy.to_dict()


def test_ctrl_constrains_endpoint_against_opposite():
    """Under Ctrl an endpoint drag routes through the scene's _constrain_angle
    with the OPPOSITE endpoint as the anchor (parity port of the legacy path)."""
    calls = []

    class _CScene(_StubScene):
        def _constrain_angle(self, anchor, raw):
            calls.append((QPointF(anchor), QPointF(raw)))
            return QPointF(42, 42)                     # sentinel

    ln = _make_line()                                  # pt1=(0,0), pt2=(100,0)
    h0 = ln.manip_handles()[0]                         # endpoint pt1, opposite=2
    sc = _CScene(); m = _StubM(sc)
    h0.on_press(m)
    h0.on_drag(m, QPointF(10, 90), Qt.KeyboardModifier.ControlModifier)
    assert len(calls) == 1
    assert calls[0][0] == QPointF(100, 0)             # anchor = opposite endpoint
    assert ln.grip_points()[0] == QPointF(42, 42)     # applied = constrain result


def test_no_ctrl_no_constrain():
    """Without Ctrl the endpoint drag lands on the raw point (no _constrain_angle)."""
    calls = []

    class _CScene(_StubScene):
        def _constrain_angle(self, anchor, raw):
            calls.append((anchor, raw))
            return QPointF(42, 42)

    ln = _make_line()
    h2 = ln.manip_handles()[2]
    sc = _CScene(); m = _StubM(sc)
    h2.on_press(m)
    h2.on_drag(m, QPointF(30, 70), Qt.KeyboardModifier.NoModifier)
    assert calls == []                                 # constrain NOT called
    assert ln.grip_points()[2] == QPointF(30, 70)


def test_midpoint_grip_translates_whole_line():
    ln = _make_line()
    h1 = ln.manip_handles()[1]
    sc = _StubScene(); m = _StubM(sc)
    h1.on_press(m)
    h1.on_drag(m, QPointF(50, 20), Qt.KeyboardModifier.NoModifier)  # mid -> (50,20)
    # whole line translated by (0, +20)
    assert ln.grip_points()[0] == QPointF(0, 20)
    assert ln.grip_points()[2] == QPointF(100, 20)


def _post_drag(view, scene, path):
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


def test_posted_drag_moves_endpoint(qapp):
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    ln = _make_line()
    scene.addItem(ln)
    m = SelectionManipulator(scene)
    ln.setSelected(True)
    qapp.processEvents()
    # endpoint pt2 at (100, 0) -> drag to (100, 60)
    _post_drag(view, scene, [QPointF(100, 0), QPointF(100, 30), QPointF(100, 60)])
    qapp.processEvents()
    moved = ln.grip_points()[2]
    assert abs(moved.x() - 100) < 1e-6
    assert abs(moved.y() - 60) < 1e-6
    assert ln.grip_points()[0] == QPointF(0, 0)        # pt1 untouched


def test_one_commit_per_gesture(qapp):
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    calls = []
    ln = _make_line(); scene.addItem(ln)
    m = SelectionManipulator(scene, commit_hook=lambda mode: calls.append(mode))
    ln.setSelected(True); qapp.processEvents()
    _post_drag(view, scene, [QPointF(100, 0), QPointF(100, 30), QPointF(100, 60)])
    qapp.processEvents()
    assert calls == ["grip"]


def test_esc_restores_and_no_commit(qapp):
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    calls = []
    ln = _make_line(); scene.addItem(ln)
    before = ln.to_dict()
    m = SelectionManipulator(scene, commit_hook=lambda mode: calls.append(mode))
    ln.setSelected(True); qapp.processEvents()
    h = ln.manip_handles()[2]
    m._begin_handle(h, QPointF(100, 0), QPointF(100, 0))
    m._update(QPointF(100, 60), Qt.KeyboardModifier.NoModifier, QPointF(100, 60))
    assert abs(ln.grip_points()[2].y() - 60) < 1e-6   # mutated live
    m.cancel_drag()
    assert ln.to_dict() == before                      # restored exactly
    assert calls == []
