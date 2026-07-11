"""Unit tests for the 3D view system (firepro3d/view_3d.py).

Tests cover:
  - _mesh_from_faces helper
  - _flux_to_colors static method (5-band colour mapping)
  - _is_visible static method (display overrides)
  - Coordinate transformations (_scene_to_3d, _level_z_mm)
  - Camera angle round-trip (_camera_to_angles / _set_camera_from_angles)
  - Scene bounds computation (_compute_scene_bounds)
  - Actor management (_add_actor / _clear_actors, entity mapping)
  - Dirty-flag rebuild scheduling
  - Module-level constants sanity checks

PyVista and VTK are required for most tests.  If unavailable, the
entire module is skipped via ``pytest.importorskip``.
"""

from __future__ import annotations

import math
import sys

import numpy as np
import pytest

pv = pytest.importorskip("pyvista")
pv.OFF_SCREEN = True

# VTK must also be importable for the view module
pytest.importorskip("vtk")
pytest.importorskip("pyvistaqt")

from PyQt6.QtWidgets import QGraphicsScene
from PyQt6.QtCore import pyqtSignal

from firepro3d.view_3d import (
    _mesh_from_faces,
    View3D,
    FT_TO_MM,
    CIRCLE_SEGMENTS,
    PICK_TOLERANCE_PX,
    MAX_CYLINDER_PIPES,
    COL_NODE,
    COL_SPRINKLER,
    COL_HIGHLIGHT,
    _PIPE_COLORS,
    _FLOOR_COLORS,
)


# ---------------------------------------------------------------------------
# Test helpers / fixtures
# ---------------------------------------------------------------------------

class _FakeSprinklerSystem:
    nodes: list = []
    pipes: list = []


class _FakeScene(QGraphicsScene):
    """Minimal QGraphicsScene subclass with the signals View3D connects to."""
    sceneModified = pyqtSignal()
    selectionChanged = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.sprinkler_system = _FakeSprinklerSystem()


class _FakeLevel:
    def __init__(self, name: str, elevation: float):
        self.name = name
        self.elevation = elevation


class _FakeLevelManager:
    def __init__(self, levels=None):
        self.levels = levels or []

    def get(self, name: str):
        for lvl in self.levels:
            if lvl.name == name:
                return lvl
        return None


class _FakeScaleManager:
    def __init__(self, ppm: float = 1.0, calibrated: bool = False):
        self.pixels_per_mm = ppm
        self.is_calibrated = calibrated


@pytest.fixture()
def view3d(qapp):
    """Create a headless View3D with empty mocks."""
    scene = _FakeScene()
    lm = _FakeLevelManager()
    sm = _FakeScaleManager()
    v = View3D(scene, lm, sm)
    yield v
    v.close()


@pytest.fixture()
def view3d_calibrated(qapp):
    """View3D with a calibrated scale manager (2 px/mm)."""
    scene = _FakeScene()
    lm = _FakeLevelManager(levels=[
        _FakeLevel("Level 1", 0.0),
        _FakeLevel("Level 2", 3048.0),
    ])
    sm = _FakeScaleManager(ppm=2.0, calibrated=True)
    v = View3D(scene, lm, sm)
    yield v
    v.close()


# ===================================================================
# Teardown: plotter finalization (VTK GL-context leak guard)
# ===================================================================

class TestCleanup:
    """View3D.cleanup() must release the VTK plotter (so its GL context does
    not leak past Qt teardown and crash later 3D renders)."""

    def test_cleanup_releases_plotter(self, view3d):
        assert view3d._plotter is not None
        view3d.cleanup()
        assert view3d._plotter is None

    def test_cleanup_is_idempotent(self, view3d):
        view3d.cleanup()
        view3d.cleanup()  # second call must not raise
        assert view3d._plotter is None

    def test_close_event_releases_plotter(self, view3d):
        view3d.close()  # QWidget.close() -> closeEvent -> cleanup()
        assert view3d._plotter is None

    def test_rebuild_after_cleanup_is_noop(self, view3d):
        """rebuild() after cleanup() must not raise.

        A closed-but-not-yet-deleted MainWindow can still receive its
        debounced _view_refresh_timer timeout at the next processEvents()
        anywhere in the process; the slot calls view_3d.rebuild() with
        _plotter already None.  Under pytest (no excepthook) the resulting
        AttributeError in a Qt-invoked slot fail-fasts the whole process
        (0xC0000409) — the long-standing "environmental" full-suite crash.
        """
        view3d.cleanup()
        view3d.rebuild()  # must not raise


# ===================================================================
# Module-level helper: _mesh_from_faces
# ===================================================================

class TestMeshFromFaces:
    """Verify _mesh_from_faces builds valid PyVista PolyData."""

    def test_single_triangle(self):
        verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32)
        faces = np.array([[0, 1, 2]], dtype=np.int32)
        mesh = _mesh_from_faces(verts, faces)
        assert mesh.n_points == 3
        assert mesh.n_cells == 1

    def test_quad_as_two_triangles(self):
        verts = np.array([
            [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        ], dtype=np.float32)
        faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
        mesh = _mesh_from_faces(verts, faces)
        assert mesh.n_points == 4
        assert mesh.n_cells == 2

    def test_empty_faces(self):
        """Zero faces should produce a mesh with no cells."""
        verts = np.array([[0, 0, 0]], dtype=np.float32)
        faces = np.empty((0, 3), dtype=np.int32)
        mesh = _mesh_from_faces(verts, faces)
        assert mesh.n_cells == 0

    def test_returns_polydata(self):
        verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32)
        faces = np.array([[0, 1, 2]], dtype=np.int32)
        mesh = _mesh_from_faces(verts, faces)
        assert isinstance(mesh, pv.PolyData)


# ===================================================================
# Static method: _flux_to_colors
# ===================================================================

class TestFluxToColors:
    """Verify the 5-band flux-to-RGBA colour mapping."""

    def test_shape_matches_input(self):
        flux = np.array([0.0, 0.5, 1.0])
        colors = View3D._flux_to_colors(flux, threshold=1.0)
        assert colors.shape == (3, 4)

    def test_all_alpha_one(self):
        flux = np.linspace(0, 2, 20)
        colors = View3D._flux_to_colors(flux, threshold=1.0)
        np.testing.assert_array_equal(colors[:, 3], 1.0)

    def test_band_below_25pct(self):
        """Ratio < 0.25 -> blue band."""
        colors = View3D._flux_to_colors(np.array([0.1]), threshold=1.0)
        np.testing.assert_array_almost_equal(colors[0], [0.0, 0.2, 0.8, 1.0])

    def test_band_25_to_50pct(self):
        """Ratio in [0.25, 0.50) -> green band."""
        colors = View3D._flux_to_colors(np.array([0.3]), threshold=1.0)
        np.testing.assert_array_almost_equal(colors[0], [0.0, 0.7, 0.2, 1.0])

    def test_band_50_to_75pct(self):
        """Ratio in [0.50, 0.75) -> yellow band."""
        colors = View3D._flux_to_colors(np.array([0.6]), threshold=1.0)
        np.testing.assert_array_almost_equal(colors[0], [0.9, 0.9, 0.0, 1.0])

    def test_band_75_to_100pct(self):
        """Ratio in [0.75, 1.00) -> orange band."""
        colors = View3D._flux_to_colors(np.array([0.8]), threshold=1.0)
        np.testing.assert_array_almost_equal(colors[0], [1.0, 0.5, 0.0, 1.0])

    def test_band_at_or_above_100pct(self):
        """Ratio >= 1.00 -> red band."""
        colors = View3D._flux_to_colors(np.array([1.0, 1.5, 10.0]), threshold=1.0)
        for i in range(3):
            np.testing.assert_array_almost_equal(colors[i], [1.0, 0.0, 0.0, 1.0])

    def test_zero_threshold_defaults_to_one(self):
        """threshold <= 0 is clamped to 1.0 to avoid division by zero."""
        colors = View3D._flux_to_colors(np.array([0.5]), threshold=0.0)
        assert colors.shape == (1, 4)

    def test_exact_boundaries(self):
        """Values at exact band boundaries land in the higher band."""
        flux = np.array([0.25, 0.50, 0.75, 1.00])
        colors = View3D._flux_to_colors(flux, threshold=1.0)
        # 0.25 -> green
        np.testing.assert_array_almost_equal(colors[0], [0.0, 0.7, 0.2, 1.0])
        # 0.50 -> yellow
        np.testing.assert_array_almost_equal(colors[1], [0.9, 0.9, 0.0, 1.0])
        # 0.75 -> orange
        np.testing.assert_array_almost_equal(colors[2], [1.0, 0.5, 0.0, 1.0])
        # 1.00 -> red
        np.testing.assert_array_almost_equal(colors[3], [1.0, 0.0, 0.0, 1.0])

    def test_negative_flux(self):
        """Negative flux should land in the lowest band."""
        colors = View3D._flux_to_colors(np.array([-5.0]), threshold=1.0)
        np.testing.assert_array_almost_equal(colors[0], [0.0, 0.2, 0.8, 1.0])

    def test_single_value(self):
        colors = View3D._flux_to_colors(np.array([0.0]), threshold=1.0)
        assert colors.shape == (1, 4)

    def test_empty_array(self):
        colors = View3D._flux_to_colors(np.array([]), threshold=1.0)
        assert colors.shape == (0, 4)


# ===================================================================
# Static method: _is_visible
# ===================================================================

class TestIsVisible:
    """Verify display-override visibility check."""

    def test_no_overrides_attr(self):
        class Plain:
            pass
        assert View3D._is_visible(Plain()) is True

    def test_overrides_none(self):
        class Item:
            _display_overrides = None
        assert View3D._is_visible(Item()) is True

    def test_overrides_visible_false(self):
        class Item:
            _display_overrides = {"visible": False}
        assert View3D._is_visible(Item()) is False

    def test_overrides_visible_true(self):
        class Item:
            _display_overrides = {"visible": True}
        assert View3D._is_visible(Item()) is True

    def test_overrides_empty_dict(self):
        class Item:
            _display_overrides = {}
        assert View3D._is_visible(Item()) is True

    def test_overrides_other_keys_only(self):
        class Item:
            _display_overrides = {"color": "red", "opacity": 0.5}
        assert View3D._is_visible(Item()) is True


# ===================================================================
# Coordinate transformations
# ===================================================================

class TestSceneTo3D:
    """Verify 2D scene -> 3D world coordinate mapping."""

    def test_uncalibrated_identity(self, view3d):
        """When uncalibrated, ppm=1.0 so sx maps straight through."""
        result = view3d._scene_to_3d(100.0, 200.0, 500.0)
        np.testing.assert_array_almost_equal(result, [100.0, -200.0, 500.0])

    def test_calibrated_divides_by_ppm(self, view3d_calibrated):
        """Calibrated at 2 px/mm: scene coords are halved."""
        result = view3d_calibrated._scene_to_3d(200.0, 400.0, 3048.0)
        np.testing.assert_array_almost_equal(result, [100.0, -200.0, 3048.0])

    def test_y_axis_negated(self, view3d):
        """Qt scene Y is top-down; 3D world Y is bottom-up."""
        result = view3d._scene_to_3d(0.0, 50.0, 0.0)
        assert result[1] == pytest.approx(-50.0)

    def test_z_passed_through(self, view3d):
        """Z (elevation in mm) is passed directly."""
        result = view3d._scene_to_3d(0.0, 0.0, 1234.5)
        assert result[2] == pytest.approx(1234.5)

    def test_origin(self, view3d):
        result = view3d._scene_to_3d(0.0, 0.0, 0.0)
        np.testing.assert_array_almost_equal(result, [0.0, 0.0, 0.0])


class TestLevelZMm:
    """Verify elevation lookup by level name."""

    def test_known_level(self, view3d_calibrated):
        assert view3d_calibrated._level_z_mm("Level 1") == pytest.approx(0.0)
        assert view3d_calibrated._level_z_mm("Level 2") == pytest.approx(3048.0)

    def test_unknown_level_returns_zero(self, view3d_calibrated):
        assert view3d_calibrated._level_z_mm("Level X") == pytest.approx(0.0)

    def test_unknown_level_empty_manager(self, view3d):
        assert view3d._level_z_mm("Level 1") == pytest.approx(0.0)


# ===================================================================
# Camera angle methods
# ===================================================================

class TestCameraAngles:
    """Verify camera angle extraction and round-trip."""

    def test_round_trip_30_45(self, view3d):
        view3d._set_camera_from_angles(
            30.0, 45.0, center=np.zeros(3), distance=10000.0,
        )
        elev, azim = view3d._camera_to_angles()
        assert elev == pytest.approx(30.0, abs=0.5)
        assert azim == pytest.approx(45.0, abs=0.5)

    def test_round_trip_60_neg90(self, view3d):
        view3d._set_camera_from_angles(
            60.0, -90.0, center=np.zeros(3), distance=5000.0,
        )
        elev, azim = view3d._camera_to_angles()
        assert elev == pytest.approx(60.0, abs=0.5)
        assert azim == pytest.approx(-90.0, abs=0.5)

    def test_zero_elevation(self, view3d):
        view3d._set_camera_from_angles(
            0.0, 0.0, center=np.zeros(3), distance=5000.0,
        )
        elev, _ = view3d._camera_to_angles()
        assert elev == pytest.approx(0.0, abs=0.5)

    def test_near_vertical(self, view3d):
        """High elevation angle should survive round-trip."""
        view3d._set_camera_from_angles(
            85.0, 0.0, center=np.zeros(3), distance=5000.0,
        )
        elev, _ = view3d._camera_to_angles()
        assert elev == pytest.approx(85.0, abs=1.0)

    def test_camera_respects_center(self, view3d):
        center = np.array([1000.0, 2000.0, 500.0])
        view3d._set_camera_from_angles(
            30.0, 45.0, center=center, distance=5000.0,
        )
        fp = np.array(view3d._plotter.camera.focal_point)
        np.testing.assert_array_almost_equal(fp, center, decimal=1)

    def test_camera_distance_preserved(self, view3d):
        view3d._set_camera_from_angles(
            30.0, 45.0, center=np.zeros(3), distance=8000.0,
        )
        pos = np.array(view3d._plotter.camera.position)
        fp = np.array(view3d._plotter.camera.focal_point)
        dist = np.linalg.norm(pos - fp)
        assert dist == pytest.approx(8000.0, rel=1e-3)


# ===================================================================
# Scene bounds
# ===================================================================

class TestComputeSceneBounds:
    """Verify bounding-box computation from point arrays."""

    def test_empty_scene(self, view3d):
        assert view3d._compute_scene_bounds() is None

    def test_nodes_only(self, view3d):
        view3d._node_positions_3d = np.array([
            [0, 0, 0], [100, 200, 300],
        ])
        center, span = view3d._compute_scene_bounds()
        np.testing.assert_array_almost_equal(center, [50, 100, 150])
        np.testing.assert_array_almost_equal(span, [100, 200, 300])

    def test_pipes_only(self, view3d):
        view3d._pipe_midpoints_3d = np.array([
            [-50, -50, 0], [50, 50, 100],
        ])
        center, span = view3d._compute_scene_bounds()
        np.testing.assert_array_almost_equal(center, [0, 0, 50])
        np.testing.assert_array_almost_equal(span, [100, 100, 100])

    def test_combined_nodes_and_pipes(self, view3d):
        view3d._node_positions_3d = np.array([[0, 0, 0]])
        view3d._pipe_midpoints_3d = np.array([[100, 100, 100]])
        center, span = view3d._compute_scene_bounds()
        np.testing.assert_array_almost_equal(center, [50, 50, 50])
        np.testing.assert_array_almost_equal(span, [100, 100, 100])

    def test_includes_walls(self, view3d):
        view3d._wall_centroids_3d = np.array([[500, 500, 500]])
        center, span = view3d._compute_scene_bounds()
        np.testing.assert_array_almost_equal(center, [500, 500, 500])
        np.testing.assert_array_almost_equal(span, [0, 0, 0])

    def test_includes_slabs(self, view3d):
        view3d._slab_centroids_3d = np.array([[0, 0, 0], [200, 0, 0]])
        center, span = view3d._compute_scene_bounds()
        np.testing.assert_array_almost_equal(center, [100, 0, 0])

    def test_includes_roofs(self, view3d):
        view3d._roof_centroids_3d = np.array([[0, 0, 3000], [0, 0, 4000]])
        center, span = view3d._compute_scene_bounds()
        np.testing.assert_array_almost_equal(center, [0, 0, 3500])

    def test_all_sources_combined(self, view3d):
        """When all position arrays are set, bounds encompass all of them."""
        view3d._node_positions_3d = np.array([[0, 0, 0]])
        view3d._pipe_midpoints_3d = np.array([[100, 0, 0]])
        view3d._wall_centroids_3d = np.array([[0, 100, 0]])
        view3d._slab_centroids_3d = np.array([[0, 0, 100]])
        view3d._roof_centroids_3d = np.array([[50, 50, 50]])
        center, span = view3d._compute_scene_bounds()
        np.testing.assert_array_almost_equal(span, [100, 100, 100])

    def test_empty_arrays_ignored(self, view3d):
        """Zero-length arrays should not contribute to bounds."""
        view3d._node_positions_3d = np.empty((0, 3))
        view3d._pipe_midpoints_3d = np.array([[10, 20, 30]])
        center, span = view3d._compute_scene_bounds()
        np.testing.assert_array_almost_equal(center, [10, 20, 30])


# ===================================================================
# Actor management
# ===================================================================

class TestActorManagement:
    """Verify actor tracking, entity mapping, and cleanup."""

    def test_add_actor_tracks_category(self, view3d):
        view3d._add_actor("cat_a", "actor1")
        view3d._add_actor("cat_a", "actor2")
        assert len(view3d._actors["cat_a"]) == 2

    def test_add_actor_maps_entity(self, view3d):
        entity = object()
        view3d._add_actor("cat_a", "actor1", entity=entity, entity_type="node")
        assert view3d._actor_to_entity["actor1"] == (entity, "node")

    def test_add_actor_no_entity(self, view3d):
        view3d._add_actor("cat_a", "actor1")
        assert "actor1" not in view3d._actor_to_entity

    def test_clear_actors_removes_category(self, view3d):
        entity = object()
        view3d._add_actor("cat_b", "actor_x", entity=entity, entity_type="pipe")
        view3d._clear_actors("cat_b")
        assert view3d._actors["cat_b"] == []
        assert "actor_x" not in view3d._actor_to_entity

    def test_clear_nonexistent_category(self, view3d):
        """Clearing a category that was never used should not raise."""
        view3d._clear_actors("no_such_category")
        assert view3d._actors.get("no_such_category") == []

    def test_z_range_cleared_on_actor_clear(self, view3d):
        view3d._add_actor("cat_c", "actor_z")
        view3d._actor_z_range["actor_z"] = (0.0, 3000.0)
        view3d._clear_actors("cat_c")
        assert "actor_z" not in view3d._actor_z_range

    def test_multiple_categories_independent(self, view3d):
        view3d._add_actor("walls", "w1")
        view3d._add_actor("pipes", "p1")
        view3d._clear_actors("walls")
        assert view3d._actors["walls"] == []
        assert view3d._actors["pipes"] == ["p1"]


# ===================================================================
# Dirty-flag rebuild scheduling
# ===================================================================

class TestDirtyFlag:
    """Verify the dirty-flag lazy rebuild mechanism."""

    def test_initial_state_dirty(self, view3d):
        """View3D starts dirty so the first show triggers a rebuild."""
        # Note: __init__ sets _dirty = True
        assert view3d._dirty is True

    def test_schedule_rebuild_sets_dirty(self, view3d):
        view3d._dirty = False
        view3d._schedule_rebuild()
        assert view3d._dirty is True

    def test_rebuild_clears_dirty(self, view3d):
        view3d._dirty = True
        view3d.rebuild()
        assert view3d._dirty is False

    def test_do_rebuild_skips_when_clean(self, view3d):
        """_do_rebuild is a no-op when not dirty."""
        view3d._dirty = False
        view3d._do_rebuild()
        # Should remain clean (no crash, no side effects)
        assert view3d._dirty is False


# ===================================================================
# Module constants sanity checks
# ===================================================================

class TestConstants:
    """Verify module-level constants are sane."""

    def test_ft_to_mm(self):
        assert FT_TO_MM == pytest.approx(304.8)

    def test_circle_segments_positive(self):
        assert CIRCLE_SEGMENTS > 0

    def test_pick_tolerance_positive(self):
        assert PICK_TOLERANCE_PX > 0

    def test_max_cylinder_pipes_positive(self):
        assert MAX_CYLINDER_PIPES > 0

    def test_color_tuples_have_three_components(self):
        for name, col in [
            ("COL_NODE", COL_NODE),
            ("COL_SPRINKLER", COL_SPRINKLER),
            ("COL_HIGHLIGHT", COL_HIGHLIGHT),
        ]:
            assert len(col) == 3, f"{name} should be an RGB tuple"

    def test_pipe_colors_all_rgb(self):
        for name, col in _PIPE_COLORS.items():
            assert len(col) == 3, f"Pipe colour '{name}' should be RGB"
            for c in col:
                assert 0.0 <= c <= 1.0, f"Pipe colour '{name}' channel out of range"

    def test_floor_colors_all_rgba(self):
        for col in _FLOOR_COLORS:
            assert len(col) == 4, "Floor colour should be RGBA"
            for c in col:
                assert 0.0 <= c <= 1.0


# ===================================================================
# Rebuild populates pick maps
# ===================================================================

class TestRebuildPopulatesPickMaps:
    """After rebuild with an empty scene, pick maps are properly reset."""

    def test_empty_rebuild_clears_node_refs(self, view3d):
        view3d.rebuild()
        assert view3d._node_refs == []
        assert view3d._node_positions_3d is None

    def test_empty_rebuild_clears_pipe_refs(self, view3d):
        view3d.rebuild()
        assert view3d._pipe_refs == []
        assert view3d._pipe_midpoints_3d is None

    def test_empty_rebuild_clears_wall_refs(self, view3d):
        view3d.rebuild()
        assert view3d._wall_refs == []
        assert view3d._wall_centroids_3d is None

    def test_empty_rebuild_clears_slab_refs(self, view3d):
        view3d.rebuild()
        assert view3d._slab_refs == []
        assert view3d._slab_centroids_3d is None

    def test_empty_rebuild_clears_roof_refs(self, view3d):
        view3d.rebuild()
        assert view3d._roof_refs == []
        assert view3d._roof_centroids_3d is None

    def test_info_label_updated(self, view3d):
        view3d.rebuild()
        text = view3d._info_label.text()
        assert "Nodes: 0" in text
        assert "Pipes: 0" in text


# ===================================================================
# 3D selection tracking
# ===================================================================

class TestSelectionTracking:
    """Verify 3D-only selection list management."""

    def test_get_3d_selected_empty(self, view3d):
        assert view3d.get_3d_selected() == []

    def test_get_3d_selected_returns_copy(self, view3d):
        sentinel = object()
        view3d._3d_selected.append(sentinel)
        result = view3d.get_3d_selected()
        assert result == [sentinel]
        # Mutating the returned list should not affect internal state
        result.clear()
        assert view3d.get_3d_selected() == [sentinel]
