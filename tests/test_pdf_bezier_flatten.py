"""Contract tests for PDF bézier flattening (task 73 — coarsen tolerance).

_flatten_bezier is a pure function (tuples in, list of (x, y) out); it does
NOT require PyMuPDF, so these tests run headless with no fitz dependency.
"""
import math

from firepro3d.pdf_import_worker import _flatten_bezier
from firepro3d import constants


# A representative curved cubic (a symmetric hump) in PDF-point space.
P0 = (0.0, 0.0)
P1 = (0.0, 100.0)
P2 = (100.0, 100.0)
P3 = (100.0, 0.0)


def _analytic_point(t):
    """Ground-truth point on the cubic Bézier at parameter t."""
    mt = 1.0 - t
    x = (mt**3 * P0[0] + 3 * mt**2 * t * P1[0]
         + 3 * mt * t**2 * P2[0] + t**3 * P3[0])
    y = (mt**3 * P0[1] + 3 * mt**2 * t * P1[1]
         + 3 * mt * t**2 * P2[1] + t**3 * P3[1])
    return (x, y)


def _point_to_segment_dist(p, a, b):
    """Shortest distance from point p to segment a→b."""
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq == 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / seg_len_sq
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def _max_deviation(polyline, samples=400):
    """Max distance from the analytic curve to the flattened polyline."""
    worst = 0.0
    for i in range(samples + 1):
        t = i / samples
        p = _analytic_point(t)
        d = min(_point_to_segment_dist(p, polyline[j], polyline[j + 1])
                for j in range(len(polyline) - 1))
        worst = max(worst, d)
    return worst


def test_default_constant_in_spinbox_range():
    """The shipped default tolerance sits within the Preferences spinbox range."""
    tol = constants.PDF_BEZIER_FLATTEN_TOL
    assert 0.25 <= tol <= 4.0, f"default tolerance {tol} outside range [0.25, 4.0]"


def test_current_flatten_tol_reads_setting(tmp_path, monkeypatch):
    """current_pdf_flatten_tol() reads the Preferences knob, else the default."""
    from PyQt6.QtCore import QSettings
    from firepro3d import pdf_import_worker

    ini = str(tmp_path / "prefs.ini")

    def _fake_qsettings(*_a, **_k):
        return QSettings(ini, QSettings.Format.IniFormat)

    monkeypatch.setattr(pdf_import_worker, "QSettings", _fake_qsettings)

    # Unset → falls back to the module default constant.
    assert (pdf_import_worker.current_pdf_flatten_tol()
            == pdf_import_worker.PDF_BEZIER_FLATTEN_TOL)

    # Set → reflects the stored value.
    w = QSettings(ini, QSettings.Format.IniFormat)
    w.setValue("import/pdf_bezier_flatten_tol", 3.25)
    w.sync()
    assert pdf_import_worker.current_pdf_flatten_tol() == 3.25


def test_coarser_tol_yields_fewer_points():
    """A coarser tolerance must produce a strictly smaller polyline."""
    fine = _flatten_bezier(P0, P1, P2, P3, tol=0.5)
    coarse = _flatten_bezier(P0, P1, P2, P3, tol=constants.PDF_BEZIER_FLATTEN_TOL)
    assert len(coarse) < len(fine)


def test_endpoints_exact_at_any_tolerance():
    """p0 and p3 are emitted exactly regardless of tolerance."""
    for tol in (0.5, 1.0, 2.0, 4.0):
        pts = _flatten_bezier(P0, P1, P2, P3, tol=tol)
        assert pts[0] == P0
        assert pts[-1] == P3


def test_deviation_within_tolerance():
    """Flattened polyline stays within ~tol of the analytic curve.

    The De Casteljau flatness heuristic keeps chord deviation on the order
    of `tol`; allow a modest 1.5x slack for the heuristic's conservatism.
    """
    for tol in (0.5, 1.0, 2.0, 4.0):
        pts = _flatten_bezier(P0, P1, P2, P3, tol=tol)
        dev = _max_deviation(pts)
        assert dev <= tol * 1.5, f"tol={tol}: deviation {dev:.3f} > {tol * 1.5:.3f}"


def test_finer_tolerance_reduces_deviation():
    """Refinement is monotone: a finer tolerance never deviates more."""
    dev_fine = _max_deviation(_flatten_bezier(P0, P1, P2, P3, tol=0.5))
    dev_coarse = _max_deviation(_flatten_bezier(P0, P1, P2, P3, tol=4.0))
    assert dev_fine <= dev_coarse
