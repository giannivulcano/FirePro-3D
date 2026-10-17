"""HF2 polish: a Display Manager pattern swatch shows the picked pattern
before OK — the pattern is not in the project yet (it loads on DM OK)."""
from firepro3d import hatch_patterns as hp
from firepro3d.display_manager import _make_fill_icon
from firepro3d.model_space import Model_Space


def _colours(pix):
    img = pix.toImage()
    return {img.pixel(x, y) for x in range(img.width()) for y in range(img.height())}


def test_dm_swatch_shows_unloaded_pattern_not_tone(qapp):
    ms = Model_Space()                                  # no patterns loaded
    assert ms.block_registry.get(hp.BUILTIN_BRICK) is None
    pix = _make_fill_icon("hatch", "#ff0000", 40, 20, pattern=hp.BUILTIN_BRICK,
                          registry=ms.block_registry)
    # A tone (D-A36) is ONE flat blended colour covering the swatch; the real
    # pattern draws pure-red lines over the #2b2b2b background (2 colours; the
    # cosmetic axis-aligned lines are not antialiased, so not >2).
    cols = _colours(pix)
    assert 0xFFFF0000 in cols and 0xFF2B2B2B in cols


def test_dm_swatch_tone_for_unknown_ref(qapp):
    """Control: a ref no folder or file holds draws the flat tone."""
    pix = _make_fill_icon("hatch", "#ff0000", 40, 20, pattern="no-such-pattern",
                          registry=Model_Space().block_registry)
    assert len(_colours(pix)) == 1
