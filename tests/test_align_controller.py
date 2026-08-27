from firepro3d.align_controller import AlignController
from firepro3d.align_engine import AcquiredRef


def _snap(point, snap_type, source_id, direction=None):
    # Minimal stand-in for what the seam extracts from an OsnapResult.
    return {"point": point, "snap_type": snap_type,
            "source_id": source_id, "direction": direction}


def test_dwell_below_threshold_does_not_acquire():
    c = AlignController(dwell_ms=400, max_points=5)
    c.on_move(cursor=(10.0, 10.0), snap=_snap((10.0, 10.0), "midpoint", 1),
              elapsed_ms=200)
    assert c.acquired == []


def test_dwell_at_threshold_acquires_point_flavor():
    c = AlignController(dwell_ms=400, max_points=5)
    c.on_move((10.0, 10.0), _snap((10.0, 10.0), "midpoint", 1), elapsed_ms=450)
    assert len(c.acquired) == 1
    a = c.acquired[0]
    assert a.flavor == "point" and a.point == (10.0, 10.0)


def test_endpoint_with_direction_captures_extension():
    c = AlignController(dwell_ms=400, max_points=5)
    c.on_move((0.0, 0.0), _snap((0.0, 0.0), "endpoint", 2, direction=(1.0, 0.0)),
              elapsed_ms=450)
    assert c.acquired[0].direction == (1.0, 0.0)


def test_nearest_hit_acquires_direction_flavor():
    c = AlignController(dwell_ms=400, max_points=5)
    c.on_move((3.0, 0.0), _snap((3.0, 0.0), "nearest", 3, direction=(0.0, 1.0)),
              elapsed_ms=450)
    assert c.acquired[0].flavor == "direction"


def test_rehover_releases():
    c = AlignController(dwell_ms=400, max_points=5)
    c.on_move((0.0, 0.0), _snap((0.0, 0.0), "endpoint", 2), elapsed_ms=450)
    assert len(c.acquired) == 1
    # cursor leaves, returns and re-dwells on the same source → release
    c.on_move((99.0, 99.0), None, elapsed_ms=50)
    c.on_move((0.0, 0.0), _snap((0.0, 0.0), "endpoint", 2), elapsed_ms=450)
    assert c.acquired == []


def test_cap_evicts_oldest():
    c = AlignController(dwell_ms=400, max_points=2)
    for i in range(3):
        c.on_move((99.0, 99.0), None, elapsed_ms=10)   # reset dwell between acquires
        c.on_move((float(i), 0.0), _snap((float(i), 0.0), "endpoint", i), elapsed_ms=450)
    ids = [a.source_id for a in c.acquired]
    assert ids == [1, 2]        # oldest (0) evicted


def test_clear_drops_all():
    c = AlignController(dwell_ms=400, max_points=5)
    c.on_move((0.0, 0.0), _snap((0.0, 0.0), "endpoint", 2), elapsed_ms=450)
    c.clear()
    assert c.acquired == []


def test_build_rays_includes_active_anchor_autoacquire():
    c = AlignController(dwell_ms=400, max_points=5)
    c.set_active_anchor((5.0, 5.0), direction=None)
    rays = c.build_rays(active_point=(5.0, 5.0))
    # anchor auto-acquire → H + V from (5,5)
    origins = {r.origin for r in rays}
    assert (5.0, 5.0) in origins
    assert any(r.direction == (1.0, 0.0) for r in rays)
    assert any(r.direction == (0.0, 1.0) for r in rays)
