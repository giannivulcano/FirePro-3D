"""AC2 (smoke re-entry 2026-10-22): section proxies -- the cut cross-section
and walls beyond the cut -- plot through their category's whole paper row
(Colour, Fill, Section body, Opacity, Visible), as plan walls do; Full Colour
keeps the model colours, as plan items do.

Model / paper rows mirror the smoke report: the model Wall row is white
(``#ffffff``) with an Automatic section body and grey fill (dark-theme house
setup), the paper Wall row is Automatic with No Fill / No Fill section. Real
PDF export through a sheet viewport (tests/_section_paper_helpers.py).
"""
import pytest
from PyQt6.QtCore import QSettings

from firepro3d import paper_display as pd
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
from tests._section_paper_helpers import drawings, export_scene, to_paper
from tests.test_section_classification import _placed_scene, _wall

SCALE = 0.01                                   # 1:100 -> 8 m crop
WHITE, GREY = (1.0, 1.0, 1.0), (0.6, 0.6, 0.6)


def _rows(paper_visible=True, paper_opacity=100):
    s = QSettings("GV", "FirePro3D")
    s.setValue("display/Wall/color", "#ffffff")
    s.setValue("display/Wall/fill", "#999999")
    s.setValue("display/Wall/section", "token:auto")
    s.setValue("display/Wall/section_pattern", "builtin-hatch-concrete")
    cats = pd.load_paper_categories()
    cats["Wall"].update(color="token:auto", fill="", section_color="",
                        visible=paper_visible, opacity=paper_opacity)
    pd.save_paper_categories(cats)


def _scene(section_scene_for):
    from firepro3d.section_scene import _ElevCutRect, _ElevProxyRect, _ROLE_SOURCE
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    cut = _wall(ms, (3000.0, -1000.0), (3000.0, 1000.0))       # crosses the cut line
    side_a = _wall(ms, (1000.0, 2000.0), (6000.0, 2000.0))     # one side is beyond
    side_b = _wall(ms, (1000.0, -2000.0), (6000.0, -2000.0))
    sec.rebuild()
    cuts = [i for i in sec.items()
            if isinstance(i, _ElevCutRect) and i.data(_ROLE_SOURCE) is cut]
    beyond = [i for i in sec.items() if type(i) is _ElevProxyRect
              and i.data(_ROLE_SOURCE) in (side_a, side_b)]
    assert cuts and beyond, (len(cuts), len(beyond))
    u = cuts[0].mapRectToScene(cuts[0].rect())
    for p in cuts[1:] + beyond:
        u = u.united(p.mapRectToScene(p.rect()))
    assert u.width() * SCALE < 76 and u.height() * SCALE < 76    # inside the box
    return sec, cuts, beyond, u.center()


def _inside(pdf, item, centre, tol=0.5):
    """Drawings lying inside *item*'s paper rect (hatch, body, outline)."""
    r = item.mapRectToScene(item.rect())
    x0, y0 = to_paper(r.topLeft(), centre, SCALE)
    x1, y1 = to_paper(r.bottomRight(), centre, SCALE)
    return [d for d in drawings(pdf)
            if d["rect"][0] >= x0 - tol and d["rect"][1] >= y0 - tol
            and d["rect"][2] <= x1 + tol and d["rect"][3] <= y1 + tol]


def _near(c, ref, tol=0.02):
    return c is not None and all(abs(a - b) <= tol for a, b in zip(c, ref))


@pytest.mark.parametrize("mode", [PaperColorMode.CUSTOM, PaperColorMode.BW])
def test_proxies_plot_through_paper_row_colours(qapp, tmp_path, section_scene_for, mode):
    save_paper_color_mode(mode)
    _rows()
    sec, cuts, beyond, centre = _scene(section_scene_for)
    pdf = export_scene(tmp_path, sec, SCALE, centre, f"col_{mode.value}.pdf")
    for it in cuts + beyond:
        ds = _inside(pdf, it, centre)
        assert ds, type(it).__name__
        strokes = [d["color"] for d in ds if "s" in d["type"]]
        assert strokes and all(_near(c, (0.0, 0.0, 0.0)) for c in strokes), (
            type(it).__name__, sorted(set(strokes)))
        # Paper body / fill = No Fill: no opaque dark or grey fill spans the
        # proxy (the hatch LOD tone is the hatch colour at HATCH_LOD_TONE).
        r = it.mapRectToScene(it.rect())
        area = r.width() * r.height() * SCALE * SCALE
        spans = [d for d in ds if "f" in d["type"] and d["fill"] is not None
                 and (d["rect"][2] - d["rect"][0]) * (d["rect"][3] - d["rect"][1])
                 >= 0.9 * area]
        bodies = [d["fill"] for d in spans if (d["fill_opacity"] or 1.0) > 0.99]
        assert not [c for c in bodies if not _near(c, WHITE)], (
            type(it).__name__, sorted(set(bodies)))
        tones = [d["fill"] for d in spans if (d["fill_opacity"] or 1.0) <= 0.99]
        assert all(_near(c, (0.0, 0.0, 0.0)) for c in tones), (
            type(it).__name__, sorted(set(tones)))


def test_full_colour_keeps_model_proxy_colours(qapp, tmp_path, section_scene_for):
    """Plan parity: Full Colour leaves model colours (white outline, grey beyond fill)."""
    save_paper_color_mode(PaperColorMode.FULL_COLOR)
    _rows()
    sec, cuts, beyond, centre = _scene(section_scene_for)
    pdf = export_scene(tmp_path, sec, SCALE, centre, "col_full.pdf")
    ds = _inside(pdf, beyond[0], centre)
    assert any(_near(d["fill"], GREY) for d in ds if d["fill"] is not None), (
        sorted({d["fill"] for d in ds if d["fill"] is not None}))
    assert any(_near(d["color"], WHITE) for d in ds if "s" in d["type"])


def test_hidden_wall_row_hides_proxies_and_restores(qapp, tmp_path, section_scene_for):
    from firepro3d.paper_display import apply_paper_overrides, restore_model_display
    save_paper_color_mode(PaperColorMode.BW)
    _rows(paper_visible=False)
    sec, cuts, beyond, centre = _scene(section_scene_for)
    pdf = export_scene(tmp_path, sec, SCALE, centre, "col_hidden.pdf")
    for it in cuts + beyond:
        assert not _inside(pdf, it, centre), type(it).__name__
    # Restore: the pass leaves every proxy exactly as projected.
    _rows(paper_opacity=40)
    before = [(i.isVisible(), i.opacity(), i._pen_src, i._brush_src,
               getattr(i, "_section_src", None), i._src_alpha)
              for i in cuts + beyond]
    saved = apply_paper_overrides(sec, sec.sceneRect(), SCALE)
    assert all(abs(i.opacity() - 0.4) < 1e-6 for i in cuts + beyond)
    assert all(i._pen_src == "token:auto" for i in cuts + beyond)
    restore_model_display(saved)
    after = [(i.isVisible(), i.opacity(), i._pen_src, i._brush_src,
              getattr(i, "_section_src", None), i._src_alpha)
             for i in cuts + beyond]
    assert after == before
