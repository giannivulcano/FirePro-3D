"""Floor-void outline snaps (floor-opening design A7, AC5) -- on a tall level whose
z passes the snap engine's 150 overlay cut (mirrors test_wall_polish_smoke_fixes F1)."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform

from firepro3d.floor_opening import FloorOpening
from firepro3d.floor_slab import FloorSlab
from firepro3d.level_manager import LevelManager
from firepro3d.snap_engine import SnapEngine


def _tall_scene():
    from firepro3d.model_space import Model_Space
    from firepro3d.scale_manager import ScaleManager
    s = Model_Space()
    s._level_manager = LevelManager()
    s.scale_manager = ScaleManager()
    s._level_manager.add_level("Level 99", elevation=72000.0)
    slab = FloorSlab(points=[QPointF(0, 0), QPointF(6000, 0),
                             QPointF(6000, 4000), QPointF(0, 4000)])
    slab._top_level = "Level 99"
    s.addItem(slab)
    s._floor_slabs.append(slab)
    op = FloorOpening([QPointF(2000, 1000), QPointF(4000, 1000),
                       QPointF(4000, 3000), QPointF(2000, 3000)], slab)
    slab.add_opening(op)
    if op.scene() is not s:
        s.addItem(op)
    s._level_manager.apply_to_scene(s, active_level="Level 1", view_height=80000.0,
                                    view_depth=-1000.0)
    return s, op


@pytest.mark.parametrize("pt, kind", [
    ((4000, 3000), "endpoint"),     # a vertex
    ((3000, 1000), "midpoint"),     # edge (2000,1000)-(4000,1000)
    ((2000, 2000), "midpoint"),     # the CLOSING edge (2000,3000)-(2000,1000)
])
def test_void_vertex_and_midpoint_snap_on_a_tall_level(qapp, pt, kind):
    """GUARD AC5: RED with FloorOpening missing from ELEV_Z_SNAPPABLE_CLASSES."""
    s, op = _tall_scene()
    assert op.isVisible()
    assert op.zValue() > 150, op.zValue()        # the overlay cut applies here
    target = QPointF(*pt)
    r = SnapEngine().find(QPointF(target), s, QTransform())
    assert r is not None
    assert r.source_item is op and r.snap_type == kind
    assert (r.point - target).manhattanLength() < 1e-6
