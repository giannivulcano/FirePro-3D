def test_halo_constants_present():
    from firepro3d import constants as C
    assert isinstance(C.HALO_APERTURE_PX, (int, float)) and C.HALO_APERTURE_PX > 0
    assert isinstance(C.HALO_CYCLE_RESET_PX, (int, float)) and C.HALO_CYCLE_RESET_PX > 0
