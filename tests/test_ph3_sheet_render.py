"""PH3 sheet viewport phasing: render guards (design DD1-DD4; AC9p, AC13p, AC15,
DD2, R1, R2; Task 9 adds AC4r, AC14 and restore).

Every guard paints a real PaperScene viewport through SheetViewport.paint (VC3)
in As Authored OFF (bw) and ON (full_color) rows (R3). Expected values cite
constants.PHASE_EXISTING_COLOUR / _FILL (D-PH10) and paper_display.DEFAULT_LINE_WEIGHTS
through tests/_ph3_helpers. Base (pre-PH3) row-ON inks seen by the 2026-11-14
probe: wall #cccccc, door #aa6633, floor #8888cc, roof #d2b48c, room #4488cc, pipe
#4488ff; sprinkler / water supply / fitting / block line: white on white (nothing);
row OFF: black -- none passes assert_status_grey.
"""
from collections import Counter

import pytest

from firepro3d.constants import PHASE_DEMOLITION, PHASE_EXISTING
from tests import _ph1_helpers as h
from tests._ph1_helpers import ph1_cleanup  # noqa: F401  (autouse: ends every scene)
from tests._ph3_helpers import (EXISTING_FILL, EXISTING_GREY, PX, assert_status_grey,
                                darkest, fill_block, inked, is_grey, make_viewport,
                                model_box, near, phasing, pixels, render, set_row,
                                set_status, to_px)
from tests.paper_mode_shim import BW, FULL_COLOR, set_paper_mode
from tests.test_materials_cut import _fresh_tables  # noqa: F401  (autouse: fill types + materials)

ROWS = [BW, FULL_COLOR]          # every row As Authored OFF / ON (R3)


def _phased(ms, kind, sid):
    """Add one *kind* (tests/_ph1_helpers.ADD) at status *sid*; an opening's host
    wall shares the status (it shares the frame)."""
    item = h.ADD[kind](ms)
    item.phase = sid
    if kind == "opening":
        ms._walls[0].phase = sid
    if kind == "pipe":
        item.set_property("Show Label", "False")   # Task 7 owns the label
    return item


def _assert_hatch_in_status_colours(colours):
    """AC15: background = the status Fill, pattern lines = the status Colour, nothing else."""
    ink = inked(colours)
    names = Counter(c.name() for c in ink)
    assert names and names.most_common(1)[0][0] == EXISTING_FILL, names.most_common(4)
    assert any(near(c, EXISTING_GREY) for c in ink), names.most_common(4)
    assert all(is_grey(c) for c in ink), names.most_common(8)


@pytest.mark.parametrize("mode", ROWS)
@pytest.mark.parametrize("kind", ["wall", "opening", "floor_slab", "roof", "room", "pipe"])
def test_ac9p_kinds_plot_existing_graphics(qapp, kind, mode):
    set_paper_mode(mode)
    ms = h.scene()
    _phased(ms, kind, PHASE_EXISTING)
    _ps, vp = make_viewport(ms, phase_display=phasing())
    assert_status_grey(pixels(render(vp)))


@pytest.mark.parametrize("mode", ROWS)
@pytest.mark.parametrize("kind", ["sprinkler", "water_supply"])
def test_ac9p_symbols_take_status_colour(qapp, real_system_library, kind, mode):
    set_paper_mode(mode)
    ms = h.scene()
    _phased(ms, kind, PHASE_EXISTING)
    _ps, vp = make_viewport(ms, phase_display=phasing())
    assert_status_grey(pixels(render(vp)))


@pytest.mark.parametrize("mode", ROWS)
def test_ac9p_block_plots_status_colour_and_fill(qapp, mode):
    set_paper_mode(mode)
    ms = h.scene()
    inst = fill_block(ms)
    inst.phase = PHASE_EXISTING
    _ps, vp = make_viewport(ms, phase_display=phasing())
    img = render(vp)
    assert_status_grey(pixels(img))
    body = inked(pixels(img, model_box(vp, inst.sceneBoundingRect(), inset=0.25)))
    assert body and {c.name() for c in body} == {EXISTING_FILL}


def test_dd2_colour_only_status_keeps_the_authored_fill(qapp):
    from firepro3d.display_manager import _apply_to_scene_items, _read_category_from_settings
    set_paper_mode(FULL_COLOR)
    ms = h.scene()
    slab = h.add_slab(ms)
    _apply_to_scene_items(ms, "Floor", {**_read_category_from_settings("Floor"),
                                        "color": "#ff0000", "fill": "#00ff00"})
    slab.phase = PHASE_EXISTING
    set_status(PHASE_EXISTING, fill=None)                 # a colour-only status
    _ps, vp = make_viewport(ms, phase_display=phasing())
    img = render(vp)
    body = inked(pixels(img, model_box(vp, slab.sceneBoundingRect(), inset=0.3)))
    assert body and {c.name() for c in body} == {"#00ff00"}          # the pinned authored fill
    assert any(near(c, EXISTING_GREY, 0) for c in inked(pixels(img)))   # outline = status colour


@pytest.mark.parametrize("mode", ROWS)
def test_r2_status_weight_replaces_the_row_weight(qapp, mode):
    set_paper_mode(mode)
    ms = h.scene()
    p = ms.add_pipe(ms.add_node(0.0, 2000.0), ms.add_node(6000.0, 2000.0))
    p.set_property("Show Label", "False")
    p.phase = PHASE_EXISTING
    set_status(PHASE_EXISTING, weight="Extra Thick")        # DEFAULT_LINE_WEIGHTS: 1.00 mm
    _ps, vp = make_viewport(ms, phase_display=phasing())
    img = render(vp)
    x, y = to_px(vp, 1000.0, 2000.0)
    column = inked(pixels(img, (x, y - 20, x + 1, y + 21)))
    assert abs(len(column) - round(1.00 * PX)) <= 1         # the Pipe row's "Fine" = 2-3 px


@pytest.mark.parametrize("status_opacity,expected", [
    (50, 255 - (255 - EXISTING_GREY) * 0.50),    # 191.5: replaces the row's 60 (R1)
    (None, 255 - (255 - EXISTING_GREY) * 0.60),  # 178.8: "--" keeps the row's 60
])
@pytest.mark.parametrize("mode", ROWS)
def test_r1_status_opacity_replaces_the_row_opacity(qapp, mode, status_opacity, expected):
    set_paper_mode(mode)
    set_row("Pipe", opacity=60)
    ms = h.scene()
    p = ms.add_pipe(ms.add_node(0.0, 2000.0), ms.add_node(6000.0, 2000.0))
    p.set_property("Show Label", "False")
    p.phase = PHASE_EXISTING
    set_status(PHASE_EXISTING, opacity=status_opacity, weight="Extra Thick")
    _ps, vp = make_viewport(ms, phase_display=phasing())
    d = darkest(inked(pixels(render(vp))))
    assert is_grey(d) and abs(d.red() - expected) <= 3, d.name()


@pytest.mark.parametrize("mode", ROWS)
def test_ac15_hatched_existing_wall_keeps_its_pattern(qapp, shipped_hatches, mode):
    from firepro3d.hatch_patterns import BUILTIN_DIAGONAL
    from tests.test_materials_cut import _cut_wall, _mat
    set_paper_mode(mode)
    ms = h.scene()
    shipped_hatches(ms)
    w = _cut_wall(ms, y=2000.0, m=_mat("H", "#ff0000", BUILTIN_DIAGONAL))
    w.phase = PHASE_EXISTING
    _ps, vp = make_viewport(ms, phase_display=phasing())
    _assert_hatch_in_status_colours(
        pixels(render(vp), model_box(vp, w.sceneBoundingRect(), inset=0.3)))


@pytest.mark.parametrize("kind", ["wall", "opening", "floor_slab", "roof", "room", "pipe",
                                  "block", "sprinkler", "water_supply"])
def test_ac13p_hidden_status_is_not_drawn(qapp, real_system_library, kind):
    set_paper_mode(FULL_COLOR)
    ms = h.scene()
    if kind == "block":
        fill_block(ms).phase = PHASE_DEMOLITION
    else:
        _phased(ms, kind, PHASE_DEMOLITION)
    if kind in ("sprinkler", "water_supply"):
        # Row-ON SVG symbols are white on white at base and Demolition forces no
        # colour (linetype only): give the status a colour so it plots when shown.
        set_status(PHASE_DEMOLITION, colour="#ff0000")
    _ps, shown = make_viewport(ms, phase_display=phasing())
    assert inked(pixels(render(shown)))                         # it plots when shown
    _ps2, hidden = make_viewport(ms, phase_display=phasing(PHASE_DEMOLITION))
    assert not inked(pixels(render(hidden)))                    # D-PH17: not drawn

# --- Task 7: host labels (R4) and section proxies (AC15) -----------------------

def _labelled_pipe(ms, sid):
    """A 6000 mm pipe at y=2000 with a real Pipe label (two 3 mm bound texts,
    authored black on paper: tests/test_sb4a_pipe_label._pipe_def)."""
    from tests.test_sb4a_pipe_label import _pipe_def
    _pipe_def(ms)
    p = ms.add_pipe(ms.add_node(0.0, 2000.0), ms.add_node(6000.0, 2000.0))
    p.phase = sid
    return p


@pytest.mark.parametrize("mode", ROWS)
def test_ac13p_shown_label_takes_its_hosts_status_colour(qapp, mode):
    set_paper_mode(mode)
    ms = h.scene()
    _labelled_pipe(ms, PHASE_EXISTING)
    _ps, vp = make_viewport(ms, phase_display=phasing())
    img = render(vp)
    assert_status_grey(pixels(img))                   # pipe AND label text: no black
    _x, py = to_px(vp, 0.0, 2000.0)
    off_band = (inked(pixels(img, (0, 0, img.width(), py - 4)))
                + inked(pixels(img, (0, py + 5, img.width(), img.height()))))
    assert off_band                                   # the label printed (off the pipe's band)


@pytest.mark.parametrize("mode", ROWS)
def test_ac13p_shown_label_takes_its_hosts_status_opacity(qapp, mode):
    set_paper_mode(mode)
    ms = h.scene()
    _labelled_pipe(ms, PHASE_EXISTING)
    set_status(PHASE_EXISTING, opacity=50)
    _ps, vp = make_viewport(ms, phase_display=phasing())
    img = render(vp)
    expected = 255 - (255 - EXISTING_GREY) * 0.50     # 191.5: #808080 at 50 % on white
    _x, py = to_px(vp, 0.0, 2000.0)
    label_ink = (inked(pixels(img, (0, 0, img.width(), py - 4)))
                 + inked(pixels(img, (0, py + 5, img.width(), img.height()))))
    d = darkest(label_ink)
    assert is_grey(d) and abs(d.red() - expected) <= 3, d.name()


@pytest.mark.parametrize("mode", ROWS)
def test_ac15_section_cut_proxy_keeps_its_hatch_in_status_colours(
        qapp, section_scene_for, shipped_hatches, mode):
    from firepro3d.hatch_patterns import BUILTIN_DIAGONAL
    from tests.test_materials_cut import _mat
    from tests.test_section_classification import _placed_scene, _source_rects, _wall
    set_paper_mode(mode)
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    shipped_hatches(ms)
    w = _wall(ms, (3000.0, -1000.0), (3000.0, 1000.0))       # straddles the cut
    w.material_id = _mat("H", "#ff0000", BUILTIN_DIAGONAL).id
    w.phase = PHASE_EXISTING
    sec.rebuild()
    r = _source_rects(sec, w)[0].sceneBoundingRect()
    _ps, vp = make_viewport(sec, kind="section", name="Section 1",
                            crop=r.adjusted(-2000.0, -2000.0, 2000.0, 2000.0),
                            phase_display=phasing())
    _assert_hatch_in_status_colours(pixels(render(vp), model_box(vp, r, inset=0.3)))


# --- Task 8: fittings (D-PH13) and underlays (R5) --------------------------------

@pytest.mark.parametrize("mode", ROWS)
def test_ac9p_fitting_takes_status_colour(qapp, monkeypatch, mode):
    from firepro3d.fitting import Fitting
    monkeypatch.setattr(Fitting, "SHOW_PLAIN_SYMBOLS", True)   # D1 hides plain types (test_hf1_seam_fixes precedent)
    set_paper_mode(mode)
    set_row("Pipe", visible=False)                     # only the fitting symbol inks
    ms = h.scene()
    a, b, c = ms.add_node(0.0, 0.0), ms.add_node(3000.0, 0.0), ms.add_node(3000.0, 3000.0)
    ms.add_pipe(a, b)
    ms.add_pipe(b, c)                                  # b: a 90 elbow; a, c: caps (New)
    b.fitting.phase_override = PHASE_EXISTING          # D-PH4 override; the pipes stay New
    _ps, vp = make_viewport(ms, phase_display=phasing())
    x, y = to_px(vp, 3000.0, 0.0)
    assert_status_grey(pixels(render(vp), (x - 20, y - 20, x + 21, y + 21)))


@pytest.mark.parametrize("mode", ROWS)
def test_r5_underlay_takes_status_colour(qapp, mode):
    from tests._ph3_helpers import underlay
    set_paper_mode(mode)
    ms = h.scene()
    underlay(ms, PHASE_EXISTING)
    _ps, vp = make_viewport(ms, phase_display=phasing())
    assert_status_grey(pixels(render(vp)))           # base: ON red layer, OFF black row


@pytest.mark.parametrize("mode", ROWS)
def test_r5_underlay_takes_status_opacity(qapp, mode):
    from tests._ph3_helpers import underlay
    set_paper_mode(mode)
    ms = h.scene()
    underlay(ms, PHASE_EXISTING)
    set_status(PHASE_EXISTING, opacity=50)
    _ps, vp = make_viewport(ms, phase_display=phasing())
    d = darkest(inked(pixels(render(vp))))
    assert is_grey(d) and abs(d.red() - (255 - (255 - EXISTING_GREY) * 0.50)) <= 3, d.name()


def test_r5_hidden_underlay_is_not_drawn(qapp):
    from tests._ph3_helpers import underlay
    ms = h.scene()
    underlay(ms, PHASE_DEMOLITION)
    _ps, shown = make_viewport(ms, phase_display=phasing())
    assert inked(pixels(render(shown)))
    _ps2, hidden = make_viewport(ms, phase_display=phasing(PHASE_DEMOLITION))
    assert not inked(pixels(render(hidden)))
