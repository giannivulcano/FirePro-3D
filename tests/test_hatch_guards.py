"""HF2 guards (VC3): placed-block hatch (H1), angle invariance (G3), legacy alias."""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath

from firepro3d import hatch_patterns as hp
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import RectangleItem
from firepro3d.model_space import Model_Space


def _hatched_rect_def(pattern=hp.BUILTIN_DIAGONAL):
    r = RectangleItem(QPointF(-500, -500), QPointF(500, 500))
    r.fill_type, r.fill_pattern = "hatch", pattern
    r._display_fill_color, r.fill_opacity = "#ff0000", 1.0
    return BlockDefinition.new(name="H", library="L", series="S",
                               primitives=[r.to_dict()], origin=(0.0, 0.0))


def _render(scene, rect=QRectF(-700, -700, 1400, 1400), px=700):
    # Aliased (no render hints) at DPR 1 — the pixel thresholds assume it.
    img = QImage(px, px, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, px, px), rect)
    p.end()
    return img


def _red(img, x, y):
    if not (0 <= x < img.width() and 0 <= y < img.height()):
        return False
    c = QColor(img.pixel(x, y))
    return c.red() > 200 and c.green() < 90 and c.blue() < 90


def _placed(load_patterns, rotation=0.0, pattern=hp.BUILTIN_DIAGONAL):
    sc = Model_Space(scene_role="block_editor")
    load_patterns(sc)                     # D-A39: patterns are project blocks
    d = _hatched_rect_def(pattern)
    sc.register_block_definition(d)
    sc.place_block_instance(d.id, (0.0, 0.0), rotation=rotation)
    return sc


def test_h1_placed_block_shows_its_hatch(qapp, shipped_hatches):
    """H1: a placed block's hatched fill renders inside its boundary only."""
    img = _render(_placed(shipped_hatches))
    inside = sum(_red(img, x, y) for x in range(150, 550, 2) for y in range(150, 550, 2))
    outside = sum(_red(img, x, y) for x in range(0, 100, 2) for y in range(0, 700, 2))
    assert inside > 20 and outside == 0


def test_g3_rotated_instance_keeps_45_degree_hatch(qapp, shipped_hatches):
    """G3 / D-A11: a 30° instance still shows 45° (Y-up) hatch lines.

    A 45° Y-up line rises to the right on screen, so a lit pixel (x, y)
    continues at (x+3, y-3). Were the hatch rotated with the instance its
    lines would run at 75° and the continuation rate would collapse.
    """
    img = _render(_placed(shipped_hatches, rotation=30.0))
    lit = [(x, y) for x in range(200, 500) for y in range(200, 500) if _red(img, x, y)]
    assert len(lit) > 50
    along = sum(_red(img, x + 3, y - 3) for x, y in lit) / len(lit)   # 45° Y-up
    assert along > 0.8


def _along_45(img, lo=200, hi=500):
    """(lit count, rate a lit pixel continues at (+3, -3) — a 45° Y-up line)."""
    lit = [(x, y) for x in range(lo, hi) for y in range(lo, hi) if _red(img, x, y)]
    return len(lit), sum(_red(img, x + 3, y - 3) for x, y in lit) / max(1, len(lit))


def test_g3_rotated_2d_rectangle_keeps_45_degree_hatch(qapp, shipped_hatches):
    """G3 / D-A11 through ``draw_fill``: a 30°-rotated hatched rectangle.

    ``RectangleItem.paint`` rotates the painter (rotation is data), so the
    ``to_scene`` it hands ``draw_fill`` must include that rotation or the
    hatch turns with the rectangle (lines at 75°).
    """
    sc = Model_Space(scene_role="block_editor")
    shipped_hatches(sc)
    r = RectangleItem(QPointF(-500, -500), QPointF(500, 500))
    r.fill_type, r.fill_pattern = "hatch", hp.BUILTIN_DIAGONAL
    r._display_fill_color, r.fill_opacity = "#ff0000", 1.0
    sc.addItem(r)
    sc._draw_rects.append(r)
    r.set_angle(30.0)
    n, along = _along_45(_render(sc), 250, 450)
    assert n > 50
    assert along > 0.8


def test_legacy_name_in_file_renders_hatch(qapp, shipped_hatches):
    """An old-file pattern name resolves through LEGACY_ALIAS and renders."""
    sc = _placed(shipped_hatches, pattern="diagonal")
    img = _render(sc)
    assert sum(_red(img, x, y) for x in range(150, 550, 2) for y in range(150, 550, 2)) > 20


def test_paper_tab_hatch_row_saves_line_weight(qapp):
    """The DM Paper tab has a Hatch row; its weight persists and drives hatch_line_mm (D-A31)."""
    from firepro3d import paper_display as pd
    from firepro3d.display_manager import DisplayManager
    cats0 = pd.load_paper_categories()
    cats0["Hatch"]["color"] = "#123456"
    pd.save_paper_categories(cats0)
    dlg = DisplayManager(Model_Space())
    try:
        row = dlg._paper_cat_data["Hatch"]
        style0 = row["color_btn"].styleSheet()
        assert row["lw_combo"].isEnabled()
        assert not row["color_btn"].isEnabled()
        pd._clear_hatch_mm()
        before = pd.hatch_line_mm()
        row["lw_combo"].setCurrentText("Thick")
        assert pd.load_paper_categories()["Hatch"]["line_weight"] == "Thick"
        after = pd.hatch_line_mm()
        assert after == 0.50 and after != before
        # Colour-mode switch must not re-enable the inapplicable cells.
        dlg._color_mode_combo.setCurrentIndex(2)
        assert not row["color_btn"].isEnabled()
        # B&W switch and Reset must not restyle or rewrite the Hatch colour (M1).
        dlg._color_mode_combo.setCurrentIndex(1)
        assert pd.load_paper_categories()["Hatch"]["color"] == "#123456"
        assert row["color_btn"].styleSheet() == style0
        dlg._reset_paper_space_tab()
        assert row["color_btn"].styleSheet() == style0
        assert not row["color_btn"].isEnabled()
    finally:
        pd.save_paper_categories(pd.factory_paper_categories())
        dlg.close()


def _zig_registry():
    from PyQt6.QtCore import QPointF
    from firepro3d.geometry_2d import LineItem
    sc = Model_Space()
    d = BlockDefinition.new(
        name="Zig", library="L", series="S", origin=(0.0, 0.0),
        primitives=[LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()],
        tile={"w": 5.0, "h": 5.0, "row_shift": 0.0, "size": "model"})
    sc.register_block_definition(d)
    return sc.block_registry, d.id


def test_section_dialog_keeps_unknown_stored_ref(qapp):
    """An unresolvable stored ref survives OK, colour-only edit or untouched (I1)."""
    from firepro3d.display_manager import SectionPatternDialog
    hp.seed_hatch_folder()                # D-A39: category dialogs list the folder
    dlg = SectionPatternDialog("#666666", "deleted-project-tile-uuid", 1.0,
                               registry=None)
    assert dlg.get_result()[1] == "deleted-project-tile-uuid"
    dlg._cur_color = "#123456"
    assert dlg.get_result() == ("#123456", "deleted-project-tile-uuid", 1.0)
    # An explicit pick still wins.
    dlg._combo.setCurrentIndex(dlg._combo.findData(hp.BUILTIN_BRICK))
    assert dlg.get_result()[1] == hp.BUILTIN_BRICK


def test_section_dialog_lists_project_tiles_only_with_registry(qapp):
    """Instance dialogs (registry) list + return a project id; category ones do not (I2b)."""
    from firepro3d.display_manager import SectionPatternDialog
    hp.seed_hatch_folder()                # D-A39: the shipped patterns are folder blocks
    reg, tid = _zig_registry()
    dlg = SectionPatternDialog("#666666", "diagonal", 1.0, registry=reg)
    labels = [dlg._combo.itemText(i) for i in range(dlg._combo.count())]
    assert "Zig" in labels
    assert dlg.get_result()[1] == hp.BUILTIN_DIAGONAL      # legacy name -> id
    dlg._combo.setCurrentIndex(labels.index("Zig"))
    assert dlg.get_result()[1] == tid
    cat = SectionPatternDialog("#666666", "diagonal", 1.0, registry=None)
    assert "Zig" not in [cat._combo.itemText(i) for i in range(cat._combo.count())]


def _vp_render_spacing(paper_scale, load_patterns):
    """Printed spacing (mm) of a horizontal hatch through a real plan viewport.

    Drives the real ``vp.paint`` -> ``apply_paper_overrides`` -> scene render
    -> ``restore_model_display`` path and returns the median row gap.
    """
    from firepro3d.paper_space import PaperScene, Sheet, SheetViewData, ViewResolver
    from firepro3d.level_manager import LevelManager, PlanViewManager
    from tests._paper_iso_helpers import _DetailMgrStub
    ms = Model_Space()
    load_patterns(ms)
    lm, pvm = LevelManager(), PlanViewManager()
    pvm.create("Level 1", lm)
    resolver = ViewResolver(ms, pvm, _DetailMgrStub(), None, level_manager=lm)
    r = RectangleItem(QPointF(0, 0), QPointF(5000, 5000))
    r.level = "Level 1"
    r.fill_type, r.fill_pattern = "hatch", "horizontal"
    r._display_fill_color, r.fill_opacity = "#ff0000", 1.0
    ms._draw_rects.append(r)
    ms.addItem(r)
    ms.active_level = "Level 1"
    ms.active_view_key = "plan:Plan: Level 1"
    lm.apply_to_scene(ms, "Level 1")
    data = SheetViewData("plan", "Plan: Level 1", "P", paper_scale, 0, 0, 0, 0)
    vp = PaperScene(Sheet.create_default(), resolver).add_viewport(data)
    data.crop_rect = QRectF(0, 0, 5000, 5000)
    vp._recompute_size_from_scale()
    px_per_mm = 10
    img = QImage(int(data.w * px_per_mm) + 20, int(data.h * px_per_mm) + 20,
                 QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.scale(px_per_mm, px_per_mm)
    vp.paint(p, None, None)
    p.end()
    assert ms._hatch_paper_scale is None          # cleared after the paint returns
    x = img.width() // 2
    ys, prev = [], False
    for y in range(img.height()):
        cur = _red(img, x, y)
        if cur and not prev:
            ys.append(y)
        prev = cur
    assert len(ys) >= 5, f"too few hatch rows ({len(ys)})"
    gaps = sorted(b - a for a, b in zip(ys, ys[1:]))
    return gaps[len(gaps) // 2] / px_per_mm


def test_d_a30_drafting_spacing_is_printed_size_at_any_viewport_scale(qapp, shipped_hatches):
    s100 = _vp_render_spacing(0.01, shipped_hatches)
    s50 = _vp_render_spacing(0.02, shipped_hatches)
    assert abs(s100 - 3.0) < 0.3 and abs(s50 - 3.0) < 0.3


def test_g4_pdf_spacing_doubles_with_scale(qapp, tmp_path, shipped_hatches):
    import fitz
    from PyQt6.QtCore import QMarginsF
    from PyQt6.QtGui import QPageLayout, QPageSize, QPdfWriter
    from firepro3d import hatch_render as hr

    class _Ctx:                                   # a paper-viewport render window at 1:1
        _hatch_paper_scale = 1.0
        block_registry = shipped_hatches()        # the project's pattern blocks

    def spacing(scale):
        path = tmp_path / f"g4_{scale}.pdf"
        w = QPdfWriter(str(path))
        w.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        w.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
        w.setResolution(72)                       # 1 device px = 1 pt
        p = QPainter(w)
        pt_per_mm = 72 / 25.4
        p.scale(pt_per_mm, pt_per_mm)             # painter units = mm
        clip = QPainterPath()
        clip.addRect(QRectF(10, 10, 150, 150))
        hr.paint_fill(p, clip, scene=_Ctx(), tile_ref="horizontal",
                      colour=QColor("#000000"), scale=scale)
        p.end()
        doc = fitz.open(str(path))
        ys = sorted({round(it[1].y, 2) for d in doc[0].get_drawings()
                     for it in d["items"] if it[0] == "l"
                     and abs(it[1].y - it[2].y) < 1e-3})
        assert len(ys) >= 5, f"too few vector rows ({len(ys)})"
        gaps = [b - a for a, b in zip(ys, ys[1:])]
        return sorted(gaps)[len(gaps) // 2] / pt_per_mm
    s1, s2 = spacing(1.0), spacing(2.0)
    assert abs(s1 - 3.0) < 0.15 and abs(s2 / s1 - 2.0) < 0.1
