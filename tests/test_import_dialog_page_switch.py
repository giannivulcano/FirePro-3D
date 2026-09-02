"""A PDF page switch loads new geometry but must PRESERVE the user's settings:
non-geometry (scale, base point, levels, DPI, import mode) AND — matched to the
new page — the layer selection (by name) and crop (by bounds). Layers absent on
the new page just aren't re-checked; the crop re-selects whatever falls in it.
"""
from __future__ import annotations

import os
import time

import firepro3d.pdf_import_worker as piw


def _pump_until_pdf_done(dlg, qapp, timeout=5.0):
    """Pump the GUI loop until the dialog's async PDF worker finishes.

    PDF vector extraction runs on a worker thread now, so a page switch's new
    geometry + layer list only appear after the worker delivers and the finish
    handler runs. Drive that to completion before asserting.
    """
    deadline = time.monotonic() + timeout
    while getattr(dlg, "_pdf_worker", None) is not None \
            and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    qapp.processEvents()


def _make_pdf_dialog(qapp, tmp_path, monkeypatch):
    """A dialog wired into a PDF state with a stubbed vector extractor so a
    page switch runs without a real PDF on disk."""
    from firepro3d.underlay_import_dialog import UnderlayImportDialog

    # Geoms on two layers so a layer subset is meaningful; the horizontal
    # "A" line sits near the origin, the "B" lines further out — enough to
    # build a preview and to exercise crop-by-bounds re-selection.
    geoms = [
        {"kind": "line", "x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 0.0,
         "layer": "A"},
        {"kind": "line", "x1": 0.0, "y1": 0.0, "x2": 0.0, "y2": 100.0,
         "layer": "A"},
        {"kind": "line", "x1": 500.0, "y1": 500.0, "x2": 600.0, "y2": 500.0,
         "layer": "B"},
    ]
    monkeypatch.setattr(
        piw, "extract_pdf_vectors_sync",
        lambda path, page: (geoms, ["A", "B"]))
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

    scale_before = dlg._current_scale()
    base_before = (dlg._base_x_edit.value_mm(), dlg._base_y_edit.value_mm())
    levels_before = dlg._levels_picker.selected()
    dpi_before = dlg._dpi_combo.currentText()
    mode_before = dlg._mode_combo.currentText()

    # ── User switches to page index 1 via the thumbnail strip ───────────────
    dlg._on_page_thumb_clicked(1)
    _pump_until_pdf_done(dlg, qapp)

    # New geometry loaded, layer list refreshed to the new page's layers.
    assert dlg._pdf_page == 1
    assert dlg._layer_list.count() == 2                  # A + B
    assert dlg._all_geoms                                # new geometry loaded

    # Non-geometry settings PRESERVED.
    assert abs(dlg._current_scale() - scale_before) < 1e-9
    assert (dlg._base_x_edit.value_mm(), dlg._base_y_edit.value_mm()) \
        == base_before
    assert dlg._levels_picker.selected() == levels_before
    assert dlg._dpi_combo.currentText() == dpi_before
    assert dlg._mode_combo.currentText() == mode_before

    dlg.deleteLater()


def test_page_switch_preserves_layers_and_crop(qapp, tmp_path, monkeypatch):
    """The layer subset (by name) and crop (by bounds) survive a page switch,
    re-matched to the new page's geometry."""
    dlg = _make_pdf_dialog(qapp, tmp_path, monkeypatch)
    dlg._mode_combo.setCurrentText("Vectors")

    # Load page 0 so the layer list is populated (indices 0=A,1=B).
    dlg._on_page_thumb_clicked(0)
    _pump_until_pdf_done(dlg, qapp)
    assert dlg._layer_list.count() == 2

    # User deselects layer "B" → only "A" active.
    from PyQt6.QtCore import Qt
    for i in range(dlg._layer_list.count()):
        it = dlg._layer_list.item(i)
        if it.text() == "B":
            it.setCheckState(Qt.CheckState.Unchecked)
    dlg._on_layer_changed()
    assert dlg._active_layers() == {"A"}

    # User crops to the near-origin horizontal "A" line (geom index 0).
    dlg._selected_indices = {0}
    dlg._rebuild_preview()
    crop_bounds = dlg._current_crop_bounds()
    assert crop_bounds is not None

    # ── Switch to page 1 (same stubbed geometry) ───────────────────────────
    dlg._on_page_thumb_clicked(1)
    _pump_until_pdf_done(dlg, qapp)

    # Layer selection re-applied by NAME (B still deselected).
    assert dlg._active_layers() == {"A"}
    # Crop re-applied by BOUNDS: geom 0 falls inside its own bbox; the far "B"
    # line does not.
    assert dlg._selected_indices is not None
    assert 0 in dlg._selected_indices
    assert 2 not in dlg._selected_indices

    dlg.deleteLater()
