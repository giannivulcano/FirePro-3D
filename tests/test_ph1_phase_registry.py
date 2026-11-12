"""PH1 registry: built-ins, factory graphics (D-PH10), id/name mapping, unknown ids.

Raw sources: concept PD1 (built-in ids "new"/"existing"/"demolition"; record
fields id/name/builtin/graphics{colour, fill, weight, linetype, opacity}/
include_in_calc); project-phasing.md D-PH10 (New no override; Existing grey
lines + light-grey fill; Demolition linetype "Demolition", colour unchanged),
D-PH14 (hydraulics exclude Demolition), D-PH19 (built-ins always present).
"""
import logging

from PyQt6.QtGui import QColor

from firepro3d import phase_registry as pr

GRAPHIC_KEYS = {"colour", "fill", "weight", "linetype", "opacity"}


def _grey(hexstr):
    c = QColor(hexstr)
    return c.isValid() and c.red() == c.green() == c.blue()


def test_factory_has_the_three_builtins_in_order():
    rows = pr.project_table().statuses()
    assert [(r["id"], r["name"], r["builtin"]) for r in rows] == [
        ("new", "New", True), ("existing", "Existing", True),
        ("demolition", "Demolition", True)]
    assert all(set(r["graphics"]) == GRAPHIC_KEYS for r in rows)


def test_factory_graphics_follow_d_ph10():
    new, existing, demo = pr.project_table().statuses()
    assert all(v is None for v in new["graphics"].values())               # New: no override
    g = existing["graphics"]
    assert _grey(g["colour"]) and _grey(g["fill"])                          # grey lines + fill
    assert QColor(g["fill"]).lightness() > QColor(g["colour"]).lightness()  # light-grey fill
    assert demo["graphics"]["linetype"] == "Demolition"
    assert demo["graphics"]["colour"] is None                              # colour unchanged
    assert [r["include_in_calc"] for r in (new, existing, demo)] == [True, True, False]


def test_round_trip_keeps_rows_and_builtins_never_go_missing():
    rows = pr.project_table().to_list()
    rows[1]["graphics"]["colour"] = "#123456"
    back = pr.PhaseRegistry.from_list(rows)
    assert back.to_list() == rows
    only_new = pr.PhaseRegistry.from_list([rows[0]])
    assert only_new.ids() == ["new", "existing", "demolition"]


def test_names_and_ids_resolve_both_ways():
    t = pr.project_table()
    assert t.names() == ["New", "Existing", "Demolition"]
    assert t.id_for_name("existing") == "existing" and t.id_for_name("Nope") is None
    assert t.name_of("demolition") == "Demolition" and t.name_of("gone") == "New"


def test_unknown_id_reads_new_and_logs_once(caplog):
    caplog.set_level(logging.INFO, logger="firepro3d.phase_registry")
    assert pr.read_id("gone") == "new" and pr.read_id("gone") == "new"
    assert pr.read_id(None) == "new" and pr.read_id("existing") == "existing"
    hits = [r for r in caplog.records if "gone" in r.getMessage()]
    assert len(hits) == 1


def test_panel_values_resolve_names_and_ids_but_not_legacy_text():
    """C2: legacy pipe text (New / Existing / Demo) has ONE home, the migration map."""
    class _Item:
        phase = "new"
    it = _Item()
    assert pr.set_from_row(it, "Existing") and it.phase == "existing"
    assert pr.set_from_row(it, "demolition") and it.phase == "demolition"
    assert not pr.set_from_row(it, "Demo") and it.phase == "demolition"
    assert pr.legacy_pipe_phase("Demo") == "demolition"


def test_load_without_rows_is_the_factory():
    pr.set_project_table(pr.PhaseRegistry.from_list(
        [{"id": "new", "name": "New", "graphics": {"colour": "#ff0000"}}]))
    pr.load_project_phases(None)
    assert pr.project_table().to_list() == pr.PhaseRegistry().to_list()


def test_a_custom_row_squatting_a_builtin_name_does_not_duplicate_it():
    """T1-M1: a custom "Existing" with another id and no built-in row -> the
    built-in comes back and the name resolves to it, one row per name."""
    reg = pr.PhaseRegistry.from_list([
        {"id": "new", "name": "New"}, {"id": "demolition", "name": "Demolition"},
        {"id": "custom-1", "name": "Existing"}])
    names = [n.casefold() for n in reg.names()]
    assert len(names) == len(set(names))
    assert reg.id_for_name("Existing") == "existing"
    assert reg.get("custom-1") is not None and reg.name_of("custom-1") != "Existing"
