"""Test fixtures for FirePro3D headless Qt tests.

Qt requires a single QApplication instance per process before any
QGraphicsScene / widget is instantiated, even when no window is shown.
This conftest provides a session-scoped fixture for it.
"""

from __future__ import annotations

import base64
import sys

import pytest
from PyQt6.QtWidgets import QApplication


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
