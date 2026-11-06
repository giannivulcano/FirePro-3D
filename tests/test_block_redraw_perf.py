"""Schematic redraw: no false cover clip, cached corner wedges."""
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QTransform
from PyQt6.QtWidgets import QGraphicsView

import firepro3d.block_instance as bi
import firepro3d.stroke_style as ss
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import RectangleItem
from firepro3d.model_space import Model_Space
from tests._block_stack_helpers import ink, lines_def, rect_def, render

VIEW = QRectF(-20, -60, 260, 180)
CORNER = [((0, 0), (100, 0)), ((100, 0), (100, 100))]    # joined at (100, 0)


@pytest.fixture
def be(qapp):
    s = Model_Space(scene_role="block_editor")
    s.opaque_blocks = True
    yield s
    s.cleanup()


def _stack(be, mask_x):
    """A joined corner under an opaque rect whose left edge is at *mask_x*."""
    a = be.place_block_instance(lines_def(be, "Corner", CORNER).id, (0.0, 0.0))
    b = be.place_block_instance(rect_def(be, "Top").id, (mask_x, -30.0))
    return a, b


def _spy_keep(monkeypatch):
    calls = []
    real = bi.keep_path
    monkeypatch.setattr(bi, "keep_path", lambda f, c: (calls.append(1), real(f, c))[1])
    return calls


def _view(be, zoom):
    v = QGraphicsView(be)
    v.scale(zoom, zoom)
    return v


@pytest.mark.parametrize("zoom, mask_x, clips", [(1.0, 106.0, 0), (0.25, 106.0, 1)])
def test_cover_clip_follows_the_ink_reach_at_this_zoom(be, monkeypatch, zoom, mask_x, clips):
    """A 1 px corner reaches 2.06 px, so the rect ends at x = 102.56 at zoom 1 and
    108.74 at zoom 0.25 (frame 102 + reach + weld 0.5 - margin 2). The worst-case
    41 px pad would clip at both. Observable: the real paint path calls
    ``keep_path`` only when a mask can touch ink."""
    a, _b = _stack(be, mask_x)
    monkeypatch.setattr(ss, "canvas_px", lambda w: 1.0)
    monkeypatch.setattr(bi, "canvas_px", lambda w: 1.0)
    v = _view(be, zoom)
    calls = _spy_keep(monkeypatch)
    try:
        render(be, VIEW)
    finally:
        v.setScene(None)
    assert len(calls) == clips


def _thin_rect_def(be):
    """An opaque-able rect whose own outline is ``Thin``: at the same 20 px as
    the block below, its stroke would paint over the ink a guard measures."""
    it = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    it.style["weight"] = "Thin"
    d = BlockDefinition.new(name="Thin Top", library="L", series="S",
                            primitives=[it.to_dict()], origin=(0.0, 0.0))
    be.register_block_definition(d)
    return d


def test_a_mask_inside_a_wide_wedge_still_hides_it(be, monkeypatch):
    """20 px pen under a 2x render: the stroke reaches 5 mm past x = 100, past
    the 2 mm frame margin. A mask starting at x = 103 must still hide it. The
    column x 104..105 is inside the mask, clear of its 1 mm outline."""
    px = lambda w: 2.0 if w == "Thin" else 20.0
    monkeypatch.setattr(ss, "canvas_px", px)
    monkeypatch.setattr(bi, "canvas_px", px)
    a = be.place_block_instance(lines_def(be, "Corner", CORNER).id, (0.0, 0.0))
    b = be.place_block_instance(_thin_rect_def(be).id, (103.0, -30.0))
    region = QRectF(104, -4, 1, 20)
    assert ink(be, a, region, VIEW) == 0
    b.set_opaque(False)
    assert ink(be, a, region, VIEW) > 0                    # premise: ink is there


def test_a_held_preview_of_the_lower_block_uses_its_moved_rect(be, monkeypatch):
    """A manipulator hold moves the block by Qt transform: the rect follows it,
    so a block held under the mask is hidden there."""
    monkeypatch.setattr(ss, "canvas_px", lambda w: 1.0)
    monkeypatch.setattr(bi, "canvas_px", lambda w: 1.0)
    a, b = _stack(be, 112.0)
    a.setTransform(QTransform.fromTranslate(30.0, 0.0))
    assert ink(be, a, QRectF(114, -3, 14, 6), VIEW) == 0
    b.set_opaque(False)
    assert ink(be, a, QRectF(114, -3, 14, 6), VIEW) > 0
