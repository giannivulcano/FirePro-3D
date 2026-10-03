"""HF2 guards (VC3): placed-block hatch (H1), angle invariance (G3), legacy alias."""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

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


def _placed(rotation=0.0, pattern=hp.BUILTIN_DIAGONAL):
    sc = Model_Space(scene_role="block_editor")
    d = _hatched_rect_def(pattern)
    sc.register_block_definition(d)
    sc.place_block_instance(d.id, (0.0, 0.0), rotation=rotation)
    return sc


def test_h1_placed_block_shows_its_hatch(qapp):
    """H1: a placed block's hatched fill renders inside its boundary only."""
    img = _render(_placed())
    inside = sum(_red(img, x, y) for x in range(150, 550, 2) for y in range(150, 550, 2))
    outside = sum(_red(img, x, y) for x in range(0, 100, 2) for y in range(0, 700, 2))
    assert inside > 20 and outside == 0


def test_g3_rotated_instance_keeps_45_degree_hatch(qapp):
    """G3 / D-A11: a 30° instance still shows 45° (Y-up) hatch lines.

    A 45° Y-up line rises to the right on screen, so a lit pixel (x, y)
    continues at (x+3, y-3). Were the hatch rotated with the instance its
    lines would run at 75° and the continuation rate would collapse.
    """
    img = _render(_placed(rotation=30.0))
    lit = [(x, y) for x in range(200, 500) for y in range(200, 500) if _red(img, x, y)]
    assert len(lit) > 50
    along = sum(_red(img, x + 3, y - 3) for x, y in lit) / len(lit)   # 45° Y-up
    assert along > 0.8


def _along_45(img, lo=200, hi=500):
    """(lit count, rate a lit pixel continues at (+3, -3) — a 45° Y-up line)."""
    lit = [(x, y) for x in range(lo, hi) for y in range(lo, hi) if _red(img, x, y)]
    return len(lit), sum(_red(img, x + 3, y - 3) for x, y in lit) / max(1, len(lit))


def test_g3_rotated_2d_rectangle_keeps_45_degree_hatch(qapp):
    """G3 / D-A11 through ``draw_fill``: a 30°-rotated hatched rectangle.

    ``RectangleItem.paint`` rotates the painter (rotation is data), so the
    ``to_scene`` it hands ``draw_fill`` must include that rotation or the
    hatch turns with the rectangle (lines at 75°).
    """
    sc = Model_Space(scene_role="block_editor")
    r = RectangleItem(QPointF(-500, -500), QPointF(500, 500))
    r.fill_type, r.fill_pattern = "hatch", hp.BUILTIN_DIAGONAL
    r._display_fill_color, r.fill_opacity = "#ff0000", 1.0
    sc.addItem(r)
    sc._draw_rects.append(r)
    r.set_angle(30.0)
    n, along = _along_45(_render(sc), 250, 450)
    assert n > 50
    assert along > 0.8


def test_legacy_name_in_file_renders_hatch(qapp):
    """An old-file pattern name resolves through LEGACY_ALIAS and renders."""
    sc = _placed(pattern="diagonal")
    img = _render(sc)
    assert sum(_red(img, x, y) for x in range(150, 550, 2) for y in range(150, 550, 2)) > 20


def test_paper_tab_hatch_row_saves_line_weight(qapp):
    """The DM Paper tab has a Hatch row; its weight persists and drives hatch_line_mm (D-A31)."""
    from firepro3d import paper_display as pd
    from firepro3d.display_manager import DisplayManager
    dlg = DisplayManager(Model_Space())
    try:
        row = dlg._paper_cat_data["Hatch"]
        assert row["lw_combo"].isEnabled()
        assert not row["color_btn"].isEnabled()
        pd._clear_hatch_mm()
        before = pd.hatch_line_mm()
        row["lw_combo"].setCurrentText("Very Heavy")
        assert pd.load_paper_categories()["Hatch"]["line_weight"] == "Very Heavy"
        after = pd.hatch_line_mm()
        assert after == 0.50 and after != before
        # Colour-mode switch must not re-enable the inapplicable cells.
        dlg._color_mode_combo.setCurrentIndex(2)
        assert not row["color_btn"].isEnabled()
    finally:
        pd.save_paper_categories(pd.FACTORY_PAPER_CATEGORIES)
        dlg.close()
