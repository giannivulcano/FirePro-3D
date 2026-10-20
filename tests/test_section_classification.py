"""Crop-box classification on real Wall / Pipe / FloorSlab footprints, lateral
clip, and the cardinal auto-extent rule (spec s4.2 / s4.3)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.section_marker import SectionMarker, ZONE_CUT, ZONE_BEHIND, ZONE_HIDDEN


def _placed_scene(section_scene_for, a, b, depth):
    """A placed (non-cardinal) section A->B with look_sign +1 over a fresh model."""
    from firepro3d.section_scene import SectionScene
    ms, _ = section_scene_for("north")
    marker = SectionMarker("Section 1", QPointF(*a), QPointF(*b), 1, depth)
    sec = SectionScene(marker, ms, ms._level_manager, ms.scale_manager)
    return ms, sec


def _wall(ms, p, q):
    from firepro3d.wall import WallSegment
    w = WallSegment(QPointF(*p), QPointF(*q))
    ms._walls.append(w); ms.addItem(w)
    return w


def _source_rects(sec, src):
    from firepro3d.section_scene import _ElevProxyRect, _ROLE_SOURCE
    return [it for it in sec.items() if isinstance(it, _ElevProxyRect) and it.data(_ROLE_SOURCE) is src]


def test_wall_zones_by_footprint_on_a_horizontal_cut(qapp, section_scene_for):
    # Scene coords: cut along y = 0 from x=0 to x=10000, look_sign +1 -> N_s = (0, -1) = scene-up.
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    cut = _wall(ms, (3000.0, -1000.0), (3000.0, 1000.0))      # straddles the line
    behind = _wall(ms, (1000.0, -2000.0), (6000.0, -2000.0))  # scene-up = look side
    front = _wall(ms, (1000.0, 2000.0), (6000.0, 2000.0))     # other side
    deep = _wall(ms, (1000.0, -6000.0), (6000.0, -6000.0))    # beyond depth
    sec.rebuild()
    assert sec.zone_of(cut) == ZONE_CUT
    assert sec.zone_of(behind) == ZONE_BEHIND and _source_rects(sec, behind)
    assert sec.zone_of(front) == ZONE_HIDDEN and not _source_rects(sec, front)
    assert sec.zone_of(deep) == ZONE_HIDDEN and not _source_rects(sec, deep)


def test_behind_wall_is_clipped_laterally_not_vertically(qapp, section_scene_for):
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    w = _wall(ms, (-5000.0, -2000.0), (15000.0, -2000.0))      # overhangs both ends
    sec.rebuild()
    (r,) = _source_rects(sec, w)
    b = sec.basis
    assert (r.rect().left(), r.rect().right()) == pytest.approx((b.h_min, b.h_max), abs=1e-6)
    assert r.rect().height() == pytest.approx(w._height_mm, abs=1e-6)   # full wall height


def test_parallel_adjacent_wall_is_behind(qapp, section_scene_for):
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    w = _wall(ms, (2000.0, -300.0), (8000.0, -300.0))   # parallel, 300 mm on the look side (wall half-width < 300)
    sec.rebuild()
    assert sec.zone_of(w) == ZONE_BEHIND


def test_45_degree_cut_classifies_pipe_and_slab(qapp, section_scene_for):
    from firepro3d.floor_slab import FloorSlab
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (8000.0, -8000.0), 6000.0)
    n1 = ms.add_node(0.0, -4000.0); n2 = ms.add_node(8000.0, -4000.0)
    pipe = ms.add_pipe(n1, n2)                                   # crosses the diagonal at (4000, -4000)
    slab = FloorSlab(points=[QPointF(5000.0, -1000.0), QPointF(7000.0, -1000.0),
                             QPointF(7000.0, -3000.0), QPointF(5000.0, -3000.0)])
    slab._top_mode = "absolute"
    ms._floor_slabs.append(slab); ms.addItem(slab)
    sec.rebuild()
    assert sec.zone_of(pipe) == ZONE_CUT
    # Slab centroid (6000, -2000): in scene coords the look normal of A=(0,0)->B=(8000,-8000)
    # with look +1 is (D.y, -D.x) = (-1, -1)/sqrt2 -> the slab (x>|y|) is on the other side.
    assert sec.zone_of(slab) == ZONE_HIDDEN
    sec.marker.flip(); sec.rebuild()
    assert sec.zone_of(slab) == ZONE_BEHIND


def test_sprinkler_node_is_never_cut(qapp, section_scene_for):
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    n = ms.add_node(5000.0, 0.0); ms.add_sprinkler(n)
    sec.rebuild()
    assert sec.zone_of(n) == ZONE_BEHIND


def test_auto_extent_refits_then_stops_after_grip(qapp, section_scene_for):
    ms, sec = section_scene_for("north")
    m = sec.marker
    sec.rebuild()
    box0 = m.box_polygon().boundingRect()
    _wall(ms, (-40000.0, 0.0), (-39000.0, 0.0))                 # far outside the seed box
    sec.rebuild()
    box1 = m.box_polygon().boundingRect()
    assert box1.left() < box0.left() - 20000.0                  # re-fit followed the building
    assert sec.zone_of(ms._walls[0]) == ZONE_BEHIND              # and the wall renders
    m.set_geometry(m.cut_a, m.cut_b, m.depth, user=True)      # a grip edit (same numbers)
    assert m.auto_extent is False
    _wall(ms, (60000.0, 0.0), (61000.0, 0.0))
    sec.rebuild()
    assert m.box_polygon().boundingRect() == box1                # no longer follows
    assert sec.zone_of(ms._walls[1]) == ZONE_HIDDEN
