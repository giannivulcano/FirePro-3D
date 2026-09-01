"""A PDF page switch changes the geometry (layers + crop legitimately reset)
but must PRESERVE the user's non-geometry settings: scale (combo/custom), base
point, levels, DPI, and import mode (Bug 3).
"""
from __future__ import annotations

import os

import firepro3d.pdf_import_worker as piw


def _make_pdf_dialog(qapp, tmp_path, monkeypatch):
    """A dialog wired into a PDF state with a stubbed vector extractor so a
    page switch runs without a real PDF on disk."""
    from firepro3d.underlay_import_dialog import UnderlayImportDialog

    # Two simple line geoms on a single layer — enough to build a preview.
    geoms = [
        {"kind": "line", "x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 0.0,
         "layer": "A"},
        {"kind": "line", "x1": 0.0, "y1": 0.0, "x2": 0.0, "y2": 100.0,
         "layer": "A"},
    ]
    monkeypatch.setattr(
        piw, "extract_pdf_vectors_sync",
        lambda path, page: (geoms, ["A"]))
    # underlay_import_dialog imports the symbol lazily inside _load_pdf_page via
    # `from .pdf_import_worker import extract_pdf_vectors_sync`, so patching the
    # module attribute above is what the lazy import resolves.

    # A real (empty) file so os.path.exists() passes in _on_page_thumb_clicked.
    fake = tmp_path / "plan.pdf"
    fake.write_bytes(b"%PDF-1.4\n")

    dlg = UnderlayImportDialog(None, levels=["Level 1", "Level 2", "Roof"],
                               current_level="Level 1")
    dlg._file_type = "pdf"
    dlg._file_edit.setText(str(fake))
    dlg._mode_combo.setCurrentText("Vectors")   # deterministic: no raster path
    return dlg


def test_page_switch_preserves_settings_resets_geometry(qapp, tmp_path,
                                                        monkeypatch):
    dlg = _make_pdf_dialog(qapp, tmp_path, monkeypatch)

    # ── Set known non-geometry settings the user would have chosen ──────────
    custom_idx = len(dlg._SCALE_OPTIONS) - 1        # the "Custom…" option
    dlg._scale_combo.setCurrentIndex(custom_idx)
    dlg._custom_scale_edit.setText("0.352778")      # arbitrary custom factor
    dlg._base_x_edit.set_value_mm(1234.0)
    dlg._base_y_edit.set_value_mm(5678.0)
    dlg._levels_picker.set_selected(["Level 2", "Roof"])
    dlg._dpi_combo.setCurrentText("300")
    dlg._mode_combo.setCurrentText("Vectors")

    # Simulate stale crop state from the previous page.
    dlg._selected_indices = {0}

    scale_before = dlg._current_scale()
    base_before = (dlg._base_x_edit.value_mm(), dlg._base_y_edit.value_mm())
    levels_before = dlg._levels_picker.selected()
    dpi_before = dlg._dpi_combo.currentText()
    mode_before = dlg._mode_combo.currentText()

    # ── User switches to page index 1 via the thumbnail strip ───────────────
    dlg._on_page_thumb_clicked(1)

    # Geometry-derived state legitimately refreshed / reset.
    assert dlg._pdf_page == 1
    assert dlg._selected_indices is None                 # crop cleared
    assert dlg._layer_list.count() == 1                  # layer list refreshed
    assert dlg._all_geoms                                # new geometry loaded

    # Non-geometry settings PRESERVED.
    assert abs(dlg._current_scale() - scale_before) < 1e-9
    assert (dlg._base_x_edit.value_mm(), dlg._base_y_edit.value_mm()) \
        == base_before
    assert dlg._levels_picker.selected() == levels_before
    assert dlg._dpi_combo.currentText() == dpi_before
    assert dlg._mode_combo.currentText() == mode_before

    dlg.deleteLater()
