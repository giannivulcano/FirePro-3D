"""872 / D7a: a gridline crossing the cut line projects vertical at the crossing;
parallel or out-of-box gridlines are absent; datums span [h_min, h_max]."""
import math
import pytest
from PyQt6.QtCore import QPointF

from tests.test_section_classification import _placed_scene


def _gridline(ms, p, q, label):
    from firepro3d.gridline import GridlineItem
    gl = GridlineItem(QPointF(*p), QPointF(*q), label=label)
    ms._gridlines.append(gl); ms.addItem(gl)
    return gl


def _grid_items(sec):
    from firepro3d.section_scene import ElevGridlineItem
    return {it._label: it for it in sec.items() if isinstance(it, ElevGridlineItem)}


def test_30_degree_gridline_draws_vertical_at_crossing(qapp, section_scene_for):
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    # Gridline through (4000, 0) at 30 degrees; its endpoints never touch y = 0 but the
    # infinite line crosses the cut at x = 4000 (spec s5: crossing of the infinite gridline).
    dx, dy = 3000.0 * math.cos(math.radians(30)), 3000.0 * math.sin(math.radians(30))
    _gridline(ms, (4000.0 + dx, dy), (4000.0 + 2 * dx, 2 * dy), "A")
    sec.rebuild()
    items = _grid_items(sec)
    assert set(items) == {"A"}
    gl = items["A"]
    assert gl.line().x1() == pytest.approx(gl.line().x2())                 # vertical
    assert gl.line().x1() == pytest.approx(sec.basis.h(4000.0, 0.0), abs=1e-6)


def test_parallel_and_outside_crossings_are_absent(qapp, section_scene_for):
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    _gridline(ms, (0.0, -2000.0), (10000.0, -2000.0), "P")      # parallel to the cut
    _gridline(ms, (15000.0, -3000.0), (15000.0, 3000.0), "O")   # crosses y=0 at x=15000 > h_max
    _gridline(ms, (5000.0, -3000.0), (5000.0, 3000.0), "I")     # crosses inside
    sec.rebuild()
    assert set(_grid_items(sec)) == {"I"}


def test_cardinal_gridlines_unchanged_from_today(qapp, section_scene_for):
    """North: a vertical-in-plan gridline shows at h = -wx; the horizontal one
    is parallel to the cut -> absent (today's cardinal rule, now derived)."""
    ms, sec = section_scene_for("north")
    _gridline(ms, (2500.0, -3000.0), (2500.0, 3000.0), "1")
    _gridline(ms, (-3000.0, 1000.0), (3000.0, 1000.0), "A")
    sec.rebuild()
    items = _grid_items(sec)
    assert set(items) == {"1"} and items["1"].line().x1() == pytest.approx(-2500.0)


def test_datum_spans_crop_box(qapp, section_scene_for):
    from firepro3d.section_scene import ElevDatumItem
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    sec.rebuild()
    datums = [it for it in sec.items() if isinstance(it, ElevDatumItem)]
    assert datums
    d = datums[0]
    assert (d._h_min, d._h_max) == pytest.approx((sec.basis.h_min, sec.basis.h_max))
