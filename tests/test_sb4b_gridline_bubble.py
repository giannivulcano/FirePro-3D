"""SB4b -- plan gridline bubble drawn by an annotation block (design
docs/superpowers/specs/2026-11-02-sb4b-gridline-bubble-design.md)."""
import math

import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.block_attributes import normalise_attr
from firepro3d.block_definition import BlockDefinition
from firepro3d.gridline import GridlineItem
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space


def _scene():
    ms = Model_Space()
    ms._level_manager = LevelManager()
    return ms


def _gridline(ms, p1=(0.0, 0.0), p2=(0.0, 5000.0), label="A"):
    gl = GridlineItem(QPointF(*p1), QPointF(*p2), label)
    ms.addItem(gl)
    ms._gridlines.append(gl)
    return gl


CIRCLE_R = 4.75          # authored mm (9.5 mm across, D14)


def _bubble_def(ms, shape="circle", name="TestBubble"):
    """An eligible Gridline bubble: Annotative, Scale with zoom, host Gridline;
    *shape* 'circle' = a 4.75 mm circle, 'square' = a 12 x 6 mm rectangle
    (non-circular trim, G6); @[Mark] 3 mm centred. Mapped as the project default."""
    if shape == "circle":
        geom = {"type": "draw_circle", "cx": 0.0, "cy": 0.0, "radius": CIRCLE_R,
                "color": "token:auto", "lineweight": 1.0}
    else:
        geom = {"type": "draw_rectangle", "x": -6.0, "y": -3.0, "w": 12.0, "h": 6.0,
                "color": "token:auto", "lineweight": 1.0}
    text = {"type": "text", "text": "@[Mark]", "x": -5.0, "y": -2.0, "height_mm": 3.0,
            "wrap_width_mm": 10.0, "box_height_mm": 4.0, "align": "C", "valign": "M"}
    d = BlockDefinition.new(name=name, library="", series="", origin=(0.0, 0.0),
                            primitives=[geom, text])
    d.scale_mode = "annotative"
    d.host_category = "Gridline"
    d.attributes = [normalise_attr({"key": "Mark", "source": "host", "host_key": "Mark",
                                    "placeholder": ""})]
    ms.register_block_definition(d)
    ms.annotation_defaults["Gridline"] = d.id
    return d


def test_gridline_is_an_annotation_category_with_a_system_default(qapp):
    from firepro3d import system_blocks as sb
    assert "Gridline" in sb.ANNOTATION_CATEGORIES
    assert sb.SYSTEM_DEFAULTS["Gridline"] == "system-tags-gridlinebubble"
    assert sb.LABEL_FIELD["Gridline"] == "Mark"
    assert sb.PAINT_WHEN_BLANK == frozenset({"Gridline"})


def test_d3_blank_mark_still_paints_the_static_geometry(qapp):
    """A blank label keeps the circle: the static ops draw, the bound text is empty."""
    from firepro3d.bound_label import BoundLabelItem
    ms = _scene()
    _bubble_def(ms)
    gl = _gridline(ms, label="")
    lab = BoundLabelItem(gl)
    ops = lab._ops(1.0)
    assert ops and all(op.kind != "text" or op.path.isEmpty() for op in ops)
    assert any(op.kind == "stroke" for op in ops)


def test_q13_blank_room_name_still_paints_nothing(qapp):
    """The Q13 rule is unchanged for every other category."""
    from firepro3d.bound_label import BoundLabelItem
    from firepro3d.room import Room
    from tests.test_sb3_paper import _tag_def
    ms = _scene()
    _tag_def(ms)
    r = Room(boundary=[QPointF(-1000, -1000), QPointF(1000, -1000),
                       QPointF(1000, 1000), QPointF(-1000, 1000)])
    r.name = ""
    r.level = "Level 1"
    ms.addItem(r)
    ms._rooms.append(r)
    assert r._tag._ops(1.0) == []
