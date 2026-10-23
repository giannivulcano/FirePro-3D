"""SB1c -- annotative helper, definition key, canvas guards."""
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt

from firepro3d import annotative as an
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space

HALF = 3.0          # authored half-length (printed mm)


def _annot_def(screen="scale", mode="annotative", name="A"):
    ln = LineItem(QPointF(-HALF, 0.0), QPointF(HALF, 0.0))
    ln.style["colour"] = "#ffffff"      # light ink on the dark render backdrop (HF1 record colour)
    d = BlockDefinition.new(name=name, library="L", series="S",
                            primitives=[ln.to_dict()], origin=(0.0, 0.0))
    d.scale_mode = mode
    d.annotative_screen = screen
    return d


def _placed(screen="scale", mode="annotative", role="plan"):
    ms = Model_Space(scene_role=role)
    d = _annot_def(screen, mode)
    ms.register_block_definition(d)
    inst = ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)
    return ms, d, inst


def test_definition_round_trips_annotative_screen(qapp):
    d = _annot_def("fixed")
    rec = d.to_dict()
    assert rec["annotative_screen"] == "fixed"
    assert BlockDefinition.from_dict(rec).annotative_screen == "fixed"
    d.annotative_screen = "scale"
    rec = d.to_dict()
    assert "annotative_screen" not in rec            # default omitted (byte-identical)
    assert BlockDefinition.from_dict(rec).annotative_screen == "scale"


def test_paper_scene_size():
    assert an.paper_scene_size(3.0, 0.02) == pytest.approx(150.0)


def test_factor_real_size_is_one(qapp):
    ms, d, inst = _placed(mode="real_size")
    assert an.annotative_factor(inst) == 1.0
    assert not an.frame_scaled(inst)


def test_factor_scale_with_zoom_is_drawing_scale(qapp):
    ms, d, inst = _placed("scale")
    ms.scale_manager.drawing_scale = 50.0
    assert an.annotative_factor(inst) == pytest.approx(50.0)
    assert not an.frame_scaled(inst)


def test_factor_paper_pass_is_inverse_scale(qapp):
    ms, d, inst = _placed("fixed")
    inst._paper_scale = 0.005
    try:
        assert an.annotative_factor(inst) == pytest.approx(200.0)
        assert not an.frame_scaled(inst)
    finally:
        inst._paper_scale = None


def test_editor_role_factor_is_one(qapp):
    ms, d, inst = _placed("scale", role="block_editor")
    ms.scale_manager.drawing_scale = 100.0
    assert an.annotative_factor(inst) == 1.0       # D5: editor nested at k = 1


from PyQt6.QtGui import QColor, QImage, QPainter


def _render(ms, scale, px=400):
    """Render the scene around the origin at *scale* image px per scene mm
    (the real QGraphicsScene.render paint path; dark backdrop)."""
    w = px / scale
    img = QImage(px, px, QImage.Format.Format_RGB32)
    img.fill(0xFF101010)
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, px, px), QRectF(-w / 2, -w / 2, w, w),
              Qt.AspectRatioMode.IgnoreAspectRatio)
    p.end()
    return img


def _ink_span(img):
    """Horizontal ink extent (px) on the rows through the image centre."""
    xs = []
    c = img.height() // 2
    for y in range(c - 2, c + 3):
        for x in range(img.width()):
            if QColor(img.pixel(x, y)).lightness() > 80:
                xs.append(x)
    return (max(xs) - min(xs) + 1) if xs else 0


@pytest.mark.parametrize("scale", [0.25, 0.5])
def test_g_zoom_scale_with_zoom_extent(qapp, scale):
    ms, d, inst = _placed("scale")
    ms.scale_manager.drawing_scale = 100.0
    want = 2 * HALF * 100.0                                   # 600 scene mm
    assert inst.geometric_rect().width() == pytest.approx(want, rel=1e-6)
    assert abs(_ink_span(_render(ms, scale)) - want * scale) <= 3


def test_g_pick_hits_scaled_extent(qapp):
    ms, d, inst = _placed("scale")
    ms.scale_manager.drawing_scale = 100.0
    assert inst.shape().contains(QPointF(290.0, 0.0))         # HALO click target
    assert not inst.shape().contains(QPointF(350.0, 0.0))
    box = ms.items(QRectF(-310.0, -10.0, 620.0, 20.0), Qt.ItemSelectionMode.ContainsItemShape)
    assert inst in box                                        # window select
    small = ms.items(QRectF(-10.0, -10.0, 20.0, 20.0), Qt.ItemSelectionMode.ContainsItemShape)
    assert inst not in small


def test_real_size_canvas_unchanged(qapp):
    ms, d, inst = _placed(mode="real_size")
    ms.scale_manager.drawing_scale = 100.0
    assert inst.geometric_rect().width() == pytest.approx(2 * HALF, rel=1e-6)


def test_nested_annotative_child_in_real_parent_is_real(qapp):
    """D5: nested blocks are flattened at compile -- the parent's mode rules."""
    ms = Model_Space()
    child = _annot_def("scale", name="C")
    parent = BlockDefinition.new(name="P", library="L", series="S",
                                 primitives=[{"type": "block_instance", "block_id": child.id,
                                              "pos": [0, 0], "rotation": 0.0}],
                                 origin=(0.0, 0.0))
    for x in (child, parent):
        ms.register_block_definition(x)
    inst = ms.place_block_instance(parent.id, (0.0, 0.0), level=ms.active_level)
    ms.scale_manager.drawing_scale = 100.0
    assert inst.geometric_rect().width() == pytest.approx(2 * HALF, rel=1e-6)


def test_explode_bakes_size_you_see(qapp):
    from firepro3d.block_explode import explode_instances
    ms, d, inst = _placed("scale")
    ms.scale_manager.drawing_scale = 100.0
    made = explode_instances(ms, [inst], flatten=True)
    lines = [m for m in made if isinstance(m, LineItem)]
    assert len(lines) == 1
    ln = lines[0]       # endpoints, not sceneBoundingRect: the bounds add the baked pen width
    span = abs(ln.mapToScene(ln.line().p2()).x() - ln.mapToScene(ln.line().p1()).x())
    assert span == pytest.approx(2 * HALF * 100.0, abs=1.0)


def test_paper_pass_reprepares_annotative(qapp):
    """D6: the pass changes an annotative block's bounds -- Qt must be told
    before (apply) and again at restore."""
    from firepro3d import paper_display as pd
    ms, d, inst = _placed("scale")
    calls = []
    orig = inst.prepareGeometryChange
    inst.prepareGeometryChange = lambda: (calls.append(1), orig())
    saved = pd.apply_paper_overrides(ms, QRectF(-50.0, -50.0, 100.0, 100.0), 0.02)
    try:
        assert calls, "apply did not re-prepare the annotative block"
        assert inst.geometric_rect().width() == pytest.approx(2 * HALF / 0.02, rel=1e-6)
    finally:
        n = len(calls)
        pd.restore_model_display(saved)
    assert len(calls) > n, "restore did not re-prepare"
    assert inst._paper_scale is None


def test_fixed_branch_factor_is_device_px_over_view_scale(qapp):
    """m5: the Fixed branch is FIXED_END_PX_PER_MM / the visible view's scale;
    swapping it with the drawing-scale branch turns this RED."""
    from firepro3d.constants import FIXED_END_PX_PER_MM
    from firepro3d.view_scale import scene_view_scale
    ms, d, inst = _placed("fixed")
    ms.scale_manager.drawing_scale = 100.0
    assert an.frame_scaled(inst)
    k = an.annotative_factor(inst)
    assert k == pytest.approx(FIXED_END_PX_PER_MM / scene_view_scale(ms))
    assert k != pytest.approx(100.0)


from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QWheelEvent

from firepro3d.constants import FIXED_END_PX_PER_MM
from firepro3d.model_view import Model_View
from firepro3d.view_scale import scene_view_scale


def _view(ms, zoom):
    v = Model_View(ms)
    v.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    v.resize(400, 400)
    v.setTransform(v.transform().fromScale(zoom, zoom))
    v.show()
    v.centerOn(0, 0)
    return v


def _wheel(v, up):
    pos = QPointF(200.0, 200.0)
    ev = QWheelEvent(pos, v.mapToGlobal(pos.toPoint()).toPointF(), QPoint(0, 0),
                     QPoint(0, 120 if up else -120), Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    v.wheelEvent(ev)


@pytest.mark.parametrize("zoom", [0.5, 2.0])
def test_g_fixed_constant_device_px(qapp, zoom):
    ms, d, inst = _placed("fixed")
    v = _view(ms, zoom)
    try:
        qapp.processEvents()
        want = 2 * HALF * FIXED_END_PX_PER_MM                    # 36 device px
        z = scene_view_scale(ms)                                 # the zoom the view really has
        assert inst.geometric_rect().width() * z == pytest.approx(want, rel=1e-3)
        assert abs(_ink_span(_render(ms, zoom)) - want) <= 3      # paint: the painter's zoom
    finally:
        v.close()


def test_g_fixed_bounds_follow_zoom(qapp):
    ms, d, inst = _placed("fixed")
    v = _view(ms, 1.0)
    try:
        v.viewport().repaint()
        qapp.processEvents()
        assert inst in ms._screen_end_items                      # registered for the zoom hook
        z1, w1 = scene_view_scale(ms), inst.boundingRect().width()
        for _ in range(12):
            _wheel(v, up=False)
        qapp.processEvents()
        z2 = scene_view_scale(ms)
        assert z2 < z1 / 2, (z1, z2)
        assert inst.geometric_rect().width() * z2 == pytest.approx(
            2 * HALF * FIXED_END_PX_PER_MM, rel=1e-3)
        assert inst.boundingRect().width() > 2 * w1
    finally:
        v.close()


def test_g_fixed_shape_and_snap_follow_zoom(qapp):
    """G-B review I1: under Fixed size the compiled ops never change with
    zoom, so the pose key's frame k is what refreshes the memoised snap
    stand-ins (the shape memo also keys on the zoomed hit width)."""
    ms, d, inst = _placed("fixed")
    v = _view(ms, 1.0)
    try:
        v.viewport().repaint()
        qapp.processEvents()
        inst.shape()                                            # fill both memos at zoom 1
        inst.snap_primitives()
        for _ in range(12):
            _wheel(v, up=False)
        qapp.processEvents()
        z = scene_view_scale(ms)
        assert z < 0.5, z
        geo = 2 * HALF * FIXED_END_PX_PER_MM / z                 # printed extent in scene mm
        sw = inst.shape().boundingRect().width()
        assert geo <= sw <= geo + 2 * 10.0 / z, (sw, geo)         # strokes + the ~10 px hit band
        left = min(b.left() for b, _ in inst.snap_primitives())
        right = max(b.right() for b, _ in inst.snap_primitives())
        assert right - left == pytest.approx(geo + 2.0, rel=0.1, abs=2.0), (right - left, geo)
    finally:
        v.close()


def _annot_end_placed(screen_mode, drawing_scale=100.0):
    """An annotative block whose line carries a printed-size (Scale-with-zoom)
    finish arrow, 3 mm long and 1 mm half-width, tip at the line's right end."""
    from tests.lt5_support import arrow, set_ends
    a = arrow(length=3.0, half=1.0)
    ln = LineItem(QPointF(-HALF, 0.0), QPointF(HALF, 0.0))
    set_ends(ln, finish=a.id)
    d = BlockDefinition.new(name="AE", library="L", series="S",
                            primitives=[ln.to_dict()], origin=(0.0, 0.0))
    d.scale_mode = "annotative"
    d.annotative_screen = screen_mode
    ms = Model_Space(scene_role="plan")
    for x in (a, d):
        ms.register_block_definition(x)
    inst = ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)
    ms.scale_manager.drawing_scale = drawing_scale
    return ms, inst


def _head_px(ms, tip_x, px_per_mm):
    """Device-px width of the arrowhead whose tip is at scene *tip_x* (the
    crop's right edge), via the real scene render."""
    from tests.test_et1_raw import _head_width, _render as et_render
    w, h = 200, 100
    crop = QRectF(tip_x - w / px_per_mm, -h / 2 / px_per_mm, w / px_per_mm, h / px_per_mm)
    return _head_width(et_render(ms, crop, w, h))


@pytest.mark.parametrize("zoom", [0.25, 2.0])
def test_g_fixed_annotative_end_constant_px_and_bounded(qapp, zoom):
    """G-B review I2: a Fixed annotative block's printed-size end draws a
    constant 3 mm x FIXED_END_PX_PER_MM device px head (the linetype/end
    factor must ignore the drawing scale) and its bounds hold the head."""
    ms, inst = _annot_end_placed("fixed")
    v = _view(ms, zoom)
    try:
        v.viewport().repaint()
        qapp.processEvents()
        z = scene_view_scale(ms)
        k = FIXED_END_PX_PER_MM / z
        head = _head_px(ms, HALF * k, z)
        assert abs(head - 3.0 * FIXED_END_PX_PER_MM) <= 2, head
        mb = inst.manip_bounds()                                  # frame rect, no hit band
        assert mb.top() <= -1.0 * k and mb.bottom() >= 1.0 * k, (mb, k)   # head half-width
        assert mb.right() >= HALF * k
    finally:
        v.close()


def test_g_scale_with_zoom_annotative_end_pad(qapp):
    """G-B review I2 (control): Scale-with-zoom at 1:100 draws the head at
    3 mm x 100 scene mm and the bounds hold it."""
    ms, inst = _annot_end_placed("scale", 100.0)
    s = 0.25
    head = _head_px(ms, HALF * 100.0, s)
    assert abs(head - 3.0 * 100.0 * s) <= 3, head
    mb = inst.manip_bounds()
    assert mb.top() <= -100.0 and mb.bottom() >= 100.0, mb
    assert mb.right() >= HALF * 100.0


def test_fixed_first_bounds_read_registers_for_reprepare(qapp):
    """G-B review m3: a bare boundingRect() on a never-painted Fixed item
    registers it with the zoom hook (bounds follow the zoom from first read)."""
    ms, d, inst = _placed("fixed")
    ms._screen_end_items.discard(inst)
    inst._screen_ends = False
    assert inst not in ms._screen_end_items
    inst.boundingRect()
    assert inst in ms._screen_end_items
