"""Lightweight SVG helpers with no Qt-widget dependencies."""
from __future__ import annotations

import re


def svg_recolor(svg_text: str, color_map: dict[str, str]) -> bytes:
    """Substitute sentinel colours in an SVG string, returning UTF-8 bytes.

    Case-insensitive on the source hex; ``none`` is never a key so
    fill:none / stroke:none survive untouched. Used by the themed icon
    loader (two-token model — see docs/specs/icon-style-guide.md).
    """
    lut = {k.lower(): v for k, v in color_map.items()}

    def _sub(m: re.Match) -> str:
        hexv = m.group(0).lower()
        return lut.get(hexv, m.group(0))

    return re.sub(r"#[0-9A-Fa-f]{6}(?![0-9A-Fa-f])", _sub, svg_text).encode("utf-8")
