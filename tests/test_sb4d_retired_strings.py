"""SB4d D7 -- the bespoke view-marker head paint is gone: circle / text
paint, the DM font / fill fields, the rotated section label, the callout's
fixed radius and the retired z constants. BUBBLE_RADIUS_MM, _R_CARDINAL
and _R_SECTION are kept as seed-proportion sources."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1] / "firepro3d"

_GONE_EVERYWHERE = ("_label_angle", "_label_font(", "_display_font_size", "_head_polygon",
                    "_TAG_RADIUS", "Z_DETAIL_MARKER", "Z_LABEL_ABOVE_PIPE")


def test_retired_symbols_are_gone_from_the_package():
    for path in sorted(ROOT.rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        for s in _GONE_EVERYWHERE:
            assert s not in src, (path.name, s)


def test_marker_modules_paint_no_bespoke_head():
    for name in ("section_marker.py", "detail_view.py"):
        src = (ROOT / name).read_text(encoding="utf-8")
        for s in ("_fill_color", "QFont", "drawText", "drawEllipse(c, R, R)",
                  "drawEllipse(end, R, R)", "drawEllipse(bp, R, R)"):
            assert s not in src, (name, s)


def test_seed_proportion_sources_are_kept():
    from firepro3d.gridline import BUBBLE_RADIUS_MM
    from firepro3d.section_marker import SectionMarker
    assert BUBBLE_RADIUS_MM == 8.0 * 25.4
    assert SectionMarker._R_CARDINAL == 3.0 * BUBBLE_RADIUS_MM
    assert SectionMarker._R_SECTION == 2.0 * BUBBLE_RADIUS_MM
