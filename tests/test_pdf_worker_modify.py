"""PDF extraction runs on a worker thread; Modify pending-state invariant holds.

The import dialog's PDF vector extraction moved off the GUI thread (mirroring
the DXF ``_DialogExtractWorker`` path) so its progress + Cancel drive the same
staged loading overlay. Because geometry is no longer final when
``_apply_modify_prefill`` returns, the saved layer subset + crop must be
consumed in the async PDF finish handler — NOT cleared at the end of prefill.

These tests build a REAL 2-page fitz PDF (pages distinguished by geometry
Y-extent, like ``test_underlay_page_persist``) and drive the REAL dialog's
async PDF load to completion by pumping the event loop.
"""

from __future__ import annotations

import time

import fitz  # PyMuPDF

from firepro3d.underlay import Underlay


# ── Real 2-page PDF (pages distinguished by geometry Y-extent) ─────────────

def _make_2page_pdf(path):
    """Page 0 draws only near the TOP (y~10); page 1 only near the BOTTOM."""
    doc = fitz.open()
    p0 = doc.new_page(width=200, height=200)
    sh0 = p0.new_shape()
    sh0.draw_line((10, 10), (180, 10))
    sh0.finish(width=1.0, color=(0, 0, 0))
    sh0.commit()
    p1 = doc.new_page(width=200, height=200)
    sh1 = p1.new_shape()
    for y in (100, 140, 180):
        sh1.draw_line((10, y), (180, y))
    sh1.finish(width=1.0, color=(0, 0, 0))
    sh1.commit()
    # Text on page 1 gives it a second layer ("PDF Text") so a layer SUBSET
    # (vectors only) is a proper subset, not the whole set.
    p1.insert_text((20, 160), "HELLO", fontsize=8)
    doc.save(str(path))
    doc.close()


def _max_y(geoms):
    ys = []
    for g in geoms:
        if g.get("kind") == "line":
            ys += [g["y1"], g["y2"]]
        elif g.get("kind") == "path_points":
            ys += [p[1] for p in g.get("points", [])]
    return max(ys) if ys else 0.0


def _pump_until_pdf_done(dlg, qapp, timeout=5.0):
    """Pump the GUI loop until the dialog's PDF worker finishes (or times out)."""
    deadline = time.monotonic() + timeout
    while getattr(dlg, "_pdf_worker", None) is not None \
            and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()


# ── (a) Invariant / round-trip on a REAL async PDF Modify load ─────────────

def test_modify_pdf_async_restores_layers_crop_and_clears_pending(
        qapp, tmp_path):
    """Open Modify on a real 2-page PDF whose record carries page=1 + a saved
    layer subset + import_bounds. Drive the async PDF load to completion, then
    assert: page 1 loaded (Y-extent), pending layers applied, crop restored,
    and BOTH pending fields cleared.

    RED-VERIFY: leaving the old ``if self._file_type == "pdf": clear`` gate in
    _apply_modify_prefill clears pending BEFORE the worker finishes, so the
    layers-applied assertion fails.
    """
    from firepro3d.underlay_import_dialog import UnderlayImportDialog

    p = tmp_path / "two.pdf"
    _make_2page_pdf(p)

    rec = Underlay(
        type="pdf", path=str(p), page=1, dpi=150, import_mode="vectors",
        import_scale=2.0,
        selected_layers=["PDF Vectors"],
        import_bounds=[0.0, 90.0, 200.0, 200.0],   # page-1 band only
        rotation=0.0, levels=["Level 1"],
    )
    dlg = UnderlayImportDialog(None, modify_record=rec)
    try:
        # Prefill kicked off the async load; drive it to completion.
        _pump_until_pdf_done(dlg, qapp)

        # Correct page loaded (page 1 = bottom band).
        assert _max_y(dlg._all_geoms) > 90

        # Pending layer subset was applied and crop restored.
        assert dlg._active_layers() == {"PDF Vectors"}
        assert dlg._selected_indices is not None

        # Invariant: both pending fields cleared once geometry is final.
        assert dlg._pending_modify_layers is None
        assert dlg._pending_modify_bounds is None
    finally:
        dlg._modified = False
        dlg.close()
        dlg.deleteLater()


# ── (b) Error path — dialog returns to un-imported, controls re-enabled ────

def test_pdf_extract_error_returns_to_unimported_state(qapp, tmp_path):
    """A PDF vector load that raises marks the overlay stage failed and leaves
    the dialog un-imported (no partial geoms, controls re-enabled)."""
    from firepro3d.underlay_import_dialog import UnderlayImportDialog

    p = tmp_path / "one.pdf"
    _make_2page_pdf(p)

    dlg = UnderlayImportDialog()
    try:
        dlg._file_edit.setText(str(p))
        dlg._file_type = "pdf"
        dlg._all_geoms = []
        # Drive the worker path directly, then force the error handler.
        dlg._on_pdf_extract_error("boom")

        assert dlg._all_geoms == []
        assert getattr(dlg, "_pdf_worker", None) is None
        # Controls re-enabled (overlay finished).
        assert not dlg._loading_overlay.is_active()
        assert "boom" in dlg._info_lbl.text() or "Error" in dlg._info_lbl.text()
    finally:
        dlg._modified = False
        dlg.close()
        dlg.deleteLater()


# ── (c) Overlay drives PDF stages (≥1 completed stage row) ─────────────────

def test_pdf_load_drives_loading_overlay(qapp, tmp_path):
    """A real PDF vector load shows the LoadingOverlay and leaves at least one
    completed stage row behind (mirrors the DXF Step-E test)."""
    from firepro3d.underlay_import_dialog import UnderlayImportDialog

    p = tmp_path / "one.pdf"
    _make_2page_pdf(p)

    dlg = UnderlayImportDialog()
    try:
        overlay = dlg._loading_overlay
        dlg._file_edit.setText(str(p))
        dlg._load_pdf(str(p))          # renders page 0 async
        _pump_until_pdf_done(dlg, qapp)

        assert overlay._rows, "overlay recorded no stage rows"
        assert any(r.state == "done" for r in overlay._rows), \
            "overlay recorded no completed stage"
    finally:
        dlg._modified = False
        dlg.close()
        dlg.deleteLater()
