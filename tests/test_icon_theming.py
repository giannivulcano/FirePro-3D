from PyQt6.QtGui import QIcon

from firepro3d import icons
from firepro3d.svg_utils import svg_recolor

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
