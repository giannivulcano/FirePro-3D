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
