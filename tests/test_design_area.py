"""tests/test_design_area.py — Design-area tile geometry, As cap, pick mode."""

from __future__ import annotations

import math

import pytest
from unittest.mock import MagicMock
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.node import Node
from firepro3d.pipe import Pipe
from firepro3d.design_area import (
    _closest_point_on_segment,
    _wall_distance_on_side,
)


@pytest.fixture
def scene(qapp):
    return QGraphicsScene()


def _mock_wall(x1, y1, x2, y2, level="Level 1"):
    """Wall stub exposing the attrs design_area geometry reads."""
    w = MagicMock()
    w.pt1 = QPointF(x1, y1)
    w.pt2 = QPointF(x2, y2)
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy) or 1.0
    w.normal.return_value = (-dy / length, dx / length)
    w.level = level
    return w


class TestClosestPointOnSegment:
    def test_interior_projection(self):
        cx, cy = _closest_point_on_segment(5, 3, 0, 0, 10, 0)
        assert (cx, cy) == (5.0, 0.0)

    def test_clamped_to_endpoint(self):
        cx, cy = _closest_point_on_segment(-4, 2, 0, 0, 10, 0)
        assert (cx, cy) == (0.0, 0.0)

    def test_degenerate_segment(self):
        cx, cy = _closest_point_on_segment(3, 4, 1, 1, 1, 1)
        assert (cx, cy) == (1.0, 1.0)


class TestWallDistanceOnSide:
    """Side-aware wall lookup: wall must face the query direction AND lie on
    that side of the point."""

    def test_wall_on_queried_side(self):
        # Vertical wall at x=1000; sprinkler at origin; query +X direction.
        wall = _mock_wall(1000, -5000, 1000, 5000)
        d = _wall_distance_on_side(0, 0, 1.0, 0.0, [wall])
        assert d == pytest.approx(1000.0)

    def test_wall_on_opposite_side_ignored(self):
        wall = _mock_wall(1000, -5000, 1000, 5000)
        d = _wall_distance_on_side(0, 0, -1.0, 0.0, [wall])
        assert d is None

    def test_parallel_wall_ignored(self):
        # Horizontal wall — its normal is perpendicular to the +X query.
        wall = _mock_wall(-5000, 1000, 5000, 1000)
        d = _wall_distance_on_side(0, 0, 1.0, 0.0, [wall])
        assert d is None

    def test_nearest_of_two_walls_wins(self):
        near = _mock_wall(800, -5000, 800, 5000)
        far = _mock_wall(2000, -5000, 2000, 5000)
        d = _wall_distance_on_side(0, 0, 1.0, 0.0, [far, near])
        assert d == pytest.approx(800.0)


# ── Tile geometry ─────────────────────────────────────────────────────────────

from firepro3d.design_area import _tile_extents, _tile_polygon
from firepro3d.constants import SQFT_TO_MM2


def _make_node(scene, x, y):
    n = Node(x, y)
    scene.addItem(n)
    return n


def _make_pipe(scene, n1, n2):
    p = Pipe(n1, n2)
    scene.addItem(p)
    return p


def _add_sprinkler(scene_qt, node):
    """Attach a real sprinkler to a node (bare-scene variant of
    Model_Space.add_sprinkler)."""
    node.add_sprinkler()
    return node.sprinkler


def _branch_of_three(scene, spacing=3000.0):
    """Three sprinklers on one X-axis branch: (0,0), (spacing,0), (2*spacing,0)."""
    nodes = [_make_node(scene, i * spacing, 0) for i in range(3)]
    _make_pipe(scene, nodes[0], nodes[1])
    _make_pipe(scene, nodes[1], nodes[2])
    return [_add_sprinkler(scene, n) for n in nodes]


FALLBACK_130 = math.sqrt(130.0 * SQFT_TO_MM2) / 2.0   # ≈ 1737.7 mm


class TestTileExtents:
    def test_middle_sprinkler_shares_half_gap(self, scene):
        sprs = _branch_of_three(scene)
        ext, angle = _tile_extents(sprs[1], sprs, walls=[], ppm=1.0)
        fwd, back, left, right = ext
        assert fwd == pytest.approx(1500.0)
        assert back == pytest.approx(1500.0)
        # No cross-branch neighbours, no walls → fallback on L sides
        assert left == pytest.approx(FALLBACK_130, rel=1e-3)
        assert right == pytest.approx(FALLBACK_130, rel=1e-3)

    def test_end_sprinkler_stops_at_wall(self, scene):
        sprs = _branch_of_three(scene)
        # Wall 1000mm beyond the last sprinkler (x = 7000), facing the branch
        wall = _mock_wall(7000, -5000, 7000, 5000)
        ext, _ = _tile_extents(sprs[2], sprs, walls=[wall], ppm=1.0)
        fwd, back, left, right = ext
        # Branch orientation (fwd vs back) depends on _branch_direction's
        # vector averaging — assert the pair, not which side is which.
        along = sorted((fwd, back))
        assert along[0] == pytest.approx(1000.0)   # stops AT the wall, not 2×
        assert along[1] == pytest.approx(1500.0)   # half-gap to middle sprinkler
        assert along[0] < 1737.0                   # regression: no √cov overshoot

    def test_neighbour_and_wall_on_same_side_takes_nearer(self, scene):
        sprs = _branch_of_three(scene)
        # Wall between middle and end sprinkler, 1200mm from middle
        wall = _mock_wall(4200, -5000, 4200, 5000)
        ext, _ = _tile_extents(sprs[1], sprs, walls=[wall], ppm=1.0)
        # Wall side: min(wall 1200, half-gap 1500) = 1200; other side 1500.
        assert sorted(ext[:2]) == pytest.approx([1200.0, 1500.0])

    def test_cross_branch_neighbour_halves_l(self, scene):
        # Two parallel X branches 4000mm apart in Y
        a = [_make_node(scene, x, 0) for x in (0.0, 3000.0)]
        b = [_make_node(scene, x, 4000.0) for x in (0.0, 3000.0)]
        _make_pipe(scene, a[0], a[1])
        _make_pipe(scene, b[0], b[1])
        sprs = [_add_sprinkler(scene, n) for n in (*a, *b)]
        ext, _ = _tile_extents(sprs[0], sprs, walls=[], ppm=1.0)
        fwd, back, left, right = ext
        # Perp neighbour at +4000 in Y → half = 2000 on that side only
        assert sorted((left, right)) == pytest.approx(
            sorted((2000.0, FALLBACK_130)), rel=1e-3)

    def test_isolated_sprinkler_falls_back_square(self, scene):
        n = _make_node(scene, 0, 0)
        spr = _add_sprinkler(scene, n)
        ext, angle = _tile_extents(spr, [spr], walls=[], ppm=1.0)
        assert all(e == pytest.approx(FALLBACK_130, rel=1e-3) for e in ext)
        assert angle == 0.0


class TestTilePolygon:
    def test_axis_aligned_asymmetric(self):
        poly = _tile_polygon(100.0, 200.0, 0.0, 1500.0, 1000.0, 600.0, 400.0)
        xs = sorted(set(round(poly[i].x() - 100.0, 3) for i in range(poly.count())))
        ys = sorted(set(round(poly[i].y() - 200.0, 3) for i in range(poly.count())))
        assert xs == [-1000.0, 1500.0]    # cx-back .. cx+fwd
        assert ys == [-400.0, 600.0]      # cy-right(-perp) .. cy+left(+perp)

    def test_rotation_preserves_area(self):
        poly = _tile_polygon(0.0, 0.0, math.radians(30), 1500.0, 1500.0, 1000.0, 1000.0)
        # Shoelace area must equal (fwd+back) × (left+right)
        area = 0.0
        for i in range(poly.count()):
            p, q = poly[i], poly[(i + 1) % poly.count()]
            area += p.x() * q.y() - q.x() * p.y()
        assert abs(area) / 2.0 == pytest.approx(3000.0 * 2000.0)


# ── DesignArea shape + As cap ────────────────────────────────────────────────

from firepro3d.design_area import DesignArea
from firepro3d.model_space import Model_Space


def _model_scene(qapp):
    return Model_Space()


def _grid_3x3(ms, spacing=3000.0):
    """3×3 sprinkler grid on X-branches (3 branches, spacing apart in Y)."""
    sprs = []
    for row in range(3):
        nodes = [ms.add_node(col * spacing, row * spacing) for col in range(3)]
        ms.add_pipe(nodes[0], nodes[1])
        ms.add_pipe(nodes[1], nodes[2])
        sprs.extend(ms.add_sprinkler(n) for n in nodes)
    return sprs


class TestDesignAreaShape:
    def test_two_selected_excludes_others(self, qapp):
        """Regression: selecting 2 of 9 must NOT produce a shape covering all 9."""
        ms = _model_scene(qapp)
        sprs = _grid_3x3(ms)
        da = DesignArea([sprs[0], sprs[1]])   # two adjacent on first branch
        ms.addItem(da)
        da.compute_area(ms.scale_manager)
        far = sprs[8].node.scenePos()          # opposite corner sprinkler
        assert da.path().contains(far) is False
        near = sprs[0].node.scenePos()
        assert da.path().contains(near) is True

    def test_islands_stay_separate(self, qapp):
        ms = _model_scene(qapp)
        sprs = _grid_3x3(ms, spacing=3000.0)
        da = DesignArea([sprs[0], sprs[8]])    # opposite corners, far apart
        ms.addItem(da)
        da.compute_area(ms.scale_manager)
        polys = da.path().toSubpathPolygons()
        assert len(polys) == 2

    def test_empty_selection_empty_path(self, qapp):
        ms = _model_scene(qapp)
        da = DesignArea([])
        ms.addItem(da)
        da.compute_area(ms.scale_manager)
        assert da.path().isEmpty()


class TestAsCapAndWarnings:
    def test_as_capped_at_listed_coverage(self, qapp):
        # 4000mm spacing → NFPA S=L=4000mm=13.12ft → S×L ≈ 172 ft² > 130
        ms = _model_scene(qapp)
        sprs = _grid_3x3(ms, spacing=4000.0)
        da = DesignArea(list(sprs))
        ms.addItem(da)
        da.compute_area(ms.scale_manager)
        assert da._as_entries, "As bookkeeping missing"
        for _spr, as_sqft, sxl_sqft, listed in da._as_entries:
            assert as_sqft <= listed + 1e-6
        assert any(sxl > listed for _s, _a, sxl, listed in da._as_entries)
        assert da.spacing_warnings, "expected a spacing-violates-listing warning"
        assert "exceeds listed coverage" in da.spacing_warnings[0]

    def test_no_warning_when_within_listing(self, qapp):
        # 2400mm: even end sprinklers (NFPA doubles single-direction
        # spacing) stay under 130 ft²: 4800×2400mm ≈ 124 ft².
        ms = _model_scene(qapp)
        sprs = _grid_3x3(ms, spacing=2400.0)
        da = DesignArea(list(sprs))
        ms.addItem(da)
        da.compute_area(ms.scale_manager)
        assert da.spacing_warnings == []

    def test_area_property_sums_capped_as(self, qapp):
        from firepro3d.scale_manager import DisplayUnit
        ms = _model_scene(qapp)
        ms.scale_manager.display_unit = DisplayUnit.IMPERIAL
        sprs = _grid_3x3(ms, spacing=4000.0)
        da = DesignArea(list(sprs))
        ms.addItem(da)
        da.compute_area(ms.scale_manager)
        total = sum(a for _s, a, _x, _l in da._as_entries)
        shown = da.get_properties()["Area"]["value"]
        assert f"{total:.0f}" in shown
        assert "sq ft" in shown


# ── Level binding + serialization ────────────────────────────────────────────


class TestLevelBinding:
    def test_serialization_round_trip_level(self, qapp):
        ms = _model_scene(qapp)
        sprs = _grid_3x3(ms)
        da = DesignArea(list(sprs[:2]))
        da.level = "Level 2"
        ms.addItem(da)
        ms.design_areas.append(da)
        ms.active_design_area = da
        state = ms._capture_network()
        assert state["design_areas"][0]["level"] == "Level 2"

    def test_restore_backfills_level_from_sprinklers(self, qapp):
        ms = _model_scene(qapp)
        sprs = _grid_3x3(ms)
        for s in sprs:
            s.node.level = "Level 3"
        da = DesignArea(list(sprs[:2]))
        ms.addItem(da)
        ms.design_areas.append(da)
        state = ms._capture_network()
        del state["design_areas"][0]["level"]     # simulate pre-2026-07 save
        ms._restore_network(state)
        assert ms.design_areas[0].level == "Level 3"

    def test_apply_to_scene_hides_other_level(self, qapp):
        ms = _model_scene(qapp)
        sprs = _grid_3x3(ms)
        da = DesignArea(list(sprs[:2]))
        da.level = "Level 2"
        ms.addItem(da)
        ms.design_areas.append(da)
        from firepro3d.level_manager import LevelManager
        lm = LevelManager()
        lm.apply_to_scene(ms, active_level="Level 1")
        assert da.isVisible() is False
        lm.apply_to_scene(ms, active_level="Level 2")
        assert da.isVisible() is True


# ── Pick mode ────────────────────────────────────────────────────────────────

from types import SimpleNamespace


def _fake_press(modifiers=Qt.KeyboardModifier.NoModifier):
    return SimpleNamespace(modifiers=lambda: modifiers)


class TestPickMode:
    def test_click_toggles_nearest_sprinkler(self, qapp):
        ms = _model_scene(qapp)
        sprs = _grid_3x3(ms)
        ms.set_mode("design_area")
        pos = sprs[4].node.scenePos()
        ms._press_design_area(_fake_press(), pos, pos, None, None, None)
        assert ms.active_design_area is not None
        assert sprs[4] in ms.active_design_area.sprinklers

    def test_miss_beyond_pick_radius(self, qapp):
        from firepro3d.constants import DESIGN_AREA_PICK_PX
        ms = _model_scene(qapp)
        sprs = _grid_3x3(ms)
        ms.set_mode("design_area")
        p = sprs[0].node.scenePos()
        # Headless scene has no view → scale 1.0 → tolerance = PICK_PX scene units
        miss = QPointF(p.x() + DESIGN_AREA_PICK_PX + 5, p.y())
        ms._press_design_area(_fake_press(), miss, miss, None, None, None)
        assert ms.active_design_area is None

    def test_raw_position_used_not_snapped(self, qapp):
        """A snap point dragged far away (e.g. onto a gridline) must not
        hijack the pick — the RAW click position decides."""
        ms = _model_scene(qapp)
        sprs = _grid_3x3(ms)
        ms.set_mode("design_area")
        pos = sprs[0].node.scenePos()
        far_snap = QPointF(pos.x() + 500, pos.y() + 500)
        ms._press_design_area(_fake_press(), pos, far_snap, None, None, None)
        assert ms.active_design_area is not None
        assert sprs[0] in ms.active_design_area.sprinklers

    def test_level_filter_on_pick(self, qapp):
        ms = _model_scene(qapp)
        sprs = _grid_3x3(ms)
        sprs[0].node.level = "Level 2"
        ms.set_mode("design_area")
        pos = sprs[0].node.scenePos()
        ms._press_design_area(_fake_press(), pos, pos, None, None, None)
        assert ms.active_design_area is None   # wrong level → no pick

    def test_design_area_mode_skips_grips(self, qapp):
        """Grip drags must not steal design-area clicks (gridline pull-tabs
        were interfering)."""
        import inspect
        src = inspect.getsource(Model_Space.mousePressEvent)
        assert '"design_area"' in src.split("_skip_grip_modes")[1].split(")")[0]

    def test_shift_rect_filters_by_level(self, qapp):
        ms = _model_scene(qapp)
        sprs = _grid_3x3(ms)
        sprs[8].node.level = "Level 2"
        ms.set_mode("design_area")
        shift = _fake_press(Qt.KeyboardModifier.ShiftModifier)
        c1 = QPointF(-500, -500)
        c2 = QPointF(6500, 6500)      # rectangle over the whole grid
        ms._press_design_area(shift, c1, c1, None, None, None)
        ms._press_design_area(shift, c2, c2, None, None, None)
        assert ms.active_design_area is not None
        assert sprs[8] not in ms.active_design_area.sprinklers
        assert len(ms.active_design_area.sprinklers) == 8


# ── Pick-mode highlight rings ────────────────────────────────────────────────


class TestPickHighlights:
    def test_toggle_adds_ring(self, qapp):
        ms = _model_scene(qapp)
        sprs = _grid_3x3(ms)
        ms.set_mode("design_area")
        pos = sprs[0].node.scenePos()
        ms._press_design_area(_fake_press(), pos, pos, None, None, None)
        assert len(ms._da_highlights) == 1
        ring = ms._da_highlights[0]
        assert ring.scene() is ms
        assert ring.pos() == sprs[0].node.scenePos()

    def test_untoggle_removes_ring(self, qapp):
        ms = _model_scene(qapp)
        sprs = _grid_3x3(ms)
        ms.set_mode("design_area")
        pos = sprs[0].node.scenePos()
        ms._press_design_area(_fake_press(), pos, pos, None, None, None)
        ms._press_design_area(_fake_press(), pos, pos, None, None, None)
        assert ms._da_highlights == []

    def test_mode_exit_clears_rings(self, qapp):
        ms = _model_scene(qapp)
        sprs = _grid_3x3(ms)
        ms.set_mode("design_area")
        pos = sprs[0].node.scenePos()
        ms._press_design_area(_fake_press(), pos, pos, None, None, None)
        ms.set_mode("select")
        assert ms._da_highlights == []

    def test_rings_ignore_mouse(self, qapp):
        ms = _model_scene(qapp)
        sprs = _grid_3x3(ms)
        ms.set_mode("design_area")
        pos = sprs[0].node.scenePos()
        ms._press_design_area(_fake_press(), pos, pos, None, None, None)
        ring = ms._da_highlights[0]
        assert ring.acceptedMouseButtons() == Qt.MouseButton.NoButton


# ── Calc warning surfacing ───────────────────────────────────────────────────


class TestCalcWarningSurfacing:
    def test_spacing_warnings_prepended_to_messages(self, qapp, monkeypatch):
        from firepro3d.hydraulic_solver import HydraulicSolver
        ms = _model_scene(qapp)
        sprs = _grid_3x3(ms)
        da = DesignArea(list(sprs[:2]))
        ms.addItem(da)
        ms.design_areas.append(da)
        ms.active_design_area = da
        da.spacing_warnings = ["Sprinkler at (0, 0): computed S×L 172 ft² "
                               "exceeds listed coverage 130 ft² — spacing "
                               "violates the listing; using 130 ft²."]
        stub = HydraulicSolver._fail("supply missing")
        monkeypatch.setattr(HydraulicSolver, "solve",
                            lambda self, design_sprinklers=None: stub)
        result = ms.run_hydraulics(design_sprinklers=sprs[:2])
        assert result.messages[0].startswith("Sprinkler at (0, 0)")
        assert "supply missing" in result.messages[1]
