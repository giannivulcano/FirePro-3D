import json
import math
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath
from PyQt6.QtWidgets import QApplication
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.gridline import GridlineItem


@pytest.fixture
def ms_view(qapp):
    ms = Model_Space()
    view = Model_View(ms); view.resize(600, 600); view.resetTransform()
    view.centerOn(0, 0)
    QApplication.processEvents()
    yield ms, view
    view.hide()


def test_scene_has_move_ghost_attr(ms_view):
    ms, view = ms_view
    assert ms._move_ghost == []
    assert ms._inference_exclude_ids == set()


def test_drawforeground_survives_move_ghost(ms_view):
    ms, view = ms_view
    p = QPainterPath(); p.moveTo(0, 0); p.lineTo(0, 5000)
    ms._move_ghost = [p]
    view.viewport().repaint()  # Model_View.drawForeground runs block 8; must not raise
    # sanity: the override is the one in play
    assert isinstance(view, Model_View)
