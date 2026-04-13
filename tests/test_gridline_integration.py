"""Integration tests for grid system: dialog CRUD, elevation, spacing."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.gridline import GridlineItem, sync_grid_counters


@pytest.fixture
def scene(qapp):
    s = QGraphicsScene()
    s._walls = []
    s._gridlines = []
    return s


class TestDialogReconciliation:
    def test_modify_in_place(self, scene):
        gl = GridlineItem(QPointF(1000, 0), QPointF(1000, 5000), label="A")
        scene.addItem(gl)
        scene._gridlines.append(gl)
        original_id = id(gl)
        gl.setLine(2000, 0, 2000, 5000)
        gl._update_bubble_positions()
        assert id(gl) == original_id
        assert gl.line().p1().x() == pytest.approx(2000.0)

    def test_create_new(self, scene):
        gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="X")
        scene.addItem(gl)
        scene._gridlines.append(gl)
        assert len(scene._gridlines) == 1

    def test_delete_removes(self, scene):
        gl = GridlineItem(QPointF(1000, 0), QPointF(1000, 5000), label="A")
        scene.addItem(gl)
        scene._gridlines.append(gl)
        scene.removeItem(gl)
        scene._gridlines.remove(gl)
        assert len(scene._gridlines) == 0


class TestElevationProjection:
    def test_vertical_projects_to_north(self, scene):
        from firepro3d.elevation_scene import _is_cardinal_for_elevation
        p1, p2 = QPointF(1000, 0), QPointF(1000, 5000)
        assert _is_cardinal_for_elevation(p1, p2, "north") is True
        assert _is_cardinal_for_elevation(p1, p2, "south") is True
        assert _is_cardinal_for_elevation(p1, p2, "east") is False
        assert _is_cardinal_for_elevation(p1, p2, "west") is False

    def test_angled_projects_to_nothing(self, scene):
        from firepro3d.elevation_scene import _is_cardinal_for_elevation
        p1, p2 = QPointF(0, 0), QPointF(5000, 5000)
        for d in ("north", "south", "east", "west"):
            assert _is_cardinal_for_elevation(p1, p2, d) is False


class TestLockEnforcement:
    def test_lock_blocks_grip(self, scene):
        gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="A")
        scene.addItem(gl)
        gl.locked = True
        original_y = gl.line().p1().y()
        gl.apply_grip(0, QPointF(0, -1000))
        assert gl.line().p1().y() == pytest.approx(original_y)

    def test_lock_blocks_perpendicular(self, scene):
        gl = GridlineItem(QPointF(1000, 0), QPointF(1000, 5000), label="A")
        scene.addItem(gl)
        gl.locked = True
        gl.move_perpendicular(500)
        assert gl.line().p1().x() == pytest.approx(1000.0)

    def test_lock_serialization_round_trip(self, scene):
        gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="A")
        gl.locked = True
        d = gl.to_dict()
        gl2 = GridlineItem.from_dict(d)
        assert gl2.locked is True
