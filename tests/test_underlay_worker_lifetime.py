"""Guard: a LEAKED DxfImportWorker (never cleaned up) whose scene/view is torn
down must NOT crash the process when its queued finished_data meta-call is
pumped (bug #371). Runs in a child process because a native abort (0xC0000409)
cannot be caught in-process. RED-on-revert: with the lambda wiring the child
aborts (non-zero exit); with the sink it purges the queued call and exits 0.

NOTE: a direct main-thread emit() would be a DIRECT call that hits the Python
_drop_late_signal guard -> false green. This uses a REAL QThread + REAL queued
emit, which is the only honest repro.
"""
import subprocess
import sys
import textwrap


_CHILD = textwrap.dedent(r'''
    import gc
    import os
    import sys
    import tempfile
    import time

    import ezdxf
    from PyQt6.QtWidgets import QApplication, QGraphicsView
    from firepro3d.model_space import Model_Space

    def main():
        app = QApplication(sys.argv[:1])
        # tiny valid DXF (mirrors tests/test_import_dialog_preview.py)
        doc = ezdxf.new()
        doc.modelspace().add_line((0, 0), (100, 100))
        path = os.path.join(tempfile.mkdtemp(), "tiny.dxf")
        doc.saveas(path)

        # LEAK exactly like a test that forgets to drain: build scene+view in a
        # local scope, start the real worker, and return WITHOUT cleanup() so all
        # refs drop. This is the honest repro — a worker.wait() would keep the
        # worker alive and let the queued call dispatch into a live guard (false
        # green). Here the worker's finished_data is posted, then gc deletes the
        # worker's C++ object while that queued meta-call is still pending.
        def leaky():
            s = Model_Space()
            v = QGraphicsView(s)          # parent for the QProgressDialog
            v.resize(400, 400)
            s.import_dxf(path)            # starts the real worker thread
            # return -> s, v, worker all become unreferenced

        leaky()
        time.sleep(0.5)                   # let run() finish + POST finished_data
        gc.collect()                      # delete worker/scene C++ while queued

        # Pump: dispatch into a dangling receiver (crash on revert) or purge (fix).
        for _ in range(50):
            app.processEvents()
            time.sleep(0.005)
        print("OK")
        return 0

    sys.exit(main())
''')


def test_leaked_worker_does_not_crash_on_pump():
    proc = subprocess.run([sys.executable, "-c", _CHILD],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, (
        f"child exited {proc.returncode}\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    assert "OK" in proc.stdout
