"""Unit tests for GridlineItem core features: lock, perpendicular move, level independence."""
import sys
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.gridline import GridlineItem
from firepro3d.gridline import (
    reset_grid_counters, sync_grid_counters,
    _next_number, _next_letter_idx, auto_label,
)


@pytest.fixture
def scene(qapp):
    s = QGraphicsScene()
    s._walls = []
    s._gridlines = []
    return s


@pytest.fixture
def vertical_gl(scene):
    """Vertical gridline at x=1000, from y=0 to y=5000."""
    gl = GridlineItem(QPointF(1000, 0), QPointF(1000, 5000))
    scene.addItem(gl)
    scene._gridlines.append(gl)
    return gl


@pytest.fixture
def horizontal_gl(scene):
    """Horizontal gridline at y=2000, from x=0 to x=5000."""
    gl = GridlineItem(QPointF(0, 2000), QPointF(5000, 2000))
    scene.addItem(gl)
    scene._gridlines.append(gl)
    return gl


class TestLock:
    def test_default_unlocked(self, vertical_gl):
        assert vertical_gl.locked is False

    def test_lock_prevents_grip_drag(self, vertical_gl):
        vertical_gl.locked = True
        original_p1 = QPointF(vertical_gl.line().p1())
        vertical_gl.apply_grip(0, QPointF(1000, -500))
        assert vertical_gl.line().p1().y() == pytest.approx(original_p1.y())

    def test_lock_prevents_perpendicular_move(self, vertical_gl):
        vertical_gl.locked = True
        original_x = vertical_gl.line().p1().x()
        vertical_gl.move_perpendicular(200.0)
        assert vertical_gl.line().p1().x() == pytest.approx(original_x)

    def test_unlock_allows_grip_drag(self, vertical_gl):
        vertical_gl.locked = True
        vertical_gl.locked = False
        vertical_gl.apply_grip(0, QPointF(1000, -500))
        assert vertical_gl.line().p1().y() != 0.0


class TestPerpendicularMove:
    def test_move_perpendicular_vertical_gl(self, vertical_gl):
        """Vertical gridline (dx=0): perpendicular is X direction."""
        vertical_gl.move_perpendicular(200.0)
        assert vertical_gl.line().p1().x() == pytest.approx(1200.0)
        assert vertical_gl.line().p2().x() == pytest.approx(1200.0)
        assert vertical_gl.line().p1().y() == pytest.approx(0.0)
        assert vertical_gl.line().p2().y() == pytest.approx(5000.0)

    def test_move_perpendicular_horizontal_gl(self, horizontal_gl):
        """Horizontal gridline (dy=0): perpendicular is Y direction."""
        horizontal_gl.move_perpendicular(-300.0)
        assert horizontal_gl.line().p1().y() == pytest.approx(1700.0)
        assert horizontal_gl.line().p2().y() == pytest.approx(1700.0)
        assert horizontal_gl.line().p1().x() == pytest.approx(0.0)
        assert horizontal_gl.line().p2().x() == pytest.approx(5000.0)

    def test_set_perpendicular_position_vertical(self, vertical_gl):
        vertical_gl.set_perpendicular_position(2500.0)
        assert vertical_gl.line().p1().x() == pytest.approx(2500.0)
        assert vertical_gl.line().p2().x() == pytest.approx(2500.0)

    def test_set_perpendicular_position_horizontal(self, horizontal_gl):
        horizontal_gl.set_perpendicular_position(500.0)
        assert horizontal_gl.line().p1().y() == pytest.approx(500.0)
        assert horizontal_gl.line().p2().y() == pytest.approx(500.0)


class TestGripConstraint:
    def test_grip_constrained_along_direction(self, vertical_gl):
        vertical_gl.apply_grip(0, QPointF(1500, -300))
        assert vertical_gl.line().p1().x() == pytest.approx(1000.0)
        assert vertical_gl.line().p1().y() == pytest.approx(-300.0, abs=1.0)


class TestLevelIndependence:
    def test_no_level_attribute(self, vertical_gl):
        assert not hasattr(vertical_gl, 'level')

    def test_serialization_no_level(self, vertical_gl):
        d = vertical_gl.to_dict()
        assert 'level' not in d

    def test_from_dict_ignores_level(self, scene):
        d = {
            "p1": [0, 0], "p2": [0, 5000],
            "label": "A", "level": "Level 2"
        }
        gl = GridlineItem.from_dict(d)
        assert not hasattr(gl, 'level')


class TestCounterSync:
    def test_sync_numbers(self, scene):
        reset_grid_counters()
        for label in ["1", "2", "5"]:
            gl = GridlineItem(QPointF(0, 0), QPointF(5000, 0), label=label)
            scene.addItem(gl)
            scene._gridlines.append(gl)
        sync_grid_counters(scene._gridlines)
        lbl = auto_label(QPointF(0, 0), QPointF(100, 0))
        assert lbl == "6"

    def test_sync_letters(self, scene):
        reset_grid_counters()
        for label in ["A", "C"]:
            gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label=label)
            scene.addItem(gl)
            scene._gridlines.append(gl)
        sync_grid_counters(scene._gridlines)
        lbl = auto_label(QPointF(0, 0), QPointF(0, 100))
        assert lbl == "D"

    def test_sync_multi_letter(self, scene):
        reset_grid_counters()
        gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="AA")
        scene.addItem(gl)
        scene._gridlines.append(gl)
        sync_grid_counters(scene._gridlines)
        lbl = auto_label(QPointF(0, 0), QPointF(0, 100))
        assert lbl == "AB"

    def test_sync_ignores_custom_labels(self, scene):
        reset_grid_counters()
        gl = GridlineItem(QPointF(0, 0), QPointF(5000, 0), label="X-1")
        scene.addItem(gl)
        scene._gridlines.append(gl)
        sync_grid_counters(scene._gridlines)
        lbl = auto_label(QPointF(0, 0), QPointF(100, 0))
        assert lbl == "1"


class TestDuplicateDetection:
    def test_duplicate_detected(self, scene):
        gl_a = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="A")
        gl_a2 = GridlineItem(QPointF(1000, 0), QPointF(1000, 5000), label="A")
        scene.addItem(gl_a)
        scene.addItem(gl_a2)
        scene._gridlines = [gl_a, gl_a2]
        from firepro3d.gridline import check_duplicate_labels
        dupes = check_duplicate_labels(scene._gridlines)
        assert gl_a in dupes
        assert gl_a2 in dupes

    def test_no_duplicate(self, scene):
        gl_a = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="A")
        gl_b = GridlineItem(QPointF(1000, 0), QPointF(1000, 5000), label="B")
        scene.addItem(gl_a)
        scene.addItem(gl_b)
        scene._gridlines = [gl_a, gl_b]
        from firepro3d.gridline import check_duplicate_labels
        dupes = check_duplicate_labels(scene._gridlines)
        assert len(dupes) == 0


class TestSerialization:
    def test_round_trip(self, scene):
        """to_dict → from_dict preserves all fields."""
        gl = GridlineItem(QPointF(100, 200), QPointF(100, 5200), label="C")
        gl.locked = True
        gl.set_bubble_visible(1, False)
        gl.paper_height_mm = 4.5
        gl.user_layer = "Gridlines"

        d = gl.to_dict()
        gl2 = GridlineItem.from_dict(d)

        assert gl2.grid_label == "C"
        assert gl2.locked is True
        assert gl2.paper_height_mm == pytest.approx(4.5)
        assert gl2.user_layer == "Gridlines"
        assert gl2.line().p1().x() == pytest.approx(100.0)
        assert gl2.line().p1().y() == pytest.approx(200.0)
        assert gl2.line().p2().x() == pytest.approx(100.0)
        assert gl2.line().p2().y() == pytest.approx(5200.0)

    def test_migration_old_format(self, scene):
        """Old GridLine format loads correctly into GridlineItem."""
        old = {
            "type": "grid_line",
            "label": "B",
            "axis": "x",
            "start": [500, 0],
            "end": [500, 3000],
            "locked": True,
            "bubble_start": True,
            "bubble_end": False,
        }
        gl = GridlineItem.from_dict(old)
        assert gl.grid_label == "B"
        assert gl.locked is True
        assert gl.line().p1().x() == pytest.approx(500.0)
        assert gl.line().p2().y() == pytest.approx(3000.0)
        assert gl.paper_height_mm == pytest.approx(3.0)
        assert gl.user_layer == "Default"

    def test_missing_fields_get_defaults(self, scene):
        """Minimal dict gets sensible defaults."""
        d = {"p1": [0, 0], "p2": [0, 1000], "label": "Z"}
        gl = GridlineItem.from_dict(d)
        assert gl.locked is False
        assert gl.paper_height_mm == pytest.approx(3.0)
        assert gl.user_layer == "Default"
