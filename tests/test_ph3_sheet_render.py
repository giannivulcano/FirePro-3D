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
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d.constants import PHASE_DEMOLITION, PHASE_EXISTING
from tests import _ph1_helpers as h
from tests._ph1_helpers import ph1_cleanup  # noqa: F401  (autouse: ends every scene)
from tests._ph3_helpers import (EXISTING_FILL, EXISTING_GREY, PX, assert_status_grey,
                                darkest, fill_block, inked, is_grey, make_viewport,
                                model_box, near, phasing, pixels, render, set_row,
                                set_status, to_px)
from tests.paper_mode_shim import BW, FULL_COLOR, set_paper_mode
from tests.test_sb4f_data import panels  # noqa: F401
from tests.test_materials_cut import _fresh_tables  # noqa: F401  (autouse: fill types + materials)

ROWS = [BW, FULL_COLOR]          # every row As Authored OFF / ON (R3)


def _phased(ms, kind, sid):
    """Add one *kind* (tests/_ph1_helpers.ADD) at status *sid*; an opening's host
    wall shares the status (it shares the frame)."""
    item = h.ADD[kind](ms)
    item.phase = sid
    if kind == "opening":
        next(w for w in ms._walls if item in w.openings).phase = sid   # its own host, not _walls[0]
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


# --- Task 9: AC4r, AC14, restore, AC13p (all kinds), panel -> render -------------

def _mixed_scene():
    """Existing wall / slab / pipe / block / underlay, a Demolition room."""
    from tests._ph3_helpers import underlay
    ms = h.scene()
    for kind in ("wall", "floor_slab", "pipe"):
        _phased(ms, kind, PHASE_EXISTING)
    fill_block(ms).phase = PHASE_EXISTING
    underlay(ms, PHASE_EXISTING)
    _phased(ms, "room", PHASE_DEMOLITION)
    return ms


@pytest.mark.parametrize("mode", ROWS)
def test_ac4r_phasing_off_and_legacy_viewports_render_identical_to_base(qapp, monkeypatch, mode):
    from firepro3d import phase_display
    from firepro3d.paper_space import SheetViewData
    from firepro3d.phase_display import PhaseDisplay
    from tests._ph3_helpers import add_viewport, viewport_data
    set_paper_mode(mode)
    ms = _mixed_scene()
    rec = viewport_data().to_dict()
    del rec["phase_display"]                                       # saved before phasing
    legacy = SheetViewData.from_dict(rec)
    off = viewport_data(phase_display=PhaseDisplay(False, frozenset({PHASE_DEMOLITION})))
    got = [render(add_viewport(ms, d)[1]) for d in (legacy, off)]
    # Base: the PH3 merge forced to identity (the pre-phasing pass).
    monkeypatch.setattr(phase_display, "merge",
                        lambda cat, item, *, keys=phase_display.ALL_KEYS: cat)
    base = render(add_viewport(ms, viewport_data())[1])
    assert inked(pixels(base))
    assert got[0] == base
    assert got[1] == base


def test_ac14_exported_pdf_plots_what_the_sheet_shows(qapp, tmp_path):
    import fitz
    from unittest.mock import MagicMock
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QColor, QImage, QPainter
    from firepro3d import paper_export
    from firepro3d.paper_space import Sheet, SheetViewData, ViewResolver
    from tests._ph3_helpers import SCALE
    from tests._section_paper_helpers import VP_W, VP_X, VP_Y
    dpi = 150
    set_paper_mode(FULL_COLOR)                       # the slab body inks when shown (#8888cc)
    ms = h.scene()
    p = ms.add_pipe(ms.add_node(0.0, 4000.0), ms.add_node(6000.0, 4000.0))
    p.set_property("Show Label", "False")
    p.phase = PHASE_EXISTING
    h.add_slab(ms).phase = PHASE_DEMOLITION          # (0,0)-(3000,2000)
    set_status(PHASE_EXISTING, weight="Extra Thick")
    crop = QRectF(-1000.0, -1000.0, VP_W / SCALE, VP_W / SCALE)
    data = SheetViewData("plan", "Plan: Level 1", "T", SCALE, VP_X, VP_Y, VP_W, VP_W,
                         show_border=False, crop_rect=QRectF(crop),
                         phase_display=phasing(PHASE_DEMOLITION))
    sheet = Sheet.create_default()
    sheet.paper_size = "A4"
    sheet.sheet_views = [data]
    res = MagicMock(spec=ViewResolver)
    res.resolve.side_effect = lambda vt, vn: (ms, QRectF(crop))
    res.display_name.side_effect = lambda vt, vn: vn
    out = tmp_path / "ph3.pdf"
    paper_export.export_pdf([sheet], res, str(out), dpi=dpi)
    pix = fitz.open(str(out))[0].get_pixmap(dpi=dpi)
    screen = QImage(pix.width, pix.height, QImage.Format.Format_RGB32)
    screen.fill(QColor("#ffffff"))
    painter = QPainter(screen)
    paper_export.render_sheet(sheet, res, painter, QRectF(0, 0, pix.width, pix.height))
    painter.end()
    per_mm = dpi / 25.4

    def at(x, y):
        px = int(round((VP_X + (x - crop.left()) * SCALE) * per_mm))
        py = int(round((VP_Y + (y - crop.top()) * SCALE) * per_mm))
        i = (py * pix.width + px) * pix.n
        return tuple(pix.samples[i:i + 3]), QColor(screen.pixel(px, py)).getRgb()[:3]

    for rgb in at(1000.0, 4000.0):                   # the Existing pipe centre (1 mm wide)
        assert all(abs(ch - EXISTING_GREY) <= 12 for ch in rgb), rgb
    for rgb in at(1500.0, 1000.0):                   # the hidden Demolition slab body
        assert min(rgb) >= 245, rgb


def test_restore_every_slot_after_a_phased_render(qapp, real_system_library):
    from tests._ph3_helpers import underlay
    set_paper_mode(BW)
    ms = h.scene()
    pipe = _labelled_pipe(ms, PHASE_EXISTING)
    wall, slab, spr = (_phased(ms, k, PHASE_EXISTING) for k in ("wall", "floor_slab", "sprinkler"))
    inst = fill_block(ms)
    inst.phase = PHASE_EXISTING
    room = _phased(ms, "room", PHASE_DEMOLITION)
    _rec, group = underlay(ms, PHASE_EXISTING)
    set_status(PHASE_EXISTING, opacity=50, weight="Extra Thick")
    tracked = [wall, slab, pipe, pipe.label, inst, spr, room, room._tag, group]

    def snap():
        return [(it.isVisible(), it.opacity(),
                 getattr(it, "_display_color", None),
                 getattr(it, "_display_fill_color", None),
                 getattr(it, "_display_section_color", None),
                 getattr(it, "_paper_fill_colour", None),
                 getattr(it, "_paper_pen_width", None),
                 getattr(it, "_paper_pen_color", None)) for it in tracked]

    before = snap()
    _ps, vp = make_viewport(ms, phase_display=phasing(PHASE_DEMOLITION))
    assert inked(pixels(render(vp)))                     # the pass ran
    for it, b, a in zip(tracked, before, snap()):
        assert a == b, (type(it).__name__, b, a)


def test_ac13p_hidden_status_hides_every_kind_and_label(qapp, real_system_library, monkeypatch):
    from firepro3d.fitting import Fitting
    from tests._ph3_helpers import underlay
    monkeypatch.setattr(Fitting, "SHOW_PLAIN_SYMBOLS", True)
    set_paper_mode(FULL_COLOR)
    ms = h.scene()
    _labelled_pipe(ms, PHASE_DEMOLITION)
    for kind in ("wall", "opening", "floor_slab", "roof", "room", "sprinkler", "water_supply"):
        _phased(ms, kind, PHASE_DEMOLITION)
    fill_block(ms).phase = PHASE_DEMOLITION
    underlay(ms, PHASE_DEMOLITION)
    a, b, c = ms.add_node(5000.0, 0.0), ms.add_node(6500.0, 0.0), ms.add_node(6500.0, 1500.0)
    for p in (ms.add_pipe(a, b), ms.add_pipe(b, c)):
        p.phase = PHASE_DEMOLITION                       # the elbow derives Demolition (D-PH4)
        p.set_property("Show Label", "False")
    _ps, shown = make_viewport(ms, phase_display=phasing())
    assert inked(pixels(render(shown)))
    _ps2, hidden = make_viewport(ms, phase_display=phasing(PHASE_DEMOLITION))
    assert not inked(pixels(render(hidden)))             # elements, labels, symbols, underlay


def test_panel_phasing_reaches_the_render_and_undo_takes_it_back(qapp, panels):
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
    from firepro3d.paper_space import ViewportProperties
    from firepro3d.property_manager import PropertyManager
    set_paper_mode(BW)
    ms = h.scene()
    _phased(ms, "floor_slab", PHASE_DEMOLITION)
    ps, vp = make_viewport(ms)
    assert inked(pixels(render(vp)))                     # Phasing off: it plots
    pm = PropertyManager()
    panels.append(pm)
    pm.resize(400, 600)
    pm.show()
    QTest.qWaitForWindowExposed(pm)
    pm.show_properties(ViewportProperties(ps, vp))
    QApplication.processEvents()
    pm._prop_widgets["Phasing"].click()
    QTest.qWait(300)
    pm._prop_widgets["Show Demolition"].click()
    QTest.qWait(300)
    assert not inked(pixels(render(vp)))                 # D-PH17 through the panel
    ps.undo_stack.undo()
    assert inked(pixels(render(vp)))


# --- Group P review guards: fitting hide, pass pop, proxy hide / label -----------

def _fitting_scene(monkeypatch, mode):
    """A 90 elbow whose Fitting overrides to Existing (strong red status colour);
    pipes hidden, so only the fitting symbol can ink."""
    from firepro3d.fitting import Fitting
    monkeypatch.setattr(Fitting, "SHOW_PLAIN_SYMBOLS", True)
    set_paper_mode(mode)
    set_row("Pipe", visible=False)
    set_status(PHASE_EXISTING, colour="#ff0000")
    ms = h.scene()
    a, b, c = ms.add_node(0.0, 0.0), ms.add_node(3000.0, 0.0), ms.add_node(3000.0, 3000.0)
    ms.add_pipe(a, b)
    ms.add_pipe(b, c)
    b.fitting.phase_override = PHASE_EXISTING
    return ms


@pytest.mark.parametrize("mode", ROWS)
def test_ph3_hidden_fitting_status_hides_the_fitting_symbol(qapp, monkeypatch, mode):
    ms = _fitting_scene(monkeypatch, mode)
    _ps, shown = make_viewport(ms, phase_display=phasing())
    x, y = to_px(shown, 3000.0, 0.0)
    box = (x - 20, y - 20, x + 21, y + 21)
    assert inked(pixels(render(shown), box))                  # the fitting inks when shown
    _ps2, hidden = make_viewport(ms, phase_display=phasing(PHASE_EXISTING))
    assert not inked(pixels(render(hidden), box))             # its status hidden: not drawn


def test_ph3_phase_pass_is_popped_after_a_phased_render(qapp):
    from firepro3d import phase_display
    set_paper_mode(FULL_COLOR)
    ms = h.scene()
    _phased(ms, "wall", PHASE_EXISTING)
    _ps, vp = make_viewport(ms, phase_display=phasing())
    assert inked(pixels(render(vp)))
    assert phase_display.active() is None
    assert phase_display._STACK == []


def test_ph3_phase_pass_is_popped_when_the_override_pass_raises(qapp, monkeypatch):
    from firepro3d import paper_display, phase_display
    set_paper_mode(FULL_COLOR)
    ms = h.scene()
    _phased(ms, "wall", PHASE_EXISTING)
    _ps, vp = make_viewport(ms, phase_display=phasing())

    def boom(*a, **kw):
        assert phase_display.active() is not None         # the pass was pushed
        raise RuntimeError("override pass failed")
    monkeypatch.setattr(paper_display, "apply_paper_overrides", boom)
    img = QImage(int(vp.data.w * PX), int(vp.data.h * PX), QImage.Format.Format_RGB32)
    painter = QPainter(img)
    try:                                   # end the painter ourselves: render() would
        with pytest.raises(RuntimeError, match="override pass failed"):   # abort on a live one
            vp.paint(painter, None, None)
    finally:
        painter.end()
    assert phase_display.active() is None
    assert phase_display._STACK == []


@pytest.mark.parametrize("mode", ROWS)
def test_ph3_hidden_status_hides_a_section_proxy(qapp, section_scene_for, mode):
    from tests.test_section_classification import _placed_scene, _source_rects, _wall
    set_paper_mode(mode)
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    w = _wall(ms, (3000.0, -1000.0), (3000.0, 1000.0))       # straddles the cut
    w.phase = PHASE_DEMOLITION
    sec.rebuild()
    r = _source_rects(sec, w)[0].sceneBoundingRect()
    crop = r.adjusted(-2000.0, -2000.0, 2000.0, 2000.0)
    _ps, shown = make_viewport(sec, kind="section", name="Section 1", crop=crop,
                               phase_display=phasing())
    x0, y0, x1, y1 = model_box(shown, r)
    box = (x0, y0 + 6, x1, y1 - 6)                            # the side outline, clear of the datum lines on its top / bottom edges
    assert inked(pixels(render(shown), box))
    _ps2, hidden = make_viewport(sec, kind="section", name="Section 1", crop=crop,
                                 phase_display=phasing(PHASE_DEMOLITION))
    assert not inked(pixels(render(hidden), box))


PIPE_CROP = QRectF(1000.0, -4500.0, 6000.0, 4000.0)


def _section_pipe_label_view(section_scene_for, mode, **status):
    from tests.test_section_pipe_labels import _labels, _scene
    from tests.test_section_pipe_symbols import _pipe
    set_paper_mode(mode)
    ms, sec = _scene(section_scene_for)
    pipe = _pipe(ms, (2000.0, -1000.0, 2500.0), (6000.0, -1000.0, 2500.0))
    pipe.phase = PHASE_EXISTING
    set_status(PHASE_EXISTING, **status)
    sec.rebuild()
    assert _labels(sec, pipe)                                  # the proxy owns a label
    return make_viewport(sec, kind="section", name="Section 1",
                         crop=PIPE_CROP, phase_display=phasing())


def _pipe_box(vp):
    """The pipe + label band (the section's datums / grids sit outside it)."""
    return model_box(vp, QRectF(2000.0, -3000.0, 4000.0, 1000.0))


@pytest.mark.parametrize("mode", ROWS)
def test_ph3_section_pipe_label_takes_its_hosts_status_colour(qapp, section_scene_for, mode):
    _ps, vp = _section_pipe_label_view(section_scene_for, mode)
    assert_status_grey(pixels(render(vp), _pipe_box(vp)))   # line AND label: a black label fails


@pytest.mark.parametrize("mode", ROWS)
def test_ph3_section_pipe_label_takes_its_hosts_status_opacity(qapp, section_scene_for, mode):
    _ps, vp = _section_pipe_label_view(section_scene_for, mode, opacity=50)
    expected = 255 - (255 - EXISTING_GREY) * 0.50              # #808080 at 50 % on white
    d = darkest(inked(pixels(render(vp), _pipe_box(vp))))                     # an opaque label would be darker
    assert is_grey(d) and abs(d.red() - expected) <= 3, d.name()


def _section_sprinkler_view(section_scene_for, mode, *hidden):
    """A section viewport over two Existing sprinklers' proxies (VC9: the proxy is
    sourced on the node, the phase lives on the sprinkler); ``(vp, proxy rect)``."""
    from tests.test_section_classification import _placed_scene
    set_paper_mode(mode)
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    for y in (-1000.0, 1000.0):                                # one is in front of the cut
        ms.add_sprinkler(ms.add_node(5000.0, y)).phase = PHASE_EXISTING
    set_status(PHASE_EXISTING, weight="Extra Thick")           # DEFAULT_LINE_WEIGHTS: 1.00 mm
    sec.rebuild()
    proxies = [it for it in sec.items() if getattr(it, "_paper_cat", None) == "Sprinkler"]
    assert proxies
    r = proxies[0].sceneBoundingRect()
    crop = r.adjusted(-1000.0, -1000.0, 1000.0, 1000.0)
    _ps, vp = make_viewport(sec, kind="section", name="Section 1", crop=crop,
                            phase_display=phasing(*hidden))
    c = r.center()                                             # the 60 mm circle's centre
    # 1.5 paper mm either side and below; the top stops 20 mm above the centre,
    # clear of the level datum dash-dot line 60 mm above it.
    return vp, QRectF(c.x() - 150.0, c.y() - 20.0, 300.0, 170.0)


@pytest.mark.parametrize("mode", ROWS)
def test_ph3_section_sprinkler_proxy_takes_colour_not_weight(qapp, section_scene_for, mode):
    """D-PH13 on a section proxy: the status colour, the Sprinkler row's own weight."""
    vp, r = _section_sprinkler_view(section_scene_for, mode)
    img = render(vp)
    colours = pixels(img, model_box(vp, r))
    assert_status_grey(colours)                                # unphased: the row colour
    x0, y0, x1, y1 = model_box(vp, r)
    xs = [x for x in range(x0, x1) for y in range(y0, y1)
          if QColor(img.pixel(x, y)).rgb() != QColor("#ffffff").rgb()]
    width_px = max(xs) - min(xs) + 1                           # the circle's ink width
    # 60 mm circle at 1:100 = 0.60 paper mm; + Fine 0.25 = 8.5 px, + Extra Thick 1.00 = 16 px
    assert width_px <= round((0.60 + 0.25) * PX) + 2, width_px


@pytest.mark.parametrize("mode", ROWS)
def test_ph3_hidden_status_hides_a_section_sprinkler_proxy(qapp, section_scene_for, mode):
    vp, r = _section_sprinkler_view(section_scene_for, mode, PHASE_EXISTING)
    assert not inked(pixels(render(vp), model_box(vp, r)))


def _section_opening_slab_view(section_scene_for, mode, sid, *hidden, opacity=None):
    """A section viewport over a door in a wall plus a slab, all at status *sid*
    (the fixture of test_section_sheet_plot); ``(sec, vp, op, slab, frame box)``."""
    from firepro3d.section_scene import _ROLE_HIDE_SOURCE, _SrcRect
    from tests.test_section_sheet_plot import _section_with_opening_and_slab
    set_paper_mode(mode)
    ms, sec, op, slab = _section_with_opening_and_slab(section_scene_for)
    op.phase = op._wall.phase = slab.phase = sid
    if opacity is not None:
        set_status(sid, opacity=opacity)
    frames = [it for it in sec.items() if isinstance(it, _SrcRect)
              and it.data(_ROLE_HIDE_SOURCE) is op and it._paper_cat is not None]
    assert frames                                              # the opening's frame lines
    box = frames[0].sceneBoundingRect()
    crop = box.adjusted(-1500.0, -1500.0, 1500.0, 1500.0)
    _ps, vp = make_viewport(sec, kind="section", name="Section 1", crop=crop,
                            phase_display=phasing(*hidden))
    return sec, vp, op, slab, box


def _head_strip(box):
    """The frame's top edge, clear of the level datum line along the sill."""
    return QRectF(box.left(), box.top() - 60.0, box.width(), 120.0)


@pytest.mark.parametrize("mode", ROWS)
def test_ph3_hidden_status_hides_a_section_opening_frame(qapp, section_scene_for, mode):
    """The frame lines are sourced on the opening only through _ROLE_HIDE_SOURCE."""
    _sec, vp, _op, _slab, box = _section_opening_slab_view(
        section_scene_for, mode, PHASE_DEMOLITION, PHASE_DEMOLITION)
    assert not inked(pixels(render(vp), model_box(vp, _head_strip(box))))


@pytest.mark.parametrize("mode", ROWS)
def test_ph3_section_opening_frame_takes_its_hosts_status_colour(qapp, section_scene_for, mode):
    _sec, vp, _op, _slab, box = _section_opening_slab_view(section_scene_for, mode, PHASE_EXISTING)
    assert_status_grey(pixels(render(vp), model_box(vp, _head_strip(box))))


@pytest.mark.parametrize("mode", ROWS)
def test_ph3_section_opening_frame_takes_its_hosts_status_opacity(qapp, section_scene_for, mode):
    """The frame plots over the cut wall, so compare 100 % (the full #808080) with 50 %."""
    def darkest_frame_px(opacity):
        _sec, vp, _op, _slab, box = _section_opening_slab_view(
            section_scene_for, mode, PHASE_EXISTING, opacity=opacity)
        return darkest(inked(pixels(render(vp), model_box(vp, _head_strip(box)))))
    full, half = darkest_frame_px(100), darkest_frame_px(50)
    assert near(full, EXISTING_GREY), full.name()
    assert half.red() >= EXISTING_GREY + 40, (full.name(), half.name())   # an opaque frame stays dark


def _slab_mask(sec, slab):
    from firepro3d.section_scene import _ROLE_HIDE_SOURCE, _ROLE_SOURCE
    masks = [it for it in sec.items() if it.data(_ROLE_HIDE_SOURCE) is slab
             and it.data(_ROLE_SOURCE) is None and getattr(it, "_paper_cat", None) is None]
    assert len(masks) == 1
    return masks[0]


@pytest.mark.parametrize("hidden,expected", [(PHASE_DEMOLITION, False), (PHASE_EXISTING, True)])
def test_ph3_hidden_status_slab_mask_does_not_occlude(qapp, section_scene_for, hidden, expected):
    """The mask is invisible during the pass only when the slab's status is hidden;
    restore re-shows it (DD6: visibility writes are saved and restored)."""
    from firepro3d import phase_display
    from firepro3d.paper_display import apply_paper_overrides, restore_model_display
    sec, vp, _op, slab, _box = _section_opening_slab_view(
        section_scene_for, FULL_COLOR, PHASE_DEMOLITION, PHASE_DEMOLITION)
    slab.phase = hidden
    mask = _slab_mask(sec, slab)
    assert mask.isVisible()
    phase_display.begin_pass(vp.data)
    try:
        saved = apply_paper_overrides(sec, sec.sceneRect(), 0.01, viewport_data=vp.data)
        during = mask.isVisible()
    finally:
        phase_display.end_pass()
    restore_model_display(saved)
    assert during is expected
    assert mask.isVisible()
