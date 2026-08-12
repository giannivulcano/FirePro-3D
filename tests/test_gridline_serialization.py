import math
from PyQt6.QtCore import QPointF
from firepro3d.gridline import GridlineItem
from firepro3d.constants import GRIDLINE_BUBBLE_OFFSET_MM


def test_roundtrip_parametric(qapp):
    gl = GridlineItem(QPointF(10, 20), QPointF(10, 1020), label="A")
    gl.set_bubble_offset(1, 300.0)
    gl._locked = True
    gl.bubble2.setVisible(False)
    d = gl.to_dict()
    assert d["origin"] == [10.0, 20.0]
    assert math.isclose(d["length"], 1000.0, abs_tol=1e-6)
    gl2 = GridlineItem.from_dict(d)
    assert gl2.origin() == QPointF(10, 20)
    assert math.isclose(gl2.length(), 1000.0, abs_tol=1e-6)
    assert gl2.bubble1_offset() == 300.0
    assert gl2._locked is True
    assert gl2.bubble2.isVisible() is False


def test_legacy_p1p2_migration(qapp):
    legacy = {"p1": [0.0, 0.0], "p2": [1000.0, 0.0], "label": "1",
              "bubble1_vis": True, "bubble2_vis": True, "locked": False}
    gl = GridlineItem.from_dict(legacy)
    assert gl.origin() == QPointF(0, 0)
    assert math.isclose(gl.length(), 1000.0, abs_tol=1e-6)
    assert math.isclose(gl.angle_deg() % 360, 0.0, abs_tol=1e-6)
    assert gl.bubble1_offset() == GRIDLINE_BUBBLE_OFFSET_MM  # defaulted


def test_legacy_start_end_migration(qapp):
    legacy = {"start": [0.0, 0.0], "end": [0.0, 1000.0], "label": "A",
              "bubble_start": True, "bubble_end": False}
    gl = GridlineItem.from_dict(legacy)
    assert math.isclose(gl.length(), 1000.0, abs_tol=1e-6)
    assert gl.bubble2.isVisible() is False


def test_undo_path_preserves_gridline(qapp):
    from firepro3d.model_space import Model_Space
    scene = Model_Space()
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 1000), label="A")
    scene.addItem(gl); scene._gridlines.append(gl)
    snap = scene._capture_network()
    scene._restore_network(snap)
    assert len(scene._gridlines) == 1
    assert math.isclose(scene._gridlines[0].length(), 1000.0, abs_tol=1e-6)
