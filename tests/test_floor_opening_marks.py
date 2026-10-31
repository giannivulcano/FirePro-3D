"""Floor voids share the Opening Mark sequence (floor-opening design A8).

Expected Marks cite their raw source: DEFAULT_PATTERNS["Opening"] = "O{n}"
(marks.py); LevelManager() seeds Level 2 with number=2 (level_manager.DEFAULT_LEVELS).
"""
from PyQt6.QtCore import QPointF

from firepro3d import element_params, marks
from firepro3d.floor_opening import FloorOpening
from firepro3d.floor_slab import FloorSlab
from firepro3d.wall import WallSegment
from firepro3d.wall_opening import WallOpening

SLAB = [(0, 0), (4000, 0), (4000, 3000), (0, 3000)]
VOID_L = [(1000, 1000), (2000, 1000), (2000, 2000), (1000, 2000)]
VOID_R = [(2500, 1000), (3500, 1000), (3500, 2000), (2500, 2000)]


def _slab(scene, top_level="Level 1"):
    s = FloorSlab(points=[QPointF(*p) for p in SLAB])
    s._top_level = top_level
    scene.addItem(s)
    scene._floor_slabs.append(s)
    return s


def _void(scene, slab, pts=VOID_L):
    op = FloorOpening([QPointF(*p) for p in pts], slab)
    slab.add_opening(op)
    if op.scene() is not scene:
        scene.addItem(op)
    return op


def _blank(scene, wall):
    op = WallOpening(wall=wall, feature_id="blank_900", offset_along=500.0)
    op.level = wall.level
    wall.openings.append(op)
    scene.addItem(op)
    return op


def test_void_is_opening_category_and_shares_the_sequence(qapp, model_scene):
    """GUARD: one Opening sequence -- walls' blanks first, then slabs' voids."""
    scene = model_scene()
    w = WallSegment(QPointF(0, -2000), QPointF(3000, -2000), thickness_mm=200.0)
    scene.addItem(w)
    scene._walls.append(w)
    b1 = _blank(scene, w)
    assert marks.mint(scene, b1) == "O1"
    slab = _slab(scene)
    v = _void(scene, slab)
    assert element_params.category_of(v) == "Opening"
    assert marks.mint(scene, v) == "O2"
    b2 = _blank(scene, w)
    assert marks.mint(scene, b2) == "O3"          # the void's O2 is seen by the scan
    assert marks.items_of_category(scene, "Opening") == [b1, b2, v]


def test_void_mark_level_comes_from_the_host_top_level(qapp, model_scene):
    """GUARD: {level} = the host's _top_level number in "level" top mode, else blank."""
    scene = model_scene()
    scene.mark_patterns = {"Opening": "{level}-O{n}"}
    slab = _slab(scene, top_level="Level 2")
    v = _void(scene, slab)
    assert marks.mint(scene, v) == "2-O1"
    slab._top_mode = "absolute"
    v2 = _void(scene, slab, VOID_R)
    assert marks.mint(scene, v2) == "-O1"          # no level -> {level} prints ""


def test_renumber_orders_voids_by_centroid(qapp, model_scene):
    """GUARD: Renumber reads each void's centroid (not its (0, 0) scenePos)."""
    scene = model_scene()
    slab = _slab(scene)
    right = _void(scene, slab, VOID_R)            # added first: list order is R, L
    left = _void(scene, slab, VOID_L)
    assert marks.sort_point(left) == (1500.0, 1500.0)
    plan = marks.renumber_plan(scene, "Opening", "project",
                               restart_per_level=False, keep_order=False)
    assert plan[left] == "O1" and plan[right] == "O2"   # same row -> left to right
