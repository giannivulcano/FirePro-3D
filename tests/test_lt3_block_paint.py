"""LT3-5 G-canvas (plan) + G4-LT3 canvas half -- placed blocks draw linetypes."""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.lt3_support import hidden
from tests.test_lt1_block_paper import _nested


def _scene(model_size=False, nested=False, weight="by_block", half_len=1500.0,
           dash_weight=None, at_y=0.0):
    ms = Model_Space()
    lid = hidden(ms, size="model" if model_size else "drafting", weight=dash_weight)
    ln = LineItem(QPointF(-half_len, 0), QPointF(half_len, 0))
    ln.style["linetype"], ln.style["weight"] = lid, weight
    d = BlockDefinition.new(name="B", library="L", series="S",
                            primitives=[ln.to_dict()], origin=(0.0, 0.0))
    ms.register_block_definition(d)
    top = d
    if nested:
        top = BlockDefinition.new(name="O", library="L", series="S",
                                  primitives=[_nested(d.id)], origin=(0.0, 0.0))
        ms.register_block_definition(top)
    ms.place_block_instance(top.id, (0.0, at_y), level=ms.active_level)
    return ms


def _render_model(ms):
    """Plan-canvas render: 4000 mm crop centred on 0 into 400 px (0.1 px/mm).

    The LT1 ``_render_model`` crops 800 mm (0.5 px/mm); this guard needs the
    whole 3000 mm line in frame -- it spans x = 50..350 px. The canvas
    guards place the block at y = 1000 mm (row 300): the origin cross at the
    crop centre (row 200) would merge into the dash at x = 0.
    """
    img = QImage(400, 400, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, 400, 400), QRectF(-2000, -2000, 4000, 4000))
    p.end()
    return img


def _lit_runs(img, y):
    runs, start = [], None
    for x in range(img.width()):
        on = QColor(img.pixel(x, y)).lightness() > 128
        if on and start is None:
            start = x
        if not on and start is not None:
            runs.append(x - start)
            start = None
    return runs


def _thickness(img, x):
    return sum(1 for y in range(img.height())
               if QColor(img.pixel(x, y)).lightness() > 128)


def test_plan_drafting_dash_is_printed_mm_times_drawing_scale(qapp):
    # drawing_scale 100: 6 mm printed = 600 mm = 60 px at 0.1 px/mm.
    img = _render_model(_scene(at_y=1000.0))
    runs = _lit_runs(img, 300)[1:-1]                # end dashes are clipped
    assert runs and all(abs(r - 60) <= 2 for r in runs), runs


def test_plan_dash_follows_drawing_scale(qapp):
    ms = _scene(at_y=1000.0)
    ms.scale_manager.drawing_scale = 50.0           # 6 mm x 50 = 300 mm = 30 px
    runs = _lit_runs(_render_model(ms), 300)[1:-1]
    assert runs and all(abs(r - 30) <= 2 for r in runs), runs


def test_nested_block_keeps_linetype(qapp):
    runs = _lit_runs(_render_model(_scene(nested=True, at_y=1000.0)), 300)[1:-1]
    assert runs and all(abs(r - 60) <= 2 for r in runs), runs


def test_model_size_linetype_is_real_mm(qapp):
    # 6 mm model dash at 0.1 px/mm = 0.6 px, period 0.9 px -> LOD solid.
    runs = _lit_runs(_render_model(_scene(model_size=True, at_y=1000.0)), 300)
    assert max(runs) > 250


def test_canvas_by_linetype_takes_dash_weight(qapp):
    """G4-LT3 canvas half: By Linetype -> the dash weight; By Block -> Model Blocks."""
    from firepro3d.stroke_style import canvas_px
    heavy = _thickness(_render_model(_scene(weight="Heavy")), 230)
    by_lt = _thickness(_render_model(_scene(weight="by_linetype", dash_weight="Heavy")), 230)
    by_blk = _thickness(_render_model(_scene(weight="by_block")), 230)
    assert by_lt == heavy
    assert by_blk != heavy and by_blk == round(canvas_px("by_block"))


# -- I2: the placement ghost stays continuous, no badge (LT3-6) ---------------

def _ghost_render(linetype_of):
    from tests._snap_polish_helpers import close_view, make_view, move
    view, ms = make_view(role="plan", scale=0.1, mode=None)
    try:
        ln = LineItem(QPointF(-1500, 0), QPointF(1500, 0))
        ln.style["linetype"] = linetype_of(ms)
        d = BlockDefinition.new(name="B", library="L", series="S",
                                primitives=[ln.to_dict()], origin=(0.0, 0.0))
        ms.register_block_definition(d)
        ms.set_mode("place_block", template=d.id)
        move(view, QPointF(0, 1000))                    # real place_block move
        g = ms._place_block_ghost
        assert g is not None and not ms._block_instances
        x, y = g.block_pos()
        return _render_model(ms), x, y
    finally:
        close_view(view, ms)


def test_placement_ghost_draws_continuous(qapp):
    img, x, y = _ghost_render(hidden)
    row = round(200 + y / 10.0)
    runs = []
    start = None
    for px in range(400):                               # ghost is 50 % opacity
        on = QColor(img.pixel(px, row)).lightness() > 40
        if on and start is None:
            start = px
        if not on and start is not None:
            runs.append(px - start)
            start = None
    assert runs and max(runs) > 250, runs


def test_placement_ghost_has_no_missing_badge(qapp):
    # The ghost paints at 50 % opacity, so the amber glyph would blend toward
    # black: detect it by hue (red well above blue), not by the exact token.
    img, x, y = _ghost_render(lambda ms: "deadbeef")
    amber = [(i, j) for i in range(400) for j in range(400)
             if QColor(img.pixel(i, j)).red() - QColor(img.pixel(i, j)).blue() > 30]
    assert amber == []


def test_nested_instance_in_block_editor_is_real_size(qapp):
    """LT3-5: a placed (nested) block inside the Block Editor draws real size,
    not x drawing_scale (the editor scene has its own ScaleManager)."""
    ms = Model_Space(scene_role="block_editor")
    lid = hidden(ms)
    ln = LineItem(QPointF(0, 0), QPointF(36, 0))
    ln.style["linetype"] = lid
    d = BlockDefinition.new(name="B", library="L", series="S",
                            primitives=[ln.to_dict()], origin=(0.0, 0.0))
    ms.register_block_definition(d)
    ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)
    img = QImage(400, 40, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, 400, 40), QRectF(0, -2, 40, 4))   # 10 px/mm
    p.end()
    row = [QColor(img.pixel(x, 20)).lightness() > 128 for x in range(400)]
    assert all(row[5:55]) and not any(row[65:85]) and all(row[95:145])
