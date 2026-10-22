"""AC2: section proxies -- the cut cross-section and walls beyond the cut --
plot at the source item's paper category weight, as plan walls do.

Real PDF export through a sheet viewport (tests/_section_paper_helpers.py);
strokes selected by geometry (the proxy's own paper rect), never by width.
"""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d import paper_display as pd
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
from tests._section_paper_helpers import export_scene, strokes_near, to_paper
from tests.test_section_classification import _placed_scene, _wall

SCALE = 0.01                                   # 1:100 -> 8 m crop


def _paper_rect(item, centre):
    r = item.mapRectToScene(item.rect())
    x0, y0 = to_paper(r.topLeft(), centre, SCALE)
    x1, y1 = to_paper(r.bottomRight(), centre, SCALE)
    return (x0, y0, x1, y1)


@pytest.mark.parametrize("lw_mm", [0.35, 0.7])
def test_cut_and_beyond_walls_plot_at_wall_weight(qapp, tmp_path, section_scene_for, lw_mm):
    from firepro3d.section_scene import _ElevCutRect, _ElevProxyRect, _ROLE_SOURCE
    save_paper_color_mode(PaperColorMode.BW)
    cats = pd.load_paper_categories()
    cats["Wall"]["line_weight"] = pd.nearest_weight_name(lw_mm)
    pd.save_paper_categories(cats)
    expect = pd.resolve_line_weight_mm(cats["Wall"]["line_weight"])
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
    proxies = cuts + beyond
    u = proxies[0].mapRectToScene(proxies[0].rect())
    for p in proxies[1:]:
        u = u.united(p.mapRectToScene(p.rect()))
    centre = u.center()
    assert u.width() * SCALE < 76 and u.height() * SCALE < 76    # inside the box
    pdf = export_scene(tmp_path, sec, SCALE, centre, f"sec_{lw_mm}.pdf")
    for it in proxies:
        hits = strokes_near(pdf, _paper_rect(it, centre))
        assert any(abs(d["width"] - expect) <= 0.02 for d in hits), (
            type(it).__name__, expect, [round(d["width"], 3) for d in hits])


def test_every_stroked_proxy_names_its_paper_category(qapp, section_scene_for):
    """Coverage: each stroked projected proxy carries the paper category of
    its source (Wall / Floor / Roof / Pipe / Sprinkler / Door|Window|Opening)."""
    from tests.test_section_sheet_plot import _section_with_opening_and_slab
    from firepro3d.section_scene import (_ColourSrcMixin, ElevGridlineItem,
                                         ElevDatumItem)
    from PyQt6.QtCore import Qt
    ms, sec, op, slab = _section_with_opening_and_slab(section_scene_for)

    def _annotation_child(it):
        p = it.parentItem()
        while p is not None:
            if isinstance(p, (ElevGridlineItem, ElevDatumItem)):
                return True
            p = p.parentItem()
        return False
    stroked = [i for i in sec.items() if isinstance(i, _ColourSrcMixin)
               and i.pen().style() != Qt.PenStyle.NoPen and not _annotation_child(i)]
    assert stroked
    missing = [type(i).__name__ for i in stroked if i._paper_cat is None]
    assert not missing, missing
    assert {i._paper_cat for i in stroked} >= {"Wall", "Floor", op.display_category}
