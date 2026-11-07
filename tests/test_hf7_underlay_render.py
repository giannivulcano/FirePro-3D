"""HF7 D3: runs and the batched underlay on real extraction output."""
from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QGraphicsPathItem

from firepro3d.constants import HATCH_LOD_TONE, UNDERLAY_MASK_SLOT
from firepro3d.underlay_freeze import _UnderlayPathItem
from firepro3d.underlay_runs import assign_runs
from tests._hf7_helpers import (BAIT, built_scene, extract, fills, is_bait, new_doc,
                                render, ring_hatch, sample, square)

RECT = QRectF(-20, -120, 240, 240)


def solid(msp, x, y, side, layer="0", color=None):
    h = msp.add_hatch(dxfattribs={"layer": layer})
    if color:
        h.rgb = color
    h.paths.add_polyline_path(square(x, y, side), is_closed=True, flags=1)
    return h


def test_ring_fills_and_keeps_its_hole(qapp, tmp_path):
    doc, msp = new_doc()
    ring_hatch(msp)
    msp.add_solid([(120, 0), (160, 0), (120, 40), (160, 40)])
    scene, *_ = built_scene(extract(doc, tmp_path))
    img = render(scene, RECT)
    assert is_bait(sample(img, RECT, 10, 10))
    assert not is_bait(sample(img, RECT, 50, 50))
    assert is_bait(sample(img, RECT, 140, 20))     # the SOLID's centre: no bowtie


def test_overlapping_rings_do_not_cancel(qapp, tmp_path):
    doc, msp = new_doc()
    ring_hatch(msp, x=0)
    ring_hatch(msp, x=70)
    scene, *_ = built_scene(extract(doc, tmp_path))
    assert is_bait(sample(render(scene, RECT), RECT, 85, 20))


def test_runs_fill_over_line_and_line_over_fill():
    line = {"kind": "line", "layer": "A", "x1": 0, "y1": 5, "x2": 10, "y2": 5}
    far = {"kind": "line", "layer": "A", "x1": 100, "y1": 5, "x2": 110, "y2": 5}
    fill = {"kind": "fill", "layer": "A", "solid": True,
            "loops": [[{"kind": "path_points", "layer": "A", "closed": True,
                        "points": [(0, 0), (10, 0), (10, 10), (0, 10)]}]]}
    assert assign_runs([line, fill]) == [0, 1]      # stroke, then fill over it
    assert assign_runs([fill, line]) == [0, 0]      # fills paint first in a run
    assert assign_runs([far, fill]) == [0, 0]       # no overlap: no extra run


def test_runs_cross_layer_fill_over_line():
    line = {"kind": "line", "layer": "A", "x1": 0, "y1": 5, "x2": 10, "y2": 5}
    fill = {"kind": "fill", "layer": "B", "solid": True,
            "loops": [[{"kind": "path_points", "layer": "B", "closed": True,
                        "points": [(0, 0), (10, 0), (10, 10), (0, 10)]}]]}
    assert assign_runs([line, fill]) == [0, 1]


def test_runs_fills_level_on_one_layer_stacked_across_layers():
    def f(layer, x):
        return {"kind": "fill", "layer": layer, "solid": True,
                "loops": [[{"kind": "path_points", "layer": layer, "closed": True,
                            "points": [(x, 0), (x + 10, 0), (x + 10, 10), (x, 10)]}]]}
    assert assign_runs([f("A", 0), f("A", 5)]) == [0, 0]
    assert assign_runs([f("A", 0), f("B", 5)]) == [0, 1]


def test_runs_split_classes_on_one_layer():
    """solid, mask, solid overlapping: the third must paint over the mask."""
    def f(**kw):
        return {"kind": "fill", "layer": "A", **kw,
                "loops": [[{"kind": "path_points", "layer": "A", "closed": True,
                            "points": [(0, 0), (10, 0), (10, 10), (0, 10)]}]]}
    geoms = [f(solid=True), f(solid=True, mask=True), f(solid=True)]
    assert assign_runs(geoms) == [0, 1, 2]


def test_run_count_for_separate_pairs_is_one():
    geoms = []
    for i in range(50):
        x = i * 100.0
        geoms.append({"kind": "fill", "layer": "A", "solid": True,
                      "loops": [[{"kind": "path_points", "layer": "A", "closed": True,
                                  "points": [(x, 0), (x + 10, 0), (x + 10, 10), (x, 10)]}]]})
        geoms.append({"kind": "line", "layer": "A", "x1": x, "y1": 5, "x2": x + 10, "y2": 5})
    assert set(assign_runs(geoms)) == {0}


def test_paint_order_fill_over_line_on_another_layer(qapp, tmp_path):
    doc, msp = new_doc()
    msp.add_line((0, 50), (100, 50), dxfattribs={"layer": "A"})
    solid(msp, 0, 0, 100, layer="B", color=(0, 0, 0))
    geoms = extract(doc, tmp_path)
    runs = assign_runs(geoms)
    assert runs == [0, 1]
    scene, _, group = built_scene(geoms)
    layers = [c.data(1) for c in group.childItems()]
    assert layers.index("A") < layers.index("B")   # B's fill paints after A's stroke


def test_draw_order_table_decides_the_top(qapp, tmp_path):
    doc, msp = new_doc()
    top = solid(msp, 0, 0, 100, layer="B")
    msp.add_line((0, 50), (100, 50), dxfattribs={"layer": "A"})
    msp.set_redraw_order([(top.dxf.handle, "FFFFF")])
    geoms = extract(doc, tmp_path)
    assert geoms[-1]["kind"] == "fill"
    assert assign_runs(geoms) == [0, 1]


def test_pattern_lines_draw_inside_the_boundary_only(qapp, tmp_path):
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.paths.add_polyline_path(square(0, 0, 100), is_closed=True, flags=1)
    h.set_pattern_fill("ANSI37", scale=2.0)
    scene, *_ = built_scene(extract(doc, tmp_path))
    img = render(scene, RECT, size=400)
    sx = lambda x: int((x - RECT.x()) / RECT.width() * 400)
    sy = lambda y: int((-y - RECT.y()) / RECT.height() * 400)
    inside = sum(is_bait(img.pixelColor(sx(x), sy(y)))
                 for x in range(10, 90) for y in range(10, 90))
    outside = sum(is_bait(img.pixelColor(sx(x), sy(y)))
                  for x in range(130, 200) for y in range(10, 90))
    assert inside > 100 and outside == 0


def _tone_geoms(tmp_path):
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.paths.add_polyline_path(square(0, 0, 100000), is_closed=True, flags=1)
    h.set_pattern_fill("ANSI31", scale=0.5)
    return extract(doc, tmp_path)


def test_tone_item_has_opacity_and_repen_keeps_it(qapp, tmp_path):
    geoms = _tone_geoms(tmp_path)
    assert fills(geoms)[0]["tone"]
    scene, rec, group = built_scene(geoms)
    tone = [c for c in group.childItems() if c.opacity() < 1.0]
    assert len(tone) == 1 and tone[0].opacity() == HATCH_LOD_TONE
    rec.colour = "#00ff00"
    scene._underlay_ctl.repen_underlay(rec)
    assert tone[0].opacity() == HATCH_LOD_TONE
    assert tone[0].brush().color().green() == 255


def test_freeze_blit_keeps_the_tone(qapp, tmp_path):
    """The freeze paints children itself, so it must carry child opacity."""
    from PyQt6.QtGui import QColor, QImage, QPainter
    from firepro3d.model_view import Model_View
    scene, rec, group = built_scene(_tone_geoms(tmp_path))
    view = Model_View(scene)
    view.resize(200, 200)
    view.fitInView(group.sceneBoundingRect())
    pix = scene._underlay_freeze._capture(view)[0]
    img = pix.toImage()
    c = img.pixelColor(img.width() // 2, img.height() // 2)
    assert 0 < c.alpha() < 200           # translucent, not a solid block


def test_mask_paints_background_and_repen_skips_it(qapp, tmp_path):
    doc, msp = new_doc()
    solid(msp, 0, 0, 100, color=(255, 0, 0))
    solid(msp, 20, 20, 60, color=(255, 255, 255))
    scene, rec, group = built_scene(extract(doc, tmp_path))
    masks = [c for c in group.childItems() if c.data(UNDERLAY_MASK_SLOT)]
    assert len(masks) == 1
    before = masks[0].brush().color().name()
    rec.colour = "#00ff00"
    scene._underlay_ctl.repen_underlay(rec)
    assert masks[0].brush().color().name() == before
    assert not is_bait(sample(render(scene, RECT), RECT, 50, 50))


def test_layer_hide_hides_fill_items(qapp, tmp_path):
    doc, msp = new_doc()
    solid(msp, 0, 0, 100, layer="B")
    scene, rec, group = built_scene(extract(doc, tmp_path))
    scene._underlay_ctl.set_underlay_layer_hidden(rec, group, "B", True)
    assert all(not c.isVisible() for c in group.childItems())
    scene._underlay_ctl.set_underlay_layer_hidden(rec, group, "B", False)
    assert all(c.isVisible() for c in group.childItems())


def test_snap_returns_boundary_not_pattern_lines(qapp, tmp_path):
    doc, msp = new_doc()
    h = msp.add_hatch()
    h.paths.add_polyline_path(square(0, 0, 100), is_closed=True, flags=1)
    h.set_pattern_fill("ANSI31", scale=5.0)
    scene, _, group = built_scene(extract(doc, tmp_path))
    got = group.data(4).query(-10, -110, 120, 120)
    assert {g["kind"] for g in got} == {"path_points"}


def test_axis_picker_takes_a_solid_edge(qapp, tmp_path):
    from firepro3d.axis_picker import _record_spans
    doc, msp = new_doc()
    msp.add_solid([(0, 0), (10, 0), (0, 10), (10, 10)])
    scene, _, group = built_scene(extract(doc, tmp_path))
    child = group.data(4).query(-1, -11, 12, 12)[0]
    assert _record_spans(child, -1, -11, 11, 1)


def test_empty_pattern_hatch_builds_no_tone_and_does_not_crash(qapp):
    """A non-solid hatch with no pattern draws nothing but keeps its boundary."""
    inert = {"kind": "fill", "layer": "A", "color": "#000000", "solid": False,
             "mask": False, "tone": False, "lines": [], "pattern": None,
             "loops": [[{"kind": "path_points", "layer": "A", "closed": True,
                         "points": [(0, 0), (10, 0), (10, 10), (0, 10)]}]]}
    line = {"kind": "line", "layer": "A", "x1": 0, "y1": 5, "x2": 10, "y2": 5}
    assert assign_runs([line, inert]) == [0, 0]     # it orders nothing
    real = {**inert, "solid": True}
    assert assign_runs([inert, real]) == [0, 0]     # nor does it lift a fill above it
    scene, _, group = built_scene([line, inert])
    kids = group.childItems()
    assert len(kids) == 1 and kids[0].opacity() == 1.0


def test_fill_reaching_append_geom_does_not_vanish(qapp):
    from PyQt6.QtGui import QPainterPath
    from firepro3d.dwg_converter import append_geom_to_path
    fill = {"kind": "fill", "layer": "A", "solid": True,
            "loops": [[{"kind": "path_points", "layer": "A", "closed": True,
                        "points": [(0, 0), (10, 0), (10, 10), (0, 10)]}]]}
    path = QPainterPath()
    append_geom_to_path(path, fill)
    assert not path.isEmpty()


# ---- fix round: paper pass, text/spline paint order, parity pins -----------

def _mask(x0, y0, x1, y1, layer="M"):
    """A mask fill record over a scene-coordinate rectangle."""
    return {"kind": "fill", "layer": layer, "color": "#ffffff", "solid": True,
            "mask": True, "tone": False, "lines": [], "pattern": None,
            "loops": [[{"kind": "path_points", "layer": layer, "closed": True,
                        "points": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]}]]}


def _bait_in(img, xs, ys):
    """Bait pixels over DXF-space x and y ranges (scene y is the negated y)."""
    return sum(is_bait(sample(img, RECT, x, y)) for x in xs for y in ys)


def _text(text, x, y, **kw):
    return {"kind": "text", "layer": "T", "x": x, "y": y, "text": text, "size": 10, **kw}


def _grid_render(geoms):
    scene, _, _ = built_scene(geoms)
    return render(scene, RECT, size=400)


def test_long_text_under_a_later_mask_is_hidden(qapp):
    text = _text("W" * 20, 0, -50)
    mask = _mask(120, -70, 160, -35)
    area = (range(125, 155, 2), range(38, 66, 2))
    assert _bait_in(_grid_render([text]), *area) > 0          # control: text is there
    assert assign_runs([text, mask]) == [0, 1]
    assert _bait_in(_grid_render([text, mask]), *area) == 0


def test_right_aligned_text_under_a_later_mask_is_hidden(qapp):
    text = _text("HELLO WORLD", 150, -50, halign=2)
    mask = _mask(60, -70, 100, -35)
    area = (range(65, 95, 2), range(38, 66, 2))
    assert _bait_in(_grid_render([text]), *area) > 0
    assert assign_runs([text, mask]) == [0, 1]
    assert _bait_in(_grid_render([text, mask]), *area) == 0


def test_text_after_a_lifted_fill_is_visible(qapp):
    line = {"kind": "line", "layer": "A", "x1": 0, "y1": -50, "x2": 200, "y2": -50}
    mask = _mask(0, -80, 60, -20)                     # lifted above the line
    text = _text("W" * 20, 100, -50, halign=1)        # centred: spills left of x+10*size
    area = (range(10, 55, 2), range(38, 66, 2))
    assert assign_runs([line, mask, text]) == [0, 1, 1]
    assert _bait_in(_grid_render([line, mask, text]), *area) > 0


def test_spline_under_a_later_mask_is_hidden(qapp):
    spline = {"kind": "spline", "layer": "S", "degree": 3,
              "control_points": [(0, -10), (30, -60), (60, -60), (90, -10)]}
    mask = _mask(35, -58, 55, -38)
    area = (range(37, 54, 1), range(40, 57, 1))
    assert _bait_in(_grid_render([spline]), *area) > 0
    assert assign_runs([spline, mask]) == [0, 1]
    assert _bait_in(_grid_render([spline, mask]), *area) == 0


def test_unknown_kind_and_rotated_text_overlap_everything():
    mask = _mask(-50, -30, -40, -20)
    assert assign_runs([{"kind": "mystery", "layer": "Z"}, mask]) == [0, 1]
    far = _text("A", 5000, -5000, rotation=45)
    assert assign_runs([far, mask]) == [0, 0]         # rotated, but still far away
    r = _text("W" * 30, 100, -5, rotation=180)        # swings back across the mask
    assert assign_runs([r, mask]) == [0, 1]


def test_rotated_ellipse_box_covers_either_axis():
    ell = {"kind": "ellipse_full", "layer": "E", "pos_cx": 0, "pos_cy": 0,
           "x": -50, "y": -5, "w": 100, "h": 10, "rotation": 90}
    tall = _mask(-3, 30, 3, 45)                       # where a 90-degree turn lands
    assert assign_runs([ell, tall]) == [0, 1]


def test_later_stroke_draws_over_an_earlier_fill_across_layers(qapp):
    far = {"kind": "line", "layer": "A", "x1": 150, "y1": -10, "x2": 160, "y2": -10}
    mask = _mask(20, -80, 80, -20, layer="B")
    line = {"kind": "line", "layer": "A", "x1": 0, "y1": -50, "x2": 100, "y2": -50}
    assert assign_runs([far, mask, line]) == [0, 0, 0]   # layer A is seen first
    img = _grid_render([far, mask, line])
    assert _bait_in(img, range(30, 70, 2), range(48, 53)) > 0   # the line, over the mask


def test_paper_pass_leaves_the_mask_brush_and_plots_white(qapp, monkeypatch):
    from firepro3d import paper_display as pd
    from firepro3d import theme
    line = {"kind": "line", "layer": "A", "x1": 0, "y1": -50, "x2": 100, "y2": -50}
    mask = _mask(20, -80, 80, -20, layer="B")
    monkeypatch.setattr(theme, "detect", lambda: theme.DARK)     # dark screen theme
    for mode in (pd.PaperColorMode.BW, pd.PaperColorMode.FULL_COLOR):
        pd.save_paper_color_mode(mode)
        scene, rec, group = built_scene([line, mask])
        m = [c for c in group.childItems() if c.data(UNDERLAY_MASK_SLOT)][0]
        before = m.brush().color().name()
        saved = pd.apply_paper_overrides(scene, RECT, paper_scale=1.0)
        try:
            assert m.brush().color().name() == before     # the pass left it alone
            c = sample(render(scene, RECT), RECT, 50, 50)
            assert (c.red(), c.green(), c.blue()) == (255, 255, 255), mode
        finally:
            pd.restore_model_display(saved)


def test_no_fills_builds_exactly_todays_items(qapp):
    """Parity pin. Values are hand-derived from the three input geoms, not read
    back from the builder: tag order, pen colour and width, z, opacity, path."""
    from PyQt6.QtCore import Qt
    from firepro3d.constants import UNDERLAY_LINE_WIDTH_PX, Z_UNDERLAY
    geoms = [{"kind": "line", "layer": "A", "x1": 0, "y1": 0, "x2": 10, "y2": 0},
             {"kind": "line", "layer": "B", "x1": 0, "y1": 5, "x2": 10, "y2": 5},
             {"kind": "text", "layer": "A", "x": 0, "y": 0, "text": "T", "size": 5}]
    scene, _, group = built_scene(geoms)
    kids = group.childItems()
    assert [c.data(1) for c in kids] == ["A", "A", "B"]
    a_line, a_text, b_line = kids
    for line, y in ((a_line, 0), (b_line, 5)):
        assert line.pen().color().name() == BAIT
        assert line.pen().isCosmetic() and line.pen().widthF() == UNDERLAY_LINE_WIDTH_PX
        assert line.brush().style() == Qt.BrushStyle.NoBrush
        assert line.zValue() == Z_UNDERLAY and line.opacity() == 1.0
        assert line.data(UNDERLAY_MASK_SLOT) is None and line.data(7) == 0.0
        assert line.path().elementCount() == 2                       # one segment
        assert line.path().boundingRect() == QRectF(0, y, 10, 0)
    assert a_text.pen().style() == Qt.PenStyle.NoPen
    assert a_text.brush().color().name() == BAIT
    assert a_text.zValue() == Z_UNDERLAY and a_text.opacity() == 1.0
    assert a_text.path().elementCount() > 4                          # a glyph outline
    assert a_text.path().boundingRect().width() < 5                  # one 5-unit glyph
