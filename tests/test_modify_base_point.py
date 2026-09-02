"""Modify preserves the saved base point across the async PDF re-load.

Opening an underlay in Modify mode restores the record's saved base point into
the base-X/base-Y fields. But the Modify prefill also kicks off an ASYNC PDF
vector re-load, and the load's finish handler auto-fills the base from the new
geometry's bounds unless gated. The prefill load must pass ``reset_base=False``
so the restored base survives to ``get_import_params()``.

These tests build a REAL 1-page fitz PDF whose geometry bounds differ from the
record's saved base, construct the REAL dialog in Modify mode, drive the async
PDF load to completion (pumping the event loop like ``test_pdf_worker_modify``),
then assert the base fields carry the RESTORED values — not the geometry bounds.
"""

from __future__ import annotations

import time

import fitz  # PyMuPDF

from firepro3d.underlay import Underlay


# ── Real 1-page PDF whose geometry bounds are well away from the saved base ──

def _make_pdf(path):
    """A 2-page PDF; page index 1 carries vectors spanning x∈[10,180],
    y∈[10,180] in PDF points.

    The geometry-bounds auto-fill would set base_x≈min(xs)=10 and
    base_y≈max(ys)=180 (in mm at import scale). The record below uses a very
    different base (1234, -567) so the two are trivially distinguishable.
    (Page 0 is a blank cover so the target page is a nonzero index — matching
    the ``page=1`` record and the sibling ``test_pdf_worker_modify`` fixture.)
    """
    doc = fitz.open()
    doc.new_page(width=200, height=200)          # page 0 — blank cover
    pg = doc.new_page(width=200, height=200)      # page 1 — target
    sh = pg.new_shape()
    sh.draw_line((10, 10), (180, 10))
    sh.draw_line((180, 10), (180, 180))
    sh.draw_line((180, 180), (10, 180))
    sh.finish(width=1.0, color=(0, 0, 0))
    sh.commit()
    doc.save(str(path))
    doc.close()


def _pump_until_pdf_done(dlg, qapp, timeout=5.0):
    """Pump the GUI loop until the dialog's PDF worker finishes (or times out)."""
    deadline = time.monotonic() + timeout
    while getattr(dlg, "_pdf_worker", None) is not None \
            and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()


def test_modify_pdf_preserves_saved_base_point(qapp, tmp_path):
    """Modify on a PDF record restores the saved base and the async re-load
    does NOT clobber it with the geometry-bounds auto-fill.

    RED-VERIFY: revert the ``reset_base=False`` in _apply_modify_prefill's
    _load_pdf_page call → the async finish handler auto-fills the base from the
    geometry bounds (≈10 / ≈180 mm) and these assertions fail.
    """
    from firepro3d.underlay_import_dialog import UnderlayImportDialog

    p = tmp_path / "two.pdf"
    _make_pdf(p)

    rec = Underlay(
        type="pdf", path=str(p), page=1, dpi=150, import_mode="vectors",
        import_scale=1.0,
        import_base_x=1234.0, import_base_y=-567.0,
        rotation=0.0, levels=["Level 1"],
    )
    dlg = UnderlayImportDialog(None, modify_record=rec)
    try:
        # Prefill kicked off the async load; drive it to completion.
        _pump_until_pdf_done(dlg, qapp)

        # Geometry actually loaded (so the auto-fill WOULD have fired if ungated).
        assert dlg._all_geoms, "no geometry loaded — test cannot discriminate"

        # The base fields carry the RESTORED record values, not the bounds.
        assert abs(dlg._base_x_edit.value_mm() - 1234.0) < 1e-6
        assert abs(dlg._base_y_edit.value_mm() - (-567.0)) < 1e-6

        # …and they flow through to the import params.
        params = dlg.get_import_params()
        assert abs(params.base_x - 1234.0) < 1e-6
        assert abs(params.base_y - (-567.0)) < 1e-6
    finally:
        dlg._modified = False
        dlg.close()
        dlg.deleteLater()
