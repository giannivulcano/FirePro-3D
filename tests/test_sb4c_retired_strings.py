"""SB4c D5 -- the bespoke elevation bubble, its paper geometry swap and the
bespoke datum head (quadrant items, fonts, upper-casing, DM fill / scale / font
reads) are gone; BUBBLE_RADIUS_MM is kept (section / detail markers use it)."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1] / "firepro3d"

_GONE_EVERYWHERE = ("_ElevBubble", "_ElevLabel", "bubble_paper_geometry",
                    "GRIDLINE_BUBBLE_PAPER_CAP_MM", "GRIDLINE_BUBBLE_LABEL_EM_FRAC",
                    "_paper_bubble_r")


def test_retired_symbols_are_gone_from_the_package():
    for path in sorted(ROOT.rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        for s in _GONE_EVERYWHERE:
            assert s not in src, (path.name, s)


def test_section_scene_has_no_bespoke_head_or_retired_display_reads():
    src = (ROOT / "section_scene.py").read_text(encoding="utf-8")
    for s in ("display/Grid Line/fill", "display/Grid Line/scale",
              "display/Level Datum/fill", "display/Level Datum/scale",
              "display/Level Datum/font", "_build_bubble", "_build_labels",
              "_reposition_children", "_fill_quad", "_name_font", "_elev_font",
              "_fill_src", "fill_src=", "cap_mm", "_SrcSimpleText", "class _SrcPath", ".upper()",
              "_bubble_r"):
        assert s not in src, s


def test_paper_display_keeps_no_head_fill_rows():
    src = (ROOT / "paper_display.py").read_text(encoding="utf-8")
    assert "cap_mm" not in src and "fill_src=" not in src


def test_bubble_radius_constant_is_kept():
    from firepro3d.gridline import BUBBLE_RADIUS_MM
    assert BUBBLE_RADIUS_MM == 8.0 * 25.4            # section_marker / detail_view proportion base
