"""Parametric title block templates: data model, layout solver, library I/O.

Governing spec: docs/specs/titleblock-template-system.md. Pure of QGraphics
types — QRectF/QFontMetricsF only — so the solver is unit-testable headless.
"""
from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass, field

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QFont, QFontMetricsF

from .constants import (
    TB_MARGIN_EDGE_DEFAULT_MM, TB_MARGIN_STRIP_DEFAULT_MM,
    TB_STRIP_DEFAULT_MM, TB_DEFAULT_FILLET_MM,
    TB_STRIP_MIN_MM, TB_AREA_MIN_MM, TEXT_METRIC_REF_PX,
    TB_CELL_PAD_MM, TB_LABEL_ROW_MM, TB_REV_ROW_MM,
)

CELL_KINDS = ("field", "static_text", "logo", "revision_table", "stamp")


@dataclass
class BorderStyle:
    """Border appearance for a frame or cell (mm widths, fillet/sharp corners)."""

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
    """Single cell in the info-strip stack: kind, content source, and typography."""

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
    """Layout parameters for one paper size: margins, strip width, and cell stack."""

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
    """Named, versioned collection of per-paper-size TemplateVariants."""

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


# ── Layout solver ────────────────────────────────────────────────────────────

@dataclass
class SolvedLayout:
    """Resolved geometry (paper mm) consumed by renderer and editor preview."""

    area_rect: QRectF
    strip_rect: QRectF
    cell_rects: list[QRectF]                 # QRectF per cell (index-aligned with cells)
    cell_lines: list[list[str]]              # wrapped value lines per cell
    cell_revision_rows: dict[int, list[dict]]  # cell index -> newest-first list of rev dicts
    warnings: list[str]


def _cell_font(cell: CellSpec) -> QFont:
    f = QFont(cell.font_family or "Arial")
    f.setBold(cell.bold)
    f.setItalic(cell.italic)
    f.setPixelSize(TEXT_METRIC_REF_PX)
    return f


def _word_wrap_paragraph(fm: QFontMetricsF, text: str,
                          avail_px: float) -> list[str]:
    """Greedy word-wrap of a single paragraph (no embedded newlines).

    Deterministic: matches the renderer path. Always produces at least one
    entry (even for an empty paragraph → one empty string).
    """
    if not text:
        return [""]
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and fm.horizontalAdvance(trial) > avail_px:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def _wrapped_height_mm(cell: CellSpec, text: str,
                        width_mm: float) -> tuple[float, list[str]]:
    """Wrapped height (mm) of *text* at the cell's cap height, plus the lines.

    Hard ``\\n`` newlines split into paragraphs first; each paragraph is then
    word-wrapped independently. An empty paragraph produces one empty line.
    Text keeps its size and wraps; the cell grows (spec DD-8).
    """
    if not text:
        return 0.0, []
    f = _cell_font(cell)
    fm = QFontMetricsF(f)
    cap_px = fm.capHeight() or 1.0
    # Guard against zero/negative cap_height_mm to avoid division by zero.
    px_per_mm = cap_px / max(cell.cap_height_mm, 0.1)
    avail_px = max(1.0, width_mm * px_per_mm)
    # Split on hard newlines first, then word-wrap each paragraph.
    lines: list[str] = []
    for para in text.split("\n"):
        lines.extend(_word_wrap_paragraph(fm, para, avail_px))
    line_h_mm = fm.lineSpacing() / px_per_mm
    return len(lines) * line_h_mm, lines


def solve_layout(variant: TemplateVariant, paper_w_mm: float,
                 paper_h_mm: float, values: dict) -> SolvedLayout:
    """Solve the parametric layout for one variant on one paper size.

    Args:
        variant: The template variant to solve.
        paper_w_mm: Paper width (mm).
        paper_h_mm: Paper height (mm).
        values: Resolved field values; key ``"__revisions__"`` optionally
            carries the sheet's revision list (oldest-first).

    Returns:
        A SolvedLayout with all rects in paper-mm coordinates.
        ``cell_revision_rows`` lists are **newest-first**; the input
        ``__revisions__`` list is oldest-first.
    """
    m, ms, sw = (variant.margin_edge_mm, variant.margin_strip_mm,
                 variant.strip_width_mm)
    warnings: list[str] = []
    strip_rect = QRectF(paper_w_mm - m - sw, m, sw, paper_h_mm - 2 * m)
    area_rect = QRectF(m, m, paper_w_mm - 2 * m - sw - ms, paper_h_mm - 2 * m)

    cell_rects: list[QRectF] = []
    cell_lines: list[list[str]] = []
    cell_revision_rows: dict[int, list[dict]] = {}
    y = strip_rect.top()
    i = 0
    cells = variant.cells
    while i < len(cells):
        pair = (cells[i].pair_with_next and i + 1 < len(cells))
        group = [cells[i], cells[i + 1]] if pair else [cells[i]]
        cw = strip_rect.width() / len(group)
        heights, lines_group = [], []
        for j, cell in enumerate(group):
            text = ""
            if cell.kind == "field":
                text = str(values.get(cell.field_key, ""))
            elif cell.kind == "static_text":
                text = cell.static_text
            h_text, lines = _wrapped_height_mm(
                cell, text, cw - 2 * TB_CELL_PAD_MM)
            extra = TB_LABEL_ROW_MM if cell.label else 0.0
            # Clamp min_height_mm to 0 so negative specs don't produce
            # negative-height rects.
            min_h = max(0.0, cell.min_height_mm)
            h = max(min_h, (h_text + extra + 2 * TB_CELL_PAD_MM)
                    if text else min_h)
            if cell.kind == "revision_table":
                revs = list(values.get("__revisions__", []))
                shown = list(reversed(revs))[: cell.revision_rows]
                cell_revision_rows[i + j] = shown
                h = max(min_h,
                        TB_LABEL_ROW_MM + (len(shown) + 1) * TB_REV_ROW_MM)
            heights.append(h)
            lines_group.append(lines)
        row_h = max(heights)
        x = strip_rect.left()
        for cell, lines in zip(group, lines_group):
            cell_rects.append(QRectF(x, y, cw, row_h))
            cell_lines.append(lines)
            x += cw
        y += row_h
        i += len(group)

    if cell_rects and cell_rects[-1].bottom() > strip_rect.bottom() + 1e-6:
        warnings.append(
            "Cells overflow the strip bottom and will be clipped.")
    return SolvedLayout(area_rect=area_rect, strip_rect=strip_rect,
                        cell_rects=cell_rects, cell_lines=cell_lines,
                        cell_revision_rows=cell_revision_rows,
                        warnings=warnings)


# ── Validation ───────────────────────────────────────────────────────────────

def validate(variant: TemplateVariant, paper_w_mm: float,
             paper_h_mm: float) -> list[str]:
    """Save-blocking validation floors (spec §Layout Solver).

    Args:
        variant: The template variant to validate.
        paper_w_mm: Paper width (mm).
        paper_h_mm: Paper height (mm).

    Returns:
        List of error/warning strings; empty list means valid.
    """
    errs: list[str] = []
    if variant.margin_edge_mm < 0 or variant.margin_strip_mm < 0:
        errs.append("Margins must be >= 0.")
    if variant.strip_width_mm < TB_STRIP_MIN_MM:
        errs.append(f"Strip width must be >= {TB_STRIP_MIN_MM:g} mm.")
    area_w = (paper_w_mm - 2 * variant.margin_edge_mm
              - variant.strip_width_mm - variant.margin_strip_mm)
    area_h = paper_h_mm - 2 * variant.margin_edge_mm
    if area_w < TB_AREA_MIN_MM or area_h < TB_AREA_MIN_MM:
        errs.append(f"Drawing area must be >= {TB_AREA_MIN_MM:g} mm "
                    "in each dimension.")
    # Fillet check against the actual rect for each frame, not the paper dims.
    strip_h = paper_h_mm - 2 * variant.margin_edge_mm
    strip_w = variant.strip_width_mm
    if (variant.area_border.corner == "fillet"
            and variant.area_border.fillet_radius_mm > min(area_w, area_h) / 2):
        errs.append("Fillet radius too large for the drawing area rect.")
    if (variant.strip_border.corner == "fillet"
            and variant.strip_border.fillet_radius_mm
            > min(strip_w, strip_h) / 2):
        errs.append("Fillet radius too large for the info-strip rect.")
    if not variant.cells:
        errs.append("Template needs at least one cell.")
    for c in variant.cells:
        if c.cap_height_mm <= 0:
            errs.append("Cell cap height must be > 0.")
            break
    for c in variant.cells:
        if c.min_height_mm < 0:
            errs.append("Cell minimum height must be >= 0.")
            break
    for c in variant.cells:
        if c.kind == "field" and not c.field_key:
            errs.append("Every field cell needs a field key.")
            break
    min_total = 0.0
    i = 0
    while i < len(variant.cells):
        pair = (variant.cells[i].pair_with_next
                and i + 1 < len(variant.cells))
        group = variant.cells[i:i + 2] if pair else [variant.cells[i]]
        row_min = 0.0
        for c in group:
            cell_min = c.min_height_mm
            if c.kind == "revision_table":
                # Use worst-case full table height so the stack check is
                # conservative: label row + (revision_rows + 1 header) rows.
                cell_min = max(cell_min,
                               TB_LABEL_ROW_MM + (c.revision_rows + 1)
                               * TB_REV_ROW_MM)
            row_min = max(row_min, cell_min)
        min_total += row_min
        i += len(group)
    if min_total > paper_h_mm - 2 * variant.margin_edge_mm:
        errs.append("Minimum cell stack does not fit the strip height.")
    return errs
