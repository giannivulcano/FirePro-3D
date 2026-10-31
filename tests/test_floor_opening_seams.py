"""Floor-void review fixes (FIX1): undo/redo mid-placement, Level.Name, place ->
undo -> redo, lone-void move, orphan Host row."""
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication

from firepro3d import marks
from firepro3d.element_params import host_values
from firepro3d.floor_opening import FloorOpening
from tests.test_floor_opening_placement import LOW, _slab, _to_polygon, _voids
from tests.test_floor_placement_workflow import _click, _key
from tests.test_selection_manipulator import (  # noqa: F401  (fixture re-export)
    _press_move_release, scene_and_view)


def _ctrl(view, key):
    vp = view.viewport()
    mod = Qt.KeyboardModifier.ControlModifier
    for et in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(vp, QKeyEvent(et, key, mod))


def _clear_floor_opening_state(scene):
    assert scene.mode is None
    assert scene._floor_active is None
    assert scene._floor_opening_candidates == []
    assert scene._feature_ctl.floor_opening_host() is None


def test_ctrl_z_mid_placement_ends_the_placement_and_undoes(qapp, shown_model_view):
    """I1 GUARD: Ctrl+Z with two points down ends floor_opening (draft, host,
    candidates cleared), undoes, and no void can be committed afterwards."""
    view, scene = shown_model_view
    _slab(scene, LOW)
    scene.push_undo_state()
    scene.set_mode("floor_opening")
    _to_polygon(scene)
    _click(view, QPointF(-300, -300))
    _click(view, QPointF(300, -300))
    _ctrl(view, Qt.Key.Key_Z)
    _clear_floor_opening_state(scene)
    _click(view, QPointF(0, 300))
    _key(view, Qt.Key.Key_Return)
    assert _voids(scene) == []


def test_redo_mid_placement_ends_the_placement(qapp, shown_model_view):
    """I1 GUARD: redo takes the same route."""
    view, scene = shown_model_view
    _slab(scene, LOW)
    scene.push_undo_state()
    scene.undo()
    scene.set_mode("floor_opening")
    _to_polygon(scene)
    _click(view, QPointF(-300, -300))
    _click(view, QPointF(300, -300))
    _ctrl(view, Qt.Key.Key_Y)
    _clear_floor_opening_state(scene)
    assert _voids(scene) == []


def test_commit_refuses_a_detached_host(qapp, shown_model_view):
    """I1 backstop: a host no longer in _floor_slabs commits nothing."""
    view, scene = shown_model_view
    slab = _slab(scene, LOW)
    scene.set_mode("floor_opening")
    scene._feature_ctl.arm_floor_host(QPointF(0, 0))
    assert scene._feature_ctl.floor_opening_host() is slab
    scene._floor_slabs.remove(slab)
    n_undo = len(scene._undo_stack)
    pts = [QPointF(-300, -300), QPointF(300, -300), QPointF(0, 300)]
    assert scene._feature_ctl.commit_floor_opening(pts) is None
    assert _voids(scene) == [] and slab.openings == []
    assert len(scene._undo_stack) == n_undo


def test_level_name_param_follows_the_host_top_level(qapp, model_scene):
    """M1 GUARD: Level.Name == Level.Number's source (the host's top level)."""
    scene = model_scene()
    slab = _slab(scene, LOW, top_level="Level 2")
    op = FloorOpening([QPointF(0, 0), QPointF(100, 0), QPointF(0, 100)], slab)
    slab.add_opening(op)
    scene.addItem(op)
    vals = host_values(op)
    assert vals["Level.Name"].raw == "Level 2"
    assert vals["Level.Number"].raw == 2


def test_place_undo_redo_end_to_end(qapp, shown_model_view):
    """M2a GUARD: place through the mode; undo -> gone, redo -> back, same Mark."""
    view, scene = shown_model_view
    _slab(scene, LOW)
    scene.push_undo_state()
    scene.set_mode("floor_opening")
    for p in ((-300, -300), (300, -300), (0, 300)):
        _click(view, QPointF(*p))
    op = _voids(scene)[0]
    mark = marks.get_mark(op)
    assert mark
    scene.undo()
    assert _voids(scene) == []
    assert all(s.openings == [] for s in scene._floor_slabs)
    assert all(not holes for s in scene._floor_slabs for _o, holes in s.cut_region())
    scene.redo()
    vs = _voids(scene)
    assert len(vs) == 1 and marks.get_mark(vs[0]) == mark
    assert vs[0].host in scene._floor_slabs and vs[0] in vs[0].host.openings
    assert any(holes for s in scene._floor_slabs for _o, holes in s.cut_region())


def test_lone_void_move_via_manipulator_drags_the_cut(qapp, scene_and_view):
    """M2b GUARD: a void selected alone, frame-dragged, moves its points and
    the host's hole follows."""
    scene, view = scene_and_view
    from firepro3d.floor_slab import FloorSlab
    slab = FloorSlab(points=[QPointF(0, 0), QPointF(300, 0),
                             QPointF(300, 200), QPointF(0, 200)])
    op = FloorOpening([QPointF(100, 80), QPointF(150, 80),
                       QPointF(150, 130), QPointF(100, 130)], host=slab)
    slab.add_opening(op)
    scene.addItem(slab)
    scene._floor_slabs.append(slab)
    scene.addItem(op)
    op.setSelected(True)
    qapp.processEvents()
    _press_move_release(view, QPointF(125, 105), QPointF(165, 105))
    assert op.points[0].x() == 140.0 and op.points[0].y() == 80.0
    assert slab.points[0].x() == 0.0                       # host untouched
    holes = [h for _o, hs in slab.cut_region() for h in hs]
    assert len(holes) == 1
    xs = [p.x() for p in holes[0]]
    assert min(xs) == 140.0 and max(xs) == 190.0


def test_orphan_void_host_row_does_not_crash(qapp, model_scene):
    """TB10(a) GUARD: a void with no host still lists its properties."""
    scene = model_scene()
    slab = _slab(scene, LOW)
    op = FloorOpening([QPointF(0, 0), QPointF(100, 0), QPointF(0, 100)], slab)
    op.host = None
    assert op.get_properties()["Host"]["value"] == "Floor"
