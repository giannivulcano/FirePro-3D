"""Candidate-whitelist API: only_types + item_filter (SNAP refinement)."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsScene
from firepro3d.snap_engine import SnapEngine
from firepro3d.construction_geometry import LineItem, CircleItem


def _x(scale=1.0):
    t = QTransform(); t.scale(scale, scale); return t


def test_only_types_center_ignores_endpoints(qapp):
    scene = QGraphicsScene()
    line = LineItem(QPointF(0.0, 0.0), QPointF(100.0, 0.0))   # endpoint at (0,0)
    circ = CircleItem(QPointF(0.0, 0.0), 30.0)                # center at (0,0)
    scene.addItem(line); scene.addItem(circ)
    eng = SnapEngine()
    res = eng.find(QPointF(2.0, 2.0), scene, _x(), only_types={"center"})
    assert res is not None and res.snap_type == "center"


def test_item_filter_excludes_non_matching_items(qapp):
    scene = QGraphicsScene()
    keep = CircleItem(QPointF(0.0, 0.0), 30.0)
    drop = LineItem(QPointF(0.0, 0.0), QPointF(100.0, 0.0))
    scene.addItem(keep); scene.addItem(drop)
    eng = SnapEngine()
    res = eng.find(QPointF(2.0, 2.0), scene, _x(),
                   item_filter=lambda it: it is keep)
    assert res is not None and res.source_item is keep
