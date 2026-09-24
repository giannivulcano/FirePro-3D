"""Selection dimension readouts — layout + paint (readout_paint.py)."""
from firepro3d import constants, theme


def test_value_font_is_consolas_px(qapp):
    f = theme.value_font(constants.SELDIM_FONT_PX)
    assert f.family() == theme.FONT_VALUE
    assert f.pixelSize() == constants.SELDIM_FONT_PX
