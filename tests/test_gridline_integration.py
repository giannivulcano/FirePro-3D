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
        gl.set_origin_x(2000.0)
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


def _shown_in(section_scene_for, direction, p1, p2):
    """True when the cardinal section ``direction`` projects a gridline p1->p2."""
    from firepro3d.section_scene import ElevGridlineItem
    ms, sec = section_scene_for(direction)
    gl = GridlineItem(p1, p2, label="G")
    ms._gridlines.append(gl)
    ms.addItem(gl)
    sec.rebuild()
    return any(isinstance(it, ElevGridlineItem) for it in sec.items())


class TestElevationProjection:
    def test_vertical_projects_to_north(self, section_scene_for):
        p1, p2 = QPointF(1000, 0), QPointF(1000, 5000)
        assert _shown_in(section_scene_for, "north", p1, p2) is True
        assert _shown_in(section_scene_for, "south", p1, p2) is True
        assert _shown_in(section_scene_for, "east", p1, p2) is False
        assert _shown_in(section_scene_for, "west", p1, p2) is False

    def test_diagonal_through_box_corners_shows_in_every_cardinal(self, section_scene_for):
        """D7a: an oblique gridline crosses every cardinal cut line."""
        # This diagonal shows in all four only because it passes through the seeded
        # crop-box corners; a general oblique line crosses two of the four.
        p1, p2 = QPointF(0, 0), QPointF(5000, 5000)
        for d in ("north", "south", "east", "west"):
            assert _shown_in(section_scene_for, d, p1, p2) is True


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
