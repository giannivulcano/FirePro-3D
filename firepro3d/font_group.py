"""Ribbon Font group for sheet text (Word's Font group as reference).

Governing specs: docs/specs/ribbon-bar.md (D3 add_widget primitive),
docs/specs/paper-space.md §9.6 (undo-routed formatting writes),
docs/specs/units-and-formatting.md (Word-style pt display, mm storage).
"""
from __future__ import annotations

from .constants import FONT_SIZE_LADDER_PT


def next_ladder_pt(pt: float) -> float:
    """Return the next Word-ladder step above *pt* (clamp at the top)."""
    for step in FONT_SIZE_LADDER_PT:
        if step > pt:
            return step
    return pt


def prev_ladder_pt(pt: float) -> float:
    """Return the next Word-ladder step below *pt* (clamp at the bottom)."""
    for step in reversed(FONT_SIZE_LADDER_PT):
        if step < pt:
            return step
    return pt
