"""text_item.py — Shared text data model for paper annotations and block/model text (C5).

This module is the single home for ``TextAnnotationData``, the serialisable
dataclass that backs both paper-space ``TextAnnotationItem`` and the upcoming
model-space ``TextItem`` primitive (containment contract C5, Slice 5.2).

Neither class is defined here — only the *data model*.  GUI code lives in
``paper_space.py`` (paper) and the forthcoming ``text_item_widget.py`` (model).
"""
from __future__ import annotations

from dataclasses import dataclass

from .constants import DEFAULT_TEXT_HEIGHT_MM


@dataclass
class TextAnnotationData:
    """Serialisable data for one text annotation.  All lengths in paper mm.

    Shared by reference with its ``TextAnnotationItem`` (never copied), exactly
    like ``SheetViewData`` ↔ ``SheetViewport``.

    Fields
    ------
    text:
        Raw string content (may contain newlines).
    x, y:
        Position on the paper sheet (mm from sheet origin).
    height_mm:
        CAP height of the rendered text, in paper mm.
    wrap_width_mm:
        Word-wrap column width; 0 = auto (no wrap).
    box_height_mm:
        Explicit box height; 0 = auto-fit content.
    font_family:
        Font family name; empty string → Arial default.
    bold, italic, underline:
        Font style flags.
    color:
        Authored hex colour string, default black ``"#000000"``.
    align:
        Horizontal alignment: ``'L'`` | ``'C'`` | ``'R'``.
    opaque_bg:
        When ``True``, render a white fill behind the text box.
    angle:
        Rotation in degrees (Y-up CCW+, same convention as the rest of the
        model).  Default ``0.0``.  Pivot is transient/recomputed at rest and
        is **not** serialised.
    type:
        Discriminator for future annotation kinds; always ``"text"`` for this
        class.
    """

    text: str = ""
    x: float = 0.0
    y: float = 0.0
    height_mm: float = DEFAULT_TEXT_HEIGHT_MM   # CAP height
    wrap_width_mm: float = 0.0                   # 0 = auto-width; >0 = word-wrap width
    box_height_mm: float = 0.0                   # 0 = auto-fit content; >0 = stored box height
    font_family: str = ""                        # "" => Arial default
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str = "#000000"                       # authored hex, default black
    align: str = "L"                             # 'L' | 'C' | 'R'
    opaque_bg: bool = False
    angle: float = 0.0                           # rotation degrees, Y-up CCW+; pivot not serialised
    type: str = "text"                           # discriminator for future annotation types

    def to_dict(self) -> dict:
        return {
            "type": self.type, "text": self.text,
            "x": self.x, "y": self.y,
            "height_mm": self.height_mm, "wrap_width_mm": self.wrap_width_mm,
            "box_height_mm": self.box_height_mm,
            "font_family": self.font_family,
            "bold": self.bold, "italic": self.italic, "underline": self.underline,
            "color": self.color, "align": self.align,
            "opaque_bg": self.opaque_bg,
            "angle": self.angle,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TextAnnotationData":
        return cls(
            text=d.get("text", ""),
            x=d.get("x", 0.0), y=d.get("y", 0.0),
            height_mm=d.get("height_mm", DEFAULT_TEXT_HEIGHT_MM),
            wrap_width_mm=d.get("wrap_width_mm", 0.0),
            box_height_mm=float(d.get("box_height_mm", 0.0)),
            font_family=d.get("font_family", ""),
            bold=bool(d.get("bold", False)), italic=bool(d.get("italic", False)),
            underline=bool(d.get("underline", False)),
            color=d.get("color", "#000000"), align=d.get("align", "L"),
            opaque_bg=bool(d.get("opaque_bg", False)),
            angle=float(d.get("angle", 0.0)),
            type=d.get("type", "text"),
        )
