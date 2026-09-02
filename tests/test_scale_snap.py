"""Calibrated scale snaps to the nearest standard plot scale.

When the user calibrates a PDF underlay (pick two points + enter a real
distance), the derived mm-per-point factor is snapped to a nearby standard
scale — an architectural/engineering NAMED preset, or (metric) a standard
``1:N`` ratio — within ``_SCALE_SNAP_TOL`` (2%). Off-standard measurements
keep the raw factor under "Custom".
"""
import math

import pytest

from firepro3d.scale_manager import ScaleManager, DisplayUnit
from firepro3d.underlay_import_dialog import (
    UnderlayImportDialog, pdf_scale_from_ratio, _arch,
    _ARCH_SCALES, _ENG_SCALES, _MM_PER_POINT, _SCALE_SNAP_TOL,
)


def _arch_factor(label: str) -> float:
    return {lbl: sc for lbl, sc in _ARCH_SCALES + _ENG_SCALES}[label]


def _pdf_dialog(sm):
    """A real dialog primed as a PDF import with unit system *sm*."""
    dlg = UnderlayImportDialog(None, scale_manager=sm)
    dlg._file_type = "pdf"
    dlg._populate_scale_combo(is_pdf=True)
    return dlg


def _imperial_sm():
    sm = ScaleManager()
    sm.display_unit = DisplayUnit.IMPERIAL
    return sm


def _metric_sm():
    sm = ScaleManager()
    sm.display_unit = DisplayUnit.METRIC_MM
    return sm


# ── New arch presets present ────────────────────────────────────────────────
def test_new_arch_presets_present():
    labels = {lbl for lbl, _ in _ARCH_SCALES}
    for lbl, paper_in in (('1/32" = 1\'-0"', 0.03125),
                          ('1/16" = 1\'-0"', 0.0625),
                          ('3/32" = 1\'-0"', 0.09375)):
        assert lbl in labels
        got = {l: sc for l, sc in _ARCH_SCALES}[lbl]
        assert math.isclose(got, _arch(lbl, paper_in, 1.0)[1], rel_tol=1e-9)


# ── Imperial arch snap (real handler) ───────────────────────────────────────
def test_imperial_arch_snap_selects_preset(qapp):
    dlg = _pdf_dialog(_imperial_sm())
    preset = _arch_factor('1/16" = 1\'-0"')
    factor = preset * 1.005                      # 0.5% off — inside 2%
    # px_dist=100 preview units; parsed_mm chosen to reproduce that factor.
    px_dist = 100.0
    parsed_mm = factor * px_dist
    dlg._apply_calibration(px_dist, parsed_mm)
    assert dlg._scale_combo.currentText() == '1/16" = 1\'-0"'
    assert dlg._scale_combo.currentData() is not None      # NOT "Custom"
    assert dlg._scale_verified is True


def test_imperial_arch_snap_helper_index(qapp):
    dlg = _pdf_dialog(_imperial_sm())
    preset = _arch_factor('1/16" = 1\'-0"')
    idx = dlg._nearest_named_scale_preset(preset * 1.005)
    assert idx is not None
    assert dlg._scale_combo.itemText(idx) == '1/16" = 1\'-0"'


# ── No false snap ───────────────────────────────────────────────────────────
def test_no_false_snap_stays_custom(qapp):
    dlg = _pdf_dialog(_imperial_sm())
    preset = _arch_factor('1/16" = 1\'-0"')
    factor = preset * 1.10                        # 10% off — no preset within 2%
    assert dlg._nearest_named_scale_preset(factor) is None
    px_dist = 100.0
    dlg._apply_calibration(px_dist, factor * px_dist)
    assert dlg._scale_combo.currentData() is None            # "Custom"


# ── Metric 1:N snap ─────────────────────────────────────────────────────────
def test_metric_snap_ratio_near_ten(qapp):
    dlg = _pdf_dialog(_metric_sm())
    # A drawing ratio of ~1:10.15 (1.5% off) -> should snap to clean 1:10.
    factor = pdf_scale_from_ratio(1.0, 10.15)
    clean = dlg._snap_metric_ratio_factor(factor)
    assert clean is not None
    M = round(clean * 72.0 / 25.4)
    assert M == 10
    assert math.isclose(clean, pdf_scale_from_ratio(1.0, 10.0), rel_tol=1e-9)


def test_metric_no_snap_when_far(qapp):
    dlg = _pdf_dialog(_metric_sm())
    # 1:37 is >2% from every standard denominator (25, 50 are nearest).
    factor = pdf_scale_from_ratio(1.0, 37.0)
    assert dlg._snap_metric_ratio_factor(factor) is None


def test_metric_snap_drives_custom_ratio(qapp):
    dlg = _pdf_dialog(_metric_sm())
    factor = pdf_scale_from_ratio(1.0, 10.15)     # ~1:10.15 (1.5% off)
    px_dist = 100.0
    dlg._apply_calibration(px_dist, factor * px_dist)
    # Snapped to 1:10 under Custom (metric two-field ratio).
    assert dlg._scale_combo.currentData() is None
    assert math.isclose(
        dlg._current_scale(), pdf_scale_from_ratio(1.0, 10.0), rel_tol=1e-6)
    assert dlg._scale_verified is True


# ── Tolerance boundary sanity ───────────────────────────────────────────────
def test_snap_tolerance_is_two_percent():
    assert _SCALE_SNAP_TOL == pytest.approx(0.02)
