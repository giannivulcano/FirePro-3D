"""Tests for firepro3d.underlay_cache."""

import json
import os
import re
import tempfile

import pytest

from firepro3d.underlay_cache import (
    cache_dir_for_project,
    compute_cache_key,
    delete_cache,
    read_cache,
    write_cache,
)

SAMPLE_GEOMS = [
    {"kind": "line", "x1": 0, "y1": 0, "x2": 100, "y2": 100, "layer": "0"},
    {"kind": "circle", "x": 50, "y": 50, "w": 20, "h": 20, "layer": "A-WALL"},
    {"kind": "path_points", "points": [(0, 0), (10, 20), (30, 40)],
     "closed": True, "layer": "0"},
    {"kind": "text", "x": 5, "y": 10, "text": "Hello", "layer": "ANNO"},
]


class TestCacheDirForProject:
    def test_returns_sibling_cache_dir(self, tmp_path):
        project_file = tmp_path / "MyProject.fpd"
        project_file.touch()
        result = cache_dir_for_project(str(project_file))
        assert result == str(tmp_path / "MyProject.fpd.cache")

    def test_different_project_names(self, tmp_path):
        result = cache_dir_for_project(str(tmp_path / "Other.fpd"))
        assert result.endswith("Other.fpd.cache")


class TestCacheKey:
    def test_same_inputs_same_key(self):
        k1 = compute_cache_key("/plans/floor1.dxf", page=0, selected_layers=None)
        k2 = compute_cache_key("/plans/floor1.dxf", page=0, selected_layers=None)
        assert k1 == k2

    def test_different_path_different_key(self):
        k1 = compute_cache_key("/plans/floor1.dxf", page=0, selected_layers=None)
        k2 = compute_cache_key("/plans/floor2.dxf", page=0, selected_layers=None)
        assert k1 != k2

    def test_different_page_different_key(self):
        k1 = compute_cache_key("/plans/sheet.pdf", page=0, selected_layers=None)
        k2 = compute_cache_key("/plans/sheet.pdf", page=1, selected_layers=None)
        assert k1 != k2

    def test_different_layers_different_key(self):
        k1 = compute_cache_key("/plans/floor.dxf", page=0, selected_layers=["A-WALL"])
        k2 = compute_cache_key("/plans/floor.dxf", page=0, selected_layers=["A-WALL", "A-DOOR"])
        assert k1 != k2

    def test_key_is_valid_filename(self):
        key = compute_cache_key("C:\\My Plans\\floor (1).dxf", page=0, selected_layers=None)
        assert re.match(r'^[\w\-.]+$', key), f"Invalid filename chars in: {key}"

    def test_none_layers_same_as_omitted(self):
        k1 = compute_cache_key("/plans/floor.dxf", page=0, selected_layers=None)
        k2 = compute_cache_key("/plans/floor.dxf", page=0)
        assert k1 == k2


class TestWriteAndReadCache:
    def test_roundtrip(self, tmp_path):
        cache_dir = str(tmp_path / "proj.fpd.cache")
        key = "test_abc123.json"
        mtime = 1715600000.0
        write_cache(cache_dir, key, SAMPLE_GEOMS, source_mtime=mtime)
        result = read_cache(cache_dir, key, source_mtime=mtime)
        assert result is not None
        assert len(result) == len(SAMPLE_GEOMS)
        assert result[0]["kind"] == "line"
        assert result[2]["points"] == [[0, 0], [10, 20], [30, 40]]  # tuples become lists in JSON

    def test_stale_cache_returns_none(self, tmp_path):
        cache_dir = str(tmp_path / "proj.fpd.cache")
        key = "test_abc123.json"
        write_cache(cache_dir, key, SAMPLE_GEOMS, source_mtime=1000.0)
        result = read_cache(cache_dir, key, source_mtime=2000.0)
        assert result is None

    def test_missing_cache_returns_none(self, tmp_path):
        cache_dir = str(tmp_path / "proj.fpd.cache")
        result = read_cache(cache_dir, "nonexistent.json", source_mtime=1000.0)
        assert result is None

    def test_cache_dir_created_on_write(self, tmp_path):
        cache_dir = str(tmp_path / "new_proj.fpd.cache")
        assert not os.path.exists(cache_dir)
        write_cache(cache_dir, "test.json", SAMPLE_GEOMS, source_mtime=1000.0)
        assert os.path.isdir(cache_dir)

    def test_read_without_mtime_skips_freshness(self, tmp_path):
        cache_dir = str(tmp_path / "proj.fpd.cache")
        key = "test.json"
        write_cache(cache_dir, key, SAMPLE_GEOMS, source_mtime=1000.0)
        result = read_cache(cache_dir, key, source_mtime=None)
        assert result is not None
        assert len(result) == len(SAMPLE_GEOMS)

    def test_corrupt_cache_returns_none(self, tmp_path):
        cache_dir = str(tmp_path / "proj.fpd.cache")
        os.makedirs(cache_dir)
        cache_file = os.path.join(cache_dir, "corrupt.json")
        with open(cache_file, "w") as f:
            f.write("not valid json{{{")
        result = read_cache(cache_dir, "corrupt.json", source_mtime=1000.0)
        assert result is None


class TestDeleteCache:
    def test_delete_existing(self, tmp_path):
        cache_dir = str(tmp_path / "proj.fpd.cache")
        write_cache(cache_dir, "test.json", SAMPLE_GEOMS, source_mtime=1000.0)
        assert os.path.isfile(os.path.join(cache_dir, "test.json"))
        delete_cache(cache_dir, "test.json")
        assert not os.path.isfile(os.path.join(cache_dir, "test.json"))

    def test_delete_nonexistent_no_error(self, tmp_path):
        cache_dir = str(tmp_path / "proj.fpd.cache")
        delete_cache(cache_dir, "ghost.json")  # should not raise
