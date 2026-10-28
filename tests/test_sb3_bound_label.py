"""SB3 -- BoundLabelItem + the Room switch: AC1 (centroid + offset, annotative), AC2
(panel rename, empty Name paints nothing), Q13 (polygon HALO), paper hooks, Q4 DM
retirement, refresh hooks, AC8 (posted grip drag + undo)."""
# -- shared helpers (copy into each SB3 test file that uses them) -------------
import hashlib

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter

from firepro3d.block_attributes import normalise_attr
from firepro3d.block_definition import BlockDefinition
from firepro3d.room import Room

TAG_MM = 3.0            # the test tag's authored cap height (printed mm)


def _tag_def(ms, name="TestTag", height=TAG_MM):
    """An eligible Room tag: Annotative, Scale with zoom, host Room, one
    @[Name] text; mapped as the project's Room annotation default."""
    d = BlockDefinition.new(name=name, library="", series="", origin=(0.0, 0.0),
                            primitives=[{"type": "text", "text": "@[Name]", "x": 0.0,
                                         "y": 0.0, "height_mm": height}])
    d.scale_mode = "annotative"
    d.host_category = "Room"
    d.attributes = [normalise_attr({"key": "Name", "source": "host", "host_key": "Name"})]
    ms.register_block_definition(d)
    ms.annotation_defaults["Room"] = d.id
    return d


def _add_room(ms, name, x0=0.0, y0=0.0, w=2000.0, h=2000.0):
    r = Room(boundary=[QPointF(x0, y0), QPointF(x0 + w, y0),
                       QPointF(x0 + w, y0 + h), QPointF(x0, y0 + h)])
    r.name = name
    r.level = "Level 1"
    r._scale_manager_ref = ms.scale_manager
    ms.addItem(r)
    ms._rooms.append(r)
    r._update_label()
    return r


def _render(scene, rect, w, h, bg=0xFF101010):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(bg)
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, w, h), rect, Qt.AspectRatioMode.IgnoreAspectRatio)
    p.end()
    return img


def _digest(img):
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    return hashlib.sha256(bytes(ptr)).hexdigest()


def _diff_bbox(a, b):
    """(x0, y0, x1, y1) of the pixels that differ between same-size images a, b."""
    assert a.size() == b.size()
    xs, ys = [], []
    for y in range(a.height()):
        for x in range(a.width()):
            if a.pixel(x, y) != b.pixel(x, y):
                xs.append(x)
                ys.append(y)
    assert xs, "no pixel differs"
    return min(xs), min(ys), max(xs), max(ys)


import pytest
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.block_attributes import bound_text_ops
from firepro3d.bound_label import PEN_MARGIN, PLACEHOLDER_MM, BoundLabelItem
from firepro3d.element_params import host_values
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space

RECT = QRectF(-500.0, -500.0, 3000.0, 3000.0)       # the 2000 x 2000 test room + margin


def _scene():
    ms = Model_Space()
    ms._level_manager = LevelManager()
    return ms


def _glyph_rect(d, room):
    """The tag's ops bbox at k = 1 (the raw source of every expected size)."""
    ops, _c = bound_text_ops(d, {}, host_values(room), False, 1.0, None, None)
    r = QRectF()
    for op in ops:
        r = r.united(op.path.boundingRect())
    return r


def test_tag_bounds_are_the_ops_bbox_times_the_drawing_scale(qapp):
    ms = _scene()
    d = _tag_def(ms)
    room = _add_room(ms, "Office")
    tag = room._tag
    assert isinstance(tag, BoundLabelItem) and tag.parentItem() is room
    assert tag.paints()
    k = ms.scale_manager.drawing_scale                       # 100.0 (ScaleManager default)
    g = _glyph_rect(d, room)
    br = tag.boundingRect().adjusted(PEN_MARGIN, PEN_MARGIN, -PEN_MARGIN, -PEN_MARGIN)
    assert br.height() == pytest.approx(g.height() * k, rel=1e-6)
    assert br.width() == pytest.approx(g.width() * k, rel=1e-6)
    assert not (tag.flags() & tag.GraphicsItemFlag.ItemIsSelectable)
    assert tag not in ms._block_instances


def test_tag_paints_nothing_when_every_host_field_is_empty(qapp):
    ms = _scene()
    _tag_def(ms)
    room = _add_room(ms, "")
    assert not room._tag.paints() and room._tag.boundingRect().isNull()


def test_tag_draws_the_orphan_placeholder_only_under_a_resolver(qapp):
    ms = _scene()                                            # resolver present, nothing mapped
    room = _add_room(ms, "Office")
    assert room._tag.definition() is None
    assert room._tag.boundingRect().width() == pytest.approx(PLACEHOLDER_MM + 2 * PEN_MARGIN)
    plain = QGraphicsScene()                                 # no resolver: nothing
    r2 = Room(boundary=[QPointF(0, 0), QPointF(2000, 0), QPointF(2000, 2000), QPointF(0, 2000)])
    r2.name = "X"
    plain.addItem(r2)
    r2._update_label()
    assert r2._tag.boundingRect().isNull()
