"""Shared helpers for the gridline-hosted blocks guards."""
from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from firepro3d.gridline import GridlineItem


def gridline(ms, p, q, label):
    gl = GridlineItem(QPointF(*p), QPointF(*q), label=label)
    ms._gridlines.append(gl)
    ms.addItem(gl)
    return gl


def defn(ms, name="A"):
    d = BlockDefinition.new(name=name, library="L", series="S",
        primitives=[{"type": "draw_line", "pt1": [0, 0], "pt2": [100, 0],
                     "color": "#ffffff", "lineweight": 1.0}], origin=(0.0, 0.0))
    ms.register_block_definition(d)
    return d
