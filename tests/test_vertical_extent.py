"""Vertical extent: one resolver per kind; every view agrees (wall-room-floor-system, Vertical extent)."""
import pytest
from PyQt6.QtCore import QPointF


class _Lvl:
    def __init__(self, e):
        self.elevation = e


class _LM:
    """Stub level manager: name -> elevation."""
    def __init__(self, **elev):
        self._m = {k.replace("_", " "): _Lvl(v) for k, v in elev.items()}

    def get(self, name):
        return self._m.get(name)


def _bare_wall(base="Level 1", top="Level 2", base_off=0.0, top_off=0.0, h=3048.0):
    from firepro3d.wall import WallSegment
    w = WallSegment(QPointF(0, 0), QPointF(3000, 0), thickness_mm=200.0)
    w._base_level, w._top_level = base, top
    w._base_offset_mm, w._top_offset_mm, w._height_mm = base_off, top_off, h
    return w


@pytest.mark.parametrize("case,lm,expect", [
    ("resolved",     _LM(Level_1=1000.0, Level_2=4000.0), (1500.0, 3800.0)),
    ("top_missing",  _LM(Level_1=1000.0),                 (1500.0, 4548.0)),
    ("base_missing", _LM(Level_2=4000.0),                 (500.0, 3800.0)),
    ("no_manager",   None,                                (500.0, 3548.0)),
])
def test_wall_resolver_table(qapp, case, lm, expect):
    w = _bare_wall(base_off=500.0, top_off=-200.0)
    assert w.vertical_extent(lm) == pytest.approx(expect)


def _bare_opening(level="Level 3", wall_base="Level 1"):
    from firepro3d.wall_opening import WallOpening
    w = _bare_wall(base=wall_base)
    op = WallOpening(wall=w, feature_id="window_900", offset_along=1500.0)
    op.level = level
    op._sill_mm, op._height_mm = 900.0, 1200.0
    return op


@pytest.mark.parametrize("case,level,lm,expect", [
    ("resolved",        "Level 3",  _LM(Level_1=1000.0, Level_3=2000.0), (2900.0, 4100.0)),
    ("own_missing",     "Gone",     _LM(Level_1=1000.0),                 (1900.0, 3100.0)),
    ("both_missing",    "Gone",     _LM(Level_2=4000.0),                 (900.0, 2100.0)),
    ("no_manager",      "Level 3",  None,                                (900.0, 2100.0)),
])
def test_opening_resolver_table(qapp, case, level, lm, expect):
    op = _bare_opening(level=level)
    assert op.vertical_extent(lm) == pytest.approx(expect)


def _scene_wall(scene, base_off=0.0, top="Level 1", top_off=3000.0, h=3048.0):
    from firepro3d.wall import WallSegment
    w = WallSegment(QPointF(0, 0), QPointF(2000, 0), thickness_mm=200.0)
    w._base_offset_mm, w._top_level, w._top_offset_mm, w._height_mm = base_off, top, top_off, h
    scene.addItem(w)
    scene._walls.append(w)
    return w


def _section_rect_z(elev, src):
    """(bot, top) z of the _ElevProxyRect tagged with *src* (scene y = -z)."""
    from firepro3d.section_scene import _ElevProxyRect, _ROLE_SOURCE
    rects = [it for it in elev.items()
             if isinstance(it, _ElevProxyRect) and it.data(_ROLE_SOURCE) is src]
    assert len(rects) == 1, rects
    r = rects[0].rect()
    return (-r.bottom(), -r.top())


def test_wall_top_missing_parity(qapp, section_scene_for):
    """RED at base: z_range_mm gave (1000, 200), panel Height -800."""
    scene, elev = section_scene_for(direction="north")
    w = _scene_wall(scene, base_off=1000.0, top="No Such Level", top_off=200.0)
    lm = scene._level_manager
    want = (1000.0, 4048.0)
    assert w.z_range_mm() == pytest.approx(want)            # plan filter / joins / rooms
    assert w.z_span_mm(lm) == pytest.approx(want)           # 3D bands
    assert w._computed_height_mm() == pytest.approx(3048.0)  # panel Height row
    elev.rebuild()
    assert _section_rect_z(elev, w) == pytest.approx(want)  # section projection


def test_wall_base_missing_parity(qapp, section_scene_for):
    """RED at base: 3D / section dropped the base offset (0 vs 1000)."""
    scene, elev = section_scene_for(direction="north")
    w = _scene_wall(scene, base_off=1000.0, top_off=4000.0)
    w._base_level = "No Such Level"
    lm = scene._level_manager
    want = (1000.0, 4000.0)
    assert w.z_range_mm() == pytest.approx(want)
    assert w.z_span_mm(lm) == pytest.approx(want)
    elev.rebuild()
    assert _section_rect_z(elev, w) == pytest.approx(want)


def test_opening_base_offset_parity(qapp, section_scene_for):
    """RED at base: the 3D cut sat at (500, 2532) while the frame sat at (0, 2032)."""
    from firepro3d.wall_opening import WallOpening
    scene, elev = section_scene_for(direction="north")
    w = _scene_wall(scene, base_off=500.0, top_off=3500.0)
    op = WallOpening(wall=w, feature_id="door_914", offset_along=1000.0)
    op.level = w._base_level
    op._sill_mm, op._height_mm = 0.0, 2032.0
    scene.addItem(op)
    w.openings.append(op)
    lm = scene._level_manager
    own = (0.0, 2032.0)
    assert op.z_range_mm() == pytest.approx(own)
    frames = op.get_3d_meshes(level_manager=lm)
    fz = [p[2] for m in frames for p in m["vertices"]]
    assert (min(fz), max(fz)) == pytest.approx(own)          # 3D frame
    cuts = w._opening_cuts(lm)
    assert [(c[1], c[2]) for c in cuts] == [pytest.approx((500.0, 2032.0))]  # clamped to wall
    elev.rebuild()
    assert _section_rect_z(elev, op) == pytest.approx(own)   # section void
    # Section cut through the opening (characterization: already op-level at base):
    # a door leaves wall material only above its head, up to the wall top.
    assert _cut_spans_through(elev, w, op) == [pytest.approx((2032.0, 3500.0))]


def _cut_spans_through(elev, wall, op):
    """Drive SectionScene._wall_cut_spans with a cut line crossing *op*'s centre.

    ``SectionMarker.cut_a`` / ``cut_b`` are read-only properties over ``_a`` /
    ``_b`` (section_marker.py), so the probe sets the backing fields.
    """
    cx = wall.centerline_pt1.x() + op._offset_along
    elev._marker._a = QPointF(cx, -1000.0)
    elev._marker._b = QPointF(cx, 1000.0)
    lo, hi = wall.vertical_extent(elev._lm)
    return elev._wall_cut_spans(wall, lo, hi)
