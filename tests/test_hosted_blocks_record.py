"""D2: host record on BlockInstance + place_block_instance(host=)."""
import pytest
from firepro3d.block_instance import BlockInstance
from tests._hosted_blocks_helpers import gridline, defn


def _hosted(ms):
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    d = defn(ms)
    host = {"gridline": gl._uid, "offset_mm": 200.0, "along_mm": 1500.0,
            "elevation_mm": 2400.0, "facing": 1}
    inst = ms.place_block_instance(d.id, (0.0, 0.0), host=host)
    return gl, d, inst


def test_place_derives_pos_from_host(qapp, make_model_space):
    ms = make_model_space()
    gl, d, inst = _hosted(ms)
    assert inst.host["gridline"] == gl._uid
    assert inst.block_pos() == pytest.approx((1500.0, -3200.0))
    assert inst.z_range_mm() == (2400.0, 2400.0)


def test_host_round_trips_and_place_kwargs(qapp, make_model_space):
    ms = make_model_space()
    gl, d, inst = _hosted(ms)
    rec = inst.to_dict()
    assert rec["host"] == inst.host
    assert BlockInstance.from_dict(rec, ms.get_block_definition).host == inst.host
    assert BlockInstance.place_kwargs(rec)["host"] == inst.host
    plain = ms.place_block_instance(d.id, (0.0, 0.0))
    assert "host" not in plain.to_dict() and plain.host is None


def test_unresolved_host_places_nothing(qapp, make_model_space):
    ms = make_model_space()
    d = defn(ms)
    n = len(ms._block_instances)
    assert ms.place_block_instance(d.id, (0, 0), host={
        "gridline": "nope", "offset_mm": 0.0, "along_mm": 0.0,
        "elevation_mm": 0.0, "facing": 1}) is None
    assert len(ms._block_instances) == n
