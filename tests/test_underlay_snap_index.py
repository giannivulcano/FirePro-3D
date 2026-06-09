"""Tests for UnderlaySnapIndex bbox filtering and single bounds pass.

Grid cells on real drawings are metres wide, so query() must reject
candidates whose bounding box misses the query rect instead of
returning everything in the overlapping cells.
"""

from __future__ import annotations

import pytest

import firepro3d.underlay_snap_index as usi
from firepro3d.underlay_snap_index import UnderlaySnapIndex


def _line(x1, y1, x2, y2, layer="0"):
    return {"kind": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "layer": layer}


class TestQueryBboxFilter:
    def test_same_cell_geom_outside_rect_excluded(self):
        # Total extent ~45 units -> a single grid cell (cells are
        # >=100 units), so both lines share a cell.  Only the line
        # whose bbox intersects the query rect may be returned.
        idx = UnderlaySnapIndex(
            [_line(0, 0, 5, 5), _line(40, 40, 45, 45)], [])
        result = idx.query(0, 0, 6, 6)
        assert len(result) == 1
        assert result[0]["x1"] == 0

    def test_geom_straddling_rect_included(self):
        idx = UnderlaySnapIndex(
            [_line(-20, 3, 20, 3), _line(40, 40, 45, 45)], [])
        result = idx.query(0, 0, 6, 6)
        assert len(result) == 1
        assert result[0]["y1"] == 3

    def test_all_returned_when_rect_covers_extent(self):
        geoms = [_line(0, 0, 5, 5), _line(40, 40, 45, 45)]
        idx = UnderlaySnapIndex(geoms, [])
        result = idx.query(-10, -10, 100, 100)
        assert len(result) == 2

    def test_hidden_layers_still_excluded(self):
        hidden = ["A-FURN"]
        idx = UnderlaySnapIndex(
            [_line(0, 0, 5, 5, layer="A-FURN"),
             _line(1, 1, 6, 6, layer="A-WALL")], hidden)
        result = idx.query(0, 0, 10, 10)
        assert len(result) == 1
        assert result[0]["layer"] == "A-WALL"

    def test_empty_geom_list(self):
        idx = UnderlaySnapIndex([], [])
        assert idx.query(0, 0, 10, 10) == []

    def test_path_points_bbox_respected(self):
        idx = UnderlaySnapIndex(
            [{"kind": "path_points",
              "points": [(100.0, 100.0), (110.0, 110.0)], "layer": "0"},
             _line(0, 0, 5, 5)], [])
        result = idx.query(0, 0, 6, 6)
        assert len(result) == 1
        assert result[0]["kind"] == "line"


class TestSingleBoundsPass:
    def test_bounds_computed_once_per_geom(self, monkeypatch):
        # __init__ used to call _geom_bounds twice per geom (extent pass
        # + cell-assignment pass) — ~40-45% of index build cost.
        calls = []
        real = usi._geom_bounds
        monkeypatch.setattr(
            usi, "_geom_bounds",
            lambda g: (calls.append(1), real(g))[1])

        geoms = [_line(i * 10.0, 0, i * 10.0 + 5, 5) for i in range(7)]
        UnderlaySnapIndex(geoms, [])
        assert len(calls) == len(geoms)
