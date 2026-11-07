"""HF7 D2: SOLID / HATCH extraction on real ezdxf documents."""
import math

import ezdxf
import pytest

from firepro3d import dxf_fills
from firepro3d.dwg_converter import apply_import_transform
from tests._hf7_helpers import fills, extract, new_doc, ring_hatch, square


def _area(pts):
    return sum(a[0] * b[1] - b[0] * a[1]
               for a, b in zip(pts, list(pts[1:]) + [pts[0]])) / 2


def test_solid_quad_is_not_a_bowtie(tmp_path):
    doc, msp = new_doc()
    msp.add_solid([(0, 0), (10, 0), (0, 10), (10, 10)])     # DXF 0-1-3-2 order
    g = fills(extract(doc, tmp_path))[0]
    child = g["loops"][0][0]
    assert g["solid"] and child["closed"] and child["straight"] is True
    assert abs(_area(child["points"])) == pytest.approx(100)   # a bowtie gives 0


def test_solid_triangle_drops_the_repeat(tmp_path):
    doc, msp = new_doc()
    msp.add_solid([(0, 0), (10, 0), (0, 10)])
    assert len(fills(extract(doc, tmp_path))[0]["loops"][0][0]["points"]) == 3


def test_ring_orients_by_depth(tmp_path):
    doc, msp = new_doc()
    ring_hatch(msp)
    g = fills(extract(doc, tmp_path))[0]
    areas = [_area(loop[0]["points"]) for loop in g["loops"]]
    assert len(areas) == 2 and areas[0] * areas[1] < 0
    assert abs(areas[0]) == pytest.approx(10000) and abs(areas[1]) == pytest.approx(400)


def _nested(style):
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.dxf.hatch_style = style
    for x, side in ((0, 100), (10, 80), (20, 60)):
        h.paths.add_polyline_path(square(x, x, side), is_closed=True, flags=0)   # no EXTERNAL flag
    return doc


@pytest.mark.parametrize("style, count", [(0, 3), (1, 2), (2, 1)])
def test_style_filter_uses_geometry_not_flags(tmp_path, style, count):
    assert len(fills(extract(_nested(style), tmp_path))[0]["loops"]) == count


def test_text_box_loop_dropped(tmp_path):
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.paths.add_polyline_path(square(0, 0, 100), is_closed=True, flags=1)
    h.paths.add_polyline_path(square(40, 40, 20), is_closed=True, flags=8)
    assert len(fills(extract(doc, tmp_path))[0]["loops"]) == 1


def _closed_area(pts):
    return abs(_area(pts))


def test_arc_loop_area_within_one_percent(tmp_path):
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.paths.add_edge_path().add_arc((0, 0), radius=1000, start_angle=0, end_angle=360)
    g = fills(extract(doc, tmp_path))[0]
    got = _closed_area(g["loops"][0][0]["points"])
    assert got == pytest.approx(math.pi * 1000 ** 2, rel=0.01)


def test_bulge_loop_area_within_one_percent(tmp_path):
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.paths.add_polyline_path([(0, 0, 1), (100, 0, 1)], is_closed=True, flags=1)   # circle
    got = _closed_area(fills(extract(doc, tmp_path))[0]["loops"][0][0]["points"])
    assert got == pytest.approx(math.pi * 50 ** 2, rel=0.01)


def test_ellipse_loop_area_within_one_percent(tmp_path):
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.paths.add_edge_path().add_ellipse((0, 0), major_axis=(100, 0), ratio=0.5,
                                        start_angle=0, end_angle=360)
    got = _closed_area(fills(extract(doc, tmp_path))[0]["loops"][0][0]["points"])
    assert got == pytest.approx(math.pi * 100 * 50, rel=0.01)


def test_spline_loop_area_within_one_percent(tmp_path):
    doc, msp = new_doc()
    h = msp.add_hatch()
    r = 100
    k = r * 4 * (math.sqrt(2) - 1) / 3
    h.paths.add_edge_path().add_spline(
        control_points=[(r, 0), (r, k), (k, r), (0, r), (-k, r), (-r, k), (-r, 0),
                        (-r, -k), (-k, -r), (0, -r), (k, -r), (r, -k), (r, 0)],
        degree=3,
        knot_values=[0, 0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 4])
    got = _closed_area(fills(extract(doc, tmp_path))[0]["loops"][0][0]["points"])
    assert got == pytest.approx(math.pi * r ** 2, rel=0.01)


def test_tolerance_is_relative_to_the_loop(tmp_path):
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.paths.add_edge_path().add_arc((0, 0), radius=1.0, start_angle=0, end_angle=360)
    assert len(fills(extract(doc, tmp_path))[0]["loops"][0][0]["points"]) >= 16


def test_exact_mode_keeps_curves(tmp_path):
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.paths.add_edge_path().add_arc((0, 0), radius=100, start_angle=0, end_angle=360)
    g = fills(extract(doc, tmp_path, preserve_curves=True))[0]
    assert g["exact_loops"][0][0]["kind"] in ("circle", "arc", "spline")
    assert g["loops"][0][0]["kind"] == "path_points"


def test_mirrored_insert_lands_at_the_world_position(tmp_path):
    doc, msp = new_doc()
    blk = doc.blocks.new("B")
    h = blk.add_hatch()
    h.paths.add_polyline_path(square(10, 0, 10), is_closed=True, flags=1)
    msp.add_blockref("B", (0, 0), dxfattribs={"xscale": -1})
    pts = fills(extract(doc, tmp_path))[0]["loops"][0][0]["points"]
    xs = [p[0] for p in pts]
    assert min(xs) == pytest.approx(-20) and max(xs) == pytest.approx(-10)


def test_pattern_lines_and_families(tmp_path):
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.paths.add_polyline_path(square(0, 0, 100), is_closed=True, flags=1)
    h.set_pattern_fill("ANSI31", scale=5.0)
    g = fills(extract(doc, tmp_path))[0]
    assert not g["solid"] and not g["tone"] and g["lines"]
    assert g["pattern"]["name"] == "ANSI31"
    fam = g["pattern"]["families"][0]
    assert fam["angle"] == pytest.approx(-45.0)
    assert set(fam) == {"angle", "base", "offset", "dashes"}


def test_line_cap_gives_a_tone(tmp_path):
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.paths.add_polyline_path(square(0, 0, 100000), is_closed=True, flags=1)
    h.set_pattern_fill("ANSI31", scale=0.5)
    g = fills(extract(doc, tmp_path))[0]
    assert g["tone"] is True and g["lines"] == []
    assert g["pattern"]["name"] == "ANSI31"


def test_white_solid_is_a_mask(tmp_path):
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.rgb = (255, 255, 255)
    h.paths.add_polyline_path(square(0, 0, 10), is_closed=True, flags=1)
    assert fills(extract(doc, tmp_path))[0]["mask"] is True


def test_draw_order_table_reverses_stream(tmp_path):
    doc, msp = new_doc()
    a = msp.add_line((0, 0), (1, 0))
    b = msp.add_line((0, 1), (1, 1))
    msp.set_redraw_order([(a.dxf.handle, "FF"), (b.dxf.handle, "10")])
    geoms = extract(doc, tmp_path)
    assert [g["y1"] for g in geoms] == [-1, 0]


def test_no_table_keeps_layout_order(tmp_path):
    doc, msp = new_doc()
    msp.add_line((0, 0), (1, 0))
    msp.add_line((0, 1), (1, 1))
    assert [g["y1"] for g in extract(doc, tmp_path)] == [0, -1]


def test_no_table_keeps_layout_order_when_handles_disagree(tmp_path):
    # Extra guard beyond the plan list: with handles in layout order the plain
    # `reorder.ascending` fallback gives the same answer, so only a layout whose
    # order differs from its handle order proves the empty-table branch.
    doc, msp = new_doc()
    a = msp.add_line((0, 0), (1, 0))
    msp.add_line((0, 1), (1, 1))
    msp.unlink_entity(a)
    msp.add_entity(a)                     # layout: b, a   handles: a, b
    assert [g["y1"] for g in extract(doc, tmp_path)] == [-1, 0]


def test_cache_round_trips_a_fill(tmp_path):
    import json
    doc, msp = new_doc()
    ring_hatch(msp)
    geoms = extract(doc, tmp_path)
    back = json.loads(json.dumps(geoms))
    assert back[0]["kind"] == "fill"
    assert apply_import_transform(back, 1.0, 0.0, 0.0)[0]["loops"]


def test_cache_version_bumped():
    from firepro3d import underlay_cache
    assert underlay_cache._CACHE_VERSION == 6


def test_in_draw_order_returns_a_list():
    doc = ezdxf.new()
    assert dxf_fills.in_draw_order(doc.modelspace()) == []


def test_paper_layout_moves_fills(tmp_path):
    doc, msp = new_doc()
    msp.add_line((0, 0), (1000, 1000))
    lay = doc.layouts.new("Sheet")
    vp = lay.add_viewport(center=(100, 100), size=(200, 200),
                          view_center_point=(500, 500), view_height=1000)
    vp.dxf.id = 2
    lay.add_solid([(100, 100), (110, 100), (100, 110), (110, 110)])
    h = lay.add_hatch()
    h.paths.add_polyline_path(square(120, 100, 10), is_closed=True, flags=1)
    h.set_pattern_fill("ANSI31", scale=1.0)
    raw = h.pattern.lines[0].offset
    path = str(tmp_path / "p.dxf")
    doc.saveas(path)
    from firepro3d.dwg_converter import extract_layout_entities
    got = fills(extract_layout_entities(path, "Sheet"))
    assert len(got) == 2
    # ps_to_ms = 5: paper (100, 100) maps to model (500, -500) after Y negation
    xs = [p[0] for p in got[0]["loops"][0][0]["points"]]
    ys = [p[1] for p in got[0]["loops"][0][0]["points"]]
    assert (min(xs), max(xs)) == pytest.approx((500.0, 550.0))
    assert (min(ys), max(ys)) == pytest.approx((-550.0, -500.0))
    assert got[1]["pattern"]["families"][0]["offset"] == pytest.approx([raw.x * 5, -raw.y * 5])
    assert got[1]["lines"]


def test_paper_layout_keeps_arc_ellipse_spline(tmp_path):
    # Behaviour change from T2: ARC / partial ELLIPSE / SPLINE on a paper layout
    # used to be dropped (getattr on an uninitialised QThread raised RuntimeError).
    from firepro3d.dwg_converter import extract_layout_entities, geom_rep_points
    doc, msp = new_doc()
    lay = doc.layouts.new("Sheet")
    vp = lay.add_viewport(center=(100, 100), size=(200, 200),
                          view_center_point=(500, 500), view_height=1000)
    vp.dxf.id = 2
    lay.add_arc((110, 100), radius=5, start_angle=0, end_angle=90)
    lay.add_ellipse((130, 100), major_axis=(10, 0), ratio=0.5,
                    start_param=0, end_param=math.pi / 2)
    lay.add_spline(fit_points=[(150, 100), (155, 105), (160, 100)])
    path = str(tmp_path / "pc.dxf")
    doc.saveas(path)
    got = extract_layout_entities(path, "Sheet")
    assert len(got) == 3
    # paper x -> model x: (x - 100) * 5 + 500; the spans below are the three entities
    spans = [(550, 560), (650, 700), (750, 800)]
    for g, (lo, hi) in zip(got, spans):
        xs = [p[0] for p in geom_rep_points(g)]
        assert xs and lo - 30 <= min(xs) and max(xs) <= hi + 30, (g["kind"], xs)
    # the arc (radius 5 paper = 25 model) spans y -525..-500 in scene space
    ys = [p[1] for p in geom_rep_points(got[0])]
    assert min(ys) >= -526 and max(ys) <= -499, (got[0]["kind"], ys)


def test_touching_island_is_a_hole(tmp_path):
    from PyQt6.QtCore import Qt, QPointF
    from PyQt6.QtGui import QPainterPath, QPolygonF
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.paths.add_polyline_path(square(0, 0, 100), is_closed=True, flags=1)
    h.paths.add_polyline_path([(50, 0), (70, 0), (70, 20), (50, 20)],   # first edge on the outer
                              is_closed=True, flags=0)
    g = fills(extract(doc, tmp_path))[0]
    areas = [_area(loop[0]["points"]) for loop in g["loops"]]
    assert areas[0] * areas[1] < 0
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    for loop in g["loops"]:
        path.addPolygon(QPolygonF([QPointF(x, y) for x, y in loop[0]["points"]]))
    assert not path.contains(QPointF(60, -10))          # inside the hole (scene Y negated)
    assert path.contains(QPointF(20, -50))


def test_many_separate_rings_get_the_right_depths(tmp_path):
    doc, msp = new_doc()
    h = msp.add_hatch()
    for i in range(150):
        x, y = (i % 15) * 300, (i // 15) * 300
        h.paths.add_polyline_path(square(x, y, 200), is_closed=True, flags=1)
        h.paths.add_polyline_path(square(x + 50, y + 50, 100), is_closed=True, flags=16)
    g = fills(extract(doc, tmp_path))[0]
    areas = [_area(loop[0]["points"]) for loop in g["loops"]]
    assert len(areas) == 300
    assert sum(1 for a in areas if a > 0) == 150 and sum(1 for a in areas if a < 0) == 150
    assert sorted(abs(round(a)) for a in areas) == [10000] * 150 + [40000] * 150


def test_huge_estimate_is_a_tone_without_calling_ezdxf(monkeypatch):
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.paths.add_polyline_path(square(0, 0, 1e7), is_closed=True, flags=1)
    h.set_pattern_fill("ANSI31", scale=0.01)

    def boom(*a, **k):
        raise AssertionError("hatch_entity must not run")
    monkeypatch.setattr(dxf_fills.hatching, "hatch_entity", boom)
    rec = dxf_fills.read_hatch(h, "0", "#000000")
    assert rec["tone"] is True and rec["lines"] == [] and rec["loops"]


def test_hatching_error_keeps_the_boundary_as_a_tone(monkeypatch):
    from ezdxf.render import hatching
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.paths.add_polyline_path(square(0, 0, 100), is_closed=True, flags=1)
    h.set_pattern_fill("ANSI31", scale=1.0)

    def bad(*a, **k):
        raise hatching.HatchLineDirectionError("zero direction")
    monkeypatch.setattr(dxf_fills.hatching, "hatch_entity", bad)
    rec = dxf_fills.read_hatch(h, "0", "#000000")
    assert rec["tone"] is True and len(rec["loops"]) == 1


def test_viewport_filter_keeps_an_enclosing_hatch():
    from firepro3d.dwg_converter import filter_geoms_by_bounds
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.paths.add_polyline_path(square(0, 0, 1000), is_closed=True, flags=1)
    h.set_pattern_fill("ANSI31", scale=1.0)
    rec = dxf_fills.read_hatch(h, "0", "#000000")
    inside = [(400.0, -600.0, 500.0, -500.0)]      # wholly within the loop, no vertex in it
    far = [(5000.0, -5100.0, 5100.0, -5000.0)]
    assert filter_geoms_by_bounds([rec], inside) == [rec]
    assert filter_geoms_by_bounds([rec], far) == []


def _slab_scene():
    """A solid slab hatch plus four well-separated lines, as dialog geoms."""
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.set_solid_fill()
    h.paths.add_polyline_path(square(0, 0, 100000), is_closed=True, flags=1)
    slab = dxf_fills.read_hatch(h, "0", "#000000")
    lines = [{"kind": "line", "layer": "0", "x1": x, "y1": y, "x2": x + 100, "y2": y}
             for x, y in ((1000, -1000), (50000, -50000), (90000, -90000), (20000, -80000))]
    return [slab, *lines]


def _crop_dialog(qapp, geoms):
    from firepro3d.underlay_import_dialog import UnderlayImportDialog
    dlg = UnderlayImportDialog()
    dlg._all_geoms = geoms
    dlg._has_vectors = True
    dlg._layers = ["0"]
    dlg._set_rotation(0.0)
    dlg._populate_layer_list()
    dlg._rebuild_preview()
    return dlg


def test_crop_round_trip_keeps_the_crop_with_an_enclosing_hatch(qapp):
    from PyQt6.QtCore import QRectF
    from firepro3d.dwg_converter import filter_geoms_by_bounds
    geoms = _slab_scene()
    dlg = _crop_dialog(qapp, geoms)
    dlg._on_rubber_band(QRectF(900, -1100, 300, 200))     # around line 1 only
    assert dlg._selected_indices == {0, 1}                # the slab encloses the crop
    bounds = dlg.get_import_params().import_bounds
    assert bounds[2] - bounds[0] < 1000                   # not the slab's 100000
    box = [tuple(bounds)]
    again = {i for i, g in enumerate(geoms) if filter_geoms_by_bounds([g], box)}
    assert again == dlg._selected_indices
    assert dlg._current_crop_bounds() == pytest.approx(bounds)   # page-switch carry


def test_modify_restore_does_not_regrow_the_crop(qapp):
    from PyQt6.QtCore import QRectF
    geoms = _slab_scene()
    first = _crop_dialog(qapp, geoms)
    first._on_rubber_band(QRectF(900, -1100, 300, 200))
    saved = first.get_import_params().import_bounds
    second = _crop_dialog(qapp, geoms)
    second._restore_crop_from_bounds(saved)
    assert second._selected_indices == first._selected_indices
    assert second.get_import_params().import_bounds == pytest.approx(saved)


@pytest.mark.parametrize("corner", ["BL", "BR", "TL", "TR"])
def test_island_sharing_two_edges_is_a_hole(tmp_path, corner):
    from PyQt6.QtCore import Qt, QPointF
    from PyQt6.QtGui import QPainterPath, QPolygonF
    ox = 50 if corner in ("BR", "TR") else 0
    oy = 50 if corner in ("TL", "TR") else 0
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.paths.add_polyline_path(square(0, 0, 100), is_closed=True, flags=1)
    h.paths.add_polyline_path(square(ox, oy, 50), is_closed=True, flags=0)
    g = fills(extract(doc, tmp_path))[0]
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    for loop in g["loops"]:
        path.addPolygon(QPolygonF([QPointF(x, y) for x, y in loop[0]["points"]]))
    assert not path.contains(QPointF(ox + 25, -(oy + 25)))      # the hole
    assert path.contains(QPointF(100 - ox - 25 if ox == 0 else 25,
                                 -(100 - oy - 25 if oy == 0 else 25)))    # the ring


@pytest.mark.parametrize("start", [1, 3, 5, 7, 11, 13, 29])
@pytest.mark.parametrize("reverse", [False, True])
def test_duplicate_outer_loop_keeps_the_fill(tmp_path, start, reverse):
    from PyQt6.QtCore import Qt, QPointF
    from PyQt6.QtGui import QPainterPath, QPolygonF
    ring = [(50 + 40 * math.cos(2 * math.pi * k / 64), 50 + 40 * math.sin(2 * math.pi * k / 64))
            for k in range(64)]
    twin = ring[start:] + ring[:start]                      # rotated start vertex
    if reverse:
        twin = list(reversed(twin))
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.paths.add_polyline_path(ring, is_closed=True, flags=1)
    h.paths.add_polyline_path(twin, is_closed=True, flags=1)
    g = fills(extract(doc, tmp_path))[0]
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    for loop in g["loops"]:
        path.addPolygon(QPolygonF([QPointF(x, y) for x, y in loop[0]["points"]]))
    assert path.contains(QPointF(50, -50))


def test_sparse_small_squares_far_apart_are_not_a_tone():
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.paths.add_polyline_path(square(0, 0, 10), is_closed=True, flags=1)
    h.paths.add_polyline_path(square(2e6, 0, 10), is_closed=True, flags=1)
    h.set_pattern_fill("ANSI31", scale=0.01)
    rec = dxf_fills.read_hatch(h, "0", "#000000")
    assert rec["tone"] is False and rec["lines"]


def test_thin_strip_parallel_to_the_pattern_is_not_a_tone():
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.paths.add_polyline_path([(0, 0), (2e6, 2e6), (2e6, 2e6 + 1), (0, 1)],
                              is_closed=True, flags=1)       # along the 45 degree family
    h.set_pattern_fill("ANSI31", scale=0.01)
    rec = dxf_fills.read_hatch(h, "0", "#000000")
    assert rec["tone"] is False


def test_dialog_crop_keeps_an_enclosing_hatch():
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QPolygonF
    from firepro3d.underlay_import_dialog import UnderlayImportDialog
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.paths.add_polyline_path(square(0, 0, 1000), is_closed=True, flags=1)
    h.set_pattern_fill("ANSI31", scale=1.0)
    rec = dxf_fills.read_hatch(h, "0", "#000000")
    near = QPolygonF(QRectF(400, -600, 100, 100))
    far = QPolygonF(QRectF(5000, -5100, 100, 100))
    assert UnderlayImportDialog._geom_in_rect(None, rec, near) is True
    assert UnderlayImportDialog._geom_in_rect(None, rec, far) is False


def test_overlapping_loops_are_not_nested(tmp_path):
    """Half of each square's samples lie inside the other: neither is nested,
    so an Ignore-style hatch keeps both (a nested reading would keep none)."""
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.dxf.hatch_style = 2
    h.paths.add_polyline_path(square(0, 0, 100), is_closed=True, flags=0)
    h.paths.add_polyline_path(square(50, 30, 100), is_closed=True, flags=0)
    assert len(fills(extract(doc, tmp_path))[0]["loops"]) == 2


def test_second_crop_narrows_the_saved_bounds(qapp):
    from PyQt6.QtCore import QRectF
    from firepro3d.dwg_converter import filter_geoms_by_bounds
    geoms = _slab_scene()
    dlg = _crop_dialog(qapp, geoms)
    dlg._on_rubber_band(QRectF(900, -51000, 50000, 51000))   # lines 1 and 2
    assert dlg._selected_indices == {0, 1, 2}
    dlg._on_rubber_band(QRectF(900, -1100, 300, 200))        # line 1 only
    assert dlg._selected_indices == {0, 1}
    bounds = dlg.get_import_params().import_bounds
    assert bounds[2] - bounds[0] < 1000
    box = [tuple(bounds)]
    assert {i for i, g in enumerate(geoms)
            if filter_geoms_by_bounds([g], box)} == {0, 1}
