"""text-sizing-wrap D2 / D3 (AC2, AC3): model-surface text Height entry and the
annotative Block Editor placement defaults.

T-height-row drives the real Property panel: the Height row's own widget shows
the value and a typed entry commits through its parser to the stored cap mm.
Expected pt values come from Arial's raw metric (capHeight at 1000 px) and the
typographic point (25.4 / 72 mm), never from the module's own converters.
T-be-default drives the real two-click text placement on a Block Editor scene.
"""
import pytest

_HELPERS = ("_parse_text_height_mm", "_text_cap_ratio", "_font_pt_from_mm",
            "_mm_from_font_pt", "_format_height_pt", "_parse_height_pt")


def test_height_helpers_have_one_home(qapp):
    """D2: the pt / mm height helpers live in text_item; paper_space and
    font_group use that one definition (network_codec imports it lazily)."""
    import firepro3d.font_group as fg
    import firepro3d.paper_space as ps
    import firepro3d.text_item as ti
    for name in _HELPERS:
        assert getattr(ti, name).__module__ == "firepro3d.text_item", name
        assert getattr(ps, name) is getattr(ti, name), name
    assert ps.MM_PER_PT == ti.MM_PER_PT == 25.4 / 72.0
    for name in ("_font_pt_from_mm", "_mm_from_font_pt", "_parse_height_pt"):
        assert getattr(fg, name) is getattr(ti, name), name
