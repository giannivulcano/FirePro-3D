"""Footer rail (chrome revamp): sub-rail structure + inline osnap toggles."""
from firepro3d.footer_rail import FooterRail, InlineOsnapBar
from firepro3d.snap_engine import SNAP_MARKERS


class _Eng:
    """Minimal SnapEngine stand-in — the osnap bar's contract is just the 8 attrs."""
    snap_endpoint = True
    snap_midpoint = True
    snap_intersection = True
    snap_center = True
    snap_quadrant = True
    snap_nearest = True
    snap_perpendicular = True
    snap_tangent = True


def test_osnap_toggle_keys_match_snap_markers(qapp):
    rail = FooterRail()
    assert rail.osnap_toggle_keys() == list(SNAP_MARKERS.keys())


def test_osnap_toggle_writes_engine_attr(qapp):
    eng = _Eng()
    rail = FooterRail(snap_engine_obj=eng)
    rail.set_osnap("snap_endpoint", False)
    assert eng.snap_endpoint is False
    rail.set_osnap("snap_endpoint", True)
    assert eng.snap_endpoint is True


def test_inline_bar_reads_initial_engine_state(qapp):
    eng = _Eng()
    eng.snap_tangent = False
    bar = InlineOsnapBar(snap_engine_obj=eng)
    # the tangent toggle reflects the engine's initial False
    assert bar._toggles["snap_tangent"].isChecked() is False
    assert bar._toggles["snap_endpoint"].isChecked() is True


def test_chevron_persists_expanded_state(qapp):
    rail = FooterRail()
    start = rail._expanded
    rail._toggle_bar()
    assert rail._expanded is (not start)
    assert rail.osnap_bar.isVisible() is (not start)


def test_snap_pill_context_menu_emits_settings_signal(qapp):
    rail = FooterRail()
    fired = []
    rail.snapSettingsRequested.connect(lambda: fired.append(True))
    rail.snap_pill.customContextMenuRequested.emit(rail.snap_pill.rect().center())
    assert fired == [True]
