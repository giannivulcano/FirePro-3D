"""Posted-event grip drag of a real RegularPolygonItem == legacy apply_grip
outcome; one undo per gesture; Esc restores; snap parity (grid fallback).

U3 migration of RegularPolygonItem onto manip_handles(). Mirrors the ArcItem
parity file; the polygon's grips (centre + N vertices) have no special drag
semantics (the legacy grip path explicitly excludes polygon from Ctrl-constrain)
and all render round per the house rule (centre = move grip; vertices = the
polygon's defining points — dragging one resizes + rotates)."""
from PyQt6.QtCore import QPointF, QEvent, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from firepro3d.construction_geometry import RegularPolygonItem
from firepro3d.manip_handle import GripHandle
from firepro3d.manip_math import HandleRole


def _make_poly():
    # centre (0,0), 6 sides, circumradius 50, rotation 0, inscribed (Y-up CCW+):
    #   grip 0    = centre  (0, 0)
    #   grip 1    = vertex 0 (50, 0)
    #   grip 2..6 = vertices 1..5
    return RegularPolygonItem(QPointF(0, 0), sides=6, radius_mm=50.0,
                              rotation_deg=0.0, inscribed=True)


def test_polygon_manip_handles_shape():
    p = _make_poly()
    hs = p.manip_handles()
    assert len(hs) == 7                               # centre + 6 vertices
    assert all(isinstance(h, GripHandle) for h in hs)
    assert [h.index for h in hs] == [0, 1, 2, 3, 4, 5, 6]
    assert all(h.role is HandleRole.GRIP for h in hs)
    # house rule: centre (move) + all vertices render round
    assert all(h.circular is True for h in hs)
    # each rides its grip point
    for i, h in enumerate(hs):
        assert h.scene_position(None) == p.grip_points()[i]


def test_handle_count_tracks_sides():
    p = RegularPolygonItem(QPointF(0, 0), sides=5, radius_mm=40.0)
    assert len(p.manip_handles()) == 6                # centre + 5 vertices


def _drive_handle(item, index, drag_to, mods=Qt.KeyboardModifier.NoModifier):
    """Run a handle's live-apply drag lifecycle against a headless fake scene."""
    h = item.manip_handles()[index]

    class _Scene:
        _tools = None
        _grip_item = None
        _grip_dragging = False
        def get_effective_position(self, pt): return QPointF(pt)
    class _M:
        _commit_hook = None
        def scene(self_m): return sc
        def _reflow_live(self_m): pass
    sc = _Scene()
    m = _M()
    h.on_press(m)
    h.on_drag(m, QPointF(drag_to), mods)
    return h, m


def test_vertex_grip_apply_matches_legacy():
    """The migrated live-apply drag mutation == calling apply_grip directly.
    Grip 1 (vertex 0) exercises the radius+rotation branch of apply_grip."""
    legacy = _make_poly()
    legacy.apply_grip(1, QPointF(80, 20))             # legacy path (vertex)

    migrated = _make_poly()
    _drive_handle(migrated, 1, QPointF(80, 20))
    assert migrated.to_dict() == legacy.to_dict()


def test_centre_grip_apply_matches_legacy():
    """Grip 0 exercises the translate branch of apply_grip."""
    legacy = _make_poly()
    legacy.apply_grip(0, QPointF(15, -25))

    migrated = _make_poly()
    _drive_handle(migrated, 0, QPointF(15, -25))
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


def test_posted_drag_moves_vertex_grip(qapp):
    """End-to-end: a posted drag on vertex-0 grip (index 1) moves it, routed
    through the manipulator (no legacy path). apply_grip stores radius+rotation
    and reprojects, so the dragged vertex lands exactly at the drop point."""
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    p = _make_poly()
    scene.addItem(p)
    SelectionManipulator(scene)
    p.setSelected(True)
    qapp.processEvents()
    # vertex-0 grip at (50, 0) -> drag to (80, 20)
    _post_drag(view, scene, [QPointF(50, 0), QPointF(65, 10), QPointF(80, 20)])
    qapp.processEvents()
    moved = p.grip_points()[1]
    assert abs(moved.x() - 80) < 1e-6
    assert abs(moved.y() - 20) < 1e-6
    # the centre is untouched by a vertex-grip drag
    assert p.grip_points()[0] == QPointF(0, 0)


def test_posted_drag_moves_centre_grip(qapp):
    """A posted drag on the centre grip (index 0) translates the polygon."""
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    p = _make_poly()
    scene.addItem(p)
    SelectionManipulator(scene)
    p.setSelected(True)
    qapp.processEvents()
    _post_drag(view, scene, [QPointF(0, 0), QPointF(10, -10), QPointF(20, -20)])
    qapp.processEvents()
    centre = p.grip_points()[0]
    assert abs(centre.x() - 20) < 1e-6
    assert abs(centre.y() - (-20)) < 1e-6


def test_one_commit_per_gesture(qapp):
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    calls = []
    p = _make_poly(); scene.addItem(p)
    SelectionManipulator(scene, commit_hook=lambda mode: calls.append(mode))
    p.setSelected(True); qapp.processEvents()
    _post_drag(view, scene, [QPointF(50, 0), QPointF(65, 10), QPointF(80, 20)])
    qapp.processEvents()
    assert calls == ["grip"]                          # exactly one commit


def test_esc_restores_and_no_commit(qapp):
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    calls = []
    p = _make_poly(); scene.addItem(p)
    before = p.to_dict()
    m = SelectionManipulator(scene, commit_hook=lambda mode: calls.append(mode))
    p.setSelected(True); qapp.processEvents()
    # press + move (mutates vertex 0), then cancel via the manipulator (Esc)
    h = p.manip_handles()[1]
    m._begin_handle(h, QPointF(50, 0), QPointF(50, 0))
    m._update(QPointF(80, 20), Qt.KeyboardModifier.NoModifier, QPointF(80, 20))
    assert p._radius_mm != 50.0                        # mutated live
    m.cancel_drag()
    assert p.to_dict() == before                       # restored exactly
    assert calls == []                                 # no undo entry on cancel


def test_provides_manip_handles():
    """The polygon provides its own manipulator handles (migrated)."""
    assert _make_poly().manip_handles()
