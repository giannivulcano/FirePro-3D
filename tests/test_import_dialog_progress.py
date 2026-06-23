"""Tests for the descriptive import-dialog progress feedback:
LoadingBar.busy() indeterminate mode and the worker status signals that
keep the bar from sitting frozen at 100 % during un-counted phases.
"""

from __future__ import annotations

import ezdxf

from firepro3d.loading_bar import LoadingBar
from firepro3d.dxf_preview_dialog import _DialogExtractWorker


class TestLoadingBarBusy:
    def test_busy_switches_to_indeterminate(self, qapp):
        bar = LoadingBar(cancel=True)
        bar.start_determinate(100, "Extracting…")
        bar.update(40)
        assert bar._bar.maximum() == 100  # determinate

        bar.busy("Clipping geometry to the layout viewport…")
        assert bar.message == "Clipping geometry to the layout viewport…"
        # indeterminate range == (0, 0)
        assert bar._bar.minimum() == 0 and bar._bar.maximum() == 0

    def test_busy_leaves_cancel_state_untouched(self, qapp):
        bar = LoadingBar(cancel=True)
        bar.start_determinate(10, "x")  # enables cancel
        assert bar._cancel_btn.isEnabled()
        bar.busy("scanning…")
        assert bar._cancel_btn.isEnabled()  # not disabled, unlike start()

    def test_bar_methods_never_call_process_events(self, qapp, monkeypatch):
        """Regression: progress/status updates run inside worker-signal
        handlers dispatched by the event loop.  Calling
        QApplication.processEvents() from here re-enters the loop, dispatches
        the next queued progress signal, and recurses until the C stack
        overflows (Win32 0xC00000FD).  The bar must repaint, never pump."""
        from PyQt6.QtWidgets import QApplication
        calls: list[int] = []
        monkeypatch.setattr(QApplication, "processEvents",
                            lambda *a, **k: calls.append(1))
        bar = LoadingBar(cancel=True)
        bar.start("a")
        bar.start_determinate(100, "b")
        bar.update(50, "c")
        bar.busy("d")
        assert calls == [], "LoadingBar must not call processEvents()"


class TestExtractWorkerStatus:
    def test_modelspace_emits_descriptive_phases(self, qapp):
        doc = ezdxf.new()
        msp = doc.modelspace()
        msp.add_line((0, 0), (10, 0))
        msp.add_spline([(0, 0), (1, 2), (3, 1), (5, 4)])

        w = _DialogExtractWorker(doc, "Model")
        msgs: list[str] = []
        w.status.connect(msgs.append)
        w._run_inner()  # synchronous; emits signals directly

        assert any("Scanning" in m for m in msgs), msgs
        assert any("Extracting geometry from" in m for m in msgs), msgs

    def test_status_signal_exists(self):
        # The dialog wires w.status.connect(...); guard against accidental
        # removal of the signal.
        assert hasattr(_DialogExtractWorker, "status")
