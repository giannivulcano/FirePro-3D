"""'Snap to Underlay' must route through SnapEngine and be zoom-invariant."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsItemGroup, QGraphicsLineItem


def test_find_snap_point_is_gone():
    from firepro3d import model_space
    assert not hasattr(model_space.Model_Space, "find_snap_point"), \
        "world-unit find_snap_point must be deleted (rerouted through SnapEngine)"


@pytest.mark.parametrize("scale", [0.05, 5.0])
def test_underlay_snap_pixel_invariant(qapp, make_model_space, scale):
    ms = make_model_space()
    ms.mode = "select"                 # OSNAP gated off in select; underlay path runs
    ms._snap_to_underlay = True
    grp = QGraphicsItemGroup(); grp.setData(0, "DXF Underlay")
    # Vertical line: p1=(0,0), p2=(0,100000).  The midpoint is at (0,50000),
    # far from any cursor position used below.  Only the p1 endpoint at (0,0)
    # is within the snap aperture when the cursor is near the origin.
    seg = QGraphicsLineItem(0.0, 0.0, 0.0, 100000.0)   # endpoint at (0,0)
    grp.addToGroup(seg); ms.addItem(grp)
    t = QTransform(); t.scale(scale, scale)
    for v in ms.views():
        v.setTransform(t)
    from firepro3d import snap_engine
    # Place the cursor 17 px (in screen pixels) away from (0,0) along x.
    # At both scale values this is inside the 20 px aperture.
    inside_scene = 17.0 / scale
    res = ms.get_effective_position(QPointF(inside_scene, 0.0))
    assert abs(res.x()) < 1.0 and abs(res.y()) < 1.0, \
        f"underlay endpoint not snapped at scale={scale}: {res}"
