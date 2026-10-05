"""LT3-11 G-perf correctness: the BlockInstance paint memo is never stale.

``BlockInstance.paint`` resolves each distinct (linetype, weight) once per
paint and holds each op's expansion across paints (keyed on the compiled op
list, the linetype reading and the length factor). Every state change below
must show on the very next render of the SAME scene: the second render must
equal a render of a fresh scene built in the changed state, and differ from
the first.
"""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d import paper_display as pd
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.lt3_support import hidden, make_linetype

_CROP = QRectF(-2000, -2000, 4000, 4000)         # 0.1 px/mm into 400 px


def _build(weight="Heavy", register_lt=True, weights=None):
    """A plan scene with one placed block of Hidden lines at y = 1000 mm.

    *weights* (one per line) overrides *weight*; lines sit 400 mm apart.
    Returns (ms, linetype id).
    """
    ms = Model_Space()
    if register_lt:
        lid = hidden(ms)
    else:
        lid = make_linetype().id                  # never registered: missing
    prims = []
    for k, w in enumerate(weights or [weight]):
        ln = LineItem(QPointF(-1500, k * 400.0), QPointF(1500, k * 400.0))
        ln.style["linetype"], ln.style["weight"] = lid, w
        prims.append(ln.to_dict())
    d = BlockDefinition.new(name="B", library="L", series="S",
                            primitives=prims, origin=(0.0, 0.0))
    ms.register_block_definition(d)
    ms.place_block_instance(d.id, (0.0, 1000.0), level=ms.active_level)
    return ms, lid


def _render(ms, crop=_CROP):
    img = QImage(400, 400, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, 400, 400), crop)
    p.end()
    return img


def _lit(img):
    return sum(1 for x in range(img.width()) for y in range(img.height())
               if QColor(img.pixel(x, y)).lightness() > 40)


def _assert_reflected(before, after, fresh):
    assert after != before, "change did not reach the next render (stale memo)"
    assert after == fresh, "next render differs from a fresh scene in that state"


def test_weight_width_edit_reaches_next_paint(qapp):
    ms, _ = _build("Heavy")
    a = _render(ms)
    pd.set_project_line_weights([pd.LineWeightDef(d.name, 1.0 if d.name == "Heavy"
                                                  else d.width_mm)
                                 for d in pd.project_line_weights()])
    _assert_reflected(a, _render(ms), _render(_build("Heavy")[0]))


def test_weight_rename_alias_reaches_next_paint(qapp):
    ms, _ = _build("Heavy")
    a = _render(ms)
    try:
        pd.set_project_line_weights(
            [pd.LineWeightDef("Bold", 1.0) if d.name == "Heavy" else d
             for d in pd.project_line_weights()])
        pd.record_weight_rename("Heavy", "Bold")
        b = _render(ms)
        _assert_reflected(a, b, _render(_build("Bold")[0]))
    finally:
        pd.set_weight_aliases({})


def test_model_blocks_weight_reaches_next_paint(qapp):
    ms, _ = _build("by_block")
    a = _render(ms)
    try:
        pd.set_model_blocks_weight("Very Heavy")
        _assert_reflected(a, _render(ms), _render(_build("by_block")[0]))
    finally:
        pd.set_model_blocks_weight(None)


def test_thin_lines_toggle_reaches_next_paint(qapp):
    ms, _ = _build("Very Heavy")
    a = _render(ms)
    pd.set_thin_lines(True)
    _assert_reflected(a, _render(ms), _render(_build("Very Heavy")[0]))
    pd.set_thin_lines(False)
    assert _render(ms) == a


def test_linetype_version_bump_reaches_next_paint(qapp):
    ms, lid = _build("Heavy")
    a = _render(ms)
    edited = make_linetype(dashes=((0.0, 3.0),))      # same 9 mm period
    ms.get_block_definition(lid).set_primitives(edited.primitives)

    fresh, flid = _build("Heavy")
    fresh.get_block_definition(flid).set_primitives(edited.primitives)
    _assert_reflected(a, _render(ms), _render(fresh))


def test_linetype_going_missing_reaches_next_paint(qapp):
    ms, lid = _build("Heavy")
    a = _render(ms)
    ms._block_definitions.pop(lid)
    _assert_reflected(a, _render(ms), _render(_build("Heavy", register_lt=False)[0]))


def test_linetype_being_loaded_reaches_next_paint(qapp):
    ms, lid = _build("Heavy", register_lt=False)
    a = _render(ms)
    lt = make_linetype()
    lt.id = lid
    ms.register_block_definition(lt)
    _assert_reflected(a, _render(ms), _render(_build("Heavy")[0]))


def test_block_content_edit_reaches_next_paint(qapp):
    """The held expansion is keyed on the compiled op list: editing the
    block itself (a new list) never serves the old op's dashes."""
    ms, lid = _build("Heavy")
    a = _render(ms)
    ln = LineItem(QPointF(-1500, 0.0), QPointF(700, 300.0))
    ln.style["linetype"], ln.style["weight"] = lid, "Heavy"
    ms._block_instances[0].definition().set_primitives([ln.to_dict()])

    fresh, flid = _build("Heavy")
    ln2 = LineItem(QPointF(-1500, 0.0), QPointF(700, 300.0))
    ln2.style["linetype"], ln2.style["weight"] = flid, "Heavy"
    fresh._block_instances[0].definition().set_primitives([ln2.to_dict()])
    _assert_reflected(a, _render(ms), _render(fresh))


def test_drawing_scale_change_reaches_next_paint(qapp):
    ms, _ = _build("Heavy")
    a = _render(ms)
    ms.scale_manager.drawing_scale = 50.0
    fresh = _build("Heavy")[0]
    fresh.scale_manager.drawing_scale = 50.0
    _assert_reflected(a, _render(ms), _render(fresh))


def test_zoom_lod_flip_reaches_next_paint(qapp):
    """Zoomed far out the 900 mm period is < 2 px -> solid; back in -> dashed."""
    far = QRectF(-200000, -200000, 400000, 400000)    # 0.001 px/mm
    ms, _ = _build("Heavy")
    a = _render(ms)
    b = _render(ms, far)
    _assert_reflected(a, b, _render(_build("Heavy")[0], far))
    assert _render(ms) == a


def test_distinct_weights_in_one_paint_keep_their_own_width(qapp):
    """Two ops of one linetype, different weights, in ONE paint: each keeps
    its own width (the per-paint memo keys on the weight)."""
    both = _lit(_render(_build(weights=["Very Light", "Very Heavy"])[0]))
    light = _lit(_render(_build(weights=["Very Light", "Very Light"])[0]))
    heavy = _lit(_render(_build(weights=["Very Heavy", "Very Heavy"])[0]))
    assert light < both < heavy


def test_paper_pass_between_canvas_paints(qapp, tmp_path):
    """A PDF pass between two canvas renders prints paper dashes/widths and
    leaves the canvas render unchanged."""
    from tests.test_lt1_block_paper import _export
    from tests.test_lt3_pdf import _viewport_hlines
    from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
    save_paper_color_mode(PaperColorMode.BW)
    ms, _ = _build("Very Heavy")
    inst = ms._block_instances[0]
    inst.set_block_pos(0.0, 0.0)                     # viewport crop is origin-centred
    a = _render(ms)
    lines = _viewport_hlines(_export(tmp_path, ms, 0.01, "memo.pdf"))
    inner = [(x1 - x0, w) for x0, x1, w in lines if 0.5 < x1 - x0][1:-1]
    assert inner and all(abs(L - 6.0) <= 0.05 for L, _ in inner), inner
    assert all(abs(w - 0.50) <= 0.01 for _, w in inner), inner
    assert _render(ms) == a
