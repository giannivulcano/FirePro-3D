"""LT7: shipped System linetypes / end types reach the real pickers; the
factory Demolition phase linetype is the shipped id (R5).

The catalog lists name the entries shipped so far; the rest of the LT7
catalog is deferred (2026-11-18, user) and joins these lists when promoted.
"""
import json
import os

import pytest

from firepro3d import phase_registry as pr
from firepro3d.constants import PHASE_DEMOLITION_LINETYPE

DEMOLITION_ID = "system-line-types-demolition"

LINETYPES = [("Line Types", n) for n in ("Dash", "Hidden", "Demolition")]
ENDS = [("Endtypes", n) for n in ("Arrow", "Dot", "Tick")]


def _shipped(root, series, name):
    with open(os.path.join(root, series, f"{name}.fpdb"), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.mark.parametrize("series,name", LINETYPES)
def test_linetype_shipped_and_in_picker(real_system_library, series, name):
    d = _shipped(real_system_library, series, name)
    assert d["library"] == "System" and d["series"] == series and d["name"] == name
    assert d.get("repeat") and not d.get("end")
    from firepro3d.linetype_choices import linetype_choices
    assert (name, d["id"]) in linetype_choices(None)


@pytest.mark.parametrize("series,name", ENDS)
def test_end_type_shipped_and_in_picker(real_system_library, series, name):
    d = _shipped(real_system_library, series, name)
    assert d["library"] == "System" and d["series"] == series and d["name"] == name
    assert d.get("end") is not None and not d.get("repeat")
    from firepro3d.capabilities import end_choices
    assert (name, d["id"]) in end_choices(None)


def test_factory_demolition_linetype_is_the_shipped_id(real_system_library):
    assert PHASE_DEMOLITION_LINETYPE == DEMOLITION_ID
    assert _shipped(real_system_library, "Line Types", "Demolition")["id"] == DEMOLITION_ID
    try:
        pr.reset_project_table()
        assert pr.project_table().graphics_of("demolition")["linetype"] == DEMOLITION_ID
    finally:
        pr.reset_project_table()


def test_legacy_demolition_name_loads_as_the_id():
    rows = pr.factory_statuses()
    rows[2]["graphics"]["linetype"] = "Demolition"          # a pre-LT7 file / setting
    try:
        pr.load_project_phases(rows)
        assert pr.project_table().graphics_of("demolition")["linetype"] == DEMOLITION_ID
        assert pr.to_list()[2]["graphics"]["linetype"] == DEMOLITION_ID   # saves as the id
        legacy = pr.PhaseRegistry(rows)                    # the DM working-copy constructor path
        assert legacy.copy().graphics_of("demolition")["linetype"] == DEMOLITION_ID
    finally:
        pr.reset_project_table()
