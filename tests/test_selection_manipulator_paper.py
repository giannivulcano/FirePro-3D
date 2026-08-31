"""Parity tests: SheetViewport resize via the SelectionManipulator (Task 7).

The paper scene adopts the model-scene SelectionManipulator. These tests prove
the manipulator-driven resize path reproduces the RETIRED
``SheetViewport._apply_grip_resize`` crop×scale semantics EXACTLY, keeps scale
fixed, produces one undo entry per gesture, and moves on paper via
``manip_translate``.

Ground-truth numbers were captured from the OLD ``_apply_grip_resize`` before it
was retired (see the module docstring in git history / the task report) and are
asserted here as literals so a future drift is caught.
"""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsRectItem
from PyQt6.QtCore import QRectF, QPointF

from firepro3d.paper_space import PaperScene, Sheet, SheetViewData
from firepro3d.manip_math import HandleRole
from tests.test_paper_viewport_crop import _resolver


def _make_scene(qapp):
    """A real PaperScene + one plan viewport bound to a real source scene.

    Source extent is (0,0,1000,500) but the QGraphicsRectItem's 0.5mm pen halo
    makes the seeded full-extent crop (-0.5,-0.5,1001,501); scale 0.1 → the
    on-paper size seeds at 100.1 x 50.1.
    """
    model = QGraphicsScene()
    model.addItem(QGraphicsRectItem(QRectF(0, 0, 1000, 500)))
    sheet = Sheet.create_default()
    data = SheetViewData("plan", "Level 1", "PLAN", 0.1, 0, 0, 0, 0)
    scene = PaperScene(sheet, _resolver(model))
    vp = scene.add_viewport(data)
    return scene, vp, data


# --------------------------------------------------------------------------- #
#  manip_scale reproduces the retired _apply_grip_resize numbers
# --------------------------------------------------------------------------- #

def test_viewport_manip_scale_matches_old_apply_grip_resize(qapp):
    """manip_scale for a BR-corner resize == the OLD _apply_grip_resize numbers.

    OLD ground truth (captured from _apply_grip_resize(BR, (+30,+20)) on the
    same fixture, before retirement):
        x=0, y=0, w=130.1, h=70.1, crop=(-0.5,-0.5,1301,701)
    The manipulator resizes about the corner opposite the dragged handle, so a
    BR drag anchors the TL corner at the on-paper (x, y). new_w/new_h grow by
    the same +30/+20 paper mm the old delta produced.
    """
    scene, vp, data = _make_scene(qapp)
    x0, y0, w0, h0 = data.x, data.y, data.w, data.h
    # BR drag by (+30, +20) paper mm → factors about the TL anchor.
    fx = (w0 + 30.0) / w0
    fy = (h0 + 20.0) / h0
    anchor = QPointF(x0, y0)      # TL corner (opposite the dragged BR handle)
    vp.manip_scale(fx, fy, anchor)

    cr = data.crop_rect
    assert data.x == pytest.approx(0.0, abs=1e-6)
    assert data.y == pytest.approx(0.0, abs=1e-6)
    assert data.w == pytest.approx(130.1, abs=1e-4)
    assert data.h == pytest.approx(70.1, abs=1e-4)
    assert (cr.x(), cr.y(), cr.width(), cr.height()) == pytest.approx(
        (-0.5, -0.5, 1301.0, 701.0), abs=1e-3)


def test_viewport_manip_scale_tl_matches_old(qapp):
    """manip_scale for a TL-corner resize == OLD _apply_grip_resize(TL,(+10,+5)).

    OLD ground truth: x=10, y=5, w=90.1, h=45.1, crop=(99.5,49.5,901,451).
    A TL drag anchors the BR corner on paper; x/y shift so the BR stays put.
    """
    scene, vp, data = _make_scene(qapp)
    x0, y0, w0, h0 = data.x, data.y, data.w, data.h
    # TL drag by (+10, +5): the TL edge moves in, shrinking on-paper size by
    # (10, 5); anchor is the BR corner (x0+w0, y0+h0).
    fx = (w0 - 10.0) / w0
    fy = (h0 - 5.0) / h0
    anchor = QPointF(x0 + w0, y0 + h0)
    vp.manip_scale(fx, fy, anchor)

    cr = data.crop_rect
    assert data.x == pytest.approx(10.0, abs=1e-4)
    assert data.y == pytest.approx(5.0, abs=1e-4)
    assert data.w == pytest.approx(90.1, abs=1e-4)
    assert data.h == pytest.approx(45.1, abs=1e-4)
    assert (cr.x(), cr.y(), cr.width(), cr.height()) == pytest.approx(
        (99.5, 49.5, 901.0, 451.0), abs=1e-3)


def test_viewport_resize_crop_at_fixed_scale(qapp):
    """A corner resize changes crop_rect, leaves scale UNCHANGED, and keeps the
    on-paper size == crop × scale invariant."""
    scene, vp, data = _make_scene(qapp)
    scale_before = data.scale
    crop_w_before = data.crop_rect.width()
    x0, y0, w0, h0 = data.x, data.y, data.w, data.h

    fx = (w0 + 30.0) / w0
    vp.manip_scale(fx, 1.0, QPointF(x0, y0))

    assert data.scale == scale_before                      # scale untouched
    assert data.crop_rect.width() == pytest.approx(crop_w_before + 300, abs=1.0)
    assert data.w == pytest.approx(data.crop_rect.width() * data.scale, abs=1e-4)
    assert data.h == pytest.approx(data.crop_rect.height() * data.scale, abs=1e-4)


# --------------------------------------------------------------------------- #
#  One undo per gesture via the paper commit hook (macro)
# --------------------------------------------------------------------------- #

def test_viewport_resize_one_geometry_command(qapp):
    """A full manipulator resize gesture pushes exactly one undo entry, and undo
    restores geometry exactly."""
    scene, vp, data = _make_scene(qapp)
    manip = scene._manipulator
    vp.setSelected(True)

    def _flat_geom(d):
        cr = d.crop_rect
        return (d.x, d.y, d.w, d.h,
                cr.x(), cr.y(), cr.width(), cr.height())

    before = _flat_geom(data)
    idx_before = scene.undo_stack.index()

    # Drive a released-drag resize through the manipulator's internal lifecycle
    # exactly like a handle press→move→release.
    manip.rebake()
    r0 = QRectF(manip._rect)
    anchor_scene = r0.topLeft()
    start = r0.bottomRight()
    manip._begin("resize", start, QPointF(0, 0), HandleRole.BOTTOM_RIGHT)
    from PyQt6.QtCore import Qt
    manip._moved = True
    manip._last_factors = ((r0.width() + 30.0) / r0.width(),
                           (r0.height() + 20.0) / r0.height())
    manip._finish(QPointF(start.x() + 30, start.y() + 20),
                  Qt.KeyboardModifier.NoModifier)

    assert scene.undo_stack.index() == idx_before + 1, "exactly one undo entry"
    assert data.w == pytest.approx(130.1, abs=1e-3)

    scene.undo_stack.undo()
    assert _flat_geom(data) == pytest.approx(before, abs=1e-4)


# --------------------------------------------------------------------------- #
#  manip_translate moves on paper
# --------------------------------------------------------------------------- #

def test_viewport_move_translates_on_paper(qapp):
    """manip_translate shifts the viewport's on-paper x/y."""
    scene, vp, data = _make_scene(qapp)
    x0, y0 = data.x, data.y
    vp.manip_translate(15.0, -7.0)
    assert data.x == pytest.approx(x0 + 15.0, abs=1e-6)
    assert data.y == pytest.approx(y0 - 7.0, abs=1e-6)
    # The Qt item position tracks the data (mirrors the retired move path).
    assert vp.pos().x() == pytest.approx(x0 + 15.0, abs=1e-6)
    assert vp.pos().y() == pytest.approx(y0 - 7.0, abs=1e-6)


def test_viewport_move_gesture_one_undo_entry(qapp):
    """A full manipulator MOVE gesture (press→move→release) translates the
    viewport, pushes exactly one undo entry (macro), and undo restores it."""
    from PyQt6.QtWidgets import QGraphicsView
    from PyQt6.QtCore import Qt
    from firepro3d.manip_math import move_delta
    scene, vp, data = _make_scene(qapp)
    _view = QGraphicsView(scene)      # manipulator needs a live view
    vp.setSelected(True)
    manip = scene._manipulator
    manip.rebake()
    assert vp in manip.selection_items()
    x0, y0 = data.x, data.y
    idx0 = scene.undo_stack.index()

    c = manip._rect.center()
    manip._begin("move", c, QPointF(0, 0))
    manip._moved = True
    manip._apply(move_delta(c, QPointF(c.x() + 25, c.y() - 10), ortho=False))
    manip._finish(QPointF(c.x() + 25, c.y() - 10), Qt.KeyboardModifier.NoModifier)

    assert data.x == pytest.approx(x0 + 25, abs=1e-6)
    assert data.y == pytest.approx(y0 - 10, abs=1e-6)
    assert scene.undo_stack.index() == idx0 + 1
    scene.undo_stack.undo()
    assert data.x == pytest.approx(x0, abs=1e-6)
    assert data.y == pytest.approx(y0, abs=1e-6)


def test_viewport_manip_bounds_is_on_paper_rect(qapp):
    """manip_bounds() is the on-paper (x, y, w, h) rect."""
    scene, vp, data = _make_scene(qapp)
    b = vp.manip_bounds()
    assert (b.x(), b.y(), b.width(), b.height()) == pytest.approx(
        (data.x, data.y, data.w, data.h), abs=1e-6)


def test_detail_viewport_has_no_scale_capability(qapp):
    """A detail viewport's extent is marker-owned: no manip_scale handles."""
    from firepro3d.selection_manipulator import item_capabilities
    model = QGraphicsScene()
    from tests.test_paper_viewport_crop import _FakeMarker
    markers = {"D1": _FakeMarker(QRectF(0, 0, 100, 100))}
    sheet = Sheet.create_default()
    data = SheetViewData("detail", "D1", "DET", 0.2, 0, 0, 0, 0)
    scene = PaperScene(sheet, _resolver(model, markers))
    vp = scene.add_viewport(data)
    assert "scale" not in item_capabilities(vp)
    # Paper viewports never rotate in v1.
    assert "rotate" not in item_capabilities(vp)


# =========================================================================== #
#  Task 8: sheet TEXT resize via the SelectionManipulator (box-model parity)
#
#  These prove TextAnnotationItem.manip_scale reproduces the RETIRED 8-handle
#  grip-resize box/wrap/pinned-edge model EXACTLY. Ground truth was captured by
#  driving the OLD mouse-move resize branch before it was retired; the numbers
#  are asserted here as literals so a future drift is caught.
#
#  OLD box/wrap/pinned-edge contract (captured on the default fixture below,
#  wrap=50 box_h=0, content height 29.170313 mm):
#    - manip_bounds box = (x, y, wrap_or_content_w, box_h_or_content_h).
#    - Horizontal: RIGHT handle pins left (x fixed), only wrap changes; LEFT
#      handle pins the right edge (x shifts), wrap changes. new_w >= 5 mm
#      (MIN_TEXT_WRAP_WIDTH_MM).
#    - Vertical: BOTTOM handle pins top (y fixed), only box_h changes; TOP
#      handle pins the bottom edge (y shifts), box_h changes. new_h >= content
#      height (the auto-height seed / clamp). box_h==0 seeds from content height.
#    - Mid-edge handle touches ONE axis only (MR never seeds box_h; BM never
#      seeds wrap) — mirrored by only writing the axis whose factor != 1.
#    - Font height_mm is never touched.
#  OLD ground-truth tuples (x, y, wrap, box_h):
#    BR(+20,+15)  -> (10, 10, 70,     44.1703)
#    TL(+10,+5)   -> (20, 15, 50,     55)       [wrap60 box60 start]
#    MR(+20)      -> (10, 10, 70,     0)
#    BM(+20)      -> (10, 10, 50,     49.1703)
#    MR minclamp  -> wrap == 5
#    BM content   -> box_h == 29.1703 (content-height clamp)
# =========================================================================== #

from firepro3d.paper_space import TextAnnotationItem, TextAnnotationData


def _text_scene(qapp, wrap=50.0, box_h=0.0):
    """A real PaperScene + one selected TextAnnotationItem at (10, 10)."""
    from tests.test_paper_annotations import _stub_resolver
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    data = TextAnnotationData(text="word " * 10, x=10.0, y=10.0,
                              wrap_width_mm=wrap, box_height_mm=box_h)
    item = TextAnnotationItem(data)
    scene.addItem(item)
    item.setPos(10.0, 10.0)
    item.setSelected(True)
    return scene, item, data


def test_text_resize_matches_old_on_box_resized(qapp):
    """manip_scale for a BR corner AND an MR edge == OLD grip-resize numbers.

    BR(+20,+15): TL anchored, wrap 50->70, box_h 0->content+15 (44.1703).
    MR(+20): left anchored, only wrap 50->70; box_h STAYS 0 (axis isolation).
    """
    # --- BR corner (both axes) ---
    # box_h==0 seeds from the content height, which is font-metric dependent
    # (varies by platform); assert the OLD arithmetic (content + delta) relative
    # to the live content height rather than a hardcoded literal.
    scene, item, data = _text_scene(qapp)
    b = item.manip_bounds()
    w0, h0 = b.width(), b.height()
    content_h = item._content_height_mm()
    assert w0 == pytest.approx(50.0, abs=1e-4)         # wrap is exact (set field)
    assert h0 == pytest.approx(content_h, abs=1e-4)    # auto height == content
    fx = (w0 + 20.0) / w0
    fy = (h0 + 15.0) / h0
    item.manip_scale(fx, fy, QPointF(b.x(), b.y()))   # anchor = TL corner
    assert (data.x, data.y, data.wrap_width_mm) == pytest.approx(
        (10.0, 10.0, 70.0), abs=1e-3)
    assert data.box_height_mm == pytest.approx(content_h + 15.0, abs=1e-3)

    # --- MR edge (horizontal only) ---
    scene, item, data = _text_scene(qapp)
    b = item.manip_bounds()
    w0 = b.width()
    fx = (w0 + 20.0) / w0
    anchor = QPointF(b.x(), b.y() + b.height() / 2)   # ML edge
    item.manip_scale(fx, 1.0, anchor)
    assert (data.x, data.y, data.wrap_width_mm, data.box_height_mm) == \
        pytest.approx((10.0, 10.0, 70.0, 0.0), abs=1e-3), \
        "MR is horizontal-only: box_height_mm must stay 0 (axis isolation)"


def test_text_resize_tl_pins_bottom_right(qapp):
    """manip_scale for a TL corner == OLD grip-resize (BR pinned, x/y shift)."""
    scene, item, data = _text_scene(qapp, wrap=60.0, box_h=60.0)
    b = item.manip_bounds()
    w0, h0 = b.width(), b.height()
    fx = (w0 - 10.0) / w0
    fy = (h0 - 5.0) / h0
    anchor = QPointF(b.x() + w0, b.y() + h0)          # BR corner pinned
    item.manip_scale(fx, fy, anchor)
    assert (data.x, data.y, data.wrap_width_mm, data.box_height_mm) == \
        pytest.approx((20.0, 15.0, 50.0, 55.0), abs=1e-3)


def test_text_resize_one_command_and_undo(qapp):
    """A full manipulator resize gesture -> one ResizeTextBoxCommand; undo
    restores x/y/wrap/box_height exactly."""
    from PyQt6.QtWidgets import QGraphicsView
    from PyQt6.QtCore import Qt
    scene, item, data = _text_scene(qapp)
    _view = QGraphicsView(scene)                       # manipulator needs a view
    manip = scene._manipulator
    manip.rebake()
    assert item in manip.selection_items()

    before = (data.x, data.y, data.wrap_width_mm, data.box_height_mm)
    content_h = item._content_height_mm()
    idx0 = scene.undo_stack.index()

    r0 = QRectF(manip._rect)
    anchor = r0.topLeft()                              # BR drag anchors TL
    start = r0.bottomRight()
    manip._begin("resize", start, QPointF(0, 0), HandleRole.BOTTOM_RIGHT)
    manip._moved = True
    manip._last_factors = ((r0.width() + 20.0) / r0.width(),
                           (r0.height() + 15.0) / r0.height())
    manip._finish(QPointF(start.x() + 20, start.y() + 15),
                  Qt.KeyboardModifier.NoModifier)

    assert scene.undo_stack.index() == idx0 + 1, "exactly one undo entry"
    assert data.wrap_width_mm == pytest.approx(70.0, abs=1e-3)
    assert data.box_height_mm == pytest.approx(content_h + 15.0, abs=1e-3)

    scene.undo_stack.undo()
    assert (data.x, data.y, data.wrap_width_mm, data.box_height_mm) == \
        pytest.approx(before, abs=1e-4)


def test_text_move_translates(qapp):
    """manip_translate shifts x/y and the Qt item position; a full move gesture
    pushes exactly one undo entry and undo restores the anchor."""
    from PyQt6.QtWidgets import QGraphicsView
    from PyQt6.QtCore import Qt
    from firepro3d.manip_math import move_delta

    # Direct bake
    scene, item, data = _text_scene(qapp)
    x0, y0 = data.x, data.y
    item.manip_translate(15.0, -7.0)
    assert (data.x, data.y) == pytest.approx((x0 + 15.0, y0 - 7.0), abs=1e-6)
    assert (item.pos().x(), item.pos().y()) == \
        pytest.approx((x0 + 15.0, y0 - 7.0), abs=1e-6)

    # Full gesture: one undo entry, wrap/box unchanged
    scene, item, data = _text_scene(qapp)
    _view = QGraphicsView(scene)
    manip = scene._manipulator
    manip.rebake()
    x0, y0 = data.x, data.y
    w0, bh0 = data.wrap_width_mm, data.box_height_mm
    idx0 = scene.undo_stack.index()
    c = manip._rect.center()
    manip._begin("move", c, QPointF(0, 0))
    manip._moved = True
    manip._apply(move_delta(c, QPointF(c.x() + 25, c.y() - 10), ortho=False))
    manip._finish(QPointF(c.x() + 25, c.y() - 10), Qt.KeyboardModifier.NoModifier)

    assert (data.x, data.y) == pytest.approx((x0 + 25, y0 - 10), abs=1e-6)
    assert (data.wrap_width_mm, data.box_height_mm) == (w0, bh0)
    assert scene.undo_stack.index() == idx0 + 1
    scene.undo_stack.undo()
    assert (data.x, data.y) == pytest.approx((x0, y0), abs=1e-6)


def test_text_min_size_clamp(qapp):
    """Resizing below the mins clamps as the OLD grip drag did: wrap >= 5 mm,
    box_height >= content height."""
    from firepro3d.constants import MIN_TEXT_WRAP_WIDTH_MM
    # Width clamp (MR dragged well left of the min)
    scene, item, data = _text_scene(qapp)
    b = item.manip_bounds()
    fx = 2.0 / b.width()                               # target 2 mm < 5 mm min
    item.manip_scale(fx, 1.0, QPointF(b.x(), b.y() + b.height() / 2))
    assert data.wrap_width_mm == pytest.approx(MIN_TEXT_WRAP_WIDTH_MM, abs=1e-6)

    # Height clamp (BM shrunk below content height)
    scene, item, data = _text_scene(qapp, box_h=30.0)
    b = item.manip_bounds()
    content_h = item._content_height_mm()
    fy = 1.0 / b.height()                              # target 1 mm < content
    item.manip_scale(1.0, fy, QPointF(b.x() + b.width() / 2, b.y()))
    assert data.box_height_mm == pytest.approx(content_h, abs=1e-3)


def test_text_manip_bounds_is_box_rect(qapp):
    """manip_bounds() is the on-paper text-box rect (wrap x box height)."""
    scene, item, data = _text_scene(qapp, wrap=60.0, box_h=40.0)
    b = item.manip_bounds()
    assert (b.x(), b.y(), b.width(), b.height()) == \
        pytest.approx((10.0, 10.0, 60.0, 40.0), abs=1e-4)


def test_text_has_scale_translate_no_rotate(qapp):
    """Sheet text exposes scale + translate but never rotate in v1."""
    from firepro3d.selection_manipulator import item_capabilities
    scene, item, data = _text_scene(qapp)
    caps = item_capabilities(item)
    assert "scale" in caps
    assert "translate" in caps
    assert "rotate" not in caps


def test_text_resize_font_height_untouched(qapp):
    """No manip_scale touches height_mm (font cap height)."""
    from tests.test_paper_annotations import _stub_resolver
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    data = TextAnnotationData(text="word " * 10, x=10.0, y=10.0,
                              wrap_width_mm=50.0, height_mm=4.7625)
    item = TextAnnotationItem(data)
    scene.addItem(item)
    item.setPos(10.0, 10.0)
    orig_h = data.height_mm
    b = item.manip_bounds()
    fx = (b.width() + 10.0) / b.width()
    fy = (b.height() + 10.0) / b.height()
    item.manip_scale(fx, fy, QPointF(b.x(), b.y()))
    assert data.height_mm == pytest.approx(orig_h, abs=1e-9)
