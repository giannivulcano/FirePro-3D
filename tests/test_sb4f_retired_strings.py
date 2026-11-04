"""SB4f AC7: the hand-painted bubble, title and scale are gone from the viewport."""
import inspect
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1] / "firepro3d"


def test_paper_space_has_no_title_strip():
    src = (ROOT / "paper_space.py").read_text(encoding="utf-8")
    for s in ("_VIEW_TITLE_H", "bubble_r", "title_rect_above", "title_rect_below",
              "display_title().upper()"):
        assert s not in src, s


def test_viewport_paint_draws_no_title():
    from firepro3d.paper_space import SheetViewport
    src = inspect.getsource(SheetViewport.paint)
    for s in ("drawEllipse", "display_title", "float_to_scale_str"):
        assert s not in src, s
