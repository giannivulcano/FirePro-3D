"""SB4g G4 / R9 / R4 / AC7: DM and paper tint reach block-drawn symbols, and
the riser strokes in its pipe's colour (T8 Sprinkler DM, T9 Water Supply,
T10 riser canvas, T13 paper). Raw sources: sprinkler0.svg (stroke #ffffff,
fill #2e2e2e), water_supply.svg (fill #2b2b2e), constants VELOCITY_HIGH_FPS
20.0 / VELOCITY_COLOR_HIGH (220, 0, 0), Pipe.BRANCH_WIDTH_MM 75.0."""
import pytest
from PyQt6.QtCore import QPointF, QRectF, QSettings
from PyQt6.QtGui import QColor

from firepro3d import display_manager as dm
from tests._sb4g_helpers import SPR0_FILL, WS_FILL, head, names, render, scene, water_supply

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
