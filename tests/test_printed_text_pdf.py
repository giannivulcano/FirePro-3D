"""Notes on schematics, Part 3: printed text through the real PDF export (N15,
N16, N18, N19, AC4, AC5, G3).

Every expected number is hand arithmetic from the viewport's scale and the
stored size; every measured number is read from the exported PDF with PyMuPDF.
The Automatic text colour plots black, so the glyph is the only filled path in
the viewport and the frame the only stroked rectangle.
"""
import fitz
import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.block_definition import BlockDefinition
from firepro3d.block_editor import BlockEditorWidget
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import resolve_line_weight_mm
from firepro3d.paper_export import export_pdf
from firepro3d.paper_space import PaperScene, Sheet, SheetViewData, ViewResolver
from firepro3d.schematic_scene import SchematicSceneManager
from firepro3d.text_item import TextAnnotationData, TextItem
from firepro3d.text_leader import normalise

_MM_PER_PT = 25.4 / 72.0
_VP_X, _VP_Y = 100.0, 60.0


class _PlanStub:
    _views: dict = {}

    def get(self, name):
        return None


class _DetailStub:
    detail_names: list = []

    def get_marker(self, name):
        return None


def _editor(proj, sizing, **data):
    """A schematic saved through the real editor, holding one text."""
    w = BlockEditorWidget(proj, kind="schematic")
    if sizing is None:                       # an old schematic: neither key
        sc = w.editor_scene
        sc.set_block_meta({k: v for k, v in sc.block_meta.items()
                           if k not in ("text_sizing", "text_scale")}, push_undo=False)
    t = TextItem(TextAnnotationData(**{"text": "H", "font_family": "Arial", **data}))
    w._add_primitive(t)
    return w, t


def _sheet(proj, defn, scale, box=(180.0, 120.0)):
    mgr = SchematicSceneManager(proj)
    res = ViewResolver(proj, _PlanStub(), _DetailStub(), None, schematic_scenes=mgr)
    sheet = Sheet.create_default()
    proj._sheets = [sheet]
    ps = PaperScene(sheet, res)
    data = SheetViewData("schematic", defn.id, "", scale, _VP_X, _VP_Y, box[0], box[1])
    data.show_title, data.show_border = False, False
    ps.add_viewport(data)
    return sheet, res, mgr, data


def _export(tmp_path, proj, defn, scale, name, box=(180.0, 120.0)):
    sheet, res, mgr, data = _sheet(proj, defn, scale, box)
    path = tmp_path / name
    export_pdf([sheet], res, str(path))
    return path, mgr, data


def _in_box(path, data):
    """The PDF's drawings inside the viewport box, in page mm rects."""
    page = fitz.open(str(path))[0]
    box = fitz.Rect(data.x / _MM_PER_PT, data.y / _MM_PER_PT,
                    (data.x + data.w) / _MM_PER_PT, (data.y + data.h) / _MM_PER_PT)
    box = box + (-2, -2, 2, 2)
    return [d for d in page.get_drawings() if box.contains(d["rect"])]


def _fills(path, data):
    """Filled ink only, skipping the viewport's own white background."""
    return [d for d in _in_box(path, data) if d["type"] in ("f", "fs")
            and d.get("fill") == (0.0, 0.0, 0.0)]


def _strokes(path, data):
    return [d for d in _in_box(path, data) if d["type"] in ("s", "fs")]


def _cap_mm(path, data) -> float:
    fills = _fills(path, data)
    assert fills, "no glyph ink in the viewport"
    top = min(d["rect"].y0 for d in fills)
    bot = max(d["rect"].y1 for d in fills)
    return (bot - top) * _MM_PER_PT


def _mm(r):
    return tuple(v * _MM_PER_PT for v in (r.x0, r.y0, r.x1, r.y1))


@pytest.mark.parametrize("scale", [0.1, 0.05, 0.0], ids=["1:10", "1:20", "NTS"])
def test_g3_three_mm_text_prints_three_mm(qapp, tmp_path, scale):
    """AC4: a 60 mm text on a 1:20 schematic is 3 printed mm in every viewport."""
    proj = Model_Space()
    proj.scale_manager.drawing_scale = 20.0
    w, _t = _editor(proj, "printed", height_mm=60.0)
    defn = w.commit_block("Riser", "", "")
    path, _m, data = _export(tmp_path, proj, defn, scale, "g3.pdf")
    assert _cap_mm(path, data) == pytest.approx(3.0, abs=0.03)


def test_g3_printed_cap_ignores_the_nts_box(qapp, tmp_path):
    """Two NTS box sizes give two viewport scales; the printed cap stays."""
    proj = Model_Space()
    proj.scale_manager.drawing_scale = 20.0
    w, _t = _editor(proj, "printed", height_mm=60.0)
    defn = w.commit_block("Riser", "", "")
    a, _m, da = _export(tmp_path, proj, defn, 0.0, "a.pdf", box=(180.0, 120.0))
    b, _m, db = _export(tmp_path, proj, defn, 0.0, "b.pdf", box=(90.0, 60.0))
    assert _cap_mm(a, da) == pytest.approx(3.0, abs=0.03)
    assert _cap_mm(b, db) == pytest.approx(3.0, abs=0.03)


@pytest.mark.parametrize("scale,want", [(0.1, 6.0), (0.05, 3.0)], ids=["1:10", "1:20"])
def test_g3_an_old_schematic_measures_as_at_base(qapp, tmp_path, scale, want):
    """AC5: real size. 60 mm x the viewport scale, as at base."""
    proj = Model_Space()
    proj.scale_manager.drawing_scale = 20.0
    w, _t = _editor(proj, None, height_mm=60.0)
    defn = w.commit_block("Old", "", "")
    assert "text_sizing" not in defn.to_dict()
    path, _m, data = _export(tmp_path, proj, defn, scale, "old.pdf")
    assert _cap_mm(path, data) == pytest.approx(want, abs=0.05)


def test_g3_an_old_schematic_at_nts_scales_with_the_box(qapp, tmp_path):
    proj = Model_Space()
    w, t = _editor(proj, None, height_mm=60.0)
    defn = w.commit_block("Old", "", "")
    a, mgr, da = _export(tmp_path, proj, defn, 0.0, "a.pdf", box=(180.0, 120.0))
    ext = mgr.extent(defn.id)
    fit = min(180.0 / ext.width(), 120.0 / ext.height())
    assert _cap_mm(a, da) == pytest.approx(60.0 * fit, abs=0.05)


def test_border_plots_true_mm_in_a_printed_pass(qapp, tmp_path):
    """N15: the frame is a true-mm stroke at every scale, not a cosmetic px."""
    proj = Model_Space()
    proj.scale_manager.drawing_scale = 20.0
    w, t = _editor(proj, "printed", height_mm=60.0, border=True, border_weight="Thick")
    defn = w.commit_block("Riser", "", "")
    want = resolve_line_weight_mm("Thick")
    for scale, name in ((0.1, "a.pdf"), (0.05, "b.pdf"), (0.0, "c.pdf")):
        path, _m, data = _export(tmp_path, proj, defn, scale, name)
        widths = {round(d["width"] * _MM_PER_PT, 2) for d in _strokes(path, data)
                  if d.get("width")}
        assert widths == {round(want, 2)}


def test_border_of_a_real_size_schematic_stays_as_at_base(qapp, tmp_path):
    """N15: the branch leaves a Real size schematic alone, border included.
    At base the frame is a cosmetic pen, which plots at a width the viewport
    scale does not change."""
    proj = Model_Space()
    w, t = _editor(proj, None, height_mm=60.0, border=True, border_weight="Thick")
    defn = w.commit_block("Old", "", "")
    got = []
    for scale, name in ((0.1, "a.pdf"), (0.05, "b.pdf")):
        path, _m, data = _export(tmp_path, proj, defn, scale, name)
        got.append({round(d["width"], 4) for d in _strokes(path, data) if d.get("width")})
    assert got[0] == got[1]
    assert got[0] != {round(resolve_line_weight_mm("Thick") / _MM_PER_PT, 4)}


@pytest.mark.parametrize("align,fx", [("L", 0.0), ("C", 0.5), ("R", 1.0)])
@pytest.mark.parametrize("valign,fy", [("T", 0.0), ("M", 0.5), ("B", 1.0)])
def test_box_scales_about_its_alignment_point(qapp, tmp_path, align, fx, valign, fy):
    """N16, read off the frame in the PDF. A 400 x 200 mm box at (100, 100) on a
    1:20 schematic through a 1:10 viewport: k = 0.5, so the box plots 20 x 10 mm
    (400 x 0.1 x 0.5) with its (fx, fy) point where the editor has it."""
    proj = Model_Space()
    proj.scale_manager.drawing_scale = 20.0
    w, t = _editor(proj, "printed", height_mm=60.0, border=True, x=100.0, y=100.0,
                   wrap_width_mm=400.0, box_height_mm=200.0, align=align, valign=valign,
                   wrap=True)
    sc = w.editor_scene
    w._add_primitive(LineItem(QPointF(-400, -400), QPointF(1000, 800)))   # a wide extent
    defn = w.commit_block("Riser", "", "")
    path, mgr, data = _export(tmp_path, proj, defn, 0.1, "n16.pdf")
    ext = mgr.extent(defn.id)
    px = data.x + (100.0 + fx * 400.0 - ext.left()) * 0.1
    py = data.y + (100.0 + fy * 200.0 - ext.top()) * 0.1
    want = (px - fx * 20.0, py - fy * 10.0, px + (1 - fx) * 20.0, py + (1 - fy) * 10.0)
    frames = [d for d in _strokes(path, data)
              if abs(d["rect"].width * _MM_PER_PT - 20.0) < 0.5]
    assert len(frames) == 1
    assert _mm(frames[0]["rect"]) == pytest.approx(want, abs=0.05)


def test_a_leader_keeps_tip_and_elbow_and_scales_the_box_and_shoulder(qapp, tmp_path):
    """N16 with a leader. Box 400 x 200 at (100, 100), R edge at mid-height,
    shoulder 120: the attach is (500, 200), the knee (620, 200), the tip stored
    at (900, 500). Through a 1:10 viewport of a 1:20 schematic k = 0.5, so the
    knee and tip plot where the editor has them, the attach 60 mm of model
    nearer the knee, and the frame's right edge on that attach."""
    proj = Model_Space()
    proj.scale_manager.drawing_scale = 20.0
    rec = normalise({"edge": "R", "t": 0.5, "shoulder_mm": 120.0, "tip_x": 900.0,
                     "tip_y": 500.0, "end": "", "weight": ""})
    w, t = _editor(proj, "printed", height_mm=60.0, border=True, x=100.0, y=100.0,
                   wrap_width_mm=400.0, box_height_mm=200.0, wrap=True, leader=rec)
    w._add_primitive(LineItem(QPointF(-100, -100), QPointF(1100, -100)))   # the extent:
    w._add_primitive(LineItem(QPointF(-100, 700), QPointF(1100, 700)))     # it omits a leader
    defn = w.commit_block("Riser", "", "")
    path, mgr, data = _export(tmp_path, proj, defn, 0.1, "leader.pdf")
    ext = mgr.extent(defn.id)

    def paper(x, y):
        return (data.x + (x - ext.left()) * 0.1, data.y + (y - ext.top()) * 0.1)

    knee = paper(620.0, 200.0)
    attach = paper(620.0 - 60.0, 200.0)
    tip = paper(900.0, 500.0)
    page = fitz.open(str(path))[0]
    pts = []
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] == "l":
                pts += [(it[1].x * _MM_PER_PT, it[1].y * _MM_PER_PT),
                        (it[2].x * _MM_PER_PT, it[2].y * _MM_PER_PT)]

    def has(p):
        return any(abs(a - p[0]) < 0.05 and abs(b - p[1]) < 0.05 for a, b in pts)

    assert has(knee), "the elbow moved"
    assert has(attach), "the shoulder did not scale about the elbow"
    frames = [d for d in _strokes(path, data) if d["rect"].height * _MM_PER_PT > 5.0
              and abs(d["rect"].x1 * _MM_PER_PT - attach[0]) < 0.05]
    assert frames, "the box did not scale about the elbow"
    # the tip's arrow trims the stroke, so the far end is read as the ink's corner
    near = [_mm(d["rect"]) for d in _in_box(path, data) if d["rect"].width * _MM_PER_PT < 60.0]
    assert max(r[2] for r in near) == pytest.approx(tip[0], abs=0.3)
    assert max(r[3] for r in near) == pytest.approx(tip[1], abs=0.3)


def test_a_rotated_box_scales_about_its_rotated_alignment_point(qapp, tmp_path):
    """Edge case, N16. Box 400 x 200 at (100, 100), turned 90 about its centre
    (300, 200), so the L T point sits at (200, 400): 100 left and 200 below the
    centre. At k = 0.5 the box is 200 x 100 model from that point along its own
    axes, which turned are up and right: x 200..300, y 200..400."""
    proj = Model_Space()
    proj.scale_manager.drawing_scale = 20.0
    w, t = _editor(proj, "printed", height_mm=60.0, border=True, x=100.0, y=100.0, angle=90.0,
                   wrap_width_mm=400.0, box_height_mm=200.0, wrap=True)
    w._add_primitive(LineItem(QPointF(-400, -400), QPointF(1000, 800)))
    defn = w.commit_block("Riser", "", "")
    path, mgr, data = _export(tmp_path, proj, defn, 0.1, "turned.pdf")
    ext = mgr.extent(defn.id)
    want = (data.x + (200.0 - ext.left()) * 0.1, data.y + (200.0 - ext.top()) * 0.1,
            data.x + (300.0 - ext.left()) * 0.1, data.y + (400.0 - ext.top()) * 0.1)
    frames = [d for d in _strokes(path, data) if abs(d["rect"].height * _MM_PER_PT - 20.0) < 0.5]
    assert len(frames) == 1
    assert _mm(frames[0]["rect"]) == pytest.approx(want, abs=0.05)


def test_overrun_clips_at_the_viewport_and_the_box_does_not_grow(qapp, tmp_path):
    """N18. A long line of 3 mm text on a 1:20 schematic in a 40 x 12 mm NTS box
    runs past the box: raster ink stops at the box edge, and the box stays."""
    proj = Model_Space()
    proj.scale_manager.drawing_scale = 20.0
    w, t = _editor(proj, "printed", height_mm=60.0, text="HHHHHHHHHHHHHHHHHHHHHHHH", x=0.0, y=0.0)
    w._add_primitive(LineItem(QPointF(0, 0), QPointF(100, 0)))
    w._add_primitive(LineItem(QPointF(0, 0), QPointF(0, 300)))
    t.set_property("Wrap", False)
    defn = w.commit_block("Riser", "", "")
    path, _m, data = _export(tmp_path, proj, defn, 0.0, "over.pdf", box=(40.0, 12.0))
    assert (data.w, data.h) == (40.0, 12.0)
    page = fitz.open(str(path))[0]
    # The glyph run overruns the box, so it is picked by its top-left corner.
    run = [d["rect"] for d in page.get_drawings() if d.get("fill") == (0.0, 0.0, 0.0)
           and data.x <= d["rect"].x0 * _MM_PER_PT < data.x + data.w
           and data.y <= d["rect"].y0 * _MM_PER_PT < data.y + data.h]
    widest = max(run, key=lambda r: r.width)           # the two lines add end dots
    assert widest.height * _MM_PER_PT == pytest.approx(3.0, abs=0.03)   # no shrink to fit
    px = page.get_pixmap(dpi=300)
    per_mm = 300 / 25.4
    x0, x1 = int(data.x * per_mm), int((data.x + data.w) * per_mm)
    y0, y1 = int(data.y * per_mm), int((data.y + data.h) * per_mm)
    s, n, width = px.samples, px.n, px.width

    def dark(x, y):
        return s[(y * width + x) * n] < 128

    assert any(dark(x, y) for y in range(y0, y1) for x in range(x1 - 6, x1 - 1)), \
        "the text does not reach the box edge"
    assert not any(dark(x, y) for y in range(y0, y1) for x in range(x1 + 3, x1 + 30))


def _annot_def(proj, mode):
    """A block with a 100 mm cross-bar in it, at *mode* size."""
    d = BlockDefinition.new(name=f"B{mode}", library="L", series="S", origin=(0.0, 0.0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict()])
    d.scale_mode = mode
    proj.register_block_definition(d)
    return d


@pytest.mark.parametrize("mode,want", [("annotative", 100.0), ("real_size", 10.0)])
def test_nested_blocks_print_as_they_did(qapp, tmp_path, mode, want):
    """N19, measured through a 1:10 viewport of a Printed 1:20 schematic: an
    annotative block's 100 printed mm, a real-size block's 100 mm x 0.1."""
    proj = Model_Space()
    proj.scale_manager.drawing_scale = 20.0
    inner = _annot_def(proj, mode)
    prims = [TextItem(TextAnnotationData(text="H", height_mm=60.0, x=0.0, y=-400.0)).to_dict(),
             {"type": "block_instance", "block_id": inner.id, "pos": [0.0, 0.0],
              "rotation": 0.0},
             LineItem(QPointF(-2000, -600), QPointF(-2000, 600)).to_dict(),
             LineItem(QPointF(2000, -600), QPointF(2000, 600)).to_dict()]
    defn = BlockDefinition.new(name="Riser", library="", series="", origin=(0.0, 0.0),
                               primitives=prims, kind="schematic")
    defn.text_sizing, defn.text_scale = "printed", 20.0
    proj.register_block_definition(defn)
    path, _m, data = _export(tmp_path, proj, defn, 0.1, "nested.pdf", box=(400.0, 120.0))
    flats = [d["rect"] for d in _strokes(path, data) if d["rect"].height < 0.5]
    assert flats and max(r.width for r in flats) * _MM_PER_PT == pytest.approx(want, abs=0.1)


def test_extent_reads_editor_size_at_every_scale(qapp):
    """N17: the crop reads the editor size even inside a pass, so S never feeds
    it and NTS has no loop. k = 5 at 0.01, 0.5 at 0.1."""
    from firepro3d.paper_display import apply_paper_overrides, restore_model_display
    proj = Model_Space()
    proj.scale_manager.drawing_scale = 20.0
    w, t = _editor(proj, "printed", height_mm=60.0, x=10.0, y=20.0, border=True)
    defn = w.commit_block("Riser", "", "")
    mgr = SchematicSceneManager(proj)
    sc = mgr.scene_for(defn.id)
    want = mgr.extent(defn.id)
    for paper_scale in (0.1, 0.05, 0.01):
        saved = apply_paper_overrides(sc, want, paper_scale=paper_scale)
        try:
            assert mgr.extent(defn.id) == want
        finally:
            restore_model_display(saved)


def test_the_pass_leaves_the_item_as_it_found_it(qapp, tmp_path):
    proj = Model_Space()
    proj.scale_manager.drawing_scale = 20.0
    w, t = _editor(proj, "printed", height_mm=60.0, x=10.0, y=20.0)
    defn = w.commit_block("Riser", "", "")
    sheet, res, mgr, data = _sheet(proj, defn, 0.1)
    sc = mgr.scene_for(defn.id)
    item = sc._texts[0]
    before = QRectF(item.boundingRect())
    export_pdf([sheet], res, str(tmp_path / "x.pdf"))
    assert item._print_pass is None
    assert item.boundingRect() == before


def test_no_new_paint_work_outside_a_printed_pass(qapp, monkeypatch):
    """Perf: a canvas paint and a Real size viewport pass never reach the
    printed geometry. Spies on the three methods only a pass may call."""
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QStyleOptionGraphicsItem
    from firepro3d.paper_display import apply_paper_overrides, restore_model_display
    calls = []
    for name in ("_print_transform", "_print_anchor_local", "set_print_pass"):
        real = getattr(TextItem, name)
        monkeypatch.setattr(TextItem, name,
                            lambda self, *a, _r=real, _n=name: calls.append(_n) or _r(self, *a))
    proj = Model_Space()
    w, t = _editor(proj, None, height_mm=60.0, border=True)
    image = QImage(200, 200, QImage.Format.Format_ARGB32)
    p = QPainter(image)
    t.paint(p, QStyleOptionGraphicsItem(), None)
    p.end()
    t.boundingRect()
    t.shape()
    assert calls == []
    defn = w.commit_block("Old", "", "")
    mgr = SchematicSceneManager(proj)
    sc = mgr.scene_for(defn.id)
    assert sc.text_print_scale is None
    restore_model_display(apply_paper_overrides(sc, mgr.extent(defn.id), paper_scale=0.1))
    assert calls == []


def test_bounds_report_the_scaled_box_during_the_pass(qapp):
    """The SB1c D6 pattern: a 1:100 viewport of a 1:20 schematic has k = 5, and
    scene.items() finds the box where it will paint."""
    from firepro3d.paper_display import apply_paper_overrides, restore_model_display
    proj = Model_Space()
    proj.scale_manager.drawing_scale = 20.0
    w, t = _editor(proj, "printed", height_mm=60.0, x=0.0, y=0.0, wrap=True,
                   wrap_width_mm=100.0, box_height_mm=100.0, valign="T", align="L")
    defn = w.commit_block("Riser", "", "")
    mgr = SchematicSceneManager(proj)
    sc = mgr.scene_for(defn.id)
    far = QRectF(450.0, 450.0, 10.0, 10.0)           # inside the 500 x 500 printed box only
    assert not sc.items(far)
    saved = apply_paper_overrides(sc, mgr.extent(defn.id), paper_scale=0.01)
    try:
        assert sc._texts[0] in sc.items(far)
    finally:
        restore_model_display(saved)
    assert not sc.items(far)
