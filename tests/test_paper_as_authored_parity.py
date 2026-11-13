"""AC3 (paper-as-authored D4 / D5): B&W, Custom and Full Color legacy
projects -- and legacy QSettings -- plot pixel-identical to the base SHA
(goldens written at e7ac8f15 by tests/make_paper_parity_goldens.py)."""
import pytest
from PyQt6.QtGui import QImage

from tests.paper_parity_support import (GOLDEN_DIR, MODES, build_scene,
                                        load_mode_via_project,
                                        load_mode_via_qsettings,
                                        pin_model_colours, render)


# SB4g (U2 ratified): the head at model (2000, 1500) is block-drawn since SB4g
# (rasterises differently from the e7ac8f15 SVG). CROP (-2500..2500, 500 px) ->
# 0.1 px/mm, head centre px (450, 400), radius 609.6 / 2 * 0.1 = 30.5 px + 4 px
# margin (the golden's SVG head; the R14 block head, 579.85 mm, lies inside it).
# Measured: the unmasked diff bbox is x 419..480, y 369..430, inside the mask.
# The goldens are never regenerated.
_HEAD_MASK = (415, 365, 485, 435)       # x0, y0, x1, y1 inclusive


def _same(img, golden_path):
    g = QImage(str(golden_path)).convertToFormat(img.format())
    assert not g.isNull(), golden_path
    assert (img.width(), img.height()) == (g.width(), g.height())
    x0, y0, x1, y1 = _HEAD_MASK
    diff = sum(1 for y in range(img.height()) for x in range(img.width())
               if not (x0 <= x <= x1 and y0 <= y <= y1)
               and img.pixel(x, y) != g.pixel(x, y))
    assert diff == 0, f"{diff} pixels differ from {golden_path.name}"


@pytest.mark.parametrize("mode", MODES)
def test_legacy_project_plots_as_base(qapp, shipped_hatches, mode):
    pin_model_colours()
    load_mode_via_project(mode)
    _same(render(build_scene(shipped_hatches)), GOLDEN_DIR / f"{mode}.png")


@pytest.mark.parametrize("mode", MODES)
def test_legacy_qsettings_plot_as_base(qapp, shipped_hatches, mode):
    pin_model_colours()
    load_mode_via_qsettings(mode)
    _same(render(build_scene(shipped_hatches)), GOLDEN_DIR / f"{mode}.png")


def test_goldens_are_distinct():
    """A guard that cannot tell the modes apart proves nothing."""
    imgs = [QImage(str(GOLDEN_DIR / f"{m}.png")) for m in MODES]
    for i, j in ((0, 1), (1, 2), (0, 2)):
        a, b = imgs[i], imgs[j]
        diff = sum(1 for y in range(a.height()) for x in range(a.width())
                   if a.pixel(x, y) != b.pixel(x, y))
        assert diff > 1000, f"{MODES[i]} vs {MODES[j]}: only {diff} px differ"
