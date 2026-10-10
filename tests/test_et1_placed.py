"""ET1 G3 / G4 / G5 inside placed blocks: a line's per-end Scale and the
end's On screen follow the authored record (Q10-e); the short-stroke rule
is per stroke op."""
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
    ms._screen_end_items = set()          # the registry Task 4 adds (a WeakSet)
    _render(ms, QRectF(0.0, -1000.0, 2000.0, 1000.0), 400, 200)
    assert inst._screen_ends is True and inst in ms._screen_end_items   # composition
    _export(tmp_path, ms, _S, "mark_placed.pdf")
    assert inst._screen_ends is True and inst in ms._screen_end_items


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
