"""Floor voids on the Display Manager / paper "Opening" row (floor-opening A8)."""
from PyQt6.QtCore import QPointF, QSettings

from firepro3d.display_manager import _items_for_category_static, apply_category_defaults
from firepro3d.floor_opening import FloorOpening
from firepro3d.floor_slab import FloorSlab
from firepro3d.paper_display import _category_for_item
from firepro3d.wall import WallSegment
from firepro3d.wall_opening import WallOpening


def _scene_with_blank_and_void(model_scene):
    scene = model_scene()
    w = WallSegment(QPointF(0, -2000), QPointF(3000, -2000), thickness_mm=200.0)
    scene.addItem(w)
    scene._walls.append(w)
    blank = WallOpening(wall=w, feature_id="blank_900", offset_along=500.0)
    w.openings.append(blank)
    scene.addItem(blank)
    slab = FloorSlab(points=[QPointF(0, 0), QPointF(4000, 0),
                             QPointF(4000, 3000), QPointF(0, 3000)])
    scene.addItem(slab)
    scene._floor_slabs.append(slab)
    void = FloorOpening([QPointF(1000, 1000), QPointF(2000, 1000),
                         QPointF(2000, 2000), QPointF(1000, 2000)], slab)
    slab.add_opening(void)
    if void.scene() is not scene:
        scene.addItem(void)
    return scene, blank, slab, void


def test_dm_opening_row_lists_wall_blanks_then_floor_voids(qapp, model_scene):
    """GUARD: the Opening row's item list (DM instance rows + live apply)."""
    scene, blank, slab, void = _scene_with_blank_and_void(model_scene)
    assert _items_for_category_static(scene, "Opening") == [blank, void]
    assert _items_for_category_static(scene, "Floor") == [slab]    # not a Floor row item


def test_category_defaults_style_the_void_from_the_opening_row(qapp, model_scene):
    """GUARD: a new void inherits the Opening row colour (isolated QSettings, #312)."""
    QSettings("GV", "FirePro3D").setValue("display/Opening/color", "#123456")
    scene, blank, slab, void = _scene_with_blank_and_void(model_scene)
    apply_category_defaults(void)
    assert void._display_color == "#123456"


def test_paper_category_of_the_void_is_opening(qapp, model_scene):
    scene, blank, slab, void = _scene_with_blank_and_void(model_scene)
    assert _category_for_item(void) == "Opening"
    assert _category_for_item(slab) == "Floor"
