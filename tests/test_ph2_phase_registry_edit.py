"""PH2 Task 1: PhaseRegistry working-copy API (concept PD2: the Phases tab edits a copy)."""
from firepro3d import phase_registry as pr


def test_copy_is_independent():
    reg = pr.PhaseRegistry()
    work = reg.copy()
    work.set_graphic("existing", "colour", "#ff0000")
    assert reg.graphics_of("existing")["colour"] == "#808080"   # constants.PHASE_EXISTING_COLOUR
    assert work.graphics_of("existing")["colour"] == "#ff0000"


def test_set_graphic_none_is_no_override_and_unknown_key_refused():
    work = pr.PhaseRegistry()
    assert work.set_graphic("existing", "fill", None) is True
    assert work.graphics_of("existing")["fill"] is None
    assert work.set_graphic("existing", "bogus", 1) is False
    assert work.set_graphic("nope", "colour", "#000000") is False


def test_reset_graphics_to_factory_keeps_names_and_order():
    work = pr.PhaseRegistry()
    work.set_graphic("demolition", "linetype", None)
    work.set_graphic("new", "opacity", 40)
    work.reset_graphics_to_factory()
    assert work.to_list() == pr.factory_statuses()
