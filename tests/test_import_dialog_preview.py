"""Tests for import dialog preview: snap index instead of invisible
items, rotation without rebuild, and per-layout extraction memoization.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform

from firepro3d.dxf_preview_dialog import UnderlayImportDialog
from firepro3d.underlay_snap_index import UnderlaySnapIndex


def _line(x1=0.0, y1=0.0, x2=200.0, y2=0.0, layer="0"):
    return {"kind": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "layer": layer}


def _prepped_dialog(n_geoms=1) -> UnderlayImportDialog:
    dlg = UnderlayImportDialog()
    if n_geoms == 1:
        dlg._all_geoms = [_line()]
    else:
        dlg._all_geoms = [
            _line(float(i), 0.0, float(i) + 1.0, 1.0)
            for i in range(n_geoms)
        ]
    dlg._has_vectors = True
    dlg._layers = ["0"]
    dlg._populate_layer_list()
    dlg._rebuild_preview()
    return dlg


class TestPreviewSnapIndex:
    def test_preview_group_has_snap_index(self, qapp):
        dlg = _prepped_dialog()
        group = dlg._preview_geom_group
        assert group is not None
        assert isinstance(group.data(4), UnderlaySnapIndex)

    def test_no_invisible_per_geom_items(self, qapp):
        dlg = _prepped_dialog(n_geoms=50)
        group = dlg._preview_geom_group
        assert len(group.childItems()) <= 6, (
            "preview group must hold only batched path items, not one "
            "invisible item per geometry")

    def test_snap_index_reused_when_geoms_unchanged(self, qapp):
        dlg = _prepped_dialog()
        idx1 = dlg._preview_geom_group.data(4)
        assert isinstance(idx1, UnderlaySnapIndex)
        dlg._rebuild_preview()  # layer toggle / rubber band path
        assert dlg._preview_geom_group.data(4) is idx1

    def test_snap_index_rebuilt_on_new_geom_list(self, qapp):
        dlg = _prepped_dialog()
        idx1 = dlg._preview_geom_group.data(4)
        assert isinstance(idx1, UnderlaySnapIndex)
        dlg._all_geoms = [_line()]  # fresh extraction → new list object
        dlg._rebuild_preview()
        idx2 = dlg._preview_geom_group.data(4)
        assert isinstance(idx2, UnderlaySnapIndex)
        assert idx2 is not idx1

    def test_snap_engine_finds_endpoint_via_index(self, qapp):
        # Pick-mode path: the dialog's engine over the preview scene.
        dlg = _prepped_dialog()
        result = dlg._snap_engine.find(
            QPointF(5, 0), dlg._preview_scene, QTransform())
        assert result is not None
        assert result.snap_type == "endpoint"
        assert abs(result.point.x() - 0) < 2.0

    def test_snap_engine_finds_midpoint_via_index(self, qapp):
        dlg = _prepped_dialog()
        result = dlg._snap_engine.find(
            QPointF(100, 5), dlg._preview_scene, QTransform())
        assert result is not None
        assert result.snap_type == "midpoint"
        assert abs(result.point.x() - 100) < 2.0


class TestRotationWithoutRebuild:
    def test_rotation_change_keeps_group(self, qapp):
        dlg = _prepped_dialog()
        group1 = dlg._preview_geom_group
        dlg._rotation_edit.setText("45.0")
        dlg._on_rotation_changed()
        assert dlg._preview_geom_group is group1, (
            "rotation must transform the existing group, not rebuild")
        assert abs(group1.rotation() - 45.0) < 1e-6

    def test_rotation_with_no_group_is_safe(self, qapp):
        dlg = UnderlayImportDialog()
        dlg._rotation_edit.setText("90.0")
        dlg._on_rotation_changed()  # must not raise


class TestLayoutMemoization:
    def _dialog_with_doc(self):
        ezdxf = pytest.importorskip("ezdxf")
        doc = ezdxf.new()
        doc.modelspace().add_line((0, 0), (100, 0))
        dlg = UnderlayImportDialog()
        dlg._file_edit.setText("dummy.dxf")
        dlg._file_type = "dxf"
        dlg._has_vectors = True
        dlg._doc = doc
        return dlg

    def test_repeat_layout_skips_extraction(self, qapp, monkeypatch):
        dlg = self._dialog_with_doc()
        dlg._extract_for_layout("Model")
        assert len(dlg._all_geoms) == 1

        calls = []
        from firepro3d.dxf_import_worker import DxfImportWorker
        real = DxfImportWorker._extract_geometry
        monkeypatch.setattr(
            DxfImportWorker, "_extract_geometry",
            lambda self, ent: (calls.append(1), real(self, ent))[1])

        dlg._extract_for_layout("Model")  # revisit same layout
        assert calls == [], "revisiting a layout must not re-extract"
        assert len(dlg._all_geoms) == 1
        assert "0" in dlg._layers

    def test_cancelled_extraction_not_cached(self, qapp):
        # Simulate the user clicking Cancel mid-extraction: the loop
        # polls _loading_bar.cancelled between entities (the loading
        # bar resets the flag on start, so it must be set during the
        # run, exactly as the cancel button does).
        dlg = self._dialog_with_doc()
        for i in range(5):
            dlg._doc.modelspace().add_line((0, i * 10), (100, i * 10))

        def _cancel_on_progress(current, total, message=""):
            dlg._loading_bar.cancelled = True

        dlg._update_progress = _cancel_on_progress
        dlg._extract_for_layout("Model")
        assert "Model" not in dlg._layout_cache, (
            "a cancelled (partial) extraction must not be memoized")

    def test_cache_cleared_on_close(self, qapp):
        dlg = self._dialog_with_doc()
        dlg._extract_for_layout("Model")
        assert dlg._layout_cache
        dlg.done(0)
        assert not dlg._layout_cache
