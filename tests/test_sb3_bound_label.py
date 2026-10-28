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
    assert room._tag.boundingRect().height() - 2 * PEN_MARGIN == pytest.approx(h100, rel=1e-6)  # re-cached
    ms.scale_manager.drawing_scale = 200.0
    reprepare_annotative(ms)
    assert len(calls) > n
    # the cached rect must have been dropped and RECOMPUTED at the new scale
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


from firepro3d.paper_display import (PaperColorMode, apply_paper_overrides,
                                     load_paper_categories, resolve_line_weight_mm,
                                     restore_model_display, save_paper_color_mode)


def test_paper_pass_routes_the_tag_through_apply_block_and_restores_it(qapp):
    ms = _scene()
    _tag_def(ms)
    room = _add_room(ms, "R101", 0.0, 0.0, 6000.0, 4000.0)
    tag = room._tag
    save_paper_color_mode(PaperColorMode.BW)
    h_model = tag.boundingRect().height() - 2 * PEN_MARGIN          # authored x drawing scale 100
    lw = resolve_line_weight_mm(load_paper_categories()["Room"]["line_weight"])
    saved = apply_paper_overrides(ms, QRectF(0, 0, 6000, 4000), paper_scale=0.02)
    try:
        assert tag._paper_scale == 0.02
        assert tag._paper_pen_width == pytest.approx(lw / 0.02)
        assert tag._paper_pen_color is not None                     # B&W forces the category colour
        assert tag.opacity() == 1.0                                  # the Room row opacity is the parent's
        assert tag.boundingRect().height() - 2 * PEN_MARGIN == pytest.approx(h_model / 2.0, rel=1e-6)  # k = 1/S = 50
    finally:
        restore_model_display(saved)
    assert (tag._paper_scale, tag._paper_pen_width, tag._paper_pen_color) == (None, None, None)
    assert tag.boundingRect().height() - 2 * PEN_MARGIN == pytest.approx(h_model, rel=1e-6)


def test_hidden_tag_is_skipped_by_the_paper_pass(qapp):
    ms = _scene()
    _tag_def(ms)
    room = _add_room(ms, "R101", 0.0, 0.0, 6000.0, 4000.0)
    room.set_property("Show Label", "False")
    saved = apply_paper_overrides(ms, QRectF(0, 0, 6000, 4000), paper_scale=0.02)
    try:
        assert room._tag._paper_scale is None
    finally:
        restore_model_display(saved)


def _tag_ink(tag):
    """Digest of the tag painted directly (paint_ops under paint_resolver)."""
    from PyQt6.QtWidgets import QStyleOptionGraphicsItem
    r = tag.boundingRect()
    img = QImage(int(r.width()) + 1, int(r.height()) + 1, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    p.translate(-r.left(), -r.top())
    tag.paint(p, QStyleOptionGraphicsItem(), None)
    p.end()
    return _digest(img)


def test_q4_room_row_font_retired_and_the_row_colour_never_tints_the_tag(qapp):
    from firepro3d.display_manager import _CATEGORY_MAP, _category_has_font, apply_display_to_item
    assert _CATEGORY_MAP["Room"]["font"] is None and _category_has_font("Room") is False
    ms = _scene()
    _tag_def(ms)
    room = _add_room(ms, "Office")
    before = _tag_ink(room._tag)
    apply_display_to_item(room, "#ff0000", 1.0, 100, True, fill_color=None, font_size=36)
    assert _tag_ink(room._tag) == before


from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QMouseEvent


def _post_mouse(view, etype, scene_pos, button=Qt.MouseButton.LeftButton, buttons=None,
                modifiers=Qt.KeyboardModifier.NoModifier):
    """Post a real QMouseEvent to the viewport (tests/test_manip_u2_parity.py idiom)."""
    app = QApplication.instance()
    vp = view.viewport()
    p = view.mapFromScene(scene_pos)
    if buttons is None:
        buttons = (Qt.MouseButton.NoButton if etype == QEvent.Type.MouseButtonRelease
                   else Qt.MouseButton.LeftButton)
    ev = QMouseEvent(etype, p.toPointF(), vp.mapToGlobal(p).toPointF(), button, buttons, modifiers)
    app.sendEvent(vp, ev)
    app.processEvents()


def test_ac8_dragging_the_tag_grip_through_the_view_writes_label_offset_and_undo_restores(qapp, shown_model_view):
    view, scene = shown_model_view
    _tag_def(scene)
    room = _add_room(scene, "Office", -1000.0, -1000.0)        # centroid (0, 0), on the viewport
    scene.push_undo_state()                                    # the pre-drag state undo returns to
    scene.set_mode("select")
    assert scene.mode in (None, "select") and not scene.is_input_mode() and scene.active_hud() is None
    scene.clearSelection()
    room.setSelected(True)
    qapp.processEvents()
    manip = scene._live_manip()
    manip.rebake()
    qapp.processEvents()
    grip = QPointF(room.grip_points()[0])
    assert view.viewport().rect().contains(view.mapFromScene(grip))   # on-viewport precondition
    assert manip.hit_handle(grip)                                     # the press will land on the handle
    end = QPointF(grip.x() + 300.0, grip.y() + 200.0)                 # 75 x 50 px at 0.25: past the drag threshold
    _post_mouse(view, QEvent.Type.MouseButtonPress, grip)
    _post_mouse(view, QEvent.Type.MouseMove, QPointF(grip.x() + 120.0, grip.y() + 80.0))
    _post_mouse(view, QEvent.Type.MouseMove, end)
    _post_mouse(view, QEvent.Type.MouseButtonRelease, end)
    moved = scene._rooms[0]
    assert moved._label_offset.x() == pytest.approx(300.0, abs=4.0)    # 1 px at 0.25 = 4 mm
    assert moved._label_offset.y() == pytest.approx(200.0, abs=4.0)
    assert moved._tag.pos() == moved.grip_points()[0]
    assert scene.can_undo()
    scene.undo()
    assert scene._rooms[0]._label_offset == QPointF(0.0, 0.0)


# -- G2 fix round (F1-F4) ---------------------------------------------------
def _red_pixels(img):
    """Count of pixels equal to the orphan placeholder colour (192, 57, 43)."""
    return sum(1 for y in range(img.height()) for x in range(img.width())
               if (img.pixel(x, y) & 0xFFFFFF) == 0xC0392B)


def test_f1_orphan_placeholder_needs_a_label_to_lose(qapp):
    ms = _scene()                                            # resolver present, nothing mapped
    named = _add_room(ms, "Office")
    assert named._tag.paints() and _red_pixels(_render(ms, RECT, 300, 300)) > 0
    named.set_property("Room Name", "")                      # nameless: nothing to lose
    assert not named._tag.paints() and named._tag.boundingRect().isNull()
    assert _red_pixels(_render(ms, RECT, 300, 300)) == 0


def test_f2_degenerate_room_hides_its_tag(qapp):
    ms = _scene()
    _tag_def(ms)
    r = Room(boundary=[])
    r.name = "Ghost"
    ms.addItem(r)
    ms._rooms.append(r)
    r._update_label()
    assert not r._tag.isVisible()
    before = _digest(_render(ms, RECT, 300, 300))
    r._show_label = False
    r._update_label()
    assert _digest(_render(ms, RECT, 300, 300)) == before   # no ink either way


def test_f3_unknown_host_key_draws_the_field_placeholder(qapp):
    ms = _scene()
    d = _tag_def(ms)
    d.attributes = [normalise_attr({"key": "Name", "source": "host", "host_key": "NoSuchKey"})]
    room = _add_room(ms, "Office")
    assert room._tag.paints()
    shown = _digest(_render(ms, RECT, 300, 300))
    room._show_label = False
    room._update_label()
    assert _digest(_render(ms, RECT, 300, 300)) != shown     # the "?" glyphs are ink


def test_f4_bounds_are_cached_until_refresh_or_the_paper_scale_changes(qapp):
    ms = _scene()
    _tag_def(ms)
    room = _add_room(ms, "Office")
    tag = room._tag
    r1 = tag.boundingRect()
    calls = []
    real = tag._compute_rect
    tag._compute_rect = lambda: (calls.append(1), real())[1]
    assert tag.boundingRect() == r1 and tag.shape().boundingRect() == r1 and not calls
    tag.set_anchor(QPointF(5.0, 5.0))
    assert tag.boundingRect() == r1 and not calls            # pos only
    tag.refresh()
    tag.boundingRect()
    assert len(calls) == 1
    tag._paper_scale = 0.02
    tag.boundingRect()
    assert len(calls) == 2
    tag._paper_scale = None
    assert tag.boundingRect() == r1 and len(calls) == 3
    assert BoundLabelItem(room).boundingRect() is not None   # scene-attached child, no crash


def test_host_values_keys_filter_matches_the_full_call_field_by_field(qapp):
    """G5 fix: the tag evaluates only the bound fields; the filtered values are
    the full call's values and the full call's key set is unchanged."""
    ms = _scene()
    room = _add_room(ms, "Office")
    full = host_values(room)
    part = host_values(room, keys={"Name"})
    assert list(part) == ["Name"] and part["Name"].raw == "Office"
    for k, v in part.items():
        assert (v.raw, v.kind, v.text) == (full[k].raw, full[k].kind, full[k].text)
    assert set(host_values(room, keys=set())) == set()
    assert {"Name", "Area", "Volume", "CeilingHeight"} <= set(full)
    assert list(host_values(room, keys=None)) == list(full)


def test_rename_through_set_property_redraws_and_empty_name_stops_painting(qapp):
    ms = _scene()
    _tag_def(ms)
    room = _add_room(ms, "Office")
    tag = room._tag
    d1 = _digest(_render(ms, RECT, 300, 300))
    room.set_property("Room Name", "Boardroom")
    d2 = _digest(_render(ms, RECT, 300, 300))
    assert d2 != d1 and tag.paints()
    room.set_property("Room Name", "")
    d3 = _digest(_render(ms, RECT, 300, 300))
    assert not tag.paints() and tag.boundingRect().isNull()
    assert d3 not in (d1, d2)
    room.set_property("Room Name", "Office")
    assert tag.paints() and _digest(_render(ms, RECT, 300, 300)) == d1
