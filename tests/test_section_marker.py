"""SectionMarker guards: dict round-trip, cardinal seed, auto-extent, PAPER_EXCLUDED."""
import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.section_marker import (SectionMarker, building_bbox, cardinal_cut,
                                      CROP_MARGIN, FALLBACK_HALF)


def test_to_dict_round_trip_all_fields():
    m = SectionMarker("Section 7", QPointF(100.0, 200.0), QPointF(900.0, 650.0),
                      look_sign=-1, depth=3200.0)
    m.gridline_z_overrides["A"] = {"v_top": -5000.0, "v_bot": 500.0}
    d = m.to_dict()
    assert d == {"name": "Section 7", "cut_a": [100.0, 200.0], "cut_b": [900.0, 650.0],
                 "look_sign": -1, "depth": 3200.0, "cardinal": None,
                 "auto_extent": False,
                 "gridline_z_overrides": {"A": {"v_top": -5000.0, "v_bot": 500.0}}}
    m2 = SectionMarker.from_dict(d)
    assert m2.to_dict() == d


def test_cardinal_cut_scene_coordinates_match_basis_table():
    box = QRectF(-10000.0, -5000.0, 20000.0, 10000.0)   # scene: top = -5000 = world y_max
    assert cardinal_cut("north", box) == ((10000.0, -5000.0), (-10000.0, -5000.0), 10000.0)
    assert cardinal_cut("south", box) == ((-10000.0, 5000.0), (10000.0, 5000.0), 10000.0)
    assert cardinal_cut("east", box) == ((10000.0, 5000.0), (10000.0, -5000.0), 20000.0)
    assert cardinal_cut("west", box) == ((-10000.0, -5000.0), (-10000.0, 5000.0), 20000.0)


def test_building_bbox_unions_gridlines_and_items_with_fallback(qapp):
    from firepro3d.model_space import Model_Space
    from firepro3d.gridline import GridlineItem
    from firepro3d.wall import WallSegment
    ms = Model_Space()
    assert building_bbox(ms) == QRectF(-FALLBACK_HALF - CROP_MARGIN, -FALLBACK_HALF - CROP_MARGIN,
                                       2 * (FALLBACK_HALF + CROP_MARGIN), 2 * (FALLBACK_HALF + CROP_MARGIN))
    gl = GridlineItem(QPointF(-1200.0, 500.0), QPointF(1200.0, 500.0), label="A")
    ms._gridlines.append(gl); ms.addItem(gl)
    w = WallSegment(QPointF(0.0, 0.0), QPointF(4000.0, 0.0))
    ms._walls.append(w); ms.addItem(w)
    bb = building_bbox(ms)
    raw = gl.sceneBoundingRect().united(w.sceneBoundingRect())
    assert bb == raw.adjusted(-CROP_MARGIN, -CROP_MARGIN, CROP_MARGIN, CROP_MARGIN)


def test_marker_scene_units_convert_to_world_mm_at_ppm_2(qapp, section_scene_for):
    """Marker geometry is plan-scene units; at ppm 2 the basis is world mm."""
    from firepro3d.section_scene import SectionScene
    ms, _ = section_scene_for("south")
    ms.scale_manager.set_pixels_per_mm(2.0)
    assert ms.scale_manager.is_calibrated
    m = SectionMarker("S", QPointF(0.0, 0.0), QPointF(4000.0, 0.0), 1, 4000.0)
    sec = SectionScene(m, ms, ms._level_manager, ms.scale_manager)
    assert sec.basis.depth == 2000.0
    wx, wy = sec._scene_to_world(2000.0, 0.0)
    assert sec.basis.h(wx, wy) == pytest.approx(1000.0)     # D = +x: h = wx


def test_paper_excluded_only_on_cardinals():
    c = SectionMarker.for_cardinal("north", QRectF(-100.0, -100.0, 200.0, 200.0))
    p = SectionMarker("Section 1", QPointF(0.0, 0.0), QPointF(1000.0, 0.0))
    assert c.PAPER_EXCLUDED is True and c.cardinal == "north" and c.auto_extent is True
    assert p.PAPER_EXCLUDED is False and p.cardinal is None and p.auto_extent is False
