"""Floor-void property panel (floor-opening design A8, AC6) through the REAL
PropertyManager row builder.  Raw: FEATURE_REGISTRY["floor_sketched"] = Opening /
Sketched (feature.py); "O{n}" (DEFAULT_PATTERNS)."""
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication, QFormLayout

from firepro3d import marks
from firepro3d.floor_opening import FloorOpening
from firepro3d.floor_slab import FloorSlab
from firepro3d.property_manager import PropertyManager


def _scene_void(model_scene, slab_name="Slab A"):
    scene = model_scene()
    slab = FloorSlab(points=[QPointF(0, 0), QPointF(3000, 0),
                             QPointF(3000, 2000), QPointF(0, 2000)])
    slab.name = slab_name
    scene.addItem(slab)
    scene._floor_slabs.append(slab)
    op = FloorOpening([QPointF(1000, 500), QPointF(2000, 500),
                       QPointF(2000, 1500), QPointF(1000, 1500)], slab)
    slab.add_opening(op)
    if op.scene() is not scene:
        scene.addItem(op)
    marks.mint(scene, op)
    return scene, slab, op


def _panel(scene, op):
    pm = PropertyManager()
    pm.set_level_manager(scene._level_manager)   # makes the legacy Level combo reachable
    pm.show_properties(op)
    QApplication.processEvents()
    return pm


def _rows(pm):
    out = []
    form = pm._form
    for r in range(form.rowCount()):
        lab = form.itemAt(r, QFormLayout.ItemRole.LabelRole)
        fld = form.itemAt(r, QFormLayout.ItemRole.FieldRole)
        if lab is None or fld is None or lab.widget() is None or fld.widget() is None:
            continue
        w = fld.widget()
        out.append((lab.widget().text(), w.text() if hasattr(w, "text") else None))
    return out


def test_panel_rows_feature_type_host_points_mark(qapp, model_scene):
    """GUARD AC6: the five rows, in order, with their real values; Host read-only;
    no legacy Level combo for a void."""
    scene, slab, op = _scene_void(model_scene)
    pm = _panel(scene, op)
    rows = _rows(pm)
    assert rows[:5] == [("Feature", "Opening"), ("Type", "Sketched"),
                        ("Host", "Slab A"), ("Points", "4"), ("Mark", "O1")]
    assert "Level" not in [lbl for lbl, _ in rows]
    assert type(pm._prop_widgets["Host"]).__name__ == "QLabel"      # read-only
    assert type(pm._prop_widgets["Mark"]).__name__ == "QLineEdit"   # the editable row


def test_unnamed_host_reads_floor(qapp, model_scene):
    scene, slab, op = _scene_void(model_scene, slab_name="")
    assert op.get_properties()["Host"]["value"] == "Floor"


def test_mark_edit_pushes_one_undo_step(qapp, model_scene):
    """GUARD: the panel commit is ONE step; a direct set_property pushes its own."""
    scene, slab, op = _scene_void(model_scene)
    pm = _panel(scene, op)
    scene.push_undo_state()            # baseline holding Mark O1
    n = len(scene._undo_stack)
    pm._apply_property("Mark", "X9")
    assert marks.get_mark(op) == "X9"
    assert len(scene._undo_stack) == n + 1
    scene.undo()                       # the step restores the OLD Mark
    restored = [o for s in scene._floor_slabs for o in s.openings]
    assert [marks.get_mark(o) for o in restored] == ["O1"]
    scene.redo()
    restored = [o for s in scene._floor_slabs for o in s.openings]
    assert [marks.get_mark(o) for o in restored] == ["X9"]
    op = restored[0]
    op.set_property("Mark", "X10")
    assert marks.get_mark(op) == "X10"
    assert len(scene._undo_stack) == n + 2
    op.set_property("Points", "9")                 # a read-only row: ignored, no step
    assert len(op.points) == 4 and len(scene._undo_stack) == n + 2
