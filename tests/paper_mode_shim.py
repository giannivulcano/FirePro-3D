"""Test shim for the retired paper Color Mode (paper-as-authored D4): sets
every row's As Authored the way a legacy file of *mode* loads, so a test
written against a colour mode keeps exercising the same pass branch."""
from __future__ import annotations

from firepro3d import paper_display as pd

BW, CUSTOM, FULL_COLOR = "bw", "custom", "full_color"


def set_paper_mode(mode: str, settings=None) -> None:
    """Rows OFF/ON per the D4 table (bw OFF/OFF, custom OFF/ON, full_color ON/ON)."""
    cats = pd.load_paper_categories(settings)
    pd.apply_legacy_mode(cats, mode)
    pd.save_paper_categories(cats, settings)
