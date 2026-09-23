"""Guard: destroying a MainWindow whose paper-scene undo stack is non-empty must
NOT crash the process when the (Python-owned, parentless) ``PaperScene`` is later
garbage-collected (test-harness.md Invariant 6).

Mechanism of the original crash: the module-scoped MainWindow fixtures
``close()`` + ``deleteLater()`` the window; once DeferredDelete is flushed the C++
MainWindow is gone, but ``paper_space_widget.paper_scene`` has no Qt parent and
survives in a Python reference cycle. When a later ``gc.collect()`` destroys it,
``~QUndoStack`` → ``clear()`` emits ``indexChanged(0)`` (only when non-empty) into
``main.py`` slots. A ``self``-capturing *lambda* has no receiver, so PyQt never
auto-disconnects it and it runs against the dead window → native abort. Bound
methods are auto-disconnected when the receiver is destroyed.

Runs in a child process because a native abort cannot be caught in-process.
RED-on-revert: with the lambda wiring the child exits non-zero (127 / 0xC0000005).
"""
import os
import subprocess
import sys
import textwrap


_CHILD = textwrap.dedent(r'''
    import gc
    import os
    import sys
    import tempfile

    # QSettings isolation (test-harness.md Invariant 1) — the child is outside
    # conftest, so reroute registry-scope QSettings to a temp INI before any
    # firepro3d/main import resolves the class.
    from PyQt6 import QtCore
    _Real = QtCore.QSettings
    _dir = tempfile.mkdtemp(prefix="fp3d_qs_child_")

    class _Iso(_Real):
        def __init__(self, *args, **kwargs):
            Fmt = _Real.Format
            if len(args) >= 2 and isinstance(args[0], str) and args[1] == Fmt.IniFormat:
                super().__init__(*args, **kwargs)
                return
            key = "_".join(a for a in args if isinstance(a, str)) or "default"
            key = "".join(c if (c.isalnum() or c in "._-") else "_" for c in key)
            super().__init__(os.path.join(_dir, key + ".ini"), Fmt.IniFormat)

    QtCore.QSettings = _Iso

    from PyQt6.QtCore import QCoreApplication, QEvent
    from PyQt6.QtWidgets import QApplication

    def main():
        app = QApplication(sys.argv[:1])
        import main as main_mod
        from firepro3d.view_3d import View3D
        main_mod.View3D = View3D
        # Never read/write the real ~/.firepro3d recovery file (a stale one pops
        # a modal recovery prompt and hangs the child).
        _autosave = os.path.join(_dir, "recovery.FPD")
        main_mod.MainWindow._autosave_path = staticmethod(lambda: _autosave)
        from firepro3d.paper_space import (
            AddTextAnnotationCommand, TextAnnotationData)

        def build_and_close():
            w = main_mod.MainWindow()
            w.show()
            app.processEvents()
            sc = w.paper_space_widget.paper_scene
            # Non-empty stack: ~QUndoStack only emits indexChanged when it
            # has commands to clear.
            sc.undo_stack.push(AddTextAnnotationCommand(
                sc, TextAnnotationData(text="x", x=30, y=30)))
            w._modified = False       # never block on the save prompt
            w.close()
            w.deleteLater()

        build_and_close()
        # Actually run the deferred delete (processEvents() alone never does at
        # this loop level) — this is what a later test's event pump does.
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        gc.collect()
        app.processEvents()
        print("OK", flush=True)
        return 0

    rc = main()
    sys.stdout.flush()
    sys.exit(rc)   # interpreter shutdown also destroys any surviving PaperScene
''')


def test_paper_scene_outliving_mainwindow_does_not_crash():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run([sys.executable, "-X", "faulthandler", "-c", _CHILD],
                          capture_output=True, text=True, timeout=180, cwd=repo)
    assert proc.returncode == 0, (
        f"child exited {proc.returncode}\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr[-4000:]}")
    assert "OK" in proc.stdout
