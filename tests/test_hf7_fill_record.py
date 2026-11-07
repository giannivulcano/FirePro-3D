"""HF7 D1: the fill record through the shared geom helpers."""
import pytest

from firepro3d import dwg_converter as dc
from firepro3d.underlay_snap_index import UnderlaySnapIndex


def _fill():
    return {
        "kind": "fill", "layer": "A", "color": "#112233",
        "solid": False, "mask": False, "tone": False,
        "loops": [[{"kind": "path_points", "layer": "A", "color": "#112233",
                    "points": [(10.0, 0.0), (20.0, 0.0), (20.0, 10.0), (10.0, 10.0)],
                    "closed": True}]],
        "exact_loops": [[{"kind": "circle", "layer": "A", "color": "#112233",
                          "x": 10.0, "y": 0.0, "w": 10.0, "h": 10.0}]],
        "lines": [[11.0, 1.0, 19.0, 9.0]],
        "pattern": {"name": "ANSI31", "families": [
            {"angle": -45.0, "base": [2.0, 3.0], "offset": [1.0, 1.0], "dashes": [4.0, -2.0]}]},
    }


def test_geom_children_only_for_fill():
    assert [c["kind"] for c in dc.geom_children(_fill())] == ["path_points"]
    assert dc.geom_children({"kind": "line"}) == []


def test_expand_fills_keeps_list_identity_without_a_fill():
    geoms = [{"kind": "line", "x1": 0, "y1": 0, "x2": 1, "y2": 1}]
    assert dc.expand_fills(geoms) is geoms


def test_rep_points_and_bounds_recurse():
    assert (10.0, 0.0) in dc.geom_rep_points(_fill())
    assert dc.compute_geom_bounds([_fill()]) == [10.0, 0.0, 20.0, 10.0]


def test_import_transform_moves_every_part():
    out = dc.apply_import_transform([_fill()], 2.0, 10.0, 0.0)[0]
    assert out["loops"][0][0]["points"][0] == (0.0, 0.0)
    assert out["exact_loops"][0][0]["x"] == 0.0 and out["exact_loops"][0][0]["w"] == 20.0
    assert out["lines"] == [[2.0, 2.0, 18.0, 18.0]]
    fam = out["pattern"]["families"][0]
    assert fam["base"] == [-16.0, 6.0]
    assert fam["offset"] == [2.0, 2.0] and fam["dashes"] == [8.0, -4.0]
    assert fam["angle"] == -45.0


def test_import_transform_rotates_families():
    out = dc.apply_import_transform([_fill()], 1.0, 0.0, 0.0, 90.0)[0]
    fam = out["pattern"]["families"][0]
    assert fam["angle"] == pytest.approx(45.0)
    assert fam["offset"] == pytest.approx([-1.0, 1.0])
    assert fam["base"] == pytest.approx([-3.0, 2.0])


def test_input_not_mutated():
    src = _fill()
    dc.apply_import_transform([src], 2.0, 1.0, 1.0)
    assert src["lines"] == [[11.0, 1.0, 19.0, 9.0]]


def test_fill_line_geoms_are_plain_lines():
    assert dc.fill_line_geoms(_fill()) == [
        {"kind": "line", "layer": "A", "color": "#112233",
         "x1": 11.0, "y1": 1.0, "x2": 19.0, "y2": 9.0}]


def test_snap_index_sees_boundaries_only():
    idx = UnderlaySnapIndex([_fill()], [])
    got = idx.query(0.0, -5.0, 30.0, 20.0)
    assert [g["kind"] for g in got] == ["path_points"]


def test_snap_index_keeps_hidden_layer_rule():
    assert UnderlaySnapIndex([_fill()], ["A"]).query(0.0, -5.0, 30.0, 20.0) == []
