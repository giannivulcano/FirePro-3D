"""SB4g G4 / R9 / R4 / AC7: DM and paper tint reach block-drawn symbols, and
the riser strokes in its pipe's colour (T8 Sprinkler DM, T9 Water Supply,
T10 riser canvas, T13 paper). Raw sources: sprinkler0.svg (stroke #ffffff,
fill #2e2e2e), water_supply.svg (fill #2b2b2e), constants VELOCITY_HIGH_FPS
20.0 / VELOCITY_COLOR_HIGH (220, 0, 0), Pipe.BRANCH_WIDTH_MM 75.0."""
import pytest
from PyQt6.QtCore import QPointF, QRectF, QSettings
from PyQt6.QtGui import QColor

from firepro3d import display_manager as dm
from firepro3d import paper_display as pd
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import CircleItem
from tests._sb4g_helpers import (SPR0_FILL, WS_FILL, head, names, render, riser_scene, ring_hits,
                                 scene, water_supply)

RECT = QRectF(-400.0, -400.0, 800.0, 800.0)


def reds(img):
    """Count red-dominant pixels (1px cosmetic strokes anti-alias, so an
    exact-colour count of a stroke is always 0)."""
    n = 0
    for x in range(img.width()):
        for y in range(img.height()):
            c = QColor(img.pixel(x, y))
            if c.red() > c.green() + 60 and c.red() > c.blue() + 60:
                n += 1
    return n


def whites(img):
    n = 0
    for x in range(img.width()):
        for y in range(img.height()):
            c = QColor(img.pixel(x, y))
            if c.red() > 200 and c.green() > 200 and c.blue() > 200:
                n += 1
    return n


TINT_CASES = [
    ("Sprinkler", lambda ms: head(ms)[1], SPR0_FILL),
    ("Water Supply", water_supply, WS_FILL),
]


@pytest.mark.parametrize("key,build,authored_fill", TINT_CASES, ids=[c[0] for c in TINT_CASES])
def test_g4_dm_colour_and_fill_tint_the_symbol_and_unset_is_authored(
        qapp, real_system_library, key, build, authored_fill):
    ms = scene()
    item = build(ms)
    authored_img = render(ms, RECT)
    authored = names(authored_img)
    assert authored_fill in authored                      # the SVG's literal fill
    assert whites(authored_img) > 0 and reds(authored_img) == 0
    repaints = []
    orig_update = item.update
    item.update = lambda *a: (repaints.append(1), orig_update(*a))   # live repaint side effect
    s = QSettings("GV", "FirePro3D")
    s.setValue(f"display/{key}/color", "#ff0000")
    s.setValue(f"display/{key}/fill", "#0000ff")
    s.sync()
    dm.apply_saved_display_settings(ms)                     # the real DM apply path
    assert repaints, "the DM apply never scheduled a repaint of the symbol"
    tinted_img = render(ms, RECT)
    tinted = names(tinted_img)
    assert "#0000ff" in tinted and reds(tinted_img) > 0
    assert authored_fill not in tinted and whites(tinted_img) == 0
    dm._set_svg_tint(item, None, None)                      # unset: the snapshot-restore call shape
    assert names(render(ms, RECT)) == authored


# -- T10: riser canvas colour ----------------------------------------------------
def _ring_dominant(ms, channel: str) -> int:
    """Pixels outside the pipe's own cap dot (Pipe.BRANCH_WIDTH_MM / 2 + 5 mm)
    where *channel* dominates (the ring is a 1px cosmetic stroke: anti-aliasing
    makes an exact-colour count 0)."""
    import math
    from firepro3d.pipe import Pipe
    img = render(ms, QRectF(-100.0, -100.0, 200.0, 200.0), 400, 400)   # 2 px / mm
    excl = Pipe.BRANCH_WIDTH_MM / 2.0 + 5.0
    n = 0
    for x in range(400):
        for y in range(400):
            if math.hypot((x - 200) / 2.0, (y - 200) / 2.0) <= excl:
                continue
            c = QColor(img.pixel(x, y))
            v = {"red": c.red(), "green": c.green(), "blue": c.blue()}
            others = [val for k, val in v.items() if k != channel]
            if v[channel] > max(others) + 60:
                n += 1
    return n


def test_g4_riser_strokes_in_the_pipe_colour_then_the_velocity_colour(
        qapp, real_system_library):
    from types import SimpleNamespace
    ms, (top, bot), p = riser_scene()
    p._properties["Colour"]["value"] = "#00c000"             # authored ring is white
    p.set_pipe_display()
    assert _ring_dominant(ms, "green") > 100                 # R4: the pipe's Colour
    assert _ring_dominant(ms, "red") == 0
    ms.hydraulic_result = SimpleNamespace(
        node_numbers={top: 1, bot: 2}, pipe_velocity={p: 25.0})   # > VELOCITY_HIGH_FPS 20.0
    p.repaint_riser()
    assert _ring_dominant(ms, "red") > 100                   # VELOCITY_COLOR_HIGH (220, 0, 0)
    assert _ring_dominant(ms, "green") == 0
    ms.hydraulic_result = None


# -- T13: paper hooks ------------------------------------------------------------
def _paper_row(key, *, as_authored, colour, fill=None):
    cats = pd.load_paper_categories()
    cats[key]["as_authored"] = as_authored
    cats[key]["color"] = colour
    if fill is not None:
        cats[key]["fill"] = fill
    pd.save_paper_categories(cats)


def test_g4_paper_row_colour_and_fill_plot_and_restore(qapp, real_system_library):
    ms = scene()
    _n, spr = head(ms)
    canvas = names(render(ms, RECT))
    _paper_row("Sprinkler", as_authored=False, colour="#00aa00", fill="#aa00aa")
    saved = pd.apply_paper_overrides(ms, RECT, paper_scale=0.02)
    try:
        assert spr._paper_scale == 0.02                    # D8 hook (secondary assert)
        paper = names(render(ms, RECT))
    finally:
        pd.restore_model_display(saved)
    assert "#aa00aa" in paper                              # fill: solid, exact
    assert any(QColor(n).green() > QColor(n).red() + 60 for n in paper)   # stroke blend
    assert spr._paper_scale is None and spr._paper_pen_width is None
    assert names(render(ms, RECT)) == canvas               # restored exactly


def test_paper_named_weight_user_symbol_plots_mm_over_scale(qapp):
    """D8: a user symbol with a NAMED weight plots its paper mm / scale
    (needs _paper_scale / _paper_pen_width). Raw source: the factory Default
    "Medium" weight 0.35 mm (paper_display.DEFAULT_LINE_WEIGHTS, LW-DC-1) at
    1:50 (paper_scale 0.02) = 17.5 scene mm."""
    ms = scene()
    ring = CircleItem(QPointF(0.0, 0.0), 300.0)
    ring.style["weight"] = "Medium"
    ring.style["colour"] = "#ff0000"
    d = BlockDefinition.new(name="U", library="Test", series="S",
                            primitives=[ring.to_dict()], origin=(0.0, 0.0))
    d.symbol_for = "Sprinkler"
    ms.register_block_definition(d)
    _n, spr = head(ms)
    spr.set_symbol_block(d.id)
    saved = pd.apply_paper_overrides(ms, RECT, paper_scale=0.02)
    try:
        img = render(ms, QRectF(-400.0, -400.0, 800.0, 800.0), 800, 800)   # 1 px / mm
    finally:
        pd.restore_model_display(saved)
    reds = [x for x in range(800) if QColor(img.pixel(x, 400)).red() > 150
            and QColor(img.pixel(x, 400)).green() < 100 and x > 600]
    # 17.5 mm band at x = 700; the Sprinkler row's own 0.25 mm would plot 12.5
    assert 15 <= len(reds) <= 20, len(reds)


def test_g4_riser_takes_the_pipe_paper_row(qapp, real_system_library):
    ms, _nodes, p = riser_scene()
    _paper_row("Pipe", as_authored=False, colour="#00aa00")
    saved = pd.apply_paper_overrides(ms, QRectF(-100.0, -100.0, 200.0, 200.0),
                                     paper_scale=0.02)
    try:
        assert p._riser_symbol._paper_scale == 0.02
        hits = _ring_dominant(ms, "green")
    finally:
        pd.restore_model_display(saved)
    assert hits > 100
    assert p._riser_symbol._paper_scale is None


def test_pipe_paper_pass_and_restore_schedule_a_riser_repaint(qapp, real_system_library):
    """T10 review: the pipe's _display_color changes in _apply_pipe and again
    in the restore; the riser pulls it at paint, so each must schedule a riser
    repaint (a mid-pass canvas repaint would otherwise show a stale colour)."""
    ms, _nodes, p = riser_scene()
    calls = []
    real = p.repaint_riser
    p.repaint_riser = lambda: (calls.append(1), real())
    saved = pd.apply_paper_overrides(ms, QRectF(-100.0, -100.0, 200.0, 200.0),
                                     paper_scale=0.02)
    in_apply = len(calls)
    pd.restore_model_display(saved)
    assert in_apply >= 1 and len(calls) > in_apply, (in_apply, len(calls))
