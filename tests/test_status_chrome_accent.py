"""Accent-derivation guard for the footer chrome (SNAP/ALIGN/HALO pills).

Post chrome-revamp the status pills live in ``firepro3d.footer_rail`` (the old
``main._pill_style``/``_mode_badge_style`` helpers are retired). The pills must
derive their accent from the active theme (``theme.detect().accent``), never a
rogue literal; the OFF state uses the muted/line tokens with no accent leak."""
from firepro3d import footer_rail
from firepro3d import theme as th


def test_pill_on_style_uses_theme_accent(qapp):
    style = footer_rail._pill_style(True)
    accent = th.detect().accent
    assert accent in style
    assert "#44ff88" not in style.lower()   # retired neon green
    assert "#44aaff" not in style.lower()   # rogue blue


def test_pill_off_style_has_no_accent(qapp):
    # Off state derives from muted/line tokens — no accent hex leaks in.
    style = footer_rail._pill_style(False)
    accent = th.detect().accent
    assert accent not in style
    assert th.detect().muted in style
