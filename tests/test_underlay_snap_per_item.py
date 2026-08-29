"""Per-underlay snap gate: UnderlaySnapIndex respects Underlay.snap flag."""
from firepro3d.underlay import Underlay
from firepro3d.underlay_snap_index import UnderlaySnapIndex


def _one_line_geom():
    return [{"kind": "line", "layer": "0", "x1": 0, "y1": 0, "x2": 100, "y2": 0}]


def test_query_returns_geometry_when_record_snap_on():
    rec = Underlay(type="dxf", path="p.dxf", snap=True)
    idx = UnderlaySnapIndex(_one_line_geom(), rec.hidden_layers, rec)
    assert len(idx.query(-10, -10, 40, 40)) == 1


def test_query_returns_nothing_when_record_snap_off():
    rec = Underlay(type="dxf", path="p.dxf", snap=False)
    idx = UnderlaySnapIndex(_one_line_geom(), rec.hidden_layers, rec)
    assert idx.query(-10, -10, 40, 40) == []


def test_toggling_record_snap_is_live_without_rebuild():
    rec = Underlay(type="dxf", path="p.dxf", snap=True)
    idx = UnderlaySnapIndex(_one_line_geom(), rec.hidden_layers, rec)
    assert len(idx.query(-10, -10, 40, 40)) == 1
    rec.snap = False
    assert idx.query(-10, -10, 40, 40) == []


def test_index_without_record_still_queries():
    # backward-compat: no record passed (e.g. import-dialog preview) → not gated
    idx = UnderlaySnapIndex(_one_line_geom(), [])
    assert len(idx.query(-10, -10, 40, 40)) == 1
