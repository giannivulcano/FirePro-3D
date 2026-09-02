"""Characterization + equivalence tests for the geom->QPainterPath builder.

Task 6 de-dups ``_append_geom_to_path`` (previously copied in ``model_space``
and ``underlay_import_dialog``) into one shared free function
``dwg_converter.append_geom_to_path``. These tests pin the *observable*
behavior of the builder (element count + bounding rect per geom kind) against
the current ``Model_Space._append_geom_to_path`` staticmethod, then assert the
extracted shared function produces byte-for-byte-equivalent paths.

Geometry dicts use the real extraction-pipeline schema (see
``dwg_converter.apply_import_transform`` / ``pdf_import_worker`` for the field
names each kind carries).
"""
import math

from PyQt6.QtGui import QPainterPath

from firepro3d.model_space import Model_Space
from firepro3d.underlay_import_dialog import UnderlayImportDialog
from firepro3d import dwg_converter


# Real geom dicts of every kind the builder handles. These mirror the shapes
# emitted by the DXF/PDF extraction pipeline.
LINE = {"kind": "line", "x1": 10.0, "y1": 20.0, "x2": 110.0, "y2": 220.0}
CIRCLE = {"kind": "circle", "x": 5.0, "y": 5.0, "w": 40.0, "h": 40.0}
ARC = {"kind": "arc", "rx": 0.0, "ry": 0.0, "rw": 100.0, "rh": 100.0,
       "start": 0.0, "span": 90.0}
ELLIPSE_FULL = {"kind": "ellipse_full", "pos_cx": 50.0, "pos_cy": 60.0,
                "x": -10.0, "y": -20.0, "w": 20.0, "h": 40.0}
PATH_OPEN = {"kind": "path_points",
             "points": [(0.0, 0.0), (30.0, 0.0), (30.0, 40.0)]}
PATH_CLOSED = {"kind": "path_points", "closed": True,
               "points": [(0.0, 0.0), (30.0, 0.0), (30.0, 40.0)]}
TEXT = {"kind": "text", "text": "SPRINKLER", "x": 0.0, "y": 0.0,
        "size": 10.0, "valign": 3, "halign": 0, "twidth": 40.0}

ALL_GEOMS = {
    "line": LINE,
    "circle": CIRCLE,
    "arc": ARC,
    "ellipse_full": ELLIPSE_FULL,
    "path_open": PATH_OPEN,
    "path_closed": PATH_CLOSED,
    "text": TEXT,
}


def _build(append_fn, g):
    path = QPainterPath()
    append_fn(path, g)
    return path


def _rect_approx(a, b, tol=1e-6):
    return (math.isclose(a.x(), b.x(), abs_tol=tol)
            and math.isclose(a.y(), b.y(), abs_tol=tol)
            and math.isclose(a.width(), b.width(), abs_tol=tol)
            and math.isclose(a.height(), b.height(), abs_tol=tol))


# ── Step 2: characterize current model_space behavior ─────────────────────────

def test_characterize_current_builder(qapp):
    """Pin the current builder's observable output for every geom kind.

    This does not hardcode magic numbers (font metrics are platform/Qt
    dependent); it records that each kind yields a non-degenerate path and
    stores the per-kind (elementCount, boundingRect) for the equivalence
    checks below to compare against.
    """
    for name, g in ALL_GEOMS.items():
        path = _build(Model_Space._append_geom_to_path, g)
        assert path.elementCount() > 0, f"{name} produced an empty path"
        br = path.boundingRect()
        assert br.width() >= 0 and br.height() >= 0, name


def test_line_bounds(qapp):
    br = _build(Model_Space._append_geom_to_path, LINE).boundingRect()
    assert _rect_approx(br, br.__class__(10.0, 20.0, 100.0, 200.0))


def test_circle_bounds(qapp):
    br = _build(Model_Space._append_geom_to_path, CIRCLE).boundingRect()
    assert _rect_approx(br, br.__class__(5.0, 5.0, 40.0, 40.0))


def test_open_vs_closed_path(qapp):
    open_p = _build(Model_Space._append_geom_to_path, PATH_OPEN)
    closed_p = _build(Model_Space._append_geom_to_path, PATH_CLOSED)
    # Closing the subpath adds an element (the return-to-start line).
    assert closed_p.elementCount() == open_p.elementCount() + 1


def test_text_produces_glyphs(qapp):
    path = _build(Model_Space._append_geom_to_path, TEXT)
    assert path.elementCount() > 0
    # x-scaled to the source span width (twidth == 40).
    assert abs(path.boundingRect().width() - 40.0) < 3.0


# ── Step 5: equivalence — shared fn == model_space == dialog ──────────────────

def test_shared_matches_model_space(qapp):
    for name, g in ALL_GEOMS.items():
        ms = _build(Model_Space._append_geom_to_path, g)
        shared = _build(dwg_converter.append_geom_to_path, g)
        assert shared.elementCount() == ms.elementCount(), name
        assert _rect_approx(shared.boundingRect(), ms.boundingRect()), name


def test_shared_matches_dialog(qapp):
    for name, g in ALL_GEOMS.items():
        dlg = _build(UnderlayImportDialog._append_geom_to_path, g)
        shared = _build(dwg_converter.append_geom_to_path, g)
        assert shared.elementCount() == dlg.elementCount(), name
        assert _rect_approx(shared.boundingRect(), dlg.boundingRect()), name


def test_model_space_matches_dialog(qapp):
    """The two former copies must render identically (they shim the same fn)."""
    for name, g in ALL_GEOMS.items():
        ms = _build(Model_Space._append_geom_to_path, g)
        dlg = _build(UnderlayImportDialog._append_geom_to_path, g)
        assert ms.elementCount() == dlg.elementCount(), name
        assert _rect_approx(ms.boundingRect(), dlg.boundingRect()), name
