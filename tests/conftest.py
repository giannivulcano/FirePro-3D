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
    view.resetTransform()
    view.centerOn(0, 0)
    view.show()
    QTest.qWaitForWindowExposed(view)
    view.setFocus()
    QApplication.processEvents()

    yield view, scene

    view.close()


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
