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


def test_section_viewport_resolves_after_reload_without_open_tab(qapp, tmp_path):
    """Acceptance (a): a sheet viewport bound as section:<name> resolves to a
    scene with no tab open (today _resolve_elevation returns None for a closed tab)."""
    from PyQt6.QtCore import QRectF
    from firepro3d.paper_space import ViewResolver
    from firepro3d.section_marker import CARDINALS
    from tests.test_section_persistence import _scene_with_manager
    ms, mgr = _scene_with_manager(qapp)
    mgr.seed_cardinals()
    mgr.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
    class _Plans:
        _views = {}

    class _Details:
        detail_names = []

    resolver = ViewResolver(ms, _Plans(), _Details(), mgr, level_manager=ms._level_manager)
    got = resolver.resolve("section", "Section 1")
    assert got is not None and got[0].marker is mgr.markers["Section 1"]
    got_e = resolver.resolve("elevation", "North")
    assert got_e is not None and got_e[0].marker is mgr.markers["north"]
    assert mgr.open_names == []                                       # no tab was opened
    assert resolver.resolve("section", "Nope") is None
    assert resolver.available_views()["Sections"] == ["Section 1"]
    assert resolver.available_views()["Elevations"] == ["North", "South", "East", "West"]
    assert resolver.resolve_level_context("section", "Section 1") is None   # no isolation


def test_section_viewport_survives_project_reload(qapp, tmp_path):
    """Acceptance (a), reload half: save, load into a fresh scene, resolve the same name."""
    from firepro3d.paper_space import ViewResolver
    from tests.test_section_persistence import _scene_with_manager
    ms, mgr = _scene_with_manager(qapp)
    mgr.seed_cardinals()
    mgr.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
    path = tmp_path / "s.fp3d"
    ms.save_to_file(str(path))
    ms2, mgr2 = _scene_with_manager(qapp)
    ms2.load_from_file(str(path))
    resolver = ViewResolver(ms2, None, None, mgr2, level_manager=ms2._level_manager)
    got = resolver.resolve("section", "Section 1")
    assert got is not None and got[0].marker is mgr2.markers["Section 1"]
    assert mgr2.open_names == []


def test_placed_marker_plots_and_cardinal_does_not(qapp, tmp_path):
    """Acceptance (a), second half: the host plan's paper render includes the
    placed marker and excludes the cardinal ones (real manager, real markers)."""
    from PyQt6.QtCore import QRectF
    from firepro3d.paper_display import apply_paper_overrides, restore_model_display
    from firepro3d.section_marker import CARDINALS
    from tests.test_section_persistence import _scene_with_manager
    ms, mgr = _scene_with_manager(qapp)
    mgr.seed_cardinals()
    s = mgr.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
    saved = apply_paper_overrides(ms, QRectF(-20000, -20000, 40000, 40000))
    try:
        assert s.isVisible() is True
        assert not any(mgr.markers[c].isVisible() for c in CARDINALS)
    finally:
        restore_model_display(saved)
    assert all(mgr.markers[c].isVisible() for c in CARDINALS)


@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_section_viewport_background_plots_paper_white(
        qapp, tmp_path, force_theme, section_scene_for, theme_name):
    """AC5: a blank point inside a section sheet viewport rasterises paper
    white in both colour modes, never the canvas colour (plan parity)."""
    import fitz
    from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
    from tests.test_lt1_block_paper import _export, _VP_X, _VP_Y
    force_theme(theme_name)
    for mode in (PaperColorMode.BW, PaperColorMode.FULL_COLOR):
        save_paper_color_mode(mode)
        ms, sec, op, slab = _section_with_opening_and_slab(section_scene_for)
        # 1:100, crop +-4 m about (0, 0): paper (VP+3, VP+3) mm = scene
        # (-3700, -3700), above the wall top and clear of the datum text.
        pdf = _export(tmp_path, sec, 0.01, f"bg_{theme_name}_{mode.name}.pdf")
        doc = fitz.open(str(pdf))
        try:
            pt = 72.0 / 25.4
            x, y = (_VP_X + 3.0) * pt, (_VP_Y + 3.0) * pt
            pix = doc[0].get_pixmap(dpi=144, clip=fitz.Rect(x, y, x + 2, y + 2))
            assert tuple(pix.pixel(0, 0)[:3]) == (255, 255, 255), (mode, pix.pixel(0, 0))
        finally:
            doc.close()
