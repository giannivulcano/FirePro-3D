"""Tests for the import dialog shell primitives.

These test the module-level classes/functions added to
firepro3d/dxf_preview_dialog.py for the step-rail / contextual-panel /
commit-sentence redesign.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# CYCLE 1 — _StepRail
# ---------------------------------------------------------------------------

def test_step_rail_states_and_click(qapp):
    from firepro3d.dxf_preview_dialog import _StepRail
    seen = []
    rail = _StepRail()
    rail.stepClicked.connect(seen.append)
    rail.set_step("source",  "site.pdf . PDF . 6 pages", "done")
    rail.set_step("content", "whole sheet",              "done")
    rail.set_step("place",   "0 levels . unverified",    "warn")
    assert rail.state("place") == "warn"
    rail.row("content").click()          # QPushButton row
    assert seen == ["content"]


# ---------------------------------------------------------------------------
# CYCLE 2 — _LevelsPicker
# ---------------------------------------------------------------------------

def test_levels_picker_default_and_selection(qapp):
    from firepro3d.dxf_preview_dialog import _LevelsPicker
    seen = []
    lp = _LevelsPicker(["Level 1", "Level 2", "Roof"], current="Level 2")
    lp.changed.connect(lambda: seen.append(lp.selected()))
    assert lp.selected() == ["Level 2"]           # defaults to current level
    lp.set_selected(["Level 1", "Roof"])
    assert lp.selected() == ["Level 1", "Roof"]
    assert seen[-1] == ["Level 1", "Roof"]


# ---------------------------------------------------------------------------
# CYCLE 3 — build_commit_sentence
# ---------------------------------------------------------------------------

def test_commit_sentence_omits_absent_clauses():
    from firepro3d.dxf_preview_dialog import build_commit_sentence
    s = build_commit_sentence(name="site-plan", page=3, pages=6, layers_hidden=2,
                              cropped=True, scale="1:48", verified=False,
                              rotation=0, levels=["Level 1", "Level 2"],
                              position="pick")
    assert "site-plan" in s and "page 3 of 6" in s and "2 layers hidden" in s
    assert "cropped" in s and "1:48" in s and "unverified" in s
    assert "Level 1 + Level 2" in s and "pick the insertion point" in s
    assert "rotated" not in s              # rotation 0 omitted


def test_commit_sentence_single_page_no_rotation():
    from firepro3d.dxf_preview_dialog import build_commit_sentence
    s = build_commit_sentence(name="plan", page=0, pages=1, layers_hidden=0,
                              cropped=False, scale="1:1", verified=True,
                              rotation=90, levels=["Level 1"], position="origin")
    assert "page" not in s and "layers hidden" not in s and "whole sheet" in s
    assert "rotated 90" in s and "placed at the origin" in s and "verified" in s


# ── Shell integration guards (T10/T11/T12/T14) ────────────────────────────

def test_zoom_clamp(qapp):
    from firepro3d.dxf_preview_dialog import _PreviewView
    from PyQt6.QtWidgets import QGraphicsScene
    v = _PreviewView(QGraphicsScene())
    v._fit_scale = 1.0
    for _ in range(100):
        v._apply_zoom(2.0)
    assert v._zoom_ratio() <= 12.0 + 1e-6
    for _ in range(100):
        v._apply_zoom(0.5)
    assert v._zoom_ratio() >= 0.25 - 1e-6


def test_shell_construction_contract(qapp):
    from firepro3d.dxf_preview_dialog import UnderlayImportDialog, ImportParams
    dlg = UnderlayImportDialog(None, levels=["Level 1", "Level 2"],
                               current_level="Level 1")
    assert dlg._rail is not None and dlg._levels_picker is not None
    assert dlg._commit_label is not None
    p = dlg.get_import_params()
    assert isinstance(p, ImportParams) and p.levels == ["Level 1"]
    dlg.deleteLater()


def test_dropzone_accepts_supported_exts(qapp):
    from firepro3d.dxf_preview_dialog import UnderlayImportDialog
    dlg = UnderlayImportDialog(None, levels=["Level 1"], current_level="Level 1")
    assert dlg._accepts_drop("C:/x/plan.pdf") is True
    assert dlg._accepts_drop("C:/x/plan.DWG") is True
    assert dlg._accepts_drop("C:/x/notes.txt") is False
    dlg.deleteLater()


def test_modify_prefill_levels_and_verified(qapp):
    from firepro3d.dxf_preview_dialog import UnderlayImportDialog
    from firepro3d.underlay import Underlay
    rec = Underlay(type="dxf", path="x.dxf", levels=["Level 2"],
                   scale_verified=True, rotation=0.0)
    dlg = UnderlayImportDialog(None, levels=["Level 1", "Level 2", "Roof"],
                               current_level="Level 1", modify_record=rec)
    assert dlg._levels_picker.selected() == ["Level 2"]
    assert dlg._scale_verified is True
    assert "Modify Underlay" in dlg.windowTitle()
    dlg.deleteLater()
