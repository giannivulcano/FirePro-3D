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
# Blocks-group icons authored for S5 (make / insert / manager).
_BLOCK_ICONS = [
    "make_block_icon.svg", "insert_block_icon.svg", "block_manager_icon.svg",
]
# 2D-geometry icons authored on-contract (two-token). NOTE: the older
# line/rectangle/circle/arc/polyline icons are LEGACY off-contract (hardcoded
# #ffffff, 40mm canvas) and are intentionally NOT listed here — they predate the
# style guide and are a separate re-authoring follow-up. polygon_icon was
# authored against the two-token contract (2026-09-05).
_GEOM2D_ICONS = [
    "polygon_icon.svg",
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


def test_accent_token_derives_from_theme_variant():
    from firepro3d import theme as th
    assert icons.token_map(icons.LIGHT)[icons.ACCENT_SENTINEL] == th.LIGHT.accent
    assert icons.token_map(icons.DARK)[icons.ACCENT_SENTINEL] == th.DARK.accent


def test_accent_token_ground_truth_values():
    # Regression guard: light accent is now green (#2f9e63), not blue (#004CFF);
    # dark accent is the dialed-in sage (#63BE8B), not neon (#44FF88).
    assert icons.token_map(icons.LIGHT)[icons.ACCENT_SENTINEL].lower() == "#2f9e63"
    assert icons.token_map(icons.DARK)[icons.ACCENT_SENTINEL].lower() == "#63be8b"


def test_legacy_accent_constants_removed():
    # The two standalone accent constants are gone — theme.accent is the only home.
    assert not hasattr(icons, "ACCENT_GREEN")
    assert not hasattr(icons, "ACCENT_BLUE")


def test_primary_token_unchanged():
    # Only accent moved to the theme; primary ink stays black(light)/white(dark).
    assert icons.token_map(icons.LIGHT)[icons.PRIMARY_SENTINEL] == "#1A1A1A"
    assert icons.token_map(icons.DARK)[icons.PRIMARY_SENTINEL] == "#F0F0F0"


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


def test_block_icons_exist_and_are_two_token_compliant():
    """S5 Blocks-group icons use only the two authoring sentinels (§4.1)."""
    import os
    for name in _BLOCK_ICONS:
        path = asset_path("Ribbon", name)
        assert os.path.isfile(path), f"{name} missing from graphics/Ribbon"
        raw = open(path, "r", encoding="utf-8").read()
        for hexval in _HEX_RE.findall(raw):
            assert len(hexval) == 7, f"{name}: 8-digit hex {hexval} is forbidden (§4.1)"
            assert hexval.lower() in _ALLOWED_HEX, \
                f"{name}: non-sentinel colour {hexval} will not retheme (§4.1)"


def test_block_icons_render_nonblank_both_themes_no_fallback(qapp, caplog):
    """Each S5 Blocks icon resolves to a real file (no _missing_icon fallback)."""
    icons._cache.clear()
    for name in _BLOCK_ICONS:
        for theme in (icons.LIGHT, icons.DARK):
            with caplog.at_level("WARNING", logger="firepro3d.icons"):
                caplog.clear()
                ic = icons.themed_icon(name, theme)
            assert isinstance(ic, QIcon) and not ic.isNull()
            assert "not found" not in caplog.text, f"{name} hit the fallback glyph"


def test_geom2d_icons_exist_and_are_two_token_compliant():
    """On-contract 2D-geometry icons use only the two authoring sentinels (§4.1)."""
    import os
    for name in _GEOM2D_ICONS:
        path = asset_path("Ribbon", name)
        assert os.path.isfile(path), f"{name} missing from graphics/Ribbon"
        raw = open(path, "r", encoding="utf-8").read()
        for hexval in _HEX_RE.findall(raw):
            assert len(hexval) == 7, f"{name}: 8-digit hex {hexval} is forbidden (§4.1)"
            assert hexval.lower() in _ALLOWED_HEX, \
                f"{name}: non-sentinel colour {hexval} will not retheme (§4.1)"


def test_geom2d_icons_render_nonblank_both_themes_no_fallback(qapp, caplog):
    """polygon_icon resolves to a real file (no _missing_icon fallback), both themes."""
    icons._cache.clear()
    for name in _GEOM2D_ICONS:
        for theme in (icons.LIGHT, icons.DARK):
            with caplog.at_level("WARNING", logger="firepro3d.icons"):
                caplog.clear()
                ic = icons.themed_icon(name, theme)
            assert isinstance(ic, QIcon) and not ic.isNull()
            assert "not found" not in caplog.text, f"{name} hit the fallback glyph"
