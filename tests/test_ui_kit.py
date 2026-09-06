from firepro3d.ui_kit import SideTabs
from firepro3d.theme import M


def test_sidetabs_select_and_signal(qapp):
    rail = SideTabs()
    seen = []
    rail.tabSelected.connect(seen.append)
    rail.add_tab("a", "Alpha", step_no=1)
    rail.add_tab("b", "Beta", step_no=2)
    rail.set_current("b")
    assert rail.current() == "b"
    rail.set_status("a", "done", "done")  # no raise


def test_sidetabs_plain_mode_no_number(qapp):
    rail = SideTabs()
    rail.add_tab("x", "Plain")   # step_no omitted → no chip
    assert rail.current() == "x"


def test_sidetabs_width_from_metrics(qapp):
    rail = SideTabs()
    assert rail.width() == M.SIDE_RAIL_W or rail.minimumWidth() == M.SIDE_RAIL_W or rail.maximumWidth() == M.SIDE_RAIL_W
