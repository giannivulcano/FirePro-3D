"""Tests for the global unhandled-exception guard (main.install_excepthook).

Background: with the default sys.excepthook, PyQt6 escalates any Python
exception that escapes Qt-invoked code (slots, timers, virtual overrides
like boundingRect) to qFatal(), killing the process silently with a
0xC0000409 fail-fast in Qt6Core. The guard keeps the app alive and logs
the traceback (stderr + error log file).
"""
import subprocess
import sys
import textwrap

import pytest


@pytest.fixture(autouse=True)
def _restore_excepthook():
    saved = sys.excepthook
    yield
    sys.excepthook = saved


def test_hook_writes_log_and_stderr(tmp_path, monkeypatch, capsys):
    import main as main_module

    log_path = tmp_path / "error.log"
    monkeypatch.setattr(main_module, "ERROR_LOG_PATH", str(log_path))

    try:
        raise ValueError("boom-for-test")
    except ValueError:
        exc_type, exc_value, exc_tb = sys.exc_info()

    main_module._log_unhandled_exception(exc_type, exc_value, exc_tb)

    err = capsys.readouterr().err
    assert "boom-for-test" in err
    content = log_path.read_text(encoding="utf-8")
    assert "boom-for-test" in content
    assert "ValueError" in content


def test_hook_survives_unwritable_log(monkeypatch, capsys):
    import main as main_module

    # A path that cannot be created (invalid drive) must not raise
    monkeypatch.setattr(main_module, "ERROR_LOG_PATH",
                        r"\\\\?\\nonexistent-zz\\error.log")
    try:
        raise RuntimeError("still-logged-to-stderr")
    except RuntimeError:
        info = sys.exc_info()
    main_module._log_unhandled_exception(*info)
    assert "still-logged-to-stderr" in capsys.readouterr().err


def test_install_excepthook_replaces_default():
    import main as main_module

    main_module.install_excepthook()
    assert sys.excepthook is main_module._log_unhandled_exception


def test_app_survives_slot_exception_with_hook():
    """End-to-end in a subprocess: a Qt slot raises; with the hook installed
    the app must keep running (without it, PyQt6 qFatal-aborts the process).
    """
    script = textwrap.dedent("""
        import sys
        sys.path.insert(0, r"{root}")
        import main as main_module
        main_module.install_excepthook()

        from PyQt6.QtWidgets import QApplication, QPushButton
        from PyQt6.QtCore import QTimer

        app = QApplication([])
        btn = QPushButton()

        def boom():
            raise ValueError("deliberate slot exception")

        btn.clicked.connect(boom)
        QTimer.singleShot(0, btn.click)
        QTimer.singleShot(300, lambda: (print("APP-SURVIVED"), app.quit()))
        app.exec()
    """).format(root=r"D:\Custom Code\FirePro3D")
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=120,
        cwd=r"D:\Custom Code\FirePro3D",
    )
    assert "APP-SURVIVED" in result.stdout, (
        f"app died: rc={result.returncode}\n"
        f"stdout={result.stdout}\nstderr={result.stderr}")
    assert "deliberate slot exception" in result.stderr
