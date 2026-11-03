"""SB4b D15 -- GridBubble and the screen-fixed / paper-swap bubble machinery are gone."""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1] / "firepro3d"


@pytest.mark.xfail(strict=True, reason="Tasks 5-6")
def test_gridline_retired_strings_are_gone():
    src = (ROOT / "gridline.py").read_text(encoding="utf-8")
    for s in ("class GridBubble", "RADIUS_PX", "enter_paper_mode", "exit_paper_mode",
              "_paper_bubble_r", "_display_scale", "ItemIgnoresTransformations, True)\n        pen"):
        assert s not in src, s
    pd = (ROOT / "paper_display.py").read_text(encoding="utf-8")
    for s in ("enter_paper_mode", "exit_paper_mode", "_paper_bubble_r", "bubble_paper_geometry",
              "bubble_pen", "bubble_brush", "label_color", "bubble_scale"):
        assert s not in pd, s
    dm = (ROOT / "display_manager.py").read_text(encoding="utf-8")
    for s in ("bubble_pen", "bubble_brush", "bubble_font_px", "bubble_scale", "bubble._label"):
        assert s not in dm, s
    assert "GridBubble" not in (ROOT / "section_scene.py").read_text(encoding="utf-8")
