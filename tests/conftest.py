"""Test fixtures for FirePro3D headless Qt tests.

Qt requires a single QApplication instance per process before any
QGraphicsScene / widget is instantiated, even when no window is shown.
This conftest provides a session-scoped fixture for it.
"""

from __future__ import annotations

import base64
import os
import sys
import tempfile

import pytest
from PyQt6 import QtCore as _QtCore
from PyQt6.QtWidgets import QApplication


# ── QSettings isolation (#312) ──────────────────────────────────────────────
# Windows NativeFormat ignores setPath()/setDefaultFormat(), so the ONLY reliable
# way to keep the ~90 ``QSettings("GV","FirePro3D")`` sites off the real dev
# registry is to intercept construction at the class level. Installed here at
# conftest-import time so every later ``from PyQt6.QtCore import QSettings`` (in
# test AND firepro3d modules) resolves to the isolated subclass.
_RealQSettings = _QtCore.QSettings
_qsettings_dir = [tempfile.mkdtemp(prefix="fp3d_qs_default_")]


class _IsolatedQSettings(_RealQSettings):
    """QSettings subclass that reroutes registry-scope constructions to a
    per-test temp INI so tests never touch the real Windows registry (#312).

    Explicit ``QSettings(fileName, IniFormat)`` constructions (the ``tmp_settings``
    fixture and the per-file isolation fixtures) are honored as-is. Every other
    form — 2-arg ``(org, app)``, bare, ``(scope, org, app)``, ``(NativeFormat,
    scope, org, app)`` — reroutes to ``<test_dir>/<org_app>.ini``, keyed by the
    string args so same-scope reads/writes stay coherent within a test.
    """

    def __init__(self, *args, **kwargs):
        Fmt = _RealQSettings.Format
        if len(args) >= 2 and isinstance(args[0], str) and args[1] == Fmt.IniFormat:
            super().__init__(*args, **kwargs)   # explicit INI-file form: honor
            return
        strs = [a for a in args if isinstance(a, str)]
        key = "_".join(strs) if strs else "default"
        key = "".join(c if (c.isalnum() or c in "._-") else "_" for c in key)
        super().__init__(os.path.join(_qsettings_dir[0], key + ".ini"), Fmt.IniFormat)


_QtCore.QSettings = _IsolatedQSettings


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication for headless Qt tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    yield app
    # Do not call app.quit() — pytest may run more tests in the same
    # process and Qt dislikes repeated QApplication creation.


@pytest.fixture(autouse=True)
def _preserve_snap_globals():
    """Snapshot/restore the snap-engine tunable module globals around every
    test so a test that mutates them (or a MainWindow that restores them from
    QSettings) can't leak into a later test under random ordering.

    These are process-wide module globals (``SNAP_TOLERANCE_PX`` /
    ``SNAP_HYSTERESIS_PX``); without this, e.g. ``test_default_hysteresis_is_3``
    flakes when a prior test leaves the global changed.
    """
    from firepro3d import snap_engine
    saved = (snap_engine.SNAP_TOLERANCE_PX, snap_engine.SNAP_HYSTERESIS_PX)
    yield
    snap_engine.SNAP_TOLERANCE_PX, snap_engine.SNAP_HYSTERESIS_PX = saved


@pytest.fixture(autouse=True)
def _isolate_qsettings(tmp_path_factory):
    """Point the isolated QSettings store at a FRESH per-test temp dir (#312), so
    a key written by one test can't leak into the next. The class-level redirect
    itself is installed at conftest import (see ``_IsolatedQSettings`` above)."""
    _qsettings_dir[0] = str(tmp_path_factory.mktemp("qsettings"))
    yield


@pytest.fixture
def real_qsettings():
    """The unpatched QSettings class — lets the isolation guard test read the
    REAL registry to prove nothing leaked there (#312)."""
    return _RealQSettings


@pytest.fixture
def tmp_settings(tmp_path):
    """A QSettings pinned to an INI file under ``tmp_path`` (no registry writes).

    Used by ALIGN-settings tests to round-trip ``align/*`` keys without touching
    the real Windows registry.  Pair with monkeypatching
    ``preferences_dialog.QSettings`` when a pane's internal
    ``QSettings(org, app)`` calls must be redirected here.
    """
    from PyQt6.QtCore import QSettings

    ini_path = str(tmp_path / "align_test.ini")
    return QSettings(ini_path, QSettings.Format.IniFormat)


@pytest.fixture
def model_space(qapp):
    """A bare ``Model_Space`` carrying an ``AlignController`` (for ALIGN tests).

    Constructed with no view/level manager — sufficient to exercise the ALIGN
    knob seam (``_align_controller`` dwell/max-points/direction flags and
    ``_align_path_tol_px``) which the SnappingPane live-applies.
    """
    from firepro3d.model_space import Model_Space

    return Model_Space()


@pytest.fixture
def make_model_space(qapp):
    """Factory that builds a Model_Space with an attached QGraphicsView.

    The view is sized 800×800 at identity transform (m11==1.0) and centred
    on the origin so that scene coords in the range ~(-400,400) are in the
    viewport.  Tests requiring wider coverage or a different transform call
    ``view.setTransform(...)`` or ``view.centerOn(...)`` on the returned
    scene's first view after construction.

    Mirrors the fixture in ``test_gridline_alignment_snap.py``.
    """
    from firepro3d.model_space import Model_Space
    from PyQt6.QtWidgets import QGraphicsView

    created: list[tuple[Model_Space, QGraphicsView]] = []

    def _factory() -> Model_Space:
        ms = Model_Space()
        view = QGraphicsView(ms)
        view.resize(800, 800)
        view.resetTransform()
        view.centerOn(0.0, 0.0)
        QApplication.processEvents()
        created.append((ms, view))
        return ms

    yield _factory

    for ms, view in created:
        ms.cleanup()   # #373: join any underlay DXF worker before teardown
        view.hide()


@pytest.fixture
def model_scene(qapp):
    """Factory fixture that returns a callable producing a fresh Model_Space
    with a LevelManager (Level 1 at elevation 0.0) and a ScaleManager.

    Usage in tests::

        def test_foo(qapp, model_scene):
            scene = model_scene()
            ...
    """
    from firepro3d.model_space import Model_Space
    from firepro3d.level_manager import LevelManager
    from firepro3d.scale_manager import ScaleManager

    def _factory():
        s = Model_Space()
        lm = LevelManager()            # seeds Level 1 (elevation 0.0) by default
        s._level_manager = lm
        s.scale_manager = ScaleManager()
        return s

    return _factory


@pytest.fixture
def shown_model_view(qapp):
    """A SHOWN, focused ``Model_View`` wrapping a ``Model_Space`` with a
    LevelManager (Level 1 @ 0.0) and ScaleManager.

    Returns ``(view, scene)``.  The view is shown, exposed and focused, and its
    transform reset + centred on the origin so scene points near (500, 0) map
    inside the viewport — posted ``QMouseEvent`` / ``QKeyEvent`` therefore route
    through the real event pipeline instead of vacuously missing every handler.
    """
    from PyQt6.QtTest import QTest
    from firepro3d.model_space import Model_Space
    from firepro3d.model_view import Model_View
    from firepro3d.level_manager import LevelManager
    from firepro3d.scale_manager import ScaleManager

    scene = Model_Space()
    scene._level_manager = LevelManager()      # seeds Level 1 (elevation 0.0)
    scene.scale_manager = ScaleManager()

    view = Model_View(scene)
    view.resize(800, 600)
    view.show()
    QTest.qWaitForWindowExposed(view)
    # Pin a known, deterministic transform AFTER the window is exposed so that
    # the auto-fit-to-scene zoom (m11 ≈ 0.02) is replaced by a fixed scale.
    # At m11=0.25 the visible range is ±1596 × ±1196 scene units (all test
    # geometry fits), and the 20 px snap aperture equals 80 scene units so that
    # test "empty space" positions (≥ 224 scene units from the nearest geometry)
    # are genuinely outside the aperture.  Without this pin the auto-fit zoom
    # collapses snap distances to 2–10 px and geometry that the tests treat as
    # "far away" snaps unexpectedly.
    view.resetTransform()
    view.scale(0.25, 0.25)
    view.centerOn(0, 0)
    view.setFocus()
    QApplication.processEvents()

    yield view, scene

    scene.cleanup()   # join the underlay DXF worker so it can't outlive the scene (#373)
    view.close()


@pytest.fixture
def elevation_scene_for(qapp):
    """Factory fixture returning a callable ``(direction) -> (model_scene, elev_scene)``.

    Creates a fresh Model_Space with a LevelManager (Level 1 at 0.0 mm) and a
    ScaleManager (uncalibrated, so pixels_per_mm == 1.0), then wraps it in an
    ElevationScene bound to the requested direction.

    Usage in tests::

        def test_foo(qapp, elevation_scene_for):
            scene, elev = elevation_scene_for("north")
            ...
    """
    from firepro3d.model_space import Model_Space
    from firepro3d.level_manager import LevelManager
    from firepro3d.scale_manager import ScaleManager
    from firepro3d.elevation_scene import ElevationScene

    def _factory(direction: str = "north"):
        ms = Model_Space()
        lm = LevelManager()            # seeds Level 1 (elevation 0.0) by default
        ms._level_manager = lm
        sm = ScaleManager()
        ms.scale_manager = sm
        elev = ElevationScene(direction=direction, model_space=ms,
                              level_manager=lm, scale_manager=sm)
        return ms, elev

    return _factory


@pytest.fixture
def tiny_png_b64(qapp):
    """A 4×4 solid-color (0xFF336699) PNG encoded as base64 ASCII.

    Shared title-block image fixture (used by test_paper_space.py and
    test_paper_export.py combined image+text cell tests).
    """
    from PyQt6.QtCore import QBuffer, QIODevice
    from PyQt6.QtGui import QImage

    img = QImage(4, 4, QImage.Format.Format_RGB32)
    img.fill(0xFF336699)
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return base64.b64encode(bytes(buf.data())).decode("ascii")


@pytest.fixture
def stub_view3d():
    """Opt-in: replace ``main.View3D`` with a windowless QWidget stub for the
    duration of a test so MainWindow-constructing tests run with no VTK plotter
    / no native window (bug #367).

    Yields the stub CLASS so tests can ``isinstance(win.view_3d, stub_view3d)``.
    ``test_view_3d.py`` does NOT use this fixture — it keeps real-View3D coverage
    via ``pv.OFF_SCREEN = True``. The stub satisfies the full interface MainWindow
    calls: cleanup/rebuild/get_3d_selected/delete_selected/show_radiation_heatmap/
    clear_radiation_heatmap/_on_escape + the entitySelected signal.
    """
    import main as _main
    from PyQt6.QtWidgets import QWidget
    from PyQt6.QtCore import pyqtSignal

    class _StubView3D(QWidget):
        entitySelected = pyqtSignal(object)

        def __init__(self, model_space, level_manager, scale_manager, parent=None):
            super().__init__(parent)
            self._plotter = None

        def cleanup(self):
            pass

        def rebuild(self):
            pass

        def get_3d_selected(self):
            return []

        def delete_selected(self):
            pass

        def show_radiation_heatmap(self, result):
            pass

        def clear_radiation_heatmap(self):
            pass

        def _on_escape(self):
            pass

    had_prev = hasattr(_main, "View3D")
    prev = getattr(_main, "View3D", None)
    _main.View3D = _StubView3D
    try:
        yield _StubView3D
    finally:
        if had_prev:
            _main.View3D = prev
        else:
            delattr(_main, "View3D")
