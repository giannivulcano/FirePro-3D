import re

from PyQt6.QtGui import QIcon

from firepro3d import icons
from firepro3d.assets import asset_path
from firepro3d.svg_utils import svg_recolor

# Architecture-tab icons authored against docs/specs/icon-style-guide.md.
_ARCH_ICONS = [
    "wall_icon.svg", "floor_icon.svg", "roof_icon.svg", "room_icon.svg",
    "door_icon.svg", "window_icon.svg", "blank_icon.svg",
    "detail_icon.svg", "levels_icon.svg", "gridline_icon.svg",
    "underlay_icon.svg",
]
# Only these colour literals may appear (style-guide §4.1). Case-insensitive.
_ALLOWED_HEX = {"#1a1a1a", "#004cff"}
_HEX_RE = re.compile(r"#[0-9a-fA-F]{6,8}")

_SVG = (
    '<?xml version="1.0"?>'
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">'
    '<path d="M0 0h10v10H0z" fill="#1A1A1A" stroke="#1A1A1A"/>'
    '<circle cx="24" cy="24" r="8" fill="#004CFF"/>'
    '<rect x="1" y="1" width="2" height="2" fill="none" stroke="none"/>'
    '</svg>'
)

def test_svg_recolor_substitutes_sentinels():
    out = svg_recolor(_SVG, {"#1A1A1A": "#FFFFFF", "#004CFF": "#00A000"}).decode("utf-8")
    assert "#FFFFFF" in out and "#00A000" in out
    assert "#1A1A1A" not in out and "#004CFF" not in out

def test_svg_recolor_is_case_insensitive_on_source():
    out = svg_recolor(_SVG.replace("#1A1A1A", "#1a1a1a"), {"#1A1A1A": "#FFFFFF"}).decode("utf-8")
    assert "#FFFFFF" in out and "#1a1a1a" not in out

def test_svg_recolor_leaves_none_untouched():
    out = svg_recolor(_SVG, {"#1A1A1A": "#FFFFFF"}).decode("utf-8")
    assert 'fill="none"' in out and 'stroke="none"' in out

def test_svg_recolor_ignores_8digit_hex():
    svg = '<svg><path fill="#1A1A1AFF"/></svg>'
    out = svg_recolor(svg, {"#1A1A1A": "#FFFFFF"}).decode("utf-8")
    assert out == '<svg><path fill="#1A1A1AFF"/></svg>'  # 8-digit hex left untouched

def test_themed_icon_returns_nonnull_for_existing(qapp):
    ic = icons.themed_icon("save_icon.svg", icons.LIGHT)
    assert isinstance(ic, QIcon) and not ic.isNull()

def test_themed_icon_missing_uses_fallback_not_blank(qapp):
    ic = icons.themed_icon("does_not_exist.svg", icons.LIGHT)
    assert isinstance(ic, QIcon) and not ic.isNull()  # fallback glyph, never blank

def test_theme_tokens_differ_light_vs_dark():
    assert icons.token_map(icons.LIGHT) != icons.token_map(icons.DARK)
    assert icons.token_map(icons.LIGHT)[icons.PRIMARY_SENTINEL] != \
           icons.token_map(icons.DARK)[icons.PRIMARY_SENTINEL]


def test_architecture_icons_exist_and_are_two_token_compliant():
    """Every Architecture-tab icon uses only the two authoring sentinels.

    Guards the coverage mandate (style-guide §7) and the two-token rule (§4.1):
    any other hex literal (or an 8-digit hex) would fail to retheme and show a
    visual defect in one or both themes — exactly the bug the old white-hardcoded
    gridline_icon had.
    """
    import os
    for name in _ARCH_ICONS:
        path = asset_path("Ribbon", name)
        assert os.path.isfile(path), f"{name} missing from graphics/Ribbon"
        raw = open(path, "r", encoding="utf-8").read()
        for hexval in _HEX_RE.findall(raw):
            assert len(hexval) == 7, f"{name}: 8-digit hex {hexval} is forbidden (§4.1)"
            assert hexval.lower() in _ALLOWED_HEX, \
                f"{name}: non-sentinel colour {hexval} will not retheme (§4.1)"


def test_architecture_icons_render_nonblank_both_themes_no_fallback(qapp, caplog):
    """Each icon resolves to a real file (no _missing_icon fallback warning)."""
    icons._cache.clear()
    for name in _ARCH_ICONS:
        for theme in (icons.LIGHT, icons.DARK):
            with caplog.at_level("WARNING", logger="firepro3d.icons"):
                caplog.clear()
                ic = icons.themed_icon(name, theme)
            assert isinstance(ic, QIcon) and not ic.isNull()
            assert "not found" not in caplog.text, f"{name} hit the fallback glyph"
