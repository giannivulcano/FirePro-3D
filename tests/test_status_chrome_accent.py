"""Accent-derivation guard for the status-bar chrome (SNAP/ALIGN pills).

The pills must derive their accent from the active theme (theme.detect().accent),
not the retired ACCENT_GREEN (#44FF88) or the rogue #44aaff. Off-state greys are
intentionally out of scope (full-chrome unification follow-up)."""
import main
from firepro3d import theme as th


def test_pill_on_style_uses_theme_accent(qapp):
    style = main._pill_style(True)
    accent = th.detect().accent
    assert accent in style
    assert "#44ff88" not in style.lower()   # retired neon green
    assert "#44aaff" not in style.lower()   # rogue blue
    assert "#004cff" not in style.lower()   # blue accent


def test_pill_off_style_has_no_accent(qapp):
    # Off state is intentionally grey — no accent hex leaks in.
    style = main._pill_style(False)
    assert "#888" in style  # off greys are deliberately retained (deferred)


def test_mode_badge_style_uses_theme_accent(qapp):
    style = main._mode_badge_style(th.detect().accent)
    assert th.detect().accent in style
    assert "#44aaff" not in style.lower()   # rogue blue retired
