import firepro3d.constants as C


def test_new_gridline_constants_exist_and_old_removed():
    assert isinstance(C.GRIDLINE_BUBBLE_OFFSET_MM, (int, float))
    assert C.GRIDLINE_BUBBLE_OFFSET_MM > 0
    assert C.DEFAULT_GRIDLINE_SPACING_MM == 7315.2
    assert C.DEFAULT_GRIDLINE_LENGTH_MM == 21945.6
    assert not hasattr(C, "GRIDLINE_BUBBLE_OVERSHOOT_FRAC")
    assert not hasattr(C, "DEFAULT_GRIDLINE_SPACING_IN")
    assert not hasattr(C, "DEFAULT_GRIDLINE_LENGTH_IN")
