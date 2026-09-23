"""Slice 1b guards — Block Editor curve fidelity (2026-09-23).

PDF cubic Béziers import as exact curves when ``preserve_curves`` is on:
circular runs -> CircleItem / ArcItem, any other curved subpath -> ONE exact
cubic SplineItem, pure-line subpaths unchanged. DXF partial ELLIPSE ->
exact rational SplineItem. The underlay path (flag off) is unchanged.

Ground truth is the constructed primitive's own painted path, not the dicts.
"""
from __future__ import annotations

import math

import fitz
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.pdf_import_worker import PdfImportWorker
from firepro3d.geometry_import import geom_dicts_to_primitives
from firepro3d.geometry_2d import ArcItem, CircleItem, SplineItem, PolylineItem

K = 0.5522847498  # cubic-Bézier circle constant


def _worker(preserve):
    w = PdfImportWorker.__new__(PdfImportWorker)
    w._cancelled = False
    w._flatten_tol = 0.1
    w._preserve_curves = preserve
    return w


def _P(x, y):
    return fitz.Point(x, y)


def _quarter(cx, cy, r, a0_deg, ccw_screen=True):
    """One cubic quarter-arc as a fitz 'c' item, Y-DOWN page coords.

    Angles are screen angles (0 = +x, positive = visually counter-clockwise,
    i.e. toward -y)."""
    s = 1 if ccw_screen else -1
    a0 = math.radians(a0_deg)
    a1 = math.radians(a0_deg + s * 90)

    def pt(a):
        return (cx + r * math.cos(a), cy - r * math.sin(a))

    def tan(a):   # d/da of pt, scaled
        return (-r * math.sin(a) * s, -r * math.cos(a) * s)

    p0, p3 = pt(a0), pt(a1)
    t0, t3 = tan(a0), tan(a1)
    p1 = (p0[0] + K * t0[0], p0[1] + K * t0[1])
    p2 = (p3[0] - K * t3[0], p3[1] - K * t3[1])
    return ("c", _P(*p0), _P(*p1), _P(*p2), _P(*p3))


def _path(items, close=False):
    return {"items": items, "closePath": close, "width": 1.0}


def _prims(geoms):
    items, skipped = geom_dicts_to_primitives(geoms, 1.0)
    assert skipped == 0
    return items


def _endpoints(item):
    p = item.path()
    return p.pointAtPercent(0.0), p.pointAtPercent(1.0)


def _close(a: QPointF, b, tol=0.05):
    return math.hypot(a.x() - b[0], a.y() - b[1]) <= tol


# ── Circle recognition ──────────────────────────────────────────────────────

def test_four_bezier_circle_becomes_circle_item():
    items = [_quarter(100, 200, 30, a) for a in (0, 90, 180, 270)]
    [c] = _prims(_worker(True)._extract_path(_path(items, close=True)))
    assert isinstance(c, CircleItem)
    r = c.mapRectToScene(c.rect())          # the painted ellipse geometry
    assert abs(r.center().x() - 100) < 0.05 and abs(r.center().y() - 200) < 0.05
    assert abs(r.width() - 60) < 0.05 and abs(r.height() - 60) < 0.05


@pytest.mark.parametrize("ccw", [True, False])
def test_bezier_quarter_arc_becomes_arc_with_true_endpoints(ccw):
    seg = _quarter(0, 0, 50, 30, ccw_screen=ccw)
    [a] = _prims(_worker(True)._extract_path(_path([seg])))
    assert isinstance(a, ArcItem)
    s, e = _endpoints(a)
    p0 = (seg[1].x, seg[1].y)
    p3 = (seg[4].x, seg[4].y)
    # The painted arc must run between the PDF endpoints (either direction).
    assert ({_close(s, p0), _close(e, p3)} == {True}
            or {_close(s, p3), _close(e, p0)} == {True}), (s, e, p0, p3)
    # ...and bulge the right way: its midpoint is ON the source circle, on the
    # side of the source Bézier's midpoint.
    m = a.path().pointAtPercent(0.5)
    assert abs(math.hypot(m.x(), m.y()) - 50) < 0.5
    bm_x = 0.125 * (seg[1].x + 3 * seg[2].x + 3 * seg[3].x + seg[4].x)
    bm_y = 0.125 * (seg[1].y + 3 * seg[2].y + 3 * seg[3].y + seg[4].y)
    assert math.hypot(m.x() - bm_x, m.y() - bm_y) < 1.0


# ── Non-circular curves -> one exact cubic spline ───────────────────────────

def _bez(t, p):
    u = 1 - t
    return (u**3 * p[0][0] + 3*u*u*t * p[1][0] + 3*u*t*t * p[2][0] + t**3 * p[3][0],
            u**3 * p[0][1] + 3*u*u*t * p[1][1] + 3*u*t*t * p[2][1] + t**3 * p[3][1])


def test_mixed_line_and_bezier_path_is_one_exact_spline():
    b = [(10, 0), (30, -40), (60, 40), (80, 0)]            # S-curve (not circular)
    items = [("l", _P(0, 0), _P(10, 0)),
             ("c", *[_P(*q) for q in b]),
             ("l", _P(80, 0), _P(80, 50))]
    [sp] = _prims(_worker(True)._extract_path(_path(items)))
    assert isinstance(sp, SplineItem)
    path = sp.path()
    # Every sample of the source curve lies on the spline (exact, no fitting).
    for t in (0.1, 0.3, 0.5, 0.7, 0.9):
        x, y = _bez(t, b)
        d = min(math.hypot(path.pointAtPercent(k / 400).x() - x,
                           path.pointAtPercent(k / 400).y() - y)
                for k in range(401))
        assert d < 0.6, f"t={t}: spline strays {d:.3f} from the Bézier"
    s, e = _endpoints(sp)
    assert _close(s, (0, 0)) and _close(e, (80, 50))


def test_subpath_gap_splits_into_separate_items():
    b1 = [(0, 0), (10, -20), (20, 20), (30, 0)]
    b2 = [(100, 0), (110, -20), (120, 20), (130, 0)]   # starts elsewhere
    items = [("c", *[_P(*q) for q in b1]), ("c", *[_P(*q) for q in b2])]
    prims = _prims(_worker(True)._extract_path(_path(items)))
    assert len(prims) == 2 and all(isinstance(p, SplineItem) for p in prims)


def test_pure_line_path_unchanged_in_preserve_mode():
    items = [("l", _P(0, 0), _P(10, 0)), ("l", _P(10, 0), _P(10, 10))]
    assert (_worker(True)._extract_path(_path(items))
            == _worker(False)._extract_path(_path(items)))


def test_underlay_mode_still_flattens():
    items = [_quarter(0, 0, 50, 0)]
    geoms = _worker(False)._extract_path(_path(items))
    assert [g["kind"] for g in geoms] == ["path_points"]


# ── Plumbing: the Block import dialog asks for curves ───────────────────────

def test_block_import_dialog_pdf_worker_preserves_curves(qapp, monkeypatch):
    from firepro3d import underlay_import_dialog as uid
    from firepro3d.block_import_dialog import BlockImportDialog
    seen = {}

    class _Spy:
        def __init__(self, path, page, preserve_curves=False):
            seen["preserve"] = preserve_curves
            self.status = self.finished_geoms = self.aborted = self.error = self
        def connect(self, *_):
            pass
        def start(self):
            pass
        def cancel(self):
            pass

    monkeypatch.setattr(uid, "_DialogPdfExtractWorker", _Spy)
    monkeypatch.setattr(uid, "_keepalive", lambda w: None)
    dlg = BlockImportDialog(None)
    try:
        dlg._mode_combo.setCurrentText("Auto")
        dlg._load_pdf_page("x.pdf", 0, dpi=150)
        assert seen.get("preserve") is True
    finally:
        dlg._pdf_worker = None
        dlg.deleteLater()


# ── DXF partial ellipse -> exact rational spline ────────────────────────────

def test_dxf_partial_ellipse_imports_as_exact_spline():
    import ezdxf
    from firepro3d.dxf_import_worker import DxfImportWorker
    doc = ezdxf.new()
    e = doc.modelspace().add_ellipse((10, 20), major_axis=(40, 0), ratio=0.5,
                                     start_param=0.3, end_param=2.0)
    w = DxfImportWorker("unused.dxf", preserve_curves=True)
    g = w._extract_geometry(e)
    assert g["kind"] == "spline" and g["weights"]
    [sp] = _prims([g])
    s, en = _endpoints(sp)
    sp0, sp1 = e.start_point, e.end_point
    assert _close(s, (sp0.x, -sp0.y), 0.05) and _close(en, (sp1.x, -sp1.y), 0.05)
    # Mid-parameter point of the true ellipse lies on the spline.
    ce = e.construction_tool()
    mid = list(ce.vertices([1.15]))[0]
    path = sp.path()
    d = min(math.hypot(path.pointAtPercent(k / 400).x() - mid.x,
                       path.pointAtPercent(k / 400).y() + mid.y)
            for k in range(401))
    assert d < 0.3



# ── Bézier-chain splines render natively (perf) and exactly ─────────────────

def _chain_dict():
    b = [(10, 0), (30, -40), (60, 40), (80, 0)]
    items = [("l", _P(0, 0), _P(10, 0)), ("c", *[_P(*q) for q in b]),
             ("c", _P(80, 0), _P(90, -30), _P(120, 30), _P(130, 0))]
    [g] = _worker(True)._extract_path(_path(items))
    return g


def test_bezier_chain_spline_matches_nurbs_evaluation():
    from ezdxf.math import BSpline
    g = _chain_dict()
    [sp] = _prims([g])
    ref = BSpline(g["control_points"], order=4, knots=g["knots"])
    path = sp.path()
    for t in [i / 20 * ref.max_t for i in range(21)]:
        v = ref.point(t)
        x, y = v.x, v.y
        d = min(math.hypot(path.pointAtPercent(k / 600).x() - x,
                           path.pointAtPercent(k / 600).y() - y)
                for k in range(601))
        assert d < 0.3, f"t={t:.2f}: {d:.3f}"


def test_bezier_chain_splines_build_fast():
    import time
    g = _chain_dict()
    t0 = time.perf_counter()
    geom_dicts_to_primitives([g] * 500, 1.0)
    # ezdxf flattening took ~30 ms/spline on real PDF glyph outlines; the
    # native cubicTo path is sub-millisecond. Generous bound, not a benchmark.
    assert time.perf_counter() - t0 < 3.0


def test_selecting_a_long_spline_computes_grips_once_per_item(qapp, monkeypatch):
    from firepro3d.model_space import Model_Space
    sc = Model_Space()
    sp = SplineItem([QPointF(i * 10.0, (i % 2) * 10.0) for i in range(301)], 3)
    sc.addItem(sp)
    sc._draw_splines.append(sp)
    calls = []
    orig = SplineItem.grip_points
    monkeypatch.setattr(SplineItem, "grip_points",
                        lambda self: calls.append(1) or orig(self))
    sc.select_items([sp])
    assert sc._manipulator.isVisible()
    # One host per control point; positioning them must not be O(n^2).
    assert len(calls) < 10, f"grip_points called {len(calls)}x for one item"
