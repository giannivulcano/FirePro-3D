"""Parametric title block templates: data model, layout solver, library I/O.

Governing spec: docs/specs/titleblock-template-system.md. Pure of QGraphics
types — QRectF/QFontMetricsF only — so the solver is unit-testable headless.
"""
from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass, field

from .constants import (
    TB_MARGIN_EDGE_DEFAULT_MM, TB_MARGIN_STRIP_DEFAULT_MM,
    TB_STRIP_DEFAULT_MM, TB_DEFAULT_FILLET_MM,
)

CELL_KINDS = ("field", "static_text", "logo", "revision_table", "stamp")


@dataclass
class BorderStyle:
    visible: bool = True
    width_mm: float = 0.5
    color: str = "#000000"
    corner: str = "fillet"              # "sharp" | "fillet"
    fillet_radius_mm: float = TB_DEFAULT_FILLET_MM

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "BorderStyle":
        return cls(
            visible=bool(d.get("visible", True)),
            width_mm=float(d.get("width_mm", 0.5)),
            color=d.get("color", "#000000"),
            corner=d.get("corner", "fillet"),
            fillet_radius_mm=float(d.get("fillet_radius_mm",
                                         TB_DEFAULT_FILLET_MM)),
        )


def _cell_border_default() -> BorderStyle:
    # Cells default to thin sharp borders; frames default to fillet.
    return BorderStyle(width_mm=0.3, corner="sharp", fillet_radius_mm=0.0)


@dataclass
class CellSpec:
    kind: str
    field_key: str = ""
    label: str = ""
    static_text: str = ""
    min_height_mm: float = 10.0
    pair_with_next: bool = False
    font_family: str = "Arial"
    cap_height_mm: float = 3.0
    bold: bool = True
    italic: bool = False
    alignment: str = "left"             # "left" | "center" | "right"
    fill_color: str = ""                # "" = no fill
    border: BorderStyle = field(default_factory=_cell_border_default)
    logo_data: str = ""                 # base64 PNG
    logo_fit: str = "contain"
    revision_rows: int = 3

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["border"] = self.border.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CellSpec":
        return cls(
            kind=d.get("kind", "field"),
            field_key=d.get("field_key", ""),
            label=d.get("label", ""),
            static_text=d.get("static_text", ""),
            min_height_mm=float(d.get("min_height_mm", 10.0)),
            pair_with_next=bool(d.get("pair_with_next", False)),
            font_family=d.get("font_family", "Arial"),
            cap_height_mm=float(d.get("cap_height_mm", 3.0)),
            bold=bool(d.get("bold", True)),
            italic=bool(d.get("italic", False)),
            alignment=d.get("alignment", "left"),
            fill_color=d.get("fill_color", ""),
            border=BorderStyle.from_dict(d.get("border", {})),
            logo_data=d.get("logo_data", ""),
            logo_fit=d.get("logo_fit", "contain"),
            revision_rows=int(d.get("revision_rows", 3)),
        )


def _frame_border_default() -> BorderStyle:
    return BorderStyle()


@dataclass
class TemplateVariant:
    paper_size: str
    margin_edge_mm: float = TB_MARGIN_EDGE_DEFAULT_MM
    margin_strip_mm: float = TB_MARGIN_STRIP_DEFAULT_MM
    strip_width_mm: float = TB_STRIP_DEFAULT_MM
    strip_edge: str = "right"           # MVP fixed; reserved (spec DD-6)
    area_border: BorderStyle = field(default_factory=_frame_border_default)
    strip_border: BorderStyle = field(default_factory=_frame_border_default)
    cells: list[CellSpec] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "paper_size": self.paper_size,
            "margin_edge_mm": self.margin_edge_mm,
            "margin_strip_mm": self.margin_strip_mm,
            "strip_width_mm": self.strip_width_mm,
            "strip_edge": self.strip_edge,
            "area_border": self.area_border.to_dict(),
            "strip_border": self.strip_border.to_dict(),
            "cells": [c.to_dict() for c in self.cells],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TemplateVariant":
        return cls(
            paper_size=d.get("paper_size", ""),
            margin_edge_mm=float(d.get("margin_edge_mm",
                                       TB_MARGIN_EDGE_DEFAULT_MM)),
            margin_strip_mm=float(d.get("margin_strip_mm",
                                        TB_MARGIN_STRIP_DEFAULT_MM)),
            strip_width_mm=float(d.get("strip_width_mm", TB_STRIP_DEFAULT_MM)),
            strip_edge=d.get("strip_edge", "right"),
            area_border=BorderStyle.from_dict(d.get("area_border", {})),
            strip_border=BorderStyle.from_dict(d.get("strip_border", {})),
            cells=[CellSpec.from_dict(c) for c in d.get("cells", [])],
        )


@dataclass
class TitleBlockTemplate:
    name: str
    uuid: str
    modified: str                       # ISO date; divergence compare key
    variants: dict[str, TemplateVariant] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "uuid": self.uuid,
            "modified": self.modified,
            "variants": {k: v.to_dict() for k, v in self.variants.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TitleBlockTemplate":
        return cls(
            name=d.get("name", "Untitled"),
            uuid=d.get("uuid", ""),
            modified=d.get("modified", ""),
            variants={k: TemplateVariant.from_dict(v)
                      for k, v in d.get("variants", {}).items()},
        )

    def copy(self) -> "TitleBlockTemplate":
        return TitleBlockTemplate.from_dict(copy.deepcopy(self.to_dict()))
