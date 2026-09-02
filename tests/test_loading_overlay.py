"""Tests for the staged loading overlay (firepro3d/loading.py).

Covers the LoadProgress state machine (cancel semantics, stage/done emission),
a guard that the module never calls processEvents(), and a real-dialog test
that a DXF extraction drives the LoadingOverlay through visible completed
stage rows.
"""

from __future__ import annotations

import inspect

import ezdxf
import pytest

from firepro3d.loading import LoadProgress, LoadCancelled, LoadingOverlay
from firepro3d import loading


# ── LoadProgress state machine ────────────────────────────────────────────

def test_progress_stage_and_done_emit(qapp):
    prog = LoadProgress()
    events = []
    prog.began.connect(lambda n: events.append(("begin", n)))
    prog.stageStarted.connect(lambda s: events.append(("stage", s)))
    prog.stageDone.connect(lambda f: events.append(("done", f)))
    prog.begin(3); prog.stage("Read file"); prog.done("2.1 MB")
    assert events == [("begin", 3), ("stage", "Read file"), ("done", "2.1 MB")]


def test_progress_cancel_raises_on_next_stage(qapp):
    prog = LoadProgress(); prog.cancel()
    assert prog.is_cancelled()
    with pytest.raises(LoadCancelled):
        prog.stage("Extract")


# ── Planned checklist (pre-list + advance) ────────────────────────────────

def test_plan_prelists_all_pending(qapp):
    """A plan pre-creates every stage row up front in the ``pending`` state."""
    ov = LoadingOverlay()
    ov.begin("f.dxf", "", "hint",
             plan=[("read", "Read file"), ("scan", "Scan"), ("extract", "Extract")])
    try:
        assert len(ov._rows) == 3
        assert all(r.state == "pending" for r in ov._rows)
    finally:
        ov.finish()
        ov.deleteLater()


def test_advance_marks_prior_done_and_current_run(qapp):
    """``advance`` runs the target row and completes everything before it."""
    ov = LoadingOverlay()
    ov.begin("f.dxf", "", "hint",
             plan=[("read", "Read file"), ("scan", "Scan"), ("extract", "Extract")])
    try:
        ov.advance("scan")
        assert ov._row_by_key["read"].state == "done"
        assert ov._row_by_key["scan"].state == "run"
        assert ov._row_by_key["extract"].state == "pending"

        ov.advance("extract")
        assert ov._row_by_key["scan"].state == "done"
        assert ov._row_by_key["extract"].state == "run"

        ov.stage_done("ok")
        assert ov._row_by_key["extract"].state == "done"
        assert ov._row_by_key["extract"].fact.text() == "ok"
    finally:
        ov.finish()
        ov.deleteLater()


def test_advance_inserts_unknown_key(qapp):
    """A key absent from the plan inserts a fresh running row in place."""
    ov = LoadingOverlay()
    ov.begin("f.dxf", "", "hint",
             plan=[("read", "Read file"), ("scan", "Scan"),
                   ("extract", "Extract"), ("build", "Build preview")])
    try:
        assert "clip" not in ov._row_by_key
        ov.advance("clip", running_label="Clipping…")
        assert "clip" in ov._row_by_key
        assert ov._row_by_key["clip"].state == "run"
        assert ov._row_by_key["clip"] in ov._rows
    finally:
        ov.finish()
        ov.deleteLater()


def test_finish_marks_remaining_done(qapp):
    """``finish`` completes any still-pending/running rows before hiding."""
    ov = LoadingOverlay()
    ov.begin("f.dxf", "", "hint",
             plan=[("read", "Read file"), ("scan", "Scan"), ("extract", "Extract")])
    try:
        ov.advance("scan")
        ov.finish()
        assert all(r.state == "done" for r in ov._rows)
        assert not ov.isVisible()
    finally:
        ov.deleteLater()


# ── processEvents guard ───────────────────────────────────────────────────

def test_loading_module_never_calls_processevents():
    assert "processEvents" not in inspect.getsource(loading)


# ── Real dialog: DXF extraction drives the overlay ────────────────────────

def _make_dxf_doc():
    """Build a small real ezdxf document (model space geometry)."""
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    msp.add_line((10, 0), (10, 10))
    msp.add_spline([(0, 0), (1, 2), (3, 1), (5, 4)])
    return doc


def test_dxf_extraction_drives_loading_overlay(qapp):
    """Constructing the real dialog and running a DXF extraction should show
    the LoadingOverlay and leave at least one completed stage row behind."""
    from firepro3d.underlay_import_dialog import UnderlayImportDialog

    dlg = UnderlayImportDialog()
    try:
        overlay = dlg._loading_overlay
        # Feed a real document into the DXF-read continuation. ezdxf docs carry
        # Model + Layout1, so the dialog shows the layout combo and defers.
        dlg._file_edit.setText("phantom.dxf")
        dlg._on_dxf_read("phantom.dxf", _make_dxf_doc())

        # Selecting a layout on the real combo kicks off _DialogExtractWorker.
        idx = dlg._layout_combo.findText("Model")
        assert idx >= 0, "Model layout missing from combo"
        dlg._layout_combo.setCurrentIndex(idx)   # fires _on_layout_changed

        # Extraction runs on a worker thread. Pump the GUI event loop so its
        # queued status/progress signals are delivered until it finishes.
        import time
        deadline = time.monotonic() + 5.0
        while dlg._extract_worker is not None and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.01)
        qapp.processEvents()

        # The overlay was driven: it collected stage rows, at least one done.
        assert overlay._rows, "overlay recorded no stage rows"
        assert any(r.state == "done" for r in overlay._rows), \
            "overlay recorded no completed stage"
    finally:
        dlg._modified = False
        dlg.close()
        dlg.deleteLater()
