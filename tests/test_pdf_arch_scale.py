"""Item 7 (PDF): architectural/engineering scale ratios compute the correct
import_scale (PDF points -> scene mm), matching the calibration ground truth
scale = real_mm / source_points."""
from firepro3d.dxf_preview_dialog import (
    pdf_scale_from_ratio, _ARCH_SCALES, _ENG_SCALES, _MM_PER_POINT,
)


def test_ratio_1to1_is_point_to_mm():
    # paper 1mm == real 1mm -> a point is just converted to mm.
    assert abs(pdf_scale_from_ratio(1.0, 1.0) - _MM_PER_POINT) < 1e-9


def test_ratio_three_eighths_equals_one_foot():
    # 3/8" = 1'-0"  -> M = 12 / (3/8) = 32 -> scale = 32 * 25.4/72 = 11.288...
    s = pdf_scale_from_ratio(0.375 * 25.4, 304.8)
    assert abs(s - 32 * _MM_PER_POINT) < 1e-6
    assert abs(s - 11.2889) < 1e-3


def test_ratio_places_known_run_at_real_size():
    # A 3/8" line on paper (27 pt) must land at 1 ft = 304.8 mm.
    s = pdf_scale_from_ratio(0.375 * 25.4, 304.8)
    points = 0.375 * 72          # 3/8" in PDF points
    assert abs(points * s - 304.8) < 0.01


def test_arch_preset_quarter_inch():
    label, scale = dict_by_label(_ARCH_SCALES)['1/4" = 1\'-0"']
    assert abs(scale - 48 * _MM_PER_POINT) < 1e-6   # M = 12/(1/4) = 48


def test_eng_preset_1in_20ft():
    label, scale = dict_by_label(_ENG_SCALES)['1" = 20\'']
    assert abs(scale - 240 * _MM_PER_POINT) < 1e-6  # M = 20*12 = 240


def dict_by_label(pairs):
    return {lbl: (lbl, sc) for lbl, sc in pairs}


def _blank_pdf(path):
    import fitz
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    doc.save(str(path))
    doc.close()


def test_pdf_load_offers_arch_scales_and_resolves(qapp, tmp_path):
    from firepro3d.dxf_preview_dialog import UnderlayImportDialog
    p = tmp_path / "blank.pdf"
    _blank_pdf(p)
    dlg = UnderlayImportDialog(None)
    dlg._load_pdf(str(p))
    labels = [dlg._scale_combo.itemText(i)
              for i in range(dlg._scale_combo.count())]
    assert '3/8" = 1\'-0"' in labels
    assert '1" = 20\'' in labels
    idx = labels.index('3/8" = 1\'-0"')
    dlg._scale_combo.setCurrentIndex(idx)
    assert abs(dlg._current_scale() - 11.2889) < 1e-2


def test_dxf_style_combo_has_no_arch_scales(qapp):
    from firepro3d.dxf_preview_dialog import UnderlayImportDialog
    dlg = UnderlayImportDialog(None)
    dlg._populate_scale_combo(is_pdf=False)
    labels = [dlg._scale_combo.itemText(i)
              for i in range(dlg._scale_combo.count())]
    assert not any("1'-0\"" in l or l.startswith('1" = ') for l in labels)
