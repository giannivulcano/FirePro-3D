"""Tests for import dialog preview: snap index instead of invisible
items, rotation without rebuild, per-layout extraction memoization,
and off-GUI-thread read/extraction workers.
"""

from __future__ import annotations

import time

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QApplication

from firepro3d.underlay_import_dialog import UnderlayImportDialog
from firepro3d.underlay_snap_index import UnderlaySnapIndex


def _pump_until(condition, timeout=10.0) -> bool:
    """Process Qt events until *condition* is true or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


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
        assert _pump_until(lambda: len(dlg._all_geoms) == 1
                           and not dlg._extracting), "extraction timed out"

        calls = []
        from firepro3d.dxf_import_worker import DxfImportWorker
        real = DxfImportWorker._extract_geometry
        monkeypatch.setattr(
            DxfImportWorker, "_extract_geometry",
            lambda self, ent: (calls.append(1), real(self, ent))[1])

        dlg._extract_for_layout("Model")  # revisit same layout — sync memo
        assert calls == [], "revisiting a layout must not re-extract"
        assert len(dlg._all_geoms) == 1
        assert "0" in dlg._layers

    def test_cache_cleared_on_close(self, qapp):
        dlg = self._dialog_with_doc()
        dlg._extract_for_layout("Model")
        assert _pump_until(lambda: dlg._layout_cache), "extraction timed out"
        dlg.done(0)
        assert not dlg._layout_cache


class TestExtractionWorkers:
    """Off-GUI-thread read and extraction workers."""

    def _doc(self, n_lines=1):
        ezdxf = pytest.importorskip("ezdxf")
        doc = ezdxf.new()
        for i in range(n_lines):
            doc.modelspace().add_line((0, i * 10), (100, i * 10))
        return doc

    def test_extract_worker_emits_geoms_and_layers(self, qapp):
        from firepro3d.underlay_import_dialog import _DialogExtractWorker
        results = []
        w = _DialogExtractWorker(self._doc(3), "Model")
        w.finished_geoms.connect(lambda g, l: results.append((g, l)))
        w.run()  # synchronous in tests — signals deliver directly
        assert len(results) == 1
        geoms, layers = results[0]
        assert len(geoms) == 3
        assert geoms[0]["kind"] == "line"
        assert "0" in layers

    def test_extract_worker_cancel_aborts_without_result(self, qapp):
        from firepro3d.underlay_import_dialog import _DialogExtractWorker
        finished, aborted = [], []
        w = _DialogExtractWorker(self._doc(5), "Model")
        w.finished_geoms.connect(lambda g, l: finished.append(1))
        w.aborted.connect(lambda: aborted.append(1))
        w.cancel()
        w.run()
        assert finished == [], "cancelled worker must not emit results"
        assert aborted == [1]

    def test_read_worker_reads_doc(self, qapp, tmp_path):
        ezdxf = pytest.importorskip("ezdxf")
        doc = ezdxf.new()
        doc.modelspace().add_line((0, 0), (50, 50))
        dxf_path = str(tmp_path / "tiny.dxf")
        doc.saveas(dxf_path)

        from firepro3d.underlay_import_dialog import _DialogReadWorker
        docs = []
        w = _DialogReadWorker(dxf_path)
        w.finished_doc.connect(lambda d: docs.append(d))
        w.run()
        assert len(docs) == 1
        assert len(list(docs[0].modelspace())) == 1

    def test_read_worker_emits_error_for_bad_file(self, qapp, tmp_path):
        bad = tmp_path / "bad.dxf"
        bad.write_text("this is not a dxf")
        from firepro3d.underlay_import_dialog import _DialogReadWorker
        errors, docs = [], []
        w = _DialogReadWorker(str(bad))
        w.finished_doc.connect(lambda d: docs.append(d))
        w.error.connect(lambda m: errors.append(m))
        w.run()
        assert docs == []
        assert len(errors) == 1

    def test_aborted_extraction_not_cached_and_clears_busy(self, qapp):
        dlg = UnderlayImportDialog()
        dlg._extracting = True
        dlg._extract_worker = object()
        dlg._on_extract_aborted()
        assert dlg._extracting is False
        assert dlg._extract_worker is None
        assert dlg._layout_cache == {}

    def test_done_cancels_running_worker(self, qapp):
        class _StubWorker:
            def __init__(self):
                self.cancelled = False
                self.waited = False
            def cancel(self):
                self.cancelled = True
            def wait(self, ms=0):
                self.waited = True
                return True

        dlg = UnderlayImportDialog()
        stub = _StubWorker()
        dlg._extract_worker = stub
        dlg.done(0)
        assert stub.cancelled, "closing the dialog must cancel extraction"


class TestAsyncLoadDxf:
    """End-to-end async load: file → read worker → extract worker → preview."""

    def test_load_dxf_populates_preview(self, qapp, tmp_path):
        ezdxf = pytest.importorskip("ezdxf")
        doc = ezdxf.new()
        doc.modelspace().add_line((0, 0), (200, 0))
        dxf_path = str(tmp_path / "one_line.dxf")
        doc.saveas(dxf_path)

        dlg = UnderlayImportDialog()
        dlg._file_edit.setText(dxf_path)
        dlg._load_dxf(dxf_path)
        # Read worker finishes first (ezdxf.new() docs have Model +
        # Layout1, so the dialog defers extraction to the layout combo).
        assert _pump_until(lambda: dlg._doc is not None
                           and dlg._read_worker is None), "read timed out"
        dlg._extract_for_layout("Model")
        assert _pump_until(lambda: len(dlg._all_geoms) == 1
                           and not dlg._extracting), "extraction timed out"
        assert dlg._preview_geom_group is not None
        assert isinstance(dlg._preview_geom_group.data(4), UnderlaySnapIndex)
        assert "Model" in dlg._layout_cache
        dlg.done(0)
