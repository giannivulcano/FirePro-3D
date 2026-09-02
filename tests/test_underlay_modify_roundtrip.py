"""Modify flow must be a LOSSLESS ROUND-TRIP.

Underlay Manager → select a placed underlay → Modify opens the import dialog
pre-filled from the saved record; Save must reproduce the SAME placement inputs
(scale, layer subset, crop, PDF page). These tests isolate the widget
round-trip: loaders are stubbed / geometry is injected directly so the geom
pipeline (covered elsewhere) does not run.
"""
import os

import pytest

from firepro3d.underlay import Underlay


def _full_pdf_record():
    return Underlay(
        type="pdf",
        path="/nonexistent/plan.pdf",
        page=2,
        dpi=300,
        import_mode="vectors",
        import_scale=3.2809,
        import_base_x=123.0,
        import_base_y=456.0,
        selected_layers=["A"],
        rotation=30.0,
        levels=["Level 1"],
        scale_verified=True,
    )


def _make_dialog(qapp, record):
    """Build the dialog with a modify_record. The record path is non-existent
    so _load_file() bails immediately — no loader thread, no geom pipeline."""
    from firepro3d.underlay_import_dialog import UnderlayImportDialog
    return UnderlayImportDialog(None, modify_record=record)


# ─────────────────────────────────────────────────────────────────────────────
# 1. SCALE
# ─────────────────────────────────────────────────────────────────────────────

def test_modify_prefill_scale_roundtrips(qapp):
    rec = Underlay(type="pdf", path="/nonexistent/x.pdf",
                   import_scale=3.2809, scale_verified=True)
    dlg = _make_dialog(qapp, rec)
    try:
        # Custom-scale edit must be routed through the VISIBLE path so the
        # commit-sentence echo and every visibility-gated read agree. Headless,
        # the dialog's top level is never shown and the scale field sits on an
        # inactive step page, so isVisible() is False for reasons unrelated to
        # the fix; isVisibleTo(parent) / not-hidden is the falsifiable proof
        # that _on_scale_combo_changed ran and un-hid the field (RED before the
        # fix: the edit stayed setVisible(False)).
        edit = dlg._custom_scale_edit
        assert not edit.isHidden()
        assert edit.isVisibleTo(edit.parentWidget())
        assert abs(dlg.get_import_params().scale - 3.2809) < 1e-4
        # A verified scale stays verified through the restore.
        assert dlg.get_import_params().scale_verified is True
    finally:
        dlg.deleteLater()


# ─────────────────────────────────────────────────────────────────────────────
# 2. LAYER SELECTION
# ─────────────────────────────────────────────────────────────────────────────

def test_modify_prefill_restores_layer_selection(qapp):
    rec = Underlay(type="pdf", path="/nonexistent/x.pdf")
    dlg = _make_dialog(qapp, rec)
    try:
        dlg._all_geoms = [{"kind": "line", "layer": "A", "x1": 0, "y1": 0,
                           "x2": 1, "y2": 1},
                          {"kind": "line", "layer": "B", "x1": 0, "y1": 0,
                           "x2": 1, "y2": 1}]
        dlg._layers = ["A", "B"]
        dlg._populate_layer_list()
        dlg._apply_selected_layers(["A"])
        assert dlg._active_layers() == {"A"}
    finally:
        dlg.deleteLater()


# ─────────────────────────────────────────────────────────────────────────────
# 3. CROP
# ─────────────────────────────────────────────────────────────────────────────

def test_modify_prefill_restores_crop_from_bounds(qapp):
    rec = Underlay(type="pdf", path="/nonexistent/x.pdf")
    dlg = _make_dialog(qapp, rec)
    try:
        # Two geoms inside [0,0,10,10]; one far outside.
        dlg._all_geoms = [
            {"kind": "line", "layer": "A", "x1": 1, "y1": 1, "x2": 2, "y2": 2},
            {"kind": "line", "layer": "A", "x1": 3, "y1": 3, "x2": 4, "y2": 4},
            {"kind": "line", "layer": "A", "x1": 900, "y1": 900,
             "x2": 901, "y2": 901},
        ]
        dlg._restore_crop_from_bounds([0.0, 0.0, 10.0, 10.0])
        assert dlg._selected_indices == {0, 1}
    finally:
        dlg.deleteLater()


# ─────────────────────────────────────────────────────────────────────────────
# 3b. ASYNC (DXF/DWG) extract-finished path applies pending layers + crop
# ─────────────────────────────────────────────────────────────────────────────

def test_modify_async_extract_finished_restores_layers_and_crop(qapp):
    """The DXF/DWG async path populates the layer list only after extraction
    finishes, so the prefill defers the layer subset + crop as pending fields.
    _on_extract_finished must consume them. Drives that site directly (a
    non-existent path makes _load_file bail, so no real thread runs)."""
    rec = Underlay(type="dxf", path="/nonexistent/x.dxf", import_scale=2.0,
                   selected_layers=["AAA"], import_bounds=[-1, -1, 50, 50],
                   rotation=0.0)
    dlg = _make_dialog(qapp, rec)
    try:
        # Prefill leaves both restores pending (no geometry yet).
        assert dlg._pending_modify_layers == ["AAA"]
        assert dlg._pending_modify_bounds == [-1, -1, 50, 50]

        dlg._extract_worker = object()   # bypass the "dialog closed" discard guard
        dlg._selected_layout = "Model"
        geoms = [
            {"kind": "line", "layer": "AAA", "x1": 0, "y1": 0, "x2": 10, "y2": 10},
            {"kind": "line", "layer": "AAA", "x1": 5, "y1": 5, "x2": 6, "y2": 6},
            {"kind": "line", "layer": "BBB", "x1": 900, "y1": 900,
             "x2": 910, "y2": 910},
        ]
        dlg._on_extract_finished(geoms, ["AAA", "BBB"])

        assert dlg._active_layers() == {"AAA"}
        assert dlg._selected_indices == {0, 1}
        assert dlg._pending_modify_layers is None
        assert dlg._pending_modify_bounds is None
        p = dlg.get_import_params()
        assert set(p.selected_layers) == {"AAA"}
        assert p.import_bounds is not None
        assert len(p.geom_list) == 2
    finally:
        dlg.deleteLater()


# ─────────────────────────────────────────────────────────────────────────────
# 3c. PDF SYNC-BLOCK reconcile — runs against the FINAL geometry
# ─────────────────────────────────────────────────────────────────────────────

def test_modify_prefill_sync_block_reapplies_against_final_geometry(
        qapp, monkeypatch):
    """The sync PDF path renders page 0, then the prefill re-renders the target
    page — so _populate_layer_list may have consumed the pending layer subset
    against the WRONG page. The `if self._all_geoms:` reconcile block in
    _apply_modify_prefill must re-apply layers + crop against the FINAL
    geometry and then clear the pending fields (so the async callback can't
    double-apply). This branch is otherwise untested — the other tests stub
    _load_file so _all_geoms stays empty and it never runs.

    Here we monkeypatch the loaders so they MIMIC the real sync PDF load:
    _file_type="pdf", populated _all_geoms (final page), populated layer list.
    Then we drive the REAL _apply_modify_prefill and assert the sync block ran.
    """
    from firepro3d.underlay_import_dialog import UnderlayImportDialog

    def fake_load_file(self):
        # Mimic the real sync PDF load leaving FINAL geometry present when the
        # sync block runs: two geoms inside [0,0,10,10] on layers A/B, one far
        # outside. Populate the layer list as the real load does.
        self._file_type = "pdf"
        self._all_geoms = [
            {"kind": "line", "layer": "A", "x1": 1, "y1": 1, "x2": 2, "y2": 2},
            {"kind": "line", "layer": "B", "x1": 3, "y1": 3, "x2": 4, "y2": 4},
            {"kind": "line", "layer": "B", "x1": 900, "y1": 900,
             "x2": 901, "y2": 901},
        ]
        self._layers = ["A", "B"]
        self._populate_layer_list()

    monkeypatch.setattr(UnderlayImportDialog, "_load_file", fake_load_file)
    monkeypatch.setattr(UnderlayImportDialog, "_load_pdf_page",
                        lambda self, *a, **k: None)

    rec = Underlay(
        type="pdf", path="/nonexistent/plan.pdf", page=2, dpi=300,
        import_mode="vectors", import_scale=2.0,
        selected_layers=["B"], import_bounds=[0.0, 0.0, 10.0, 10.0],
        rotation=0.0, levels=["Level 1"],
    )
    dlg = UnderlayImportDialog(None, modify_record=rec)
    try:
        # (a) The sync block ran: layers reflect the record's subset, and the
        #     crop reduced _selected_indices to the two geoms inside the bounds
        #     (indices 0 and 1 — crop selection is layer-independent; geom 2 is
        #     far outside). If the block never ran, layers would stay all-checked
        #     (None) and _selected_indices would stay None.
        assert dlg._active_layers() == {"B"}
        assert dlg._selected_indices == {0, 1}
        # (b) Pending fields cleared (so the async callback can't double-apply).
        assert dlg._pending_modify_layers is None
        assert dlg._pending_modify_bounds is None
    finally:
        dlg.deleteLater()


# ─────────────────────────────────────────────────────────────────────────────
# 3d. RASTER PDF — pending state invariant (nothing to apply, still cleared)
# ─────────────────────────────────────────────────────────────────────────────

def test_modify_raster_pdf_clears_pending_state(qapp, tmp_path):
    """A raster-mode PDF Modify sets _pending_modify_* but a raster load retains
    no vector geometry (and raster records carry no layers/crop), so there is
    nothing to consume. Since PDF extraction is now ASYNC, the raster clear
    lives in _load_pdf_page's raster branch — which runs SYNCHRONOUSLY and is
    geometry-final on return. Drive the REAL raster branch and assert both
    pending fields are nulled so no stale pending survives a same-session
    import-mode switch."""
    import fitz

    from firepro3d.underlay_import_dialog import UnderlayImportDialog

    p = tmp_path / "raster.pdf"
    d = fitz.open()
    pg = d.new_page(width=200, height=200)
    sh = pg.new_shape()
    sh.draw_line((10, 10), (180, 10))
    sh.finish(width=1.0, color=(0, 0, 0))
    sh.commit()
    d.save(str(p))
    d.close()

    dlg = UnderlayImportDialog()
    try:
        dlg._file_type = "pdf"
        dlg._file_edit.setText(str(p))
        dlg._mode_combo.setCurrentText("Raster")
        # Simulate a Modify prefill having stashed pending state.
        dlg._pending_modify_layers = ["A"]
        dlg._pending_modify_bounds = [0.0, 0.0, 10.0, 10.0]

        # The raster branch runs synchronously (no worker) and must clear both.
        dlg._load_pdf_page(str(p), 0)

        assert dlg._pending_modify_layers is None
        assert dlg._pending_modify_bounds is None
    finally:
        dlg._modified = False
        dlg.close()
        dlg.deleteLater()


# ─────────────────────────────────────────────────────────────────────────────
# 4. END-TO-END NO-OP GUARD
# ─────────────────────────────────────────────────────────────────────────────

def test_modify_noop_roundtrip_preserves_all_placement_params(qapp, monkeypatch):
    from firepro3d.underlay_import_dialog import UnderlayImportDialog

    # Stub loaders so no file/thread is touched; we inject geometry ourselves.
    monkeypatch.setattr(UnderlayImportDialog, "_load_file",
                        lambda self: None)
    monkeypatch.setattr(UnderlayImportDialog, "_load_pdf_page",
                        lambda self, *a, **k: None)

    rec = _full_pdf_record()
    dlg = UnderlayImportDialog(None, modify_record=rec)
    try:
        dlg._file_type = "pdf"
        # Inject geometry mirroring the saved crop + layer subset.
        dlg._all_geoms = [
            {"kind": "line", "layer": "A", "x1": 1, "y1": 1, "x2": 2, "y2": 2},
            {"kind": "line", "layer": "A", "x1": 3, "y1": 3, "x2": 4, "y2": 4},
            {"kind": "line", "layer": "B", "x1": 900, "y1": 900,
             "x2": 901, "y2": 901},
        ]
        dlg._layers = ["A", "B"]
        dlg._populate_layer_list()
        dlg._apply_selected_layers(["A"])
        dlg._restore_crop_from_bounds([0.0, 0.0, 10.0, 10.0])

        p = dlg.get_import_params()
        assert p.pdf_page == 2
        assert p.pdf_dpi == 300
        assert abs(p.scale - 3.2809) < 1e-4
        assert abs(p.base_x - 123.0) < 1e-3
        assert set(p.selected_layers) == {"A"}
        assert p.rotation == pytest.approx(30.0)
        assert list(p.levels) == ["Level 1"]
        assert p.scale_verified is True
        # Crop reflected in the filtered geom_list (only the two A-layer geoms
        # inside the bounds survive).
        assert len(p.geom_list) == 2
        assert p.import_bounds is not None
    finally:
        dlg.deleteLater()
