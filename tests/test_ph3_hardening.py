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


# --- Task 10: phase weights are by-name references (DD6 / R7a) -----------------
from PyQt6.QtTest import QTest                                       # noqa: E402
from PyQt6.QtWidgets import QApplication                             # noqa: E402

from tests.test_lwdc_delete_replace import _Modal, _cleanup, _dm, _row, _setup  # noqa: E402,F401


def test_dd6_deleting_a_weight_a_phase_uses_is_counted_and_replaced(qapp, tmp_path,
                                                                    monkeypatch):
    from firepro3d import weight_refs as wr
    settings = _setup(tmp_path, [("Pen X", 0.40)])
    ms = h.scene()
    pr.project_table().set_graphic(PHASE_EXISTING, "weight", "Pen X")
    assert wr.weight_ref_count(ms, settings, "Pen X") == 1        # the phase is the one holder
    d = _dm(ms, settings)
    modal = _Modal(monkeypatch, pick="Wide")
    d._lw_table.setCurrentCell(_row(d, "Pen X"), 0)
    d._on_lw_remove()
    assert len(modal.seen) == 1                                   # LW-DC-5: replace, never a silent delete
    assert pr.project_table().graphics_of(PHASE_EXISTING)["weight"] == "Wide"
    assert d._phases_tab.table().graphics_of(PHASE_EXISTING)["weight"] == "Wide"
    d.accept()
    assert pr.project_table().graphics_of(PHASE_EXISTING)["weight"] == "Wide"


def test_dd6_renaming_a_weight_retargets_the_phase_with_phase_edits_pending(qapp, tmp_path):
    settings = _setup(tmp_path, [("Pen X", 0.40)])
    ms = h.scene()
    pr.project_table().set_graphic(PHASE_EXISTING, "weight", "Pen X")
    d = _dm(ms, settings)
    d._phases_tab.cell(PHASE_DEMOLITION, "opacity").setValue(40)   # a pending Phases edit
    d._lw_table.item(_row(d, "Pen X"), 0).setText("Pen Y")
    assert pr.project_table().graphics_of(PHASE_EXISTING)["weight"] == "Pen Y"
    d.accept()                                         # installs the (dirty) working copy
    reg = pr.project_table()
    assert reg.graphics_of(PHASE_EXISTING)["weight"] == "Pen Y"
    assert reg.graphics_of(PHASE_DEMOLITION)["opacity"] == 40


def test_dd6_cancel_puts_the_phase_weight_back(qapp, tmp_path):
    settings = _setup(tmp_path, [("Pen X", 0.40)])
    ms = h.scene()
    pr.project_table().set_graphic(PHASE_EXISTING, "weight", "Pen X")
    d = _dm(ms, settings)
    d._lw_table.item(_row(d, "Pen X"), 0).setText("Pen Y")
    assert pr.project_table().graphics_of(PHASE_EXISTING)["weight"] == "Pen Y"   # live mid-state
    d.reject()
    assert pr.project_table().graphics_of(PHASE_EXISTING)["weight"] == "Pen X"


def test_dd6_cancel_after_delete_replace_puts_the_phase_weight_back(qapp, tmp_path,
                                                                     monkeypatch):
    """Delete-replace journals the phase holder; Cancel replays the journal (DD6)."""
    settings = _setup(tmp_path, [("Pen X", 0.40)])
    ms = h.scene()
    pr.project_table().set_graphic(PHASE_EXISTING, "weight", "Pen X")
    d = _dm(ms, settings)
    _Modal(monkeypatch, pick="Wide")
    d._lw_table.setCurrentCell(_row(d, "Pen X"), 0)
    d._on_lw_remove()
    assert pr.project_table().graphics_of(PHASE_EXISTING)["weight"] == "Wide"    # live mid-state
    d.reject()
    assert pr.project_table().graphics_of(PHASE_EXISTING)["weight"] == "Pen X"


def test_dd6_phases_weight_combo_lists_a_weight_added_this_session(qapp, tmp_path):
    settings = _setup(tmp_path, [])
    ms = h.scene()
    d = _dm(ms, settings)
    try:
        d.show()
        QTest.qWaitForWindowExposed(d)
        before = {lw.name for lw in d._lw_defs}
        d._on_lw_add()
        (added,) = {lw.name for lw in d._lw_defs} - before   # the one new weight
        d._tabs.set_current("phases")
        QApplication.processEvents()
        combo = d._phases_tab.cell(PHASE_EXISTING, "weight")
        assert added in [combo.itemText(i) for i in range(combo.count())]
    finally:
        d.reject()
