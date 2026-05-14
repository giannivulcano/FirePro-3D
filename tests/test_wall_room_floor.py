"""Unit tests for WallSegment, Room, and FloorSlab entities."""

from __future__ import annotations

import math
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.wall import (
    WallSegment,
    ALIGN_CENTER,
    ALIGN_LEFT,
    ALIGN_RIGHT,
    DEFAULT_THICKNESS_MM,
    FILL_NONE,
    FILL_SOLID,
    compute_wall_quad,
)
from firepro3d.room import Room
from firepro3d.floor_slab import FloorSlab
from firepro3d.constants import DEFAULT_LEVEL


# ── Helpers ──────────────────────────────────────────────────────────────────

def _pt_approx(actual: QPointF, expected: QPointF, abs_tol: float = 0.01):
    """Assert two QPointF values are approximately equal."""
    assert actual.x() == pytest.approx(expected.x(), abs=abs_tol), (
        f"x mismatch: {actual.x()} != {expected.x()}"
    )
    assert actual.y() == pytest.approx(expected.y(), abs=abs_tol), (
        f"y mismatch: {actual.y()} != {expected.y()}"
    )


def _pts_approx(actual: list[QPointF], expected: list[QPointF],
                 abs_tol: float = 0.01):
    assert len(actual) == len(expected)
    for a, e in zip(actual, expected):
        _pt_approx(a, e, abs_tol)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def scene(qapp):
    """Minimal QGraphicsScene with _walls list (needed by mitered_quad)."""
    s = QGraphicsScene()
    s._walls = []
    return s


@pytest.fixture
def horiz_wall(scene):
    """Horizontal wall: (0,0)->(1000,0), default thickness (152.4 mm)."""
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0))
    scene.addItem(w)
    scene._walls.append(w)
    return w


@pytest.fixture
def vert_wall(scene):
    """Vertical wall: (0,0)->(0,1000), default thickness."""
    w = WallSegment(QPointF(0, 0), QPointF(0, 1000))
    scene.addItem(w)
    scene._walls.append(w)
    return w


@pytest.fixture
def square_room(qapp):
    """1000x1000 mm square room."""
    pts = [QPointF(0, 0), QPointF(1000, 0),
           QPointF(1000, 1000), QPointF(0, 1000)]
    return Room(boundary=pts, color="#4488cc")


@pytest.fixture
def triangle_slab(qapp):
    """Right triangle floor slab: (0,0), (1000,0), (0,1000)."""
    pts = [QPointF(0, 0), QPointF(1000, 0), QPointF(0, 1000)]
    return FloorSlab(points=pts)


# ═══════════════════════════════════════════════════════════════════════════════
# WallSegment tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestWallConstruction:
    """Basic construction and property access."""

    def test_default_thickness(self, horiz_wall):
        assert horiz_wall.thickness_mm == DEFAULT_THICKNESS_MM
        assert horiz_wall.thickness_in == pytest.approx(6.0)

    def test_custom_thickness(self, scene):
        w = WallSegment(QPointF(0, 0), QPointF(500, 0), thickness_mm=304.8)
        scene.addItem(w)
        assert w.thickness_mm == pytest.approx(304.8)
        assert w.thickness_in == pytest.approx(12.0)

    def test_endpoints(self, horiz_wall):
        _pt_approx(horiz_wall.pt1, QPointF(0, 0))
        _pt_approx(horiz_wall.pt2, QPointF(1000, 0))

    def test_centerline_length(self, horiz_wall):
        assert horiz_wall.centerline_length() == pytest.approx(1000.0)

    def test_centerline_angle_horizontal(self, horiz_wall):
        assert horiz_wall.centerline_angle_rad() == pytest.approx(0.0)

    def test_centerline_angle_vertical(self, vert_wall):
        assert vert_wall.centerline_angle_rad() == pytest.approx(math.pi / 2)

    def test_default_alignment_center(self, horiz_wall):
        assert horiz_wall._alignment == ALIGN_CENTER

    def test_default_fill_none(self, horiz_wall):
        assert horiz_wall._fill_mode == FILL_NONE

    def test_default_levels(self, horiz_wall):
        assert horiz_wall._base_level == DEFAULT_LEVEL
        assert horiz_wall._top_level == "Level 2"


class TestWallNormal:
    """Unit normal perpendicular to centerline."""

    def test_horizontal_wall_normal(self, horiz_wall):
        nx, ny = horiz_wall.normal()
        # Horizontal wall (angle=0): normal = (-sin(0), cos(0)) = (0, 1)
        assert nx == pytest.approx(0.0, abs=1e-9)
        assert ny == pytest.approx(1.0, abs=1e-9)

    def test_vertical_wall_normal(self, vert_wall):
        nx, ny = vert_wall.normal()
        # Vertical wall (angle=pi/2): normal = (-sin(pi/2), cos(pi/2)) = (-1, 0)
        assert nx == pytest.approx(-1.0, abs=1e-9)
        assert ny == pytest.approx(0.0, abs=1e-9)

    def test_diagonal_wall_normal(self, scene):
        w = WallSegment(QPointF(0, 0), QPointF(1000, 1000))
        scene.addItem(w)
        nx, ny = w.normal()
        # 45-degree wall: normal direction is (-sin(pi/4), cos(pi/4))
        inv_sqrt2 = 1.0 / math.sqrt(2)
        assert nx == pytest.approx(-inv_sqrt2, abs=1e-9)
        assert ny == pytest.approx(inv_sqrt2, abs=1e-9)
        # Verify unit length
        assert math.hypot(nx, ny) == pytest.approx(1.0)


class TestWallHalfThickness:
    """half_thickness_scene falls back to half_mm without a ScaleManager."""

    def test_fallback_no_scale_manager(self, horiz_wall):
        ht = horiz_wall.half_thickness_scene()
        assert ht == pytest.approx(DEFAULT_THICKNESS_MM / 2.0)

    def test_custom_thickness_half(self, scene):
        w = WallSegment(QPointF(0, 0), QPointF(100, 0), thickness_mm=200.0)
        scene.addItem(w)
        assert w.half_thickness_scene() == pytest.approx(100.0)


class TestWallAlignment:
    """quad_points for Center / Left / Right alignment."""

    def test_center_alignment(self, horiz_wall):
        """Center: wall quad is symmetric about the centerline."""
        p1l, p1r, p2r, p2l = horiz_wall.quad_points()
        ht = horiz_wall.half_thickness_scene()
        # For a horizontal wall, normal is (0,1) so offset is in Y
        _pt_approx(p1l, QPointF(0, ht))
        _pt_approx(p1r, QPointF(0, -ht))
        _pt_approx(p2r, QPointF(1000, -ht))
        _pt_approx(p2l, QPointF(1000, ht))

    def test_left_alignment(self, scene):
        """Left: axis is on the left face, wall extends rightward."""
        w = WallSegment(QPointF(0, 0), QPointF(1000, 0))
        w._alignment = ALIGN_LEFT
        scene.addItem(w)
        ht = w.half_thickness_scene()
        p1l, p1r, p2r, p2l = w.quad_points()
        # Left face at axis (offset by 2*ht in normal direction)
        _pt_approx(p1l, QPointF(0, 2 * ht))
        _pt_approx(p1r, QPointF(0, 0))
        _pt_approx(p2r, QPointF(1000, 0))
        _pt_approx(p2l, QPointF(1000, 2 * ht))

    def test_right_alignment(self, scene):
        """Right: axis is on the right face, wall extends leftward."""
        w = WallSegment(QPointF(0, 0), QPointF(1000, 0))
        w._alignment = ALIGN_RIGHT
        scene.addItem(w)
        ht = w.half_thickness_scene()
        p1l, p1r, p2r, p2l = w.quad_points()
        _pt_approx(p1l, QPointF(0, 0))
        _pt_approx(p1r, QPointF(0, -2 * ht))
        _pt_approx(p2r, QPointF(1000, -2 * ht))
        _pt_approx(p2l, QPointF(1000, 0))


class TestComputeWallQuad:
    """Test the standalone compute_wall_quad function."""

    def test_center_matches_method(self, qapp):
        pt1, pt2 = QPointF(0, 0), QPointF(1000, 0)
        p1l, p1r, p2r, p2l = compute_wall_quad(pt1, pt2, DEFAULT_THICKNESS_MM, ALIGN_CENTER)
        ht = DEFAULT_THICKNESS_MM / 2.0
        _pt_approx(p1l, QPointF(0, ht))
        _pt_approx(p1r, QPointF(0, -ht))
        _pt_approx(p2r, QPointF(1000, -ht))
        _pt_approx(p2l, QPointF(1000, ht))

    def test_left_alignment(self, qapp):
        pt1, pt2 = QPointF(0, 0), QPointF(1000, 0)
        p1l, p1r, p2r, p2l = compute_wall_quad(pt1, pt2, 100.0, ALIGN_LEFT)
        _pt_approx(p1l, QPointF(0, 100))    # 2 * ht = 100
        _pt_approx(p1r, QPointF(0, 0))

    def test_right_alignment(self, qapp):
        pt1, pt2 = QPointF(0, 0), QPointF(1000, 0)
        p1l, p1r, p2r, p2l = compute_wall_quad(pt1, pt2, 100.0, ALIGN_RIGHT)
        _pt_approx(p1l, QPointF(0, 0))
        _pt_approx(p1r, QPointF(0, -100))


class TestWallGripPoints:
    """Grip points: pt1, pt2, midpoint, width grip."""

    def test_grip_count(self, horiz_wall):
        grips = horiz_wall.grip_points()
        assert len(grips) == 4

    def test_grip_pt1(self, horiz_wall):
        grips = horiz_wall.grip_points()
        _pt_approx(grips[0], QPointF(0, 0))

    def test_grip_pt2(self, horiz_wall):
        grips = horiz_wall.grip_points()
        _pt_approx(grips[1], QPointF(1000, 0))

    def test_grip_midpoint(self, horiz_wall):
        grips = horiz_wall.grip_points()
        _pt_approx(grips[2], QPointF(500, 0))

    def test_grip_width_center_alignment(self, horiz_wall):
        """Width grip on the positive-normal (left) face midpoint."""
        grips = horiz_wall.grip_points()
        ht = horiz_wall.half_thickness_scene()
        # Midpoint of left face for center-aligned horizontal wall
        _pt_approx(grips[3], QPointF(500, ht))

    def test_grip_width_right_alignment(self, scene):
        """Right-aligned: width grip on the right (negative-normal) face."""
        w = WallSegment(QPointF(0, 0), QPointF(1000, 0))
        w._alignment = ALIGN_RIGHT
        scene.addItem(w)
        ht = w.half_thickness_scene()
        grips = w.grip_points()
        # Right-aligned: far face is right side = negative-normal
        _pt_approx(grips[3], QPointF(500, -2 * ht))


class TestWallApplyGrip:
    """Applying grip transforms."""

    def test_move_pt1(self, horiz_wall):
        horiz_wall.apply_grip(0, QPointF(100, 50))
        _pt_approx(horiz_wall.pt1, QPointF(100, 50))
        _pt_approx(horiz_wall.pt2, QPointF(1000, 0))

    def test_move_pt2(self, horiz_wall):
        horiz_wall.apply_grip(1, QPointF(2000, 100))
        _pt_approx(horiz_wall.pt1, QPointF(0, 0))
        _pt_approx(horiz_wall.pt2, QPointF(2000, 100))

    def test_move_midpoint_translates_both(self, horiz_wall):
        """Grip index 2 (midpoint) translates the whole wall."""
        horiz_wall.apply_grip(2, QPointF(600, 100))
        # Old mid was (500,0), new mid is (600,100), so delta=(100,100)
        _pt_approx(horiz_wall.pt1, QPointF(100, 100))
        _pt_approx(horiz_wall.pt2, QPointF(1100, 100))

    def test_width_grip_changes_thickness(self, horiz_wall):
        """Grip index 3 (width) adjusts thickness when dragged."""
        old_thick = horiz_wall.thickness_mm
        ht = horiz_wall.half_thickness_scene()
        # Drag width grip further from centerline (double the distance)
        horiz_wall.apply_grip(3, QPointF(500, 2 * ht))
        new_thick = horiz_wall.thickness_mm
        assert new_thick > old_thick

    def test_width_grip_minimum_clamp(self, horiz_wall):
        """Width grip cannot make thickness less than 25.4 mm (1 inch)."""
        horiz_wall.apply_grip(3, QPointF(500, 0.001))
        assert horiz_wall.thickness_mm >= 25.4


class TestWallTranslate:
    def test_translate(self, horiz_wall):
        horiz_wall.translate(100, 200)
        _pt_approx(horiz_wall.pt1, QPointF(100, 200))
        _pt_approx(horiz_wall.pt2, QPointF(1100, 200))


class TestWallJoinModes:
    """Per-endpoint join modes: Auto, Butt, Solid."""

    def test_default_auto(self, horiz_wall):
        assert horiz_wall._join_mode_pt1 == "Auto"
        assert horiz_wall._join_mode_pt2 == "Auto"

    def test_resolve_auto_single_wall_butt(self, horiz_wall):
        """Auto with 1 wall at endpoint resolves to Butt."""
        mode = horiz_wall._resolve_join_mode(0, num_walls_at_point=1)
        assert mode == "Butt"

    def test_resolve_auto_two_walls_solid(self, horiz_wall):
        """Auto with 2 walls at endpoint resolves to Solid."""
        mode = horiz_wall._resolve_join_mode(0, num_walls_at_point=2)
        assert mode == "Solid"

    def test_resolve_auto_three_walls_butt(self, horiz_wall):
        """Auto with 3+ walls (T-junction) resolves to Butt."""
        mode = horiz_wall._resolve_join_mode(0, num_walls_at_point=3)
        assert mode == "Butt"

    def test_explicit_solid_overrides_auto(self, horiz_wall):
        horiz_wall._join_mode_pt1 = "Solid"
        mode = horiz_wall._resolve_join_mode(0, num_walls_at_point=5)
        assert mode == "Solid"

    def test_explicit_butt_overrides_auto(self, horiz_wall):
        horiz_wall._join_mode_pt1 = "Butt"
        mode = horiz_wall._resolve_join_mode(0, num_walls_at_point=2)
        assert mode == "Butt"

    def test_mitered_quad_no_partners_no_solid(self, horiz_wall):
        """Standalone wall: mitered_quad sets no solid flags."""
        horiz_wall.mitered_quad()
        assert horiz_wall._solid_pt1 is False
        assert horiz_wall._solid_pt2 is False


class TestWallEndpointNear:
    def test_near_pt1(self, horiz_wall):
        assert horiz_wall.endpoint_near(QPointF(0.5, 0.5), tolerance=1.0) == 0

    def test_near_pt2(self, horiz_wall):
        assert horiz_wall.endpoint_near(QPointF(999.5, 0.5), tolerance=1.0) == 1

    def test_not_near(self, horiz_wall):
        assert horiz_wall.endpoint_near(QPointF(500, 500), tolerance=1.0) is None


class TestWallSerialization:
    """to_dict / from_dict round-trip."""

    def test_round_trip_basic(self, horiz_wall):
        d = horiz_wall.to_dict()
        assert d["type"] == "wall"
        assert d["pt1"] == [0.0, 0.0]
        assert d["pt2"] == [1000.0, 0.0]
        assert d["thickness_mm"] == DEFAULT_THICKNESS_MM

        restored = WallSegment.from_dict(d)
        _pt_approx(restored.pt1, horiz_wall.pt1)
        _pt_approx(restored.pt2, horiz_wall.pt2)
        assert restored.thickness_mm == pytest.approx(horiz_wall.thickness_mm)

    def test_round_trip_custom_properties(self, scene):
        w = WallSegment(QPointF(10, 20), QPointF(300, 400),
                        thickness_mm=304.8, color="#ff0000")
        w._fill_mode = FILL_SOLID
        w._alignment = ALIGN_LEFT
        w._base_level = "Level 1"
        w._top_level = "Level 3"
        w._height_mm = 4000.0
        w._base_offset_mm = 50.0
        w._top_offset_mm = -25.0
        w.name = "TestWall"
        w._join_mode_pt1 = "Butt"
        w._join_mode_pt2 = "Solid"
        w.level = "Level 1"
        scene.addItem(w)

        d = w.to_dict()
        restored = WallSegment.from_dict(d)

        assert restored._fill_mode == FILL_SOLID
        assert restored._alignment == ALIGN_LEFT
        assert restored._base_level == "Level 1"
        assert restored._top_level == "Level 3"
        assert restored._height_mm == pytest.approx(4000.0)
        assert restored._base_offset_mm == pytest.approx(50.0)
        assert restored._top_offset_mm == pytest.approx(-25.0)
        assert restored.name == "TestWall"
        assert restored._join_mode_pt1 == "Butt"
        assert restored._join_mode_pt2 == "Solid"
        assert restored.level == "Level 1"

    def test_legacy_thickness_in_migration(self, qapp):
        """Old files stored thickness_in; from_dict should convert."""
        data = {
            "type": "wall",
            "pt1": [0, 0], "pt2": [100, 0],
            "thickness_in": 8.0,
            "color": "#cccccc",
        }
        w = WallSegment.from_dict(data)
        assert w.thickness_mm == pytest.approx(8.0 * 25.4)

    def test_legacy_miter_migration(self, qapp):
        """Old 'Miter' join mode should be mapped to 'Solid'."""
        data = {
            "type": "wall",
            "pt1": [0, 0], "pt2": [100, 0],
            "thickness_mm": 100,
            "join_mode_pt1": "Miter",
            "join_mode_pt2": "Miter",
        }
        w = WallSegment.from_dict(data)
        assert w._join_mode_pt1 == "Solid"
        assert w._join_mode_pt2 == "Solid"

    def test_legacy_alignment_migration(self, qapp):
        """Old Interior/Exterior should map to Left/Right."""
        data = {
            "type": "wall",
            "pt1": [0, 0], "pt2": [100, 0],
            "thickness_mm": 100,
            "alignment": "Interior",
        }
        w = WallSegment.from_dict(data)
        assert w._alignment == "Left"

        data["alignment"] = "Exterior"
        w2 = WallSegment.from_dict(data)
        assert w2._alignment == "Right"

    def test_thickness_clamp_on_load(self, qapp):
        """Thickness below 1.0 mm is clamped to 1.0 on load."""
        data = {
            "type": "wall",
            "pt1": [0, 0], "pt2": [100, 0],
            "thickness_mm": 0.5,
        }
        w = WallSegment.from_dict(data)
        assert w.thickness_mm >= 1.0

    def test_openings_list_in_dict(self, horiz_wall):
        """to_dict includes openings (empty list when none)."""
        d = horiz_wall.to_dict()
        assert "openings" in d
        assert d["openings"] == []


class TestWallProperties:
    """get_properties / set_property."""

    def test_get_properties_keys(self, horiz_wall):
        props = horiz_wall.get_properties()
        expected_keys = {
            "Type", "Name", "Colour", "Thickness", "Fill Mode",
            "Alignment", "Base Level", "Base Offset", "Top Level",
            "Top Offset", "Height", "Join Start", "Join End",
        }
        assert expected_keys == set(props.keys())

    def test_set_name(self, horiz_wall):
        horiz_wall.set_property("Name", "Wall-A")
        assert horiz_wall.name == "Wall-A"

    def test_set_fill_mode(self, horiz_wall):
        horiz_wall.set_property("Fill Mode", "Solid")
        assert horiz_wall._fill_mode == "Solid"

    def test_set_alignment(self, horiz_wall):
        horiz_wall.set_property("Alignment", "Left")
        assert horiz_wall._alignment == "Left"

    def test_set_thickness_numeric(self, horiz_wall):
        horiz_wall.set_property("Thickness", 200.0)
        assert horiz_wall.thickness_mm == pytest.approx(200.0)

    def test_set_join_modes(self, horiz_wall):
        horiz_wall.set_property("Join Start", "Solid")
        assert horiz_wall._join_mode_pt1 == "Solid"
        horiz_wall.set_property("Join End", "Butt")
        assert horiz_wall._join_mode_pt2 == "Butt"


# ═══════════════════════════════════════════════════════════════════════════════
# Room tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoomConstruction:
    def test_boundary_stored(self, square_room):
        assert len(square_room.boundary) == 4

    def test_boundary_is_copy(self, square_room):
        """boundary property returns a copy, not internal list."""
        b1 = square_room.boundary
        b2 = square_room.boundary
        assert b1 is not b2

    def test_default_properties(self, square_room):
        assert square_room._hazard_class == "Light Hazard"
        assert square_room._compartment_type == "Room"
        assert square_room._ceiling_type == "Noncombustible unobstructed"
        assert square_room._show_label is True
        assert square_room.level == DEFAULT_LEVEL

    def test_empty_boundary(self, qapp):
        r = Room(boundary=[], color="#ff0000")
        assert len(r.boundary) == 0


class TestRoomArea:
    def test_square_area(self, square_room):
        area = square_room._compute_area_mm2()
        assert area == pytest.approx(1_000_000.0)

    def test_triangle_area(self, qapp):
        pts = [QPointF(0, 0), QPointF(1000, 0), QPointF(0, 1000)]
        r = Room(boundary=pts)
        area = r._compute_area_mm2()
        assert area == pytest.approx(500_000.0)

    def test_degenerate_area(self, qapp):
        """Fewer than 3 points => 0 area."""
        r = Room(boundary=[QPointF(0, 0), QPointF(100, 0)])
        assert r._compute_area_mm2() == 0.0


class TestRoomPerimeter:
    def test_square_perimeter(self, square_room):
        perim = square_room._compute_perimeter_mm()
        assert perim == pytest.approx(4000.0)

    def test_single_point_perimeter(self, qapp):
        r = Room(boundary=[QPointF(0, 0)])
        assert r._compute_perimeter_mm() == 0.0


class TestRoomTranslate:
    def test_translate(self, square_room):
        square_room.translate(100, 200)
        pts = square_room.boundary
        _pt_approx(pts[0], QPointF(100, 200))
        _pt_approx(pts[1], QPointF(1100, 200))
        _pt_approx(pts[2], QPointF(1100, 1200))
        _pt_approx(pts[3], QPointF(100, 1200))


class TestRoomSerialization:
    def test_round_trip(self, square_room):
        square_room.name = "Office"
        square_room._tag = "R-101"
        square_room._hazard_class = "Ordinary Hazard Group 1"
        square_room._compartment_type = "Corridor"
        square_room._ceiling_type = "Combustible obstructed - exposed members >= 3ft (910 mm) O/C"
        square_room._ceiling_level = "Level 3"
        square_room._ceiling_offset = 25.4

        d = square_room.to_dict()
        assert d["type"] == "room"
        assert len(d["boundary"]) == 4
        assert d["name"] == "Office"
        assert d["tag"] == "R-101"
        assert d["hazard_class"] == "Ordinary Hazard Group 1"

        restored = Room.from_dict(d)
        assert restored.name == "Office"
        assert restored._tag == "R-101"
        assert restored._hazard_class == "Ordinary Hazard Group 1"
        assert restored._compartment_type == "Corridor"
        assert restored._ceiling_type == "Combustible obstructed - exposed members >= 3ft (910 mm) O/C"
        assert restored._ceiling_level == "Level 3"
        assert restored._ceiling_offset == pytest.approx(25.4)
        assert len(restored.boundary) == 4

    def test_defaults_on_minimal_data(self, qapp):
        data = {
            "type": "room",
            "boundary": [[0, 0], [100, 0], [100, 100]],
        }
        r = Room.from_dict(data)
        assert r.name == ""
        assert r._hazard_class == "Light Hazard"
        assert r.level == DEFAULT_LEVEL
        assert r._ceiling_level == "Level 2"
        assert len(r.boundary) == 3

    def test_label_offset_round_trip(self, square_room):
        square_room._label_offset = QPointF(50, -30)
        d = square_room.to_dict()
        assert d["label_offset"] == [50, -30]

        restored = Room.from_dict(d)
        _pt_approx(restored._label_offset, QPointF(50, -30))


class TestRoomProperties:
    def test_get_properties_keys(self, square_room):
        props = square_room.get_properties()
        expected_keys = {
            "Type", "Room Name", "Room Tag", "Show Label",
            "Area", "Perimeter", "Floor Level", "Ceiling Level",
            "Ceiling Offset", "Ceiling Height", "Volume",
            "Hazard Class", "Compartment Type", "Ceiling Type",
            "Sprinkler Count", "Coverage/Sprinkler", "Max Coverage",
            "Coverage Status", "Fill Color",
        }
        assert expected_keys == set(props.keys())

    def test_set_hazard_class(self, square_room):
        square_room.set_property("Hazard Class", "Extra Hazard Group 1")
        assert square_room._hazard_class == "Extra Hazard Group 1"

    def test_set_invalid_hazard_class_ignored(self, square_room):
        square_room.set_property("Hazard Class", "Nonexistent")
        assert square_room._hazard_class == "Light Hazard"

    def test_set_room_name(self, square_room):
        square_room.set_property("Room Name", "Server Room")
        assert square_room.name == "Server Room"

    def test_set_room_tag(self, square_room):
        square_room.set_property("Room Tag", "SR-1")
        assert square_room._tag == "SR-1"

    def test_max_coverage_by_hazard(self, square_room):
        square_room._hazard_class = "Light Hazard"
        assert square_room._nfpa_max_coverage_sqft() == pytest.approx(225.0)
        square_room._hazard_class = "Extra Hazard Group 2"
        assert square_room._nfpa_max_coverage_sqft() == pytest.approx(100.0)


# ═══════════════════════════════════════════════════════════════════════════════
# FloorSlab tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestFloorSlabConstruction:
    def test_default_thickness(self, triangle_slab):
        assert triangle_slab._thickness_mm == pytest.approx(152.4)

    def test_points_stored(self, triangle_slab):
        assert len(triangle_slab.points) == 3

    def test_default_level(self, triangle_slab):
        assert triangle_slab.level == DEFAULT_LEVEL

    def test_empty_slab(self, qapp):
        slab = FloorSlab(points=[])
        assert len(slab.points) == 0


class TestFloorSlabPoints:
    def test_add_point(self, qapp):
        slab = FloorSlab(points=[QPointF(0, 0), QPointF(100, 0)])
        slab.add_point(QPointF(100, 100))
        assert len(slab.points) == 3

    def test_grip_points_match(self, triangle_slab):
        grips = triangle_slab.grip_points()
        assert len(grips) == 3
        _pt_approx(grips[0], QPointF(0, 0))
        _pt_approx(grips[1], QPointF(1000, 0))
        _pt_approx(grips[2], QPointF(0, 1000))

    def test_apply_grip(self, triangle_slab):
        triangle_slab.apply_grip(1, QPointF(2000, 500))
        _pt_approx(triangle_slab.points[1], QPointF(2000, 500))

    def test_apply_grip_out_of_range(self, triangle_slab):
        """Out-of-range grip index is a no-op."""
        triangle_slab.apply_grip(10, QPointF(999, 999))
        assert len(triangle_slab.points) == 3

    def test_insert_point(self, triangle_slab):
        triangle_slab.insert_point(1, QPointF(500, 0))
        assert len(triangle_slab.points) == 4
        _pt_approx(triangle_slab.points[1], QPointF(500, 0))

    def test_remove_point_blocks_below_3(self, triangle_slab):
        """Cannot remove a point if it would leave fewer than 3."""
        triangle_slab.remove_point(0)
        assert len(triangle_slab.points) == 3

    def test_remove_point_succeeds_above_3(self, qapp):
        pts = [QPointF(0, 0), QPointF(100, 0),
               QPointF(100, 100), QPointF(0, 100)]
        slab = FloorSlab(points=pts)
        slab.remove_point(2)
        assert len(slab.points) == 3


class TestFloorSlabTranslate:
    def test_translate(self, triangle_slab):
        triangle_slab.translate(50, 75)
        _pt_approx(triangle_slab.points[0], QPointF(50, 75))
        _pt_approx(triangle_slab.points[1], QPointF(1050, 75))
        _pt_approx(triangle_slab.points[2], QPointF(50, 1075))


class TestFloorSlabNearestEdge:
    def test_nearest_edge_on_edge(self, triangle_slab):
        idx, dist, proj = triangle_slab.nearest_edge(QPointF(500, 0))
        assert idx == 0  # first edge: (0,0)->(1000,0)
        assert dist == pytest.approx(0.0, abs=0.1)

    def test_nearest_edge_off_edge(self, triangle_slab):
        idx, dist, proj = triangle_slab.nearest_edge(QPointF(500, -50))
        assert idx == 0
        assert dist == pytest.approx(50.0, abs=0.1)


class TestFloorSlabSerialization:
    def test_round_trip(self, triangle_slab):
        triangle_slab.name = "Slab-1"
        triangle_slab._thickness_mm = 200.0
        triangle_slab._level_offset_mm = 10.0

        d = triangle_slab.to_dict()
        assert d["type"] == "floor_slab"
        assert len(d["points"]) == 3
        assert d["thickness_mm"] == pytest.approx(200.0)
        assert d["name"] == "Slab-1"
        assert d["level_offset_mm"] == pytest.approx(10.0)

        restored = FloorSlab.from_dict(d)
        assert restored.name == "Slab-1"
        assert restored._thickness_mm == pytest.approx(200.0)
        assert restored._level_offset_mm == pytest.approx(10.0)
        assert len(restored.points) == 3

    def test_level_offset_omitted_when_zero(self, triangle_slab):
        d = triangle_slab.to_dict()
        assert "level_offset_mm" not in d

    def test_defaults_on_minimal_data(self, qapp):
        data = {
            "type": "floor_slab",
            "points": [[0, 0], [100, 0], [100, 100]],
        }
        slab = FloorSlab.from_dict(data)
        assert slab.name == ""
        assert slab.level == DEFAULT_LEVEL
        assert slab._thickness_mm == pytest.approx(152.4)

    def test_legacy_thickness_ft_migration(self, qapp):
        """Old files stored thickness_ft; from_dict converts."""
        data = {
            "type": "floor_slab",
            "points": [[0, 0], [100, 0], [100, 100]],
            "thickness_ft": 0.5,
        }
        slab = FloorSlab.from_dict(data)
        assert slab._thickness_mm == pytest.approx(0.5 * 304.8)


class TestFloorSlabProperties:
    def test_get_properties_keys(self, triangle_slab):
        props = triangle_slab.get_properties()
        expected_keys = {
            "Type", "Name", "Level", "Level Offset",
            "Colour", "Thickness", "Points",
        }
        assert expected_keys == set(props.keys())

    def test_set_name(self, triangle_slab):
        triangle_slab.set_property("Name", "Ground Floor")
        assert triangle_slab.name == "Ground Floor"

    def test_set_thickness_numeric(self, triangle_slab):
        triangle_slab.set_property("Thickness", 300.0)
        assert triangle_slab._thickness_mm == pytest.approx(300.0)

    def test_set_level(self, triangle_slab):
        triangle_slab.set_property("Level", "Level 2")
        assert triangle_slab.level == "Level 2"

    def test_set_level_offset(self, triangle_slab):
        triangle_slab.set_property("Level Offset", 50.0)
        assert triangle_slab._level_offset_mm == pytest.approx(50.0)
