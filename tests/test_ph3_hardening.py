"""PH3 DD6 / R7 hardening guards (design 2026-11-14-ph3-sheet-phasing-design.md).

Raw sources: factory graphics = constants.PHASE_EXISTING_FILL (D-PH10); the "phases"
project key = project_tables.tables_for_save / begin_load (PH1); the Phases tab
shows an unset slot as phases_tab.DASH (PH2, AC6).
"""
import json

from PyQt6.QtCore import QPointF

from firepro3d import phase_registry as pr
from firepro3d.constants import PHASE_DEMOLITION, PHASE_EXISTING, PHASE_EXISTING_FILL
from tests import _ph1_helpers as h
from tests._ph1_helpers import ph1_cleanup  # noqa: F401  (autouse: ends every scene)


def test_dd6_deleted_item_reads_as_not_phased(qapp):
    """A sip-deleted wrapper never reaches section_source_of (which raises on it)."""
    from PyQt6 import sip
    from firepro3d.wall import WallSegment
    w = WallSegment(QPointF(0.0, 0.0), QPointF(1000.0, 0.0))
    w.phase = PHASE_EXISTING
    assert pr.effective_phase(w) == PHASE_EXISTING
    sip.delete(w)
    assert pr.effective_phase(w) is None


def test_dd6_malformed_phase_graphics_load_normalised_and_the_display_manager_opens(
        qapp, tmp_path):
    from firepro3d.display_manager import DisplayManager
    from firepro3d.phases_tab import DASH
    ms = h.scene()
    path, payload = h.save_raw(ms, tmp_path)
    rows = {r["id"]: r for r in payload["phases"]}
    rows[PHASE_EXISTING]["graphics"].update(opacity="abc", colour=5, weight=["Wide"])
    rows[PHASE_DEMOLITION]["graphics"]["opacity"] = 250.4
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    ms2 = h.load(path)
    g = pr.project_table().graphics_of(PHASE_EXISTING)
    assert g["opacity"] is None and g["colour"] is None and g["weight"] is None
    assert g["fill"] == PHASE_EXISTING_FILL                       # a valid slot is kept
    assert pr.project_table().graphics_of(PHASE_DEMOLITION)["opacity"] == 100   # clamped
    d = DisplayManager(ms2, active_context="paper")   # PH2: PhasesTab._make_cell int("abc") raised here
    try:
        assert d._phases_tab.cell_text(PHASE_EXISTING, "opacity") == DASH
        assert d._phases_tab.cell_text(PHASE_DEMOLITION, "opacity") == "100"
    finally:
        d.reject()
