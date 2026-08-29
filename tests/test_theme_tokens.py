"""Tests for the two-layer design-token system (theme.py)."""
from dataclasses import fields

import pytest
from PyQt6.QtGui import QColor

from firepro3d import theme as th

PRIMITIVES = {
    "ground", "surface", "sunken", "raised", "line", "line_strong",
    "ink", "muted", "faint", "accent", "accent_ink",
    "selection", "selection_active", "ok", "warn", "danger",
}

SEMANTICS = {
    "bg_base", "bg_raised", "bg_sunken", "bg_tab_inactive", "bg_tab_selected",
    "btn_hover", "btn_pressed", "btn_checked", "btn_checked_border",
    "border_strong", "border_subtle",
    "text_primary", "text_secondary", "text_disabled", "text_accent",
    "canvas_bg", "grid_dot",
    "accent_primary", "status_ok", "status_warn", "status_error",
    "accent_soft", "accent_soft2", "chip", "chip_ink",
    "warn_soft", "danger_soft", "surface2", "table",
}


def test_theme_has_exactly_16_primitive_fields():
    names = {f.name for f in fields(th.Theme)} - {"name"}
    assert names == PRIMITIVES


def test_presets_author_only_primitives_and_are_hex():
    for preset in (th.DARK, th.LIGHT):
        for name in PRIMITIVES:
            val = getattr(preset, name)
            assert isinstance(val, str) and val.startswith("#") and len(val) == 7, (
                f"{preset.name}.{name} = {val!r}"
            )


def test_dark_primitive_values():
    assert th.DARK.accent == "#63BE8B"
    assert th.DARK.ground == "#141619"
    assert th.DARK.selection_active == "#8FE3B4"


def test_semantic_aliases_resolve_for_both_presets():
    for preset in (th.DARK, th.LIGHT):
        for name in SEMANTICS:
            val = getattr(preset, name)
            assert isinstance(val, str) and val, f"{preset.name}.{name}"


def test_semantic_mapping_points_at_primitives():
    t = th.DARK
    assert t.bg_base == t.ground
    assert t.bg_raised == t.raised
    assert t.bg_sunken == t.sunken
    assert t.border_strong == t.line_strong
    assert t.text_primary == t.ink
    assert t.accent_primary == t.accent
    assert t.status_warn == t.warn


def test_color_resolves_primitive_and_semantic_names_with_alpha():
    t = th.DARK
    c = t.color("accent")
    assert isinstance(c, QColor) and c.name().lower() == "#63be8b"
    assert t.color("accent", 40).alpha() == 40
    assert t.color("chip_ink").name().lower() == t.color("muted").name().lower()


def test_detect_returns_a_theme():
    assert isinstance(th.detect(), th.Theme)


def test_app_qss_contains_token_values_and_density():
    qss = th.build_app_qss(th.DARK)
    assert th.DARK.ink in qss
    assert th.DARK.accent in qss
    assert th.DARK.raised in qss
    assert "border-radius: 6px" in qss
    assert "font-size: 13px" in qss or "font-size:13px" in qss


def test_app_qss_has_variant_and_role_selectors():
    qss = th.build_app_qss(th.DARK)
    assert 'QPushButton[variant="primary"]' in qss
    assert 'QPushButton[variant="danger"]' in qss
    assert 'QLabel[role="header"]' in qss
    assert 'QLabel[state="warn"]' in qss
