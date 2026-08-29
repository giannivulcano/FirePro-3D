"""Underlay snapping routes through SnapEngine (zoom-invariant, per-record gated).

The global _snap_to_underlay toggle was removed in favour of per-underlay
Underlay.snap flag.  Underlay geometry is offered to the snap engine through
the UnderlaySnapIndex attached to each group (group.data(4)).
"""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsItemGroup, QGraphicsLineItem

from firepro3d.underlay import Underlay
from firepro3d.underlay_snap_index import UnderlaySnapIndex


def test_find_snap_point_is_gone():
    from firepro3d import model_space
    assert not hasattr(model_space.Model_Space, "find_snap_point"), \
        "world-unit find_snap_point must be deleted (rerouted through SnapEngine)"


def test_global_toggle_attribute_removed():
    """_snap_to_underlay must not be assigned anywhere in Model_Space.__init__."""
    import inspect
    from firepro3d.model_space import Model_Space
    src = inspect.getsource(Model_Space.__init__)
    assert "_snap_to_underlay" not in src, \
        "_snap_to_underlay assignment must be removed from Model_Space.__init__"


@pytest.mark.parametrize("scale", [0.05, 5.0])
def test_underlay_snap_pixel_invariant(qapp, make_model_space, scale):
    """Underlay endpoints snap correctly through the normal snap engine path."""
    from firepro3d import snap_engine
    snap_engine.SNAP_TOLERANCE_PX = 20   # pin the aperture this test's px offsets assume
    ms = make_model_space()
    # Use a placement mode so the normal snap block fires
    ms.set_mode("draw_pipe")
    ms._snap_enabled = True
    ms._snap_engine.enabled = True

    # Build a group backed by a real UnderlaySnapIndex (snap=True)
    rec = Underlay(type="dxf", path="test.dxf", snap=True)
    geom = [{"kind": "line", "layer": "0",
              "x1": 0.0, "y1": 0.0, "x2": 0.0, "y2": 100000.0}]
    index = UnderlaySnapIndex(geom, rec.hidden_layers, rec)

    grp = QGraphicsItemGroup()
    grp.setData(0, "DXF Underlay")
    grp.setData(4, index)
    # Add a visible line child so the group has a bounding rect
    seg = QGraphicsLineItem(0.0, 0.0, 0.0, 100000.0)
    grp.addToGroup(seg)
    ms.addItem(grp)

    t = QTransform(); t.scale(scale, scale)
    for v in ms.views():
        v.setTransform(t)

    # Place the cursor 17 px (in screen pixels) away from (0,0) along x.
    # At both scale values this is inside the 20 px aperture.
    inside_scene = 17.0 / scale
    res = ms.get_effective_position(QPointF(inside_scene, 0.0))
    assert abs(res.x()) < 1.0 and abs(res.y()) < 1.0, \
        f"underlay endpoint not snapped at scale={scale}: {res}"
