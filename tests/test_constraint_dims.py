"""CS4 Smart Dimension — headless guards (parametric-constraint-system D48–D55).

Real ``Model_Space(scene_role="block_editor")`` scenes and primitives."""
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d import constraint_dims as cd
from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.model_space import Model_Space


def _scene():
    return Model_Space(scene_role="block_editor")


def _line(sc, a, b):
    ln = LineItem(QPointF(*a), QPointF(*b))
    sc.addItem(ln); sc._draw_lines.append(ln)
    return ln


def _rect(sc, a, b):
    r = RectangleItem(QPointF(*a), QPointF(*b))
    sc.addItem(r); sc._draw_rects.append(r)
    return r


def _len(ln):
    return math.hypot(ln._pt2.x() - ln._pt1.x(), ln._pt2.y() - ln._pt1.y())


def E(it, h="edge"):
    return {"uid": it._uid, "h": h}


# ── Task 3: dim <-> readout mapping ─────────────────────────────────────────

def test_readout_key_maps_edges_to_their_readouts(qapp):
    sc = _scene()
    ln = _line(sc, (0, 0), (300, 0))
    r = _rect(sc, (0, 0), (400, 200))
    assert cd.readout_key(ln, "edge") == "length"
    assert cd.readout_key(r, "top") == cd.readout_key(r, "bottom") == "width"
    assert cd.readout_key(r, "left") == cd.readout_key(r, "right") == "height"
    assert cd.readout_key(ln, "p1") is None
