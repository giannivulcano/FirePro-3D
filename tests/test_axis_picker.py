"""DD2 axis picker: the nearest visible STRAIGHT segment within tolerance.

Governing: docs/superpowers/specs/2026-10-01-scene-tools-p1-batch-design.md
DD2 (folded into snapping-engine.md / scene-tools.md at Account). Real
Model_Space scenes and real items; the asserted ground truth is the picked
segment's scene endpoints and its source item.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainterPath
from PyQt6.QtWidgets import QGraphicsItemGroup, QGraphicsPathItem

from firepro3d.axis_picker import pick_axis
from firepro3d.dwg_converter import append_geom_to_path
from firepro3d.geometry_2d import (ArcItem, CircleItem, EllipseItem, LineItem,
                                   PolylineItem, RectangleItem,
                                   ReferenceLineItem, RegularPolygonItem,
                                   SplineItem)
from firepro3d.gridline import GridlineItem
from firepro3d.underlay_snap_index import UnderlaySnapIndex
from firepro3d.wall import WallSegment

TOL = 10.0


@pytest.fixture
def editor(qapp):
    from firepro3d.model_space import Model_Space
    s = Model_Space(scene_role="block_editor")
    yield s
    s.cleanup()


@pytest.fixture
def plan(qapp):
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    yield s
    s.cleanup()


def _add(scene, item, attr):
    scene.addItem(item)
    getattr(scene, attr).append(item)
    return item


def _ends(pick):
    return {(round(pick.p1.x(), 2), round(pick.p1.y(), 2)),
            (round(pick.p2.x(), 2), round(pick.p2.y(), 2))}


def _closed_poly():
    pl = PolylineItem(QPointF(300, 0))
    pl.append_point(QPointF(400, 0))
    pl.append_point(QPointF(400, -100))
    pl.close()
    return pl


STRAIGHT = {
    "line": (lambda: LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines",
             QPointF(50, 3), {(0.0, 0.0), (100.0, 0.0)}),
    "refline": (lambda: ReferenceLineItem(QPointF(0, 0), QPointF(100, 0)),
                "_reference_lines", QPointF(50, -3), {(0.0, 0.0), (100.0, 0.0)}),
    "rect_edge": (lambda: RectangleItem(QPointF(600, 0), QPointF(700, -50)),
                  "_draw_rects", QPointF(650, -48), {(600.0, -50.0), (700.0, -50.0)}),
    # The generator walks a polyline's vertex chain only; the closing edge of a
    # CLOSED polyline is still an edge (DD2: the selection's own edges count).
    "closed_poly_closing_edge": (_closed_poly, "_polylines", QPointF(350, -50),
                                 {(400.0, -100.0), (300.0, 0.0)}),
    "polygon_edge": (lambda: RegularPolygonItem(QPointF(0, 0), sides=4,
                                                radius_mm=100.0, rotation_deg=45.0),
                     "_draw_polygons", QPointF(0, -68),
                     {(70.71, -70.71), (-70.71, -70.71)}),
}


@pytest.mark.parametrize("name", list(STRAIGHT))
def test_picks_the_straight_segment_under_the_cursor(editor, name):
    factory, attr, cursor, ends = STRAIGHT[name]
    item = _add(editor, factory(), attr)
    pick = pick_axis(editor, cursor, TOL)
    assert pick is not None and pick.source is item                  # [RED]
    assert _ends(pick) == ends


CURVES = {
    "arc_top": (lambda: ArcItem(QPointF(0, -300), 100.0, 0.0, 180.0), "_draw_arcs",
                QPointF(0, -398)),
    "arc_centre_chord": (lambda: ArcItem(QPointF(0, -300), 100.0, 0.0, 180.0),
                         "_draw_arcs", QPointF(0, -300)),
    "circle": (lambda: CircleItem(QPointF(0, 0), 50.0), "_draw_circles",
               QPointF(50, 2)),
    "ellipse": (lambda: EllipseItem(QPointF(0, 0), 80.0, 40.0), "_draw_ellipses",
                QPointF(0, -38)),
    "spline": (lambda: SplineItem([QPointF(0, 300), QPointF(50, 240),
                                   QPointF(100, 300)]), "_draw_splines",
               QPointF(50, 270)),
}


@pytest.mark.parametrize("name", list(CURVES))
def test_curves_are_never_an_axis(editor, name):
    factory, attr, cursor = CURVES[name]
    _add(editor, factory(), attr)
    assert pick_axis(editor, cursor, TOL) is None                    # [RED]


def test_hidden_items_are_skipped(editor):
    ln = _add(editor, LineItem(QPointF(0, 600), QPointF(100, 600)), "_draw_lines")
    ln.setVisible(False)
    assert pick_axis(editor, QPointF(50, 600), TOL) is None


def test_exclude_and_empty_space(editor):
    ln = _add(editor, LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines")
    assert pick_axis(editor, QPointF(50, 3), TOL, exclude=[ln]) is None
    assert pick_axis(editor, QPointF(5000, 5000), TOL) is None


def test_nearest_segment_wins(editor):
    _add(editor, LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines")
    nearer = _add(editor, LineItem(QPointF(0, 6), QPointF(100, 6)), "_draw_lines")
    pick = pick_axis(editor, QPointF(50, 4), TOL)          # 4 mm vs 2 mm away
    assert pick.source is nearer


def test_axis_heading_is_y_up(editor):
    """A segment drawn visually upward reads 90° (scene Y is down)."""
    _add(editor, LineItem(QPointF(0, 0), QPointF(0, -100)), "_draw_lines")
    pick = pick_axis(editor, QPointF(2, -50), TOL)
    assert pick.angle_deg == pytest.approx(90.0)


def test_gridline_and_wall_face_are_axes(plan):
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 500), "A")
    plan._register_gridline(gl)
    pick = pick_axis(plan, QPointF(4, 250), TOL)
    assert pick is not None and pick.source is gl
    w = WallSegment(QPointF(1000, 0), QPointF(2000, 0), thickness_mm=200.0)
    plan.addItem(w)
    plan._walls.append(w)
    pick = pick_axis(plan, QPointF(1500, 98), TOL)
    assert pick is not None and pick.source is w
    assert _ends(pick) == {(1000.0, 100.0), (2000.0, 100.0)}


def _underlay_group(scene, path, index=None):
    grp = QGraphicsItemGroup()
    grp.setData(0, "DXF Underlay")
    scene.addItem(grp)
    child = QGraphicsPathItem(path)
    scene.addItem(child)
    grp.addToGroup(child)
    if index is not None:
        grp.setData(4, index)
    return grp, child


def test_indexed_underlay_segment_is_an_axis(plan):
    path = QPainterPath()
    path.moveTo(3000, 0)
    path.lineTo(3100, 0)
    grp, _ = _underlay_group(plan, path, UnderlaySnapIndex(
        [{"kind": "line", "x1": 3000, "y1": 0, "x2": 3100, "y2": 0}], []))
    pick = pick_axis(plan, QPointF(3050, 3), TOL)
    assert pick is not None and pick.source is grp
    assert _ends(pick) == {(3000.0, 0.0), (3100.0, 0.0)}


def test_unindexed_underlay_child_is_never_an_axis(plan):
    """No real import path builds an underlay group without a snap index, and
    a flattened curve's chords cannot be told apart in a bare QPainterPath,
    so an un-indexed underlay child is rejected outright (I1, 2026-10-01)."""
    path = QPainterPath()
    append_geom_to_path(path, {"kind": "line", "x1": 4000, "y1": 0,
                               "x2": 4100, "y2": 0})
    _underlay_group(plan, path)
    assert pick_axis(plan, QPointF(4050, 3), TOL) is None


# ── Real DXF import path (I1, user decision 2026-10-01) ────────────────────
# ezdxf entities -> DxfImportWorker._extract_geometry (the underlay mode:
# curves flattened into path_points chords) -> the real batched builder
# (append_geom_to_path) + _attach_snap_index (UnderlaySnapIndex). Curve
# chords are never an axis; LINE and straight LWPOLYLINE spans are. DXF is
# Y-up, the scene Y-down: DXF (x, y) lands at scene (x*s, -y*s).

def _dxf_entities():
    import ezdxf
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_arc(center=(0, 0), radius=1000, start_angle=0, end_angle=180)
    msp.add_ellipse(center=(0, 3000), major_axis=(800, 0), ratio=0.5,
                    start_param=0.0, end_param=3.141592653589793)
    msp.add_lwpolyline([(3000, 0), (4000, 0), (4000, 500)])
    msp.add_lwpolyline([(6000, 0), (7000, 0), (7000, 1000), (6000, 1000)],
                       close=True)
    msp.add_line((9000, 0), (10000, 0))
    return list(msp)


def _extract(entities):
    from firepro3d.dxf_import_worker import DxfImportWorker
    w = DxfImportWorker.__new__(DxfImportWorker)   # sync path, as the tests do
    w._layer_colors = {}
    w._preserve_curves = False                     # underlay import mode
    return [w._extract_geometry(e) for e in entities]


def _record(**kw):
    from firepro3d.underlay import Underlay
    kw.setdefault("type", "dxf")
    kw.setdefault("path", "x.dxf")
    return Underlay(**kw)


def _build_like_import(scene, geoms):
    """The _on_dxf_finished build sequence (underlay_controller)."""
    rec = _record()
    group, _layers = scene._build_batched_underlay_group(geoms, rec)
    group.setData(0, "DXF Underlay")
    scene._attach_snap_index(group, geoms, rec)
    return group


def _curve_cursors(s=1.0):
    # 1 mm inside the arc at its top and at 45 deg; 1 mm inside the ellipse top.
    return [QPointF(0, -999 * s), QPointF(706.4 * s, -706.4 * s),
            QPointF(0, -3399 * s)]


def _assert_straight_axes(scene, grp, s=1.0):
    for cursor, ends in (
            (QPointF(3500 * s, 2), {(3000 * s, 0.0), (4000 * s, 0.0)}),
            (QPointF(4000 * s + 2, -250 * s), {(4000 * s, 0.0), (4000 * s, -500 * s)}),
            # the CLOSED LWPOLYLINE's closing edge
            (QPointF(6000 * s + 2, -500 * s), {(6000 * s, -1000 * s), (6000 * s, 0.0)}),
            (QPointF(9500 * s, 2), {(9000 * s, 0.0), (10000 * s, 0.0)})):
        pick = pick_axis(scene, cursor, TOL)
        assert pick is not None and pick.source is grp, cursor
        assert _ends(pick) == {(round(x, 2), round(y, 2)) for x, y in ends}


def test_real_dxf_underlay_curves_are_never_an_axis(plan):
    grp = _build_like_import(plan, _extract(_dxf_entities()))
    for cursor in _curve_cursors():
        assert pick_axis(plan, cursor, TOL) is None, cursor          # [RED]
    _assert_straight_axes(plan, grp)


def test_curve_chords_stay_cursor_snap_geometry(plan):
    """Only the picker rejects curve chords — the snap generator still emits
    them for the group (cursor snap behaviour unchanged)."""
    from firepro3d.snap_engine import _SnapCtx
    grp = _build_like_import(plan, _extract(_dxf_entities()))
    c = _curve_cursors()[0]
    rect = QRectF(c.x() - TOL, c.y() - TOL, 2 * TOL, 2 * TOL)
    ctx = _SnapCtx(cursor=c, scale=1.0, aperture_px=0.0, priority_band_px=0.0)
    segs = [r for k, r in plan._snap_engine._iter_geometry_segments(
        plan, rect, None, [], None, ctx) if k == "seg" and r[2] is grp]
    assert segs


def test_straight_tag_survives_cache_round_trip_and_import_transform(plan, tmp_path):
    """Save -> load through the REAL cache + _load_underlay_from_cache path,
    with a non-unit import scale so apply_import_transform runs."""
    from firepro3d.underlay_cache import cache_dir_for_project, write_cache
    geoms = _extract(_dxf_entities())
    project = tmp_path / "proj.fpd"
    plan._project_path = str(project)
    rec = _record(import_scale=2.0)
    write_cache(cache_dir_for_project(str(project)), rec.cache_key(), geoms,
                source_mtime=123.0)
    assert plan._load_underlay_from_cache(rec, 123.0)
    grp = plan._underlay_ctl.items[-1][1]
    assert any(g.get("straight") is True for g in grp.data(4)._geom_list)
    for cursor in _curve_cursors(2.0):
        assert pick_axis(plan, cursor, TOL) is None, cursor
    _assert_straight_axes(plan, grp, 2.0)


def test_legacy_cache_record_without_key_is_not_an_axis(plan, tmp_path):
    """A cache written before the tag existed: its path_points (straight or
    not) are never an axis; its LINE records still are."""
    from firepro3d.underlay_cache import cache_dir_for_project, write_cache
    legacy = [{k: v for k, v in g.items() if k != "straight"}
              for g in _extract(_dxf_entities())]
    project = tmp_path / "proj.fpd"
    plan._project_path = str(project)
    rec = _record()
    write_cache(cache_dir_for_project(str(project)), rec.cache_key(), legacy,
                source_mtime=123.0)
    assert plan._load_underlay_from_cache(rec, 123.0)
    grp = plan._underlay_ctl.items[-1][1]
    assert pick_axis(plan, QPointF(3500, 2), TOL) is None       # legacy LWPOLYLINE
    pick = pick_axis(plan, QPointF(9500, 2), TOL)               # legacy LINE
    assert pick is not None and pick.source is grp
    assert _ends(pick) == {(9000.0, 0.0), (10000.0, 0.0)}


# ── Real PDF import path (underlay mode: Béziers flattened) ─────────────────

def _pdf_geoms():
    import fitz
    from firepro3d.pdf_import_worker import PdfImportWorker
    w = PdfImportWorker.__new__(PdfImportWorker)
    w._cancelled = False
    w._flatten_tol = 0.1
    w._preserve_curves = False
    P = fitz.Point
    k = 0.5522847498 * 1000                       # quarter circle r=1000 at (0,0)
    curve_then_line = [("c", P(1000, 0), P(1000, -k), P(k, -1000), P(0, -1000)),
                       ("l", P(0, -1000), P(-2000, -1000))]
    lines_only = [("l", P(3000, 0), P(4000, 0)), ("l", P(4000, 0), P(4000, -500))]
    rect = [("re", fitz.Rect(6000, -1000, 7000, 0))]
    geoms = []
    for items in (curve_then_line, lines_only, rect):
        geoms += w._extract_path({"items": items, "closePath": False,
                                  "width": 1.0})
    return geoms


def test_real_pdf_underlay_only_pure_line_records_are_axes(plan):
    geoms = _pdf_geoms()
    assert [g.get("straight") for g in geoms] == [None, True, True]
    rec = _record(type="pdf", path="x.pdf")
    group, _ = plan._build_batched_underlay_group(geoms, rec)
    group.setData(0, "PDF Underlay")
    plan._attach_snap_index(group, geoms, rec)
    # The flattened Bézier's chords are never an axis; the "l" span sharing
    # its record is dropped with it (one record, no per-span tag).
    assert pick_axis(plan, QPointF(706.4, -706.4), TOL) is None
    assert pick_axis(plan, QPointF(-1000, -998), TOL) is None
    pick = pick_axis(plan, QPointF(3500, 2), TOL)
    assert pick is not None and pick.source is group
    assert _ends(pick) == {(3000.0, 0.0), (4000.0, 0.0)}
    pick = pick_axis(plan, QPointF(6500, -998), TOL)            # rect edge
    assert pick is not None and _ends(pick) == {(6000.0, -1000.0), (7000.0, -1000.0)}


# ── RR-1 perf: a large straight underlay record (user bar 2026-10-01) ──────

def _big_underlay_geoms():
    """50k records: 40k lines + 10k 5-point straight polylines + one closed
    20k-vertex straight contour (a site contour / building outline)."""
    import math
    import random
    rnd = random.Random(1)
    geoms = []
    for _ in range(40000):
        x, y = rnd.uniform(0, 100000), rnd.uniform(0, 100000)
        geoms.append({"kind": "line", "layer": "L", "x1": x, "y1": y,
                      "x2": x + rnd.uniform(-300, 300),
                      "y2": y + rnd.uniform(-300, 300)})
    for _ in range(10000):
        x, y = rnd.uniform(0, 100000), rnd.uniform(0, 100000)
        geoms.append({"kind": "path_points", "layer": "P", "closed": False,
                      "straight": True,
                      "points": [(x + 200 * k, y + (50 if k % 2 else 0))
                                 for k in range(5)]})
    n, r, cx, cy = 20000, 20000.0, 50000.0, 50000.0
    contour = [(cx + r * math.cos(2 * math.pi * k / n),
                cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
    geoms.append({"kind": "path_points", "layer": "C", "closed": True,
                  "straight": True, "points": contour})
    return geoms, contour


@pytest.mark.perf
def test_pick_axis_on_a_huge_straight_underlay_record_is_interactive(plan):
    """Median ``pick_axis`` per hover with the cursor ON a 20k-vertex straight
    contour inside a 50k-record underlay: <= 8 ms (user bar, 2026-10-01)."""
    import statistics
    import time
    geoms, contour = _big_underlay_geoms()
    grp = _build_like_import(plan, geoms)
    step = len(contour) // 20
    cursors = []
    for k in range(0, len(contour), step):
        (ax, ay), (bx, by) = contour[k], contour[(k + 1) % len(contour)]
        cursors.append(QPointF((ax + bx) / 2, (ay + by) / 2))
    for c in cursors:                                   # every hover hits it
        pick = pick_axis(plan, c, 15.0)
        assert pick is not None and pick.source is grp
    times = []
    for _ in range(5):
        for c in cursors:
            t0 = time.perf_counter()
            pick_axis(plan, c, 15.0)
            times.append((time.perf_counter() - t0) * 1000.0)
    med = statistics.median(times)
    assert med <= 8.0, f"median pick_axis {med:.2f} ms"                 # [RED]


# ── RR-2: bulged polyline spans are arcs in the source ─────────────────────

def _bulge_entities():
    import ezdxf
    doc = ezdxf.new()
    msp = doc.modelspace()
    # Door swing: quarter arc as a 2-vertex LWPOLYLINE, bulge tan(90/4).
    msp.add_lwpolyline([(0, 0, 0, 0, 0.41421356), (-1000, 1000, 0, 0, 0)],
                       format="xyseb")
    # Old-style heavy POLYLINE with one bulged span.
    heavy = msp.add_polyline2d([(3000, 0), (4000, 0), (4000, 1000)])
    heavy.vertices[1].dxf.bulge = 0.5
    # Straight heavy POLYLINE, and an OPEN LWPOLYLINE whose only bulge sits
    # on its last vertex (it shapes no span) — both straight.
    msp.add_polyline2d([(6000, 0), (7000, 0)])
    msp.add_lwpolyline([(9000, 0, 0, 0, 0), (10000, 0, 0, 0, 0.7)],
                       format="xyseb")
    return list(msp)


def test_bulged_polyline_spans_are_never_an_axis(plan):
    geoms = _extract(_bulge_entities())
    assert [g.get("straight") for g in geoms] == [None, None, True, True]  # [RED]
    grp = _build_like_import(plan, geoms)
    assert pick_axis(plan, QPointF(-500, -500), TOL) is None      # swing chord
    assert pick_axis(plan, QPointF(3500, 2), TOL) is None         # heavy, bulged
    for cursor, ends in ((QPointF(6500, 2), {(6000.0, 0.0), (7000.0, 0.0)}),
                         (QPointF(9500, 2), {(9000.0, 0.0), (10000.0, 0.0)})):
        pick = pick_axis(plan, cursor, TOL)
        assert pick is not None and pick.source is grp
        assert _ends(pick) == ends
