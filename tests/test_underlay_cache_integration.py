"""Integration tests for underlay geometry caching.

Covers: cache for missing source files, cache invalidation on refresh,
and edge cases (tuple roundtrip, empty geom list, arc geometry).
"""

import os
import pytest

from firepro3d.underlay import Underlay
from firepro3d.underlay_cache import (
    cache_dir_for_project, compute_cache_key, read_cache, write_cache,
)


SAMPLE_GEOMS = [
    {"kind": "line", "x1": 0, "y1": 0, "x2": 100, "y2": 100, "layer": "0"},
    {"kind": "circle", "x": 50, "y": 50, "w": 20, "h": 20, "layer": "0"},
]


class TestRecordCacheKeyIncludesBounds:
    """Same source file cropped differently must not share a cache entry."""

    def test_same_file_different_crop_distinct_keys(self):
        a = Underlay(type="dxf", path="/plans/floor.dxf",
                     import_bounds=[0.0, 0.0, 100.0, 100.0])
        b = Underlay(type="dxf", path="/plans/floor.dxf",
                     import_bounds=[200.0, 200.0, 300.0, 300.0])
        assert a.cache_key() != b.cache_key()

    def test_crop_vs_full_distinct_keys(self):
        a = Underlay(type="dxf", path="/plans/floor.dxf")
        b = Underlay(type="dxf", path="/plans/floor.dxf",
                     import_bounds=[0.0, 0.0, 100.0, 100.0])
        assert a.cache_key() != b.cache_key()

    def test_key_survives_serialisation_roundtrip(self):
        a = Underlay(type="dxf", path="/plans/floor.dxf",
                     import_bounds=[0.5, 1.5, 100.25, 100.75])
        b = Underlay.from_dict(a.to_dict())
        assert a.cache_key() == b.cache_key()


class TestEnsureUnderlayCachesDirtyFlag:
    """Save-time cache writes are skipped when geometry is unchanged."""

    def _make_scene(self, tmp_path, dirty):
        from PyQt6.QtWidgets import QGraphicsItemGroup
        from firepro3d.model_space import Model_Space

        scene = Model_Space()
        project = tmp_path / "proj.fpd"
        project.touch()
        scene._project_path = str(project)

        src = tmp_path / "floor.dxf"
        src.write_text("dummy dxf content")

        record = Underlay(type="dxf", path=str(src))
        group = QGraphicsItemGroup()
        scene.addItem(group)
        group.setData(5, SAMPLE_GEOMS)
        group.setData(6, dirty)
        scene.underlays.append((record, group))
        return scene, record, group, str(project)

    def test_dirty_underlay_written_and_flag_cleared(self, qapp, tmp_path):
        scene, record, group, project = self._make_scene(tmp_path, dirty=True)
        scene._ensure_underlay_caches(project)

        cache_file = os.path.join(cache_dir_for_project(project),
                                  record.cache_key())
        assert os.path.isfile(cache_file)
        assert not group.data(6), "dirty flag must be cleared after write"

    def test_clean_underlay_with_cache_skips_write(self, qapp, tmp_path,
                                                   monkeypatch):
        scene, record, group, project = self._make_scene(tmp_path, dirty=True)
        scene._ensure_underlay_caches(project)  # initial write

        calls = []
        import firepro3d.underlay_cache as uc
        real_write = uc.write_cache
        monkeypatch.setattr(
            uc, "write_cache",
            lambda *a, **kw: (calls.append(a), real_write(*a, **kw)))

        scene._ensure_underlay_caches(project)  # clean second save
        assert calls == [], "clean underlay with existing cache must not rewrite"

    def test_clean_underlay_with_missing_cache_heals(self, qapp, tmp_path):
        # Save-As to a new location: flags are clean but the new cache
        # directory is empty — the entry must still be written.
        scene, record, group, project = self._make_scene(tmp_path, dirty=False)
        scene._ensure_underlay_caches(project)

        cache_file = os.path.join(cache_dir_for_project(project),
                                  record.cache_key())
        assert os.path.isfile(cache_file)


class TestCacheForMissingSource:
    """When source file is gone but cache exists, underlay should render."""

    def test_missing_source_loads_from_cache(self, tmp_path):
        cache_dir = str(tmp_path / "test.fpd.cache")
        source_path = str(tmp_path / "floor.dxf")

        record = Underlay(type="dxf", path=source_path, x=10.0, y=20.0)
        key = record.cache_key()
        write_cache(cache_dir, key, SAMPLE_GEOMS, source_mtime=1000.0)

        assert not os.path.exists(source_path)

        result = read_cache(cache_dir, key, source_mtime=None)
        assert result is not None
        assert len(result) == 2


class TestCacheInvalidationOnRefresh:
    def test_stale_cache_returns_none(self, tmp_path):
        cache_dir = str(tmp_path / "proj.fpd.cache")
        key = compute_cache_key("/plans/floor.dxf", page=0, selected_layers=None)

        write_cache(cache_dir, key, SAMPLE_GEOMS, source_mtime=1000.0)

        result = read_cache(cache_dir, key, source_mtime=2000.0)
        assert result is None, "Stale cache should return None"

    def test_fresh_write_overwrites_stale(self, tmp_path):
        cache_dir = str(tmp_path / "proj.fpd.cache")
        key = compute_cache_key("/plans/floor.dxf", page=0, selected_layers=None)

        write_cache(cache_dir, key, SAMPLE_GEOMS, source_mtime=1000.0)
        new_geoms = [{"kind": "line", "x1": 0, "y1": 0, "x2": 50, "y2": 50, "layer": "0"}]
        write_cache(cache_dir, key, new_geoms, source_mtime=2000.0)

        result = read_cache(cache_dir, key, source_mtime=2000.0)
        assert result is not None
        assert len(result) == 1
        assert result[0]["x2"] == 50


class TestCacheEdgeCases:
    def test_path_points_tuple_roundtrip(self, tmp_path):
        cache_dir = str(tmp_path / "proj.fpd.cache")
        key = "tuple_test.json"
        geoms = [{"kind": "path_points",
                  "points": [(1.5, 2.5), (3.0, 4.0)],
                  "closed": True, "layer": "0"}]
        write_cache(cache_dir, key, geoms, source_mtime=1000.0)

        result = read_cache(cache_dir, key, source_mtime=1000.0)
        assert result[0]["points"] == [[1.5, 2.5], [3.0, 4.0]]

    def test_empty_geom_list(self, tmp_path):
        cache_dir = str(tmp_path / "proj.fpd.cache")
        key = "empty.json"
        write_cache(cache_dir, key, [], source_mtime=1000.0)

        result = read_cache(cache_dir, key, source_mtime=1000.0)
        assert result == []

    def test_arc_geometry_roundtrip(self, tmp_path):
        cache_dir = str(tmp_path / "proj.fpd.cache")
        key = "arc_test.json"
        geoms = [{"kind": "arc", "rx": 10.0, "ry": 20.0,
                  "rw": 30.0, "rh": 30.0,
                  "start": 0.0, "span": 180.0, "layer": "0"}]
        write_cache(cache_dir, key, geoms, source_mtime=1000.0)

        result = read_cache(cache_dir, key, source_mtime=1000.0)
        assert result[0]["start"] == 0.0
        assert result[0]["span"] == 180.0
