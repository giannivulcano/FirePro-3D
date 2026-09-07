from firepro3d.ui_kit import SideTabs, DetailsPanel, Section, SwitchBar, ToggleSwitch, Pill
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


def test_details_panel_widths(qapp):
    p1 = DetailsPanel(width=M.PANEL_W)
    assert p1.width() == M.PANEL_W or p1.maximumWidth() == M.PANEL_W
    p = DetailsPanel(width=M.PANEL_W_WIDE, title="DETAILS")
    assert p.content_layout() is not None


def test_section_sets_content(qapp):
    from PyQt6.QtWidgets import QLabel
    s = Section("GENERAL")
    s.set_content(QLabel("x"))  # no raise


def test_switchbar_single_select(qapp):
    bar = SwitchBar([("a", "A"), ("b", "B"), ("c", "C")])
    seen = []
    bar.changed.connect(seen.append)
    bar.set_current("c")
    assert bar.current() == "c"


def test_toggle_switch(qapp):
    t = ToggleSwitch("Insert at origin", checked=False)
    t.setChecked(True)
    assert t.isChecked() is True


def test_pill_props(qapp):
    p = Pill("Calibrate")
    assert p.property("pill") == "true"
