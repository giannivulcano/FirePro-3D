"""Slice 8 guards — a closed DXF SPLINE imports as a periodic spline (DD7).

Real path: an ezdxf document saved to disk and read back, the import worker's
sync extraction (preserve_curves, the Block Editor import contract), then
BlockEditorWidget._add_imported_geoms (geometry_import) — and the underlay /
import-preview path (dwg_converter.append_geom_to_path).
"""
from __future__ import annotations

import math

import ezdxf
from ezdxf.math import Vec3, closed_uniform_bspline
from PyQt6.QtGui import QPainterPath

from firepro3d.dxf_import_worker import DxfImportWorker
from firepro3d.geometry_2d import SplineItem

SQUARE = [(0, 0), (100, 0), (100, 100), (0, 100)]          # DXF Y-up


def _worker():
    w = DxfImportWorker.__new__(DxfImportWorker)           # sync path
    w._layer_colors = {}
    w._preserve_curves = True
    return w


def _read_back(tmp_path, build):
    doc = ezdxf.new()
    build(doc.modelspace())
    fp = tmp_path / "spline.dxf"
    doc.saveas(fp)
    ents = [e for e in ezdxf.readfile(fp).modelspace() if e.dxftype() == "SPLINE"]
    assert len(ents) == 1
    return _worker()._extract_geometry(ents[0])


def _closed_periodic(msp):
    sp = msp.add_spline()
    sp.apply_construction_tool(closed_uniform_bspline(
        [Vec3(x, y) for x, y in SQUARE], order=4))
    sp.closed = True


def _import(geoms):
    from firepro3d.block_editor import BlockEditorWidget
    from firepro3d.model_space import Model_Space
    w = BlockEditorWidget(Model_Space())
    added, skipped = w._add_imported_geoms(geoms, 1.0)
    assert (added, skipped) == (1, 0)
    prims = w.gather_primitives()
    assert len(prims) == 1 and isinstance(prims[0], SplineItem)
    return prims[0]


def _hull_ok(path, pad=1e-3):
    br = path.boundingRect()           # scene Y-down: the square is y in [-100, 0]
    return (br.left() >= -pad and br.right() <= 100 + pad
            and br.top() >= -100 - pad and br.bottom() <= pad)


def test_fixture_is_a_wrapped_uniform_closed_spline(tmp_path):
    g = _read_back(tmp_path, _closed_periodic)
    assert g["kind"] == "spline" and g["closed"] is True
    cps = g["control_points"]
    assert len(cps) == 7 and cps[-3:] == cps[:3]            # wrapped
    assert g["knots"] == [float(i) for i in range(11)]       # uniform, n + 4


def test_closed_dxf_spline_imports_periodic(qapp, tmp_path):
    s = _import([_read_back(tmp_path, _closed_periodic)])
    assert s.is_periodic()                                               # [RED]
    assert [(p.x(), p.y()) for p in s.grip_points()] == [(0, 0), (100, 0),
                                                         (100, -100), (0, -100)]
    p0, p1 = s.path().pointAtPercent(0.0), s.path().pointAtPercent(1.0)
    assert math.hypot(p1.x() - p0.x(), p1.y() - p0.y()) < 1e-6
    assert _hull_ok(s.path())                     # no garbage tail


def test_open_dxf_spline_keeps_the_verbatim_path(qapp, tmp_path):
    def _open(msp):
        # add_open_spline writes a clamped knot vector (a bare add_spline with
        # assigned control points round-trips with knots=None — P4 probe)
        msp.add_open_spline([(0, 0), (10, 20), (30, -20), (40, 0)], degree=3)
    g = _read_back(tmp_path, _open)
    assert g["knots"] == [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0]
    s = _import([g])
    assert not s.is_periodic()
    assert s._knots == g["knots"] and len(s.grip_points()) == 4


def test_closed_flag_without_wrapped_cps_keeps_the_verbatim_path(qapp, tmp_path):
    """A closed-flagged clamped spline (coincident ends, not wrapped) is not
    the DD7 form: today's path, all control points kept."""
    def _clamped_closed(msp):
        sp = msp.add_open_spline([(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)],
                                 degree=3)
        sp.closed = True
    g = _read_back(tmp_path, _clamped_closed)
    assert g["closed"] is True and len(g["control_points"]) == 5
    s = _import([g])
    assert not s.is_periodic() and len(s.grip_points()) == 5
    assert s.is_closed()                          # legacy coincident-end rule


def test_import_preview_path_draws_the_periodic_curve(tmp_path):
    from firepro3d.dwg_converter import append_geom_to_path
    g = _read_back(tmp_path, _closed_periodic)
    path = QPainterPath()
    append_geom_to_path(path, g)
    p0, p1 = path.pointAtPercent(0.0), path.pointAtPercent(1.0)
    assert math.hypot(p1.x() - p0.x(), p1.y() - p0.y()) < 1e-6          # [RED]
    assert _hull_ok(path)                                                # [RED]
