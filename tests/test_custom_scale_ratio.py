"""Two-field ``[paper] = [real]`` custom-scale input for PDF underlays.

The raw mm-per-point "Custom" factor field is replaced (PDF only) by a
human-readable two-field ratio: imperial ``[N] in = [N] ft``; metric
``1 : [N]``. The derived ``import_scale`` factor must match the shipped
architectural presets, and DXF Custom must keep its raw-factor field.
"""
import math

import pytest

from firepro3d.scale_manager import ScaleManager, DisplayUnit
from firepro3d.underlay_import_dialog import (
    UnderlayImportDialog, pdf_scale_from_ratio, _ARCH_SCALES,
)


def _arch_factor(label: str) -> float:
    return {lbl: sc for lbl, sc in _ARCH_SCALES}[label]


def _select_custom(dlg):
    """Select the "Custom…" combo entry (currentData() is None)."""
    ci = next(i for i in range(dlg._scale_combo.count())
              if dlg._scale_combo.itemData(i) is None
              and dlg._scale_combo.itemText(i).startswith("Custom"))
    dlg._scale_combo.setCurrentIndex(ci)


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


# 1. Math contract (pure) — pins the derivation before any UI.
def test_imperial_two_field_matches_shipped_arch_preset():
    # 3/8" = 1'-0"  ->  paper_in=0.375, real_ft=1.0
    factor = pdf_scale_from_ratio(0.375 * 25.4, 1.0 * 304.8)
    assert math.isclose(factor, _arch_factor('3/8" = 1\'-0"'), rel_tol=1e-6)


# 2. Real dialog, PDF Custom, imperial.
def test_pdf_custom_imperial_reproduces_preset(qapp):
    dlg = _pdf_dialog(_imperial_sm())
    _select_custom(dlg)
    dlg._paper_edit.setText("3/8")
    dlg._real_edit.setText("1")
    got = dlg.get_import_params().scale
    assert math.isclose(got, _arch_factor('3/8" = 1\'-0"'), rel_tol=1e-6)
    # Raw factor field hidden; two-field ratio visible.
    assert dlg._custom_scale_edit.isHidden()
    assert not dlg._paper_edit.isHidden()
    assert not dlg._real_edit.isHidden()


# 3. Real dialog, PDF Custom, metric.
def test_pdf_custom_metric_one_to_n(qapp):
    dlg = _pdf_dialog(_metric_sm())
    _select_custom(dlg)
    dlg._real_edit.setText("100")
    got = dlg._current_scale()
    assert math.isclose(got, pdf_scale_from_ratio(1.0, 100.0), rel_tol=1e-6)


# 4. DXF Custom unchanged — the two-field ratio must not hijack DXF.
def test_dxf_custom_uses_raw_factor(qapp):
    sm = _imperial_sm()
    dlg = UnderlayImportDialog(None, scale_manager=sm)
    dlg._file_type = "dxf"
    dlg._populate_scale_combo(is_pdf=False)
    _select_custom(dlg)
    assert not dlg._custom_scale_edit.isHidden()
    assert dlg._paper_edit.isHidden()
    assert dlg._real_edit.isHidden()
    dlg._custom_scale_edit.setText("2.5")
    assert math.isclose(dlg._current_scale(), 2.5, rel_tol=1e-9)


# 5. Calibrate fills the two fields (PDF).
def test_calibrate_back_solve_roundtrips_imperial(qapp):
    dlg = _pdf_dialog(_imperial_sm())
    _select_custom(dlg)
    known = _arch_factor('1/4" = 1\'-0"')
    dlg._set_ratio_fields_from_factor(known)
    assert math.isclose(dlg._custom_ratio_factor(), known, rel_tol=1e-6)


def test_calibrate_back_solve_roundtrips_metric(qapp):
    dlg = _pdf_dialog(_metric_sm())
    _select_custom(dlg)
    known = pdf_scale_from_ratio(1.0, 250.0)
    dlg._set_ratio_fields_from_factor(known)
    assert math.isclose(dlg._custom_ratio_factor(), known, rel_tol=1e-6)
