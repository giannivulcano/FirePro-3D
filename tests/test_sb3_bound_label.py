"""SB3 -- BoundLabelItem + the Room switch: AC1 (centroid + offset, annotative), AC2
(panel rename, empty Name paints nothing), Q13 (polygon HALO), paper hooks, Q4 DM
retirement, refresh hooks, AC8 (posted grip drag + undo)."""
# -- shared helpers (copy into each SB3 test file that uses them) -------------
import hashlib

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
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


from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QApplication

from firepro3d.annotative import reprepare_annotative
from firepro3d.property_manager import PropertyManager


def _grab(view):
    img = view.viewport().grab().toImage()      # viewport px = mapToScene px (view.grab() adds the 2 px frame)
    return img, (img.devicePixelRatio() or 1.0)


def test_ac1_tag_renders_at_centroid_plus_offset_and_scales_with_the_drawing_scale(qapp, shown_model_view):
    view, scene = shown_model_view                      # shown, m11 = 0.25, centred on the origin
    d = _tag_def(scene)
    room = _add_room(scene, "Office", -1000.0, -1000.0)   # centroid (0, 0): the vertex mean
    room._label_offset = QPointF(300.0, -200.0)
    room._update_label()
    qapp.processEvents()
    k = scene.scale_manager.drawing_scale               # 100.0
    g = _glyph_rect(d, room)                            # ops bbox at k = 1 (raw source)
    on, dpr = _grab(view)
    room._show_label = False
    room._update_label()
    qapp.processEvents()
    off, _ = _grab(view)
    x0, y0, x1, y1 = _diff_bbox(on, off)                # the tag's ink, device px
    cx, cy = (x0 + x1 + 1) / 2.0 / dpr, (y0 + y1 + 1) / 2.0 / dpr
    centre = view.mapToScene(int(round(cx)), int(round(cy)))
    want = QPointF(0.0 + 300.0 + g.center().x() * k, 0.0 - 200.0 + g.center().y() * k)
    assert abs(centre.x() - want.x()) <= 8.0 and abs(centre.y() - want.y()) <= 8.0   # 2 px at 0.25
    h_px = (y1 - y0 + 1) / dpr
    assert abs(h_px - g.height() * k * 0.25) <= 2.0     # 3 mm x 100 x 0.25 = 75 px for the test tag
    # Annotative: 1:200 doubles the ink (SB1c: k = drawing scale).
    room._show_label = True
    room._update_label()
    scene.scale_manager.drawing_scale = 200.0
    reprepare_annotative(scene)
    qapp.processEvents()
    on2, _ = _grab(view)
    _, y2, _, y3 = _diff_bbox(on2, off)
    assert abs((y3 - y2 + 1) / dpr - g.height() * 200.0 * 0.25) <= 2.0


def test_ac2_panel_rename_changes_the_rendered_tag_and_an_empty_name_paints_nothing(qapp):
    ms = _scene()
    _tag_def(ms)
    room = _add_room(ms, "Office")
    base = _digest(_render(ms, RECT, 300, 300))
    pm = PropertyManager()
    pm.show_properties(room)
    QApplication.processEvents()
    pm._apply_property("Room Name", "Lobby")
    assert room.name == "Lobby"
    assert _digest(_render(ms, RECT, 300, 300)) != base
    pm._apply_property("Room Name", "")
    empty = _digest(_render(ms, RECT, 300, 300))
    room._show_label = False
    room._update_label()
    assert _digest(_render(ms, RECT, 300, 300)) == empty        # no ink either way (Q13)
    assert not room._tag.paints()
    # Tear the panel down before the test ends: an unparented PropertyManager
    # still showing a Room kills a later QGraphicsView test (0xC0000409) --
    # reproduced at base 23512cb3 with no SB3 code.
    pm.show_properties(None)
    pm.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    del pm


def test_q13_labelled_room_is_a_halo_candidate_by_its_polygon(qapp):
    sc = _scene()
    _tag_def(sc)
    r = _add_room(sc, "R1")                                      # 0..2000 square, tag near (1000, 1000)
    pt = QPointF(150.0, 150.0)
    assert not r._tag.sceneBoundingRect().contains(pt)           # inside the polygon, off the tag
    assert r in sc.halo_candidates_at(pt, 4.0, QTransform())
    assert r in sc.rubber_band_hits(QRectF(50.0, 50.0, 200.0, 200.0), True)
    assert r._tag not in sc.halo_candidates_at(QPointF(1000.0, 1000.0), 4.0, QTransform())


def test_units_and_scale_hooks_walk_the_room_tags(qapp):
    ms = _scene()
    _tag_def(ms)
    room = _add_room(ms, "Office")
    h100 = room._tag.boundingRect().height() - 2 * PEN_MARGIN
    calls = []
    real = room._tag.prepareGeometryChange
    room._tag.prepareGeometryChange = lambda: (calls.append(1), real())[1]
    ms._refresh_all_labels()
    assert calls
    n = len(calls)
    ms.scale_manager.drawing_scale = 200.0
    reprepare_annotative(ms)
    assert len(calls) > n
    assert room._tag.boundingRect().height() - 2 * PEN_MARGIN == pytest.approx(2 * h100, rel=1e-6)


def test_grip_sits_on_the_tag_anchor_and_apply_grip_writes_label_offset(qapp):
    ms = _scene()
    _tag_def(ms)
    room = _add_room(ms, "Office")
    assert room.grip_points() == [QPointF(1000.0, 1000.0)]      # centroid: vertex mean of the square
    room.apply_grip(0, QPointF(1300.0, 800.0))
    assert room._label_offset == QPointF(300.0, -200.0)
    assert room._tag.pos() == QPointF(1300.0, 800.0)
    assert room.to_dict()["label_offset"] == [300.0, -200.0]
    room.set_property("Show Label", "False")
    assert room.grip_points() == [] and not room._tag.isVisible()
