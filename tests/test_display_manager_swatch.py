"""HF2 polish: a Display Manager pattern swatch shows the picked pattern
before OK — the pattern is not in the project yet (it loads on DM OK)."""
from firepro3d import hatch_patterns as hp
from PyQt6.QtGui import QColor
from firepro3d.hatch_render import pattern_preview
from firepro3d.model_space import Model_Space


def _colours(pix):
    img = pix.toImage()
    return {img.pixel(x, y) for x in range(img.width()) for y in range(img.height())}


def test_dm_swatch_shows_unloaded_pattern_not_tone(qapp):
    ms = Model_Space()                                  # no patterns loaded
    assert ms.block_registry.get(hp.BUILTIN_BRICK) is None
    pix = pattern_preview(hp.BUILTIN_BRICK, QColor("#ff0000"), 40, 20,
                          ms.block_registry)
    # A tone (D-A36) is ONE flat blended colour covering the swatch; the real
    # pattern draws pure-red lines over the #2b2b2b background (2 colours; the
    # cosmetic axis-aligned lines are not antialiased, so not >2).
    cols = _colours(pix)
    assert 0xFFFF0000 in cols and 0xFF2B2B2B in cols


def test_dm_swatch_tone_for_unknown_ref(qapp):
    """Control: a ref no folder or file holds draws the flat tone."""
    pix = pattern_preview("no-such-pattern", QColor("#ff0000"), 40, 20,
                          Model_Space().block_registry)
    assert len(_colours(pix)) == 1


def test_pattern_preview_background_parameter(qapp):
    pix = pattern_preview("no-such-pattern", QColor("#ff0000"), 40, 20, None,
                          background=QColor("#00ff00"))
    assert pix.width() == 40 and pix.height() == 20
    dflt = pattern_preview("no-such-pattern", QColor("#ff0000"), 40, 20, None)
    assert pix.toImage() != dflt.toImage()       # background reaches the pixels
