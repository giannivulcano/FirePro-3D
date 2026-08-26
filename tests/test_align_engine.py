import math
from firepro3d.align_engine import (
    Ray, AcquiredRef, rays_for_acquired, path_x_path, path_x_segment,
    project_to_ray, point_along_ray,
)


def test_point_acquire_emits_h_and_v_rays():
    ref = AcquiredRef(point=(10.0, 20.0), direction=None,
                      flavor="point", snap_type="midpoint", source_id=1)
    rays = rays_for_acquired([ref], active_point=(0.0, 0.0))
    kinds = {(r.kind, round(r.direction[0], 6), round(r.direction[1], 6)) for r in rays}
    assert ("hv", 1.0, 0.0) in kinds   # horizontal
    assert ("hv", 0.0, 1.0) in kinds   # vertical
    assert all(r.origin == (10.0, 20.0) for r in rays)


def test_endpoint_with_direction_also_emits_extension():
    ref = AcquiredRef(point=(0.0, 0.0), direction=(1.0, 1.0),
                      flavor="point", snap_type="endpoint", source_id=2)
    rays = rays_for_acquired([ref], active_point=(0.0, 0.0))
    ext = [r for r in rays if r.kind == "extension"]
    assert len(ext) == 1
    d = ext[0].direction
    assert math.isclose(d[0], 1 / math.sqrt(2)) and math.isclose(d[1], 1 / math.sqrt(2))


def test_direction_acquire_emits_parallel_anchored_at_active_point():
    ref = AcquiredRef(point=None, direction=(1.0, 0.0),
                      flavor="direction", snap_type="nearest", source_id=3)
    rays = rays_for_acquired([ref], active_point=(5.0, 7.0))
    par = [r for r in rays if r.kind == "parallel"]
    assert len(par) == 1
    assert par[0].origin == (5.0, 7.0)
    assert par[0].direction == (1.0, 0.0)


def test_path_x_path_intersection_is_ground_truth():
    # H ray of M=(3,9) × V ray of N=(4,2)  ==  (Nx, My) = (4, 9)
    h = Ray(origin=(3.0, 9.0), direction=(1.0, 0.0), kind="hv", source_id=1)
    v = Ray(origin=(4.0, 2.0), direction=(0.0, 1.0), kind="hv", source_id=2)
    pt = path_x_path(h, v)
    assert pt is not None
    assert math.isclose(pt[0], 4.0) and math.isclose(pt[1], 9.0)


def test_parallel_rays_have_no_intersection():
    a = Ray(origin=(0.0, 0.0), direction=(1.0, 0.0), kind="hv", source_id=1)
    b = Ray(origin=(0.0, 5.0), direction=(1.0, 0.0), kind="hv", source_id=2)
    assert path_x_path(a, b) is None


def test_path_x_segment_crossing():
    ray = Ray(origin=(0.0, 0.0), direction=(1.0, 0.0), kind="hv", source_id=1)
    pt = path_x_segment(ray, (5.0, -3.0), (5.0, 3.0))   # vertical wall at x=5
    assert pt is not None and math.isclose(pt[0], 5.0) and math.isclose(pt[1], 0.0)


def test_path_x_segment_miss_when_crossing_outside_segment():
    ray = Ray(origin=(0.0, 0.0), direction=(1.0, 0.0), kind="hv", source_id=1)
    assert path_x_segment(ray, (5.0, 10.0), (5.0, 20.0)) is None  # crossing y=0 not on seg


def test_project_to_ray_returns_foot_and_signed_distance():
    ray = Ray(origin=(0.0, 0.0), direction=(1.0, 0.0), kind="hv", source_id=1)
    foot, dist = project_to_ray((7.0, 2.0), ray)
    assert math.isclose(foot[0], 7.0) and math.isclose(foot[1], 0.0)
    assert math.isclose(dist, 7.0)


def test_point_along_ray():
    ray = Ray(origin=(1.0, 1.0), direction=(0.0, 1.0), kind="hv", source_id=1)
    pt = point_along_ray(ray, 4.0)   # 4 units along +y (scene y-down)
    assert math.isclose(pt[0], 1.0) and math.isclose(pt[1], 5.0)
