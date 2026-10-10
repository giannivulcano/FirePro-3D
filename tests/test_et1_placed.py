"""ET1 G3 / G4 / G5 inside placed blocks: a line's per-end Scale and the
end's On screen follow the authored record (Q10-e); the short-stroke rule
is per stroke op."""
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor

from firepro3d.block_definition import BlockDefinition
from firepro3d.constants import FIXED_END_PX_PER_MM
from firepro3d.geometry_2d import LineItem
from tests.lt5_support import arrow, set_ends
from tests.test_et1_raw import _head_width, _render
from tests.wm2_support import scene_with


def _block(a, scale=None, length=2000.0, name="B"):
    ln = LineItem(QPointF(0.0, 0.0), QPointF(length, 0.0))
    set_ends(ln, finish=a.id, scale=scale)
    return BlockDefinition.new(name=name, library="L", series="S",
                               primitives=[ln.to_dict()], origin=(0.0, 0.0))


def test_g3_placed_line_scale_doubles_head(qapp):
    a = arrow(length=3.0, half=1.0)
    d1, d2 = _block(a), _block(a, scale=2.0, name="B2")
    ms1, _ = scene_with([a, d1], d1.id)
    ms2, _ = scene_with([a, d2], d2.id)
    crop = QRectF(0.0, -400.0, 2000.0, 800.0)                   # 0.2 px/mm
    h1, h2 = _head_width(_render(ms1, crop, 400, 160)), _head_width(_render(ms2, crop, 400, 160))
    assert abs(h1 - 60) <= 3 and abs(h2 - 120) <= 3, (h1, h2)


def test_g4_placed_fixed_size_end_is_constant_px(qapp):
    a = arrow(length=3.0, half=1.0, screen="fixed")
    d = _block(a)
    ms, inst = scene_with([a, d], d.id)
    near = _head_width(_render(ms, QRectF(1800.0, -100.0, 200.0, 100.0), 400, 200))
    far = _head_width(_render(ms, QRectF(0.0, -1000.0, 2000.0, 1000.0), 400, 200))
    want = 3.0 * FIXED_END_PX_PER_MM
    assert abs(near - want) <= 2 and abs(far - want) <= 2, (near, far)
    # bounds cover the end at the far zoom: the pad is the screen reach in scene mm
    assert inst.boundingRect().right() >= inst.mapFromScene(QPointF(2000.0, 0.0)).x() - 1.0


def test_placed_paper_pass_keeps_the_screen_end_mark(qapp, tmp_path):
    """Spec C, plain-op path: a PDF pass of the live scene keeps the mark."""
    from tests.test_lt1_block_paper import _export
    from tests.test_lt5_render_raw import _S
    a = arrow(length=3.0, half=1.0, screen="fixed")
    d = _block(a)
    ms, inst = scene_with([a, d], d.id)
    _render(ms, QRectF(0.0, -1000.0, 2000.0, 1000.0), 400, 200)
    assert inst._screen_ends is True and inst in ms._screen_end_items   # composition
    _export(tmp_path, ms, _S, "mark_placed.pdf")
    assert inst._screen_ends is True and inst in ms._screen_end_items


def _lt_block(a, lt, length, scale=None, name="LT"):
    """A block holding one linetyped line with Fixed-size ends both sides."""
    ln = LineItem(QPointF(0.0, 0.0), QPointF(length, 0.0))
    ln.style["linetype"] = lt.id
    set_ends(ln, start=a.id, finish=a.id, scale=scale)
    return BlockDefinition.new(name=name, library="L", series="S",
                               primitives=[ln.to_dict()], origin=(0.0, 0.0))


def test_g5_placed_linetyped_short_op_draws_plain(qapp):
    """G5 through BlockInstance.paint's linetyped branch: a linetyped op too
    short on screen for its Fixed-size trims draws its plain stroke, no
    heads."""
    from tests.lt3_support import make_linetype
    a = arrow(screen="fixed")
    lt = make_linetype()
    d = _lt_block(a, lt, 100.0)
    ms, inst = scene_with([a, lt, d], d.id)
    assert inst._linetype_ids(inst.render_ops()) == frozenset({lt.id})   # composition
    img = _render(ms, QRectF(-100.0, -100.0, 400.0, 200.0), 40, 20)   # 0.1 px/mm
    assert _head_width(img) == 0
    mid = img.height() // 2
    lit = [x for x in range(img.width()) for y in range(mid - 2, mid + 3)
           if QColor(img.pixel(x, y)).lightness() > 128]
    assert lit, "the plain stroke must draw"


def test_g5_placed_linetyped_long_op_scale_doubles_heads(qapp):
    """The same linetyped op, long on screen: per-end Scale 2 draws heads
    twice the Fixed-size width (2 x 3 mm x FIXED_END_PX_PER_MM)."""
    from tests.lt3_support import make_linetype
    a = arrow(length=3.0, half=1.0, screen="fixed")
    lt = make_linetype()
    heads = []
    for scale, name in ((None, "L1"), (2.0, "L2")):
        d = _lt_block(a, lt, 2000.0, scale=scale, name=name)
        ms, inst = scene_with([a, lt, d], d.id)
        assert inst._linetype_ids(inst.render_ops()) == frozenset({lt.id})
        heads.append(_head_width(_render(ms, QRectF(1800.0, -100.0, 200.0, 100.0), 400, 200)))
    want = 3.0 * FIXED_END_PX_PER_MM
    assert abs(heads[0] - want) <= 2 and abs(heads[1] - 2 * want) <= 2, heads


@pytest.mark.parametrize("screen", ["fixed", "scale"])   # "scale": the control
def test_placed_end_poking_into_a_viewport_prints(qapp, tmp_path, screen):
    """Seam fix 3 (placed): the block's line lies just outside the 1:50
    viewport crop; its end draws wholly inside -- the pass's pick bounds it
    at the printed reach, so it reaches the PDF."""
    from tests.test_et1_raw import poke_end
    from tests.test_lt1_block_paper import _export
    from tests.test_lt5_render_raw import _S, _fills
    a = poke_end(screen)
    ln = LineItem(QPointF(5000.0, 0.0), QPointF(2100.0, 0.0))
    set_ends(ln, finish=a.id)
    d = BlockDefinition.new(name="P", library="L", series="S",
                            primitives=[ln.to_dict()], origin=(0.0, 0.0))
    ms, _ = scene_with([a, d], d.id)
    fills = _fills(_export(tmp_path, ms, _S, f"poke_placed_{screen}.pdf"))
    assert len(fills) == 1, fills                   # whole square (placed: 1:100 drafting)
    x0, y0, x1, y1 = fills[0]
    assert abs((x1 - x0) - 8.0) <= 0.1 and abs((y1 - y0) - 8.0) <= 0.1, fills


def test_g5_placed_short_op_draws_plain(qapp):
    a = arrow(screen="fixed")
    d = _block(a, length=100.0)
    ln2 = LineItem(QPointF(0.0, 0.0), QPointF(100.0, 0.0))
    set_ends(ln2, start=a.id, finish=a.id)
    d = BlockDefinition.new(name="S", library="L", series="S",
                            primitives=[ln2.to_dict()], origin=(0.0, 0.0))
    ms, _ = scene_with([a, d], d.id)
    img = _render(ms, QRectF(-100.0, -100.0, 400.0, 200.0), 40, 20)   # 0.1 px/mm
    assert _head_width(img) == 0
    img = _render(ms, QRectF(-20.0, -20.0, 140.0, 40.0), 140, 40)     # 1 px/mm
    assert _head_width(img) >= 100
