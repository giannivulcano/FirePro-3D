"""Tests for import dialog resource release and extraction re-entrancy.

The dialog is parented to the main window, so it survives close until
deleteLater(); done() must drop the heavy references (ezdxf doc,
preview scene items) immediately.  During extraction the controls must
be disabled — processEvents in the progress bar otherwise lets layer
toggles / Import clicks land on a half-built _all_geoms.
"""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QGraphicsRectItem

from firepro3d.dxf_preview_dialog import UnderlayImportDialog


def _dialog(qapp) -> UnderlayImportDialog:
    return UnderlayImportDialog()


class TestExtractionControlsDisabled:
    def test_set_extracting_disables_controls(self, qapp):
        dlg = _dialog(qapp)
        dlg._set_extracting(100)
        assert not dlg._preview_view.isEnabled()
        btns = dlg.findChild(QDialogButtonBox)
        assert btns is not None
        assert not btns.isEnabled(), (
            "Import/Cancel must be disabled during extraction")
        dlg._clear_loading()
        assert dlg._preview_view.isEnabled()
        assert btns.isEnabled()

    def test_accept_ignored_while_extracting(self, qapp):
        dlg = _dialog(qapp)
        dlg._all_geoms = [{"kind": "line", "x1": 0, "y1": 0,
                           "x2": 1, "y2": 1, "layer": "0"}]
        dlg._has_vectors = True
        dlg._extracting = True
        dlg._on_accept()
        assert dlg.result() != QDialog.DialogCode.Accepted, (
            "Import accepted mid-extraction would commit a half-built "
            "geometry list")

    def test_extract_for_layout_is_not_reentrant(self, qapp, monkeypatch):
        dlg = _dialog(qapp)
        dlg._extracting = True
        # _doc access would raise on this bare dialog — a re-entrant
        # call must return before touching it.
        dlg._extract_for_layout("Model")  # must be a no-op, not raise


class TestResourceReleaseOnClose:
    def test_done_drops_doc(self, qapp):
        dlg = _dialog(qapp)
        dlg._doc = object()
        dlg.done(0)
        assert dlg._doc is None

    def test_done_clears_preview_scene(self, qapp):
        dlg = _dialog(qapp)
        dlg._preview_scene.addItem(QGraphicsRectItem(0, 0, 10, 10))
        assert len(dlg._preview_scene.items()) > 0
        dlg.done(0)
        assert len(dlg._preview_scene.items()) == 0

    def test_get_import_params_works_after_accept(self, qapp):
        # get_import_params() is called AFTER exec() returns (and after
        # done(1) ran) — it must survive the resource release.
        dlg = _dialog(qapp)
        dlg._doc = object()
        dlg._all_geoms = [{"kind": "line", "x1": 0, "y1": 0,
                           "x2": 1, "y2": 1, "layer": "0"}]
        dlg._has_vectors = True
        dlg.done(QDialog.DialogCode.Accepted)
        params = dlg.get_import_params()
        assert len(params.geom_list) == 1
