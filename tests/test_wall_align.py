"""Tests for WallSegment.alignment_reference_points() — ALIGN provider.

Task 3: WallSegment emits H/V alignment references at its TRUE centerline
(endpoints + midpoint).  Pure-logic: no scene required.

Task 9: wall mode sets the ALIGN active-item sentinel, and
_collect_alignment_refs spatially filters walls so only near walls contribute.
"""
from PyQt6.QtCore import QPointF
from firepro3d.wall import WallSegment, ALIGN_LEFT


def test_provider_emits_centerline_endpoints_and_midpoint():
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    w._alignment = ALIGN_LEFT
    feats = w.alignment_reference_points()
    coords = {(round(f.x, 6), round(f.y, 6)) for f in feats}
    a, b, m = w.centerline_pt1, w.centerline_pt2, w.centerline_midpoint()
    assert (round(a.x(), 6), round(a.y(), 6)) in coords
    assert (round(b.x(), 6), round(b.y(), 6)) in coords
    assert (round(m.x(), 6), round(m.y(), 6)) in coords
    assert {f.source_id for f in feats} == {id(w)}


# ---------------------------------------------------------------------------
# Task 9 tests
# ---------------------------------------------------------------------------

def test_wall_mode_sets_align_active_item(qapp):
    """set_mode('wall') must arm the ALIGN sentinel so wall placement
    consumes H/V alignment guides."""
    from firepro3d.model_space import Model_Space
    scene = Model_Space()
    scene.set_mode("wall")
    assert scene._align_active_item is scene._PLACEMENT_SENTINEL


def test_collect_includes_near_wall_refs_only(qapp, shown_model_view):
    """_collect_alignment_refs with cursor+tol must include refs from a wall
    within the tolerance rect and EXCLUDE refs from a wall 100 m away."""
    view, scene = shown_model_view
    from firepro3d.wall import WallSegment

    near = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=100.0)
    far  = WallSegment(QPointF(0, 100000), QPointF(1000, 100000), thickness_mm=100.0)
    for w in (near, far):
        scene.addItem(w)
        scene._walls.append(w)

    scene.set_mode("wall")

    cursor = QPointF(500, 0)
    tol = 200.0   # 200 mm — captures near wall, misses far wall (100 000 mm away)

    refs = scene._collect_alignment_refs(cursor, tol)
    sids = {f.source_id for f in refs}

    assert id(near) in sids, "near wall refs must appear in the collection"
    assert id(far)  not in sids, "far wall refs must be excluded by the spatial filter"
