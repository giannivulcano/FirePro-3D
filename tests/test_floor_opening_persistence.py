"""Floor voids survive save/load, undo/redo, delete-host+undo, paste (spec A2, AC7)."""
import json

from PyQt6.QtCore import QPointF as P

from firepro3d.floor_slab import FloorSlab
from firepro3d.floor_opening import FloorOpening


def _rect(x0, y0, x1, y1):
    return [P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1)]


def _xy(pts):
    return [(p.x(), p.y()) for p in pts]


_VOID = [(1000, 1000), (2000, 1000), (2000, 2000), (1000, 2000)]


def _slab_with_void(scene, mark="OP1"):
    slab = FloorSlab(points=_rect(0, 0, 4000, 3000))
    scene.addItem(slab)
    scene._floor_slabs.append(slab)
    op = FloorOpening(_rect(1000, 1000, 2000, 2000), host=slab, mark=mark)
    slab.add_opening(op)
    scene.addItem(op)
    return slab, op


def _voids_in(scene):
    return [it for it in scene.items() if isinstance(it, FloorOpening)]


def test_file_round_trip_restores_voids(qapp, tmp_path):
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    _slab_with_void(ms)
    f = tmp_path / "v.fpd"
    ms.save_to_file(str(f))
    ms2 = Model_Space()
    ms2.load_from_file(str(f))
    (slab,) = ms2._floor_slabs
    (op,) = slab.openings
    assert op.host is slab and op._mark == "OP1" and _xy(op.points) == _VOID
    assert op.scene() is ms2 and _voids_in(ms2) == [op]


def test_void_less_project_saves_no_openings_key(qapp, tmp_path):
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    slab = FloorSlab(points=_rect(0, 0, 4000, 3000))
    ms.addItem(slab)
    ms._floor_slabs.append(slab)
    f = tmp_path / "plain.fpd"
    ms.save_to_file(str(f))
    rec = json.loads(f.read_text(encoding="utf-8"))["floor_slabs"][0]
    assert "openings" not in rec                     # AC7: unchanged on disk


def test_undo_redo_restores_void_edit_without_leaking_items(qapp, model_scene):
    scene = model_scene()
    slab, op = _slab_with_void(scene)
    scene.push_undo_state()
    op.set_points(_rect(1000, 1000, 3000, 2000))
    scene.push_undo_state()
    scene.undo()
    (s,) = scene._floor_slabs
    (o,) = s.openings
    assert _xy(o.points) == _VOID and o.host is s
    assert _voids_in(scene) == [o]                   # the replaced void left the scene
    scene.redo()
    (o,) = scene._floor_slabs[0].openings
    assert _xy(o.points) == [(1000, 1000), (3000, 1000), (3000, 2000), (1000, 2000)]
    assert _voids_in(scene) == [o]


def test_delete_host_removes_void_and_undo_restores_both(qapp, model_scene):
    scene = model_scene()
    slab, op = _slab_with_void(scene)
    scene.push_undo_state()
    scene.delete_items([slab])
    assert scene._floor_slabs == [] and op.scene() is None
    assert _voids_in(scene) == []
    scene.undo()
    (s,) = scene._floor_slabs
    (o,) = s.openings
    assert o.host is s and o.scene() is scene and o._mark == "OP1"


def test_delete_void_detaches_it_from_host(qapp, model_scene):
    scene = model_scene()
    slab, op = _slab_with_void(scene)
    scene.push_undo_state()
    scene.delete_items([op])
    assert slab.openings == [] and op.scene() is None
    assert slab in scene._floor_slabs and slab.scene() is scene


def test_delete_slab_and_its_void_together(qapp, model_scene):
    scene = model_scene()
    slab, op = _slab_with_void(scene)
    scene.push_undo_state()
    scene.delete_items([op, slab])
    assert scene._floor_slabs == [] and _voids_in(scene) == []


def test_paste_reattaches_and_translates_voids(qapp, shown_model_view):
    view, scene = shown_model_view
    slab, op = _slab_with_void(scene)
    scene.clearSelection()
    slab.setSelected(True)
    scene.copy_selected_items()
    scene.paste_items(P(0, 5000))
    assert len(scene._floor_slabs) == 2
    copy = scene._floor_slabs[1]
    (cop,) = copy.openings
    assert cop is not op and cop.host is copy and cop.scene() is scene
    assert _xy(cop.points) == [(x, y + 5000) for x, y in _VOID]     # rides the offset
    assert _xy(op.points) == _VOID and slab.openings == [op]        # source untouched
