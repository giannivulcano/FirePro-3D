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

    Explicit ``QSettings(fileName, IniFormat)`` constructions (e.g. a test's own
    temp-INI fixture) are honored as-is. Every other
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


class FakeClipboard(_QtCore.QObject):
    """In-memory stand-in for ``QApplication.clipboard()``.

    The Windows clipboard refuses writes (ACCESS_DENIED) whenever another
    process holds it, which failed ~59 copy / cut / paste tests per run. The
    app's own copy path reads its write back, so a faithful fake only needs
    ``text`` / ``setText`` / ``clear`` and ``dataChanged``.
    """
    dataChanged = _QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        self._text = ""

    def text(self, *a):
        return self._text

    def setText(self, text, *a):
        self._text = text
        self.dataChanged.emit()

    def clear(self, *a):
        self.setText("")


@pytest.fixture(autouse=True)
def _fake_clipboard(request):
    """Every test gets a fresh in-memory clipboard instead of the OS one.

    Opt out with ``@pytest.mark.real_clipboard`` for a test that needs the real
    clipboard (a Qt text control's own Ctrl+C / Ctrl+V never goes through
    Python). A test that patches the accessors itself (``dead_clip``) layers on
    top of this and is undone first.
    """
    if request.node.get_closest_marker("real_clipboard"):
        yield None
        return
    from PyQt6.QtGui import QGuiApplication
    clip = FakeClipboard()
    # Its OWN MonkeyPatch, never the shared ``monkeypatch`` fixture: requesting
    # that from an autouse fixture sets it up before every test's own fixtures,
    # so it would be torn down AFTER them and a test that patches a method its
    # fixture's teardown calls (test_selection_readouts_fixes) would break.
    mp = pytest.MonkeyPatch()
    mp.setattr(QApplication, "clipboard", staticmethod(lambda: clip))
    mp.setattr(QGuiApplication, "clipboard", staticmethod(lambda: clip))
    try:
        yield clip
    finally:
        mp.undo()


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
def _preserve_halo_globals():
    """Snapshot/restore the HALO tunable module globals (aperture/band)."""
    from firepro3d import halo_selection as hs
    saved = (hs.HALO_APERTURE_PX, hs.HALO_PRIORITY_BAND_PX)
    yield
    hs.HALO_APERTURE_PX, hs.HALO_PRIORITY_BAND_PX = saved


@pytest.fixture(autouse=True)
def _preserve_grip_object_limit():
    """Snapshot/restore ``selection_manipulator.GRIP_OBJECT_LIMIT`` (an
    app-wide module global a test may set to exercise the grip-object-limit
    branch) so it can't leak into a later test under random ordering."""
    from firepro3d import selection_manipulator as sm
    saved = sm.GRIP_OBJECT_LIMIT
    yield
    sm.GRIP_OBJECT_LIMIT = saved


@pytest.fixture(autouse=True)
def _reset_project_line_weights():
    """Reset the project weight table + Thin Lines flag + Model weight factor
    (paper_display module globals, linetypes.md LT1 / MW-2) so a table one
    test sets can't leak into the next; the lazy re-seed reads that test's
    (isolated or patched) template."""
    from firepro3d import paper_display as pd
    pd._PROJECT_LW = None
    pd._THIN_LINES = False
    pd._THIN_SUSPEND = 0
    pd._MODEL_FACTOR = pd.MODEL_WEIGHT_FACTOR
    pd._clear_hatch_mm()
    yield
    pd._PROJECT_LW = None
    pd._THIN_LINES = False
    pd._THIN_SUSPEND = 0
    pd._MODEL_FACTOR = pd.MODEL_WEIGHT_FACTOR
    pd._clear_hatch_mm()


@pytest.fixture(autouse=True)
def _reset_current_stroke_style():
    """Reset the WM1 current Linetype/Weight store (stroke_style module
    global, linetypes.md WM-10) so one test's current can't leak."""
    from firepro3d import stroke_style as ss
    ss.reset_current()
    yield
    ss.reset_current()


@pytest.fixture(autouse=True)
def _isolate_qsettings(tmp_path_factory):
    """Point the isolated QSettings store at a FRESH per-test temp dir (#312), so
    a key written by one test can't leak into the next. The class-level redirect
    itself is installed at conftest import (see ``_IsolatedQSettings`` above)."""
    _qsettings_dir[0] = str(tmp_path_factory.mktemp("qsettings"))
    yield


@pytest.fixture(autouse=True)
def _isolate_block_library(_isolate_qsettings, tmp_path_factory):
    """Point the block library at a FRESH per-test temp dir (Invariant 7).

    ``block_library`` with the default root resolves to ``paths/block_dir`` →
    else the REAL ``%APPDATA%/FirePro3D/blocks``; the Blocks browser reads it
    at construction and the Save flows write it. Setting the override in the
    already-isolated QSettings store keeps every test off the user's library.
    Also points ``paths/schematic_dir`` at a fresh temp dir (SV3).
    """
    from firepro3d.app_data import BLOCK_DIR_KEY, SCHEMATIC_DIR_KEY
    from PyQt6.QtCore import QSettings
    s = QSettings("GV", "FirePro3D")
    s.setValue(BLOCK_DIR_KEY, str(tmp_path_factory.mktemp("block_library")))
    # The schematic templates folder (schematics.md D-S5) is a SECOND root the
    # Save-as-Template / New Schematic flows write and read; isolate it too.
    s.setValue(SCHEMATIC_DIR_KEY, str(tmp_path_factory.mktemp("schematics")))
    yield


@pytest.fixture(scope="session", autouse=True)
def _isolate_system_library_session(tmp_path_factory):
    """Session-wide EMPTY System tier (SB1b D15): module-scoped fixtures (a
    shared MainWindow) are built before any function-scoped fixture runs, and
    must not see the real shipped tier either (D2 would make it own the
    seeded hatch ids)."""
    from firepro3d import block_library
    block_library.set_system_root(str(tmp_path_factory.mktemp("system_library_s")))
    yield
    block_library.set_system_root(None)


@pytest.fixture(scope="session", autouse=True)
def _isolate_block_library_session(tmp_path_factory):
    """Session-wide block library in the DEFAULT isolated QSettings store: a
    module-scoped MainWindow built before the first test's
    ``_isolate_block_library`` would otherwise resolve the REAL
    ``%APPDATA%/FirePro3D/blocks`` -- and its startup runs
    ``system_library.migrate_user_library()`` (SB1b D5), which moves files."""
    from firepro3d.app_data import BLOCK_DIR_KEY, SCHEMATIC_DIR_KEY
    from PyQt6.QtCore import QSettings
    s = QSettings("GV", "FirePro3D")
    s.setValue(BLOCK_DIR_KEY, str(tmp_path_factory.mktemp("block_library_s")))
    s.setValue(SCHEMATIC_DIR_KEY, str(tmp_path_factory.mktemp("schematics_s")))
    yield


@pytest.fixture(autouse=True)
def _isolate_system_library(_isolate_system_library_session, tmp_path_factory):
    """Point the read-only System tier at an EMPTY per-test dir (SB1b D15), so
    tests that enumerate a temp library see only their own blocks. A guard
    that needs the real shipped tier requests ``real_system_library``."""
    from firepro3d import block_library
    prev = block_library._system_root_override[0]
    block_library.set_system_root(str(tmp_path_factory.mktemp("system_library")))
    yield
    block_library.set_system_root(prev)


@pytest.fixture
def real_system_library():
    """Opt in to the real shipped System tier; returns its root."""
    from firepro3d import block_library
    block_library.set_system_root(None)
    return block_library.system_root()


# Invariant 11: MainWindow autosaves to ~/.firepro3d/autosave/recovery.FPD and
# closeEvent / _check_recovery DELETE that file -- so an unredirected test can
# plant a recovery file (hanging later fixtures on the Recover dialog) or wipe
# the user's real one. The class is patched once per session (module-scoped
# fixtures build their window before function fixtures run, and many test
# bodies import ``main`` lazily); the directory it points at is per test.
_autosave_dir = [None]


@pytest.fixture(scope="session", autouse=True)
def _redirect_autosave(tmp_path_factory):
    """Point ``MainWindow._autosave_path`` at ``_autosave_dir`` for the session."""
    import main as _main_module
    _autosave_dir[0] = str(tmp_path_factory.mktemp("autosave_session"))
    mp = pytest.MonkeyPatch()
    mp.setattr(_main_module.MainWindow, "_autosave_path",
               staticmethod(lambda: os.path.join(_autosave_dir[0], "recovery.FPD")))
    yield
    mp.undo()


@pytest.fixture(autouse=True)
def _isolate_autosave(_redirect_autosave, tmp_path_factory):
    """A FRESH per-test autosave dir (see ``_redirect_autosave``)."""
    _autosave_dir[0] = str(tmp_path_factory.mktemp("autosave"))
    yield


@pytest.fixture
def shipped_hatches(qapp):
    """Loader for the five shipped hatch-pattern blocks (hatch D-A39).

    There is no code-level pattern table: a pattern resolves only once its
    block is in the project registry. Returns ``load(scene=None)``:

    - with a project ``Model_Space``: loads the shipped ``.fpdb`` files into
      its registry through the real outside-history path
      (``Model_Space.load_blocks_outside_history``) and returns
      ``scene.block_registry``;
    - with None: returns a standalone ``BlockRegistry`` holding them (for
      renderer tests whose stand-in scene carries a ``block_registry``).
    """
    from firepro3d.block_library import load_block_file
    from firepro3d.block_registry import BlockRegistry
    from firepro3d.hatch_patterns import shipped_pattern_files

    def load(scene=None):
        files = shipped_pattern_files()
        assert len(files) == 5, files
        if scene is None:
            reg = BlockRegistry({})
            for _bid, path in files:
                reg.add(load_block_file(path))
            return reg
        scene.load_blocks_outside_history([p for _bid, p in files])
        return scene.block_registry

    return load


@pytest.fixture
def real_qsettings():
    """The unpatched QSettings class — lets the isolation guard test read the
    REAL registry to prove nothing leaked there (#312)."""
    return _RealQSettings


@pytest.fixture
def tooltips_installed(qapp):
    """The ET1 tooltip wrap filter, installed for one test (removed after)."""
    from firepro3d import tooltips
    tooltips.install(qapp)
    yield qapp
    tooltips.uninstall(qapp)


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

    import gc
    from firepro3d.text_item import editing_text_item
    ed = editing_text_item(scene)
    if ed is not None:
        # A test that left an inline-edit session live must not leak the
        # TextItem's caret QTimer / scene._editing_item marker into the next
        # test — abandon (not commit) since the test already made its
        # assertions and any further undo-stack write here would be spurious.
        scene._text_edit_ctl.abandon(ed)
    scene.cleanup()   # join the underlay DXF worker so it can't outlive the scene (#373)
    view.close()
    view.deleteLater()
    QApplication.processEvents()
    gc.collect()


@pytest.fixture
def section_scene_for(qapp):
    """Factory ``(direction="north") -> (model_scene, section_scene)``: a fresh
    Model_Space + LevelManager (Level 1 at 0.0) + uncalibrated ScaleManager
    (pixels_per_mm == 1.0), wrapped in a SectionScene bound to a cardinal
    marker (auto-extent).

    Usage in tests::

        def test_foo(qapp, section_scene_for):
            scene, elev = section_scene_for("north")
            ...
    """
    from firepro3d.model_space import Model_Space
    from firepro3d.level_manager import LevelManager
    from firepro3d.scale_manager import ScaleManager
    from firepro3d.section_scene import SectionScene
    from firepro3d.section_marker import SectionMarker, building_bbox

    def _factory(direction: str = "north"):
        ms = Model_Space()
        lm = LevelManager()            # seeds Level 1 (elevation 0.0) by default
        ms._level_manager = lm
        sm = ScaleManager()
        ms.scale_manager = sm
        marker = SectionMarker.for_cardinal(direction, building_bbox(ms))
        elev = SectionScene(marker, model_space=ms,
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
    calls: cleanup/rebuild/request_rebuild/get_3d_selected/delete_selected/
    show_radiation_heatmap/clear_radiation_heatmap/cancel_interaction/clear_pick/
    reset_for_project + the entitySelected signal.
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

        def cancel_interaction(self):
            pass

        def request_rebuild(self):
            pass

        def clear_pick(self):
            pass

        def reset_for_project(self, scale_manager):
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
