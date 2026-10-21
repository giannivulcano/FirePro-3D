"""600: a dark-theme sheet viewport of a cardinal section exports edges black
and opening voids / slab masks white; token:bg resolves per surface."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor

from firepro3d import theme
from firepro3d.constants import TOKEN_AUTO, TOKEN_BG
from tests.test_hf1_seam_fixes import force_theme   # noqa: F401  (fixture re-export)


def test_token_bg_resolves_canvas_bg_on_canvas_and_white_on_paper(qapp, force_theme):
    from PyQt6.QtWidgets import QGraphicsScene, QGraphicsRectItem
    from firepro3d.colour_tokens import resolve_colour
    from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
    force_theme("dark")
    assert resolve_colour(TOKEN_BG).name() == QColor(theme.DARK.canvas_bg).name()
    paper = QGraphicsScene()
    paper.paints_on_paper = True                  # what _paper_mode reads
    item = QGraphicsRectItem(0, 0, 1, 1)
    paper.addItem(item)
    for mode in (PaperColorMode.BW, PaperColorMode.FULL_COLOR):
        save_paper_color_mode(mode)
        assert resolve_colour(TOKEN_BG, item=item).name() == "#ffffff"


def _section_with_opening_and_slab(section_scene_for):
    from firepro3d.wall import WallSegment
    from firepro3d.wall_opening import WallOpening
    from firepro3d.floor_slab import FloorSlab
    ms, sec = section_scene_for("north")
    w = WallSegment(QPointF(-3000.0, 0.0), QPointF(3000.0, 0.0))
    ms._walls.append(w); ms.addItem(w)
    op = WallOpening(w, offset_along=3000.0, width_mm=1200.0, height_mm=2100.0,
                     sill_mm=0.0, feature_id="door_914")
    w.openings.append(op)
    slab = FloorSlab(points=[QPointF(-3000.0, -500.0), QPointF(3000.0, -500.0),
                             QPointF(3000.0, 500.0), QPointF(-3000.0, 500.0)])
    slab._top_mode = "absolute"
    ms._floor_slabs.append(slab); ms.addItem(slab)
    sec.rebuild()
    return ms, sec, op, slab


def test_void_and_mask_carry_bg_source_frame_carries_auto(qapp, section_scene_for):
    from firepro3d.section_scene import _SrcRect, _ROLE_SOURCE
    ms, sec, op, slab = _section_with_opening_and_slab(section_scene_for)
    void = next(it for it in sec.items() if it.data(_ROLE_SOURCE) is op)
    assert void._brush_src == TOKEN_BG
    frames = [it for it in sec.items() if isinstance(it, _SrcRect) and it._pen_src == TOKEN_AUTO]
    assert frames                                   # the opening frame rect
    masks = [it for it in sec.items() if isinstance(it, _SrcRect)
             and it._brush_src == TOKEN_BG and it.data(_ROLE_SOURCE) is None]
    assert masks                                    # the slab mask


def test_dark_theme_export_edges_black_voids_white(qapp, tmp_path, force_theme, section_scene_for):
    """Acceptance (b): the exported PDF's drawings inside the viewport hold a
    black stroke (frame) and white fills (void + mask) and no canvas colours."""
    from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
    from tests.test_lt1_block_paper import _export
    from tests.test_hf1_seam_fixes import _plot_colours
    force_theme("dark")
    save_paper_color_mode(PaperColorMode.FULL_COLOR)
    ms, sec, op, slab = _section_with_opening_and_slab(section_scene_for)
    # 1:100 -> an 8 m crop around (0, 0): the wall, door frame and slab mask lie
    # fully inside the viewport box (_plot_colours skips drawings that touch its edge).
    pdf = _export(tmp_path, sec, 0.01, "section600.pdf")     # resolver returns (sec, crop)
    strokes, fills = _plot_colours(pdf)
    assert (0.0, 0.0, 0.0) in strokes, strokes
    assert (1.0, 1.0, 1.0) in fills, fills
    dark_bg = tuple(round(c / 255.0, 2) for c in QColor(theme.DARK.canvas_bg).getRgb()[:3])
    assert dark_bg not in fills and (0.82, 0.82, 0.82) not in strokes   # #d0d0d0 edge retired
