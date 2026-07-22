"""Parametric title block templates: data model, layout solver, library I/O.

Governing spec: docs/specs/titleblock-template-system.md. Pure of QGraphics
types — QRectF/QFontMetricsF only — so the solver is unit-testable headless.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import logging
import os
import uuid as _uuid
from dataclasses import dataclass, field

_log = logging.getLogger("FirePro3D")

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QFont, QFontMetricsF

from .constants import (
    TB_MARGIN_EDGE_DEFAULT_MM, TB_MARGIN_STRIP_DEFAULT_MM,
    TB_STRIP_DEFAULT_MM, TB_DEFAULT_FILLET_MM,
    TB_STRIP_MIN_MM, TB_AREA_MIN_MM, TEXT_METRIC_REF_PX,
    TB_CELL_PAD_MM, TB_LABEL_ROW_MM, TB_REV_ROW_MM,
)

CELL_KINDS = ("field", "static_text", "logo", "revision_table", "stamp")

# Native orientation for each known paper size:
# "landscape" means stored dims have w > h; "portrait" means h > w.
# Derived from PAPER_SIZES in paper_space.py (cannot import — cycle risk);
# encoded once here. Update when PAPER_SIZES changes.
_NATIVE_ORIENTATION: dict[str, str] = {
    # ISO A-series: w < h → portrait
    "A4":     "portrait",
    "A3":     "portrait",
    "A2":     "portrait",
    "A1":     "portrait",
    "A0":     "portrait",
    # ANSI: w > h → landscape
    "ANSI B": "landscape",
    "ANSI D": "landscape",
    # Legacy
    "Letter": "portrait",   # 215.9 < 279.4 → portrait
    "D-size": "portrait",   # 558.8 < 863.6 → portrait
}


def native_orientation(paper_size: str) -> str:
    """Return "landscape" or "portrait" for the named paper size's stored dims.

    Defaults to "landscape" for unknown sizes.

    Args:
        paper_size: Key into PAPER_SIZES / _NATIVE_ORIENTATION.

    Returns:
        "landscape" or "portrait".
    """
    return _NATIVE_ORIENTATION.get(paper_size, "landscape")


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
    sizing: str = "static"               # "static" | "dynamic" (DD-8b)
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
        raw_sizing = d.get("sizing", "static")
        # Unknown values load as "static" (forward-compat)
        sizing = raw_sizing if raw_sizing in ("static", "dynamic") else "static"
        return cls(
            kind=d.get("kind", "field"),
            field_key=d.get("field_key", ""),
            label=d.get("label", ""),
            static_text=d.get("static_text", ""),
            min_height_mm=float(d.get("min_height_mm", 10.0)),
            sizing=sizing,
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
class TemplateLayout:
    """Layout parameters for a single paper size: margins, strip width, and cell stack.

    Formerly named TemplateVariant (renamed 2026-07-22).  The ``paper_size``
    field was removed from this class and hoisted to ``TitleBlockTemplate``.
    """

    margin_edge_mm: float = TB_MARGIN_EDGE_DEFAULT_MM
    margin_strip_mm: float = TB_MARGIN_STRIP_DEFAULT_MM
    strip_width_mm: float = TB_STRIP_DEFAULT_MM
    strip_edge: str = "right"           # MVP fixed; reserved (spec DD-6)
    area_border: BorderStyle = field(default_factory=_frame_border_default)
    strip_border: BorderStyle = field(default_factory=_frame_border_default)
    cells: list[CellSpec] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "margin_edge_mm": self.margin_edge_mm,
            "margin_strip_mm": self.margin_strip_mm,
            "strip_width_mm": self.strip_width_mm,
            "strip_edge": self.strip_edge,
            "area_border": self.area_border.to_dict(),
            "strip_border": self.strip_border.to_dict(),
            "cells": [c.to_dict() for c in self.cells],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TemplateLayout":
        return cls(
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
    """Single-size parametric title block template (revised 2026-07-22).

    A template now holds ONE layout for ONE paper_size + orientation.
    The old variant-family format (``variants: dict``) is accepted by
    ``from_dict`` for back-compat (takes the first variant; hoists paper_size).
    """

    name: str
    uuid: str
    modified: str                       # ISO date; divergence compare key
    paper_size: str = "ANSI D"
    orientation: str = "landscape"      # "landscape" | "portrait"
    layout: TemplateLayout = field(default_factory=TemplateLayout)

    @property
    def display_name(self) -> str:
        """Human-readable name with size; appends orientation when non-native.

        Examples:
            "FirePro Default (ANSI D)" — landscape ANSI D (native)
            "FirePro Default (ANSI D, Portrait)" — non-native portrait
            "My A4 (A4, Landscape)" — non-native landscape on A4
        """
        nat = native_orientation(self.paper_size)
        if self.orientation != nat:
            label = "Portrait" if self.orientation == "portrait" else "Landscape"
            return f"{self.name} ({self.paper_size}, {label})"
        return f"{self.name} ({self.paper_size})"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "uuid": self.uuid,
            "modified": self.modified,
            "paper_size": self.paper_size,
            "orientation": self.orientation,
            "layout": self.layout.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TitleBlockTemplate":
        # ── Back-compat: old variant-family format ────────────────────────
        if "variants" in d and "layout" not in d:
            variants_raw = d["variants"]
            if isinstance(variants_raw, dict) and variants_raw:
                # Take the first variant; hoist its paper_size
                first_key = next(iter(variants_raw))
                first_v = variants_raw[first_key]
                hoisted_size = first_v.get("paper_size", first_key) or first_key
                # Build layout from first variant (ignore its paper_size key)
                layout_d = dict(first_v)
                layout_d.pop("paper_size", None)
                layout = TemplateLayout.from_dict(layout_d)
                orientation = _NATIVE_ORIENTATION.get(hoisted_size, "landscape")
                return cls(
                    name=d.get("name", "Untitled"),
                    uuid=d.get("uuid", ""),
                    modified=d.get("modified", ""),
                    paper_size=hoisted_size,
                    orientation=orientation,
                    layout=layout,
                )
            # Empty variants dict → fall through to default
        # ── New single-size format ────────────────────────────────────────
        layout_d = d.get("layout", {})
        # Ignore any legacy paper_size that may appear inside layout_d
        layout_d.pop("paper_size", None)
        return cls(
            name=d.get("name", "Untitled"),
            uuid=d.get("uuid", ""),
            modified=d.get("modified", ""),
            paper_size=d.get("paper_size", "ANSI D"),
            orientation=d.get("orientation", "landscape"),
            layout=TemplateLayout.from_dict(layout_d),
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


def solve_layout(variant: TemplateLayout, paper_w_mm: float,
                 paper_h_mm: float, values: dict) -> SolvedLayout:
    """Solve the parametric layout for one variant on one paper size.

    Args:
        variant: The template layout to solve.
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
    # Track which row-index each cell belongs to (for the dynamic pass)
    cell_row_indices: list[int] = []
    # Per-row info for dynamic pass:
    #   (first_cell_idx, is_dynamic, solved_row_h, row_min_height_mm)
    # row_min_height_mm = max(cell.min_height_mm) across the row's group;
    # used as proportionality basis for leftover distribution (spec DD-8b).
    row_info: list[tuple[int, bool, float, float]] = []

    y = strip_rect.top()
    i = 0
    row_idx = 0
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
        # A paired row is dynamic if EITHER member has sizing=="dynamic"
        row_dynamic = any(c.sizing == "dynamic" for c in group)
        # Row min height = max of pair members' min_height_mm (clamped ≥ 0).
        # This is the spec DD-8b proportionality basis, independent of wrapping.
        row_min_h = max(max(0.0, c.min_height_mm) for c in group)
        # Track per-row: start cell index, dynamic flag, solved height, min height
        row_info.append((len(cell_rects), row_dynamic, row_h, row_min_h))

        x = strip_rect.left()
        for cell, lines in zip(group, lines_group):
            cell_rects.append(QRectF(x, y, cw, row_h))
            cell_lines.append(lines)
            cell_row_indices.append(row_idx)
            x += cw
        y += row_h
        i += len(group)
        row_idx += 1

    # ── Dynamic pass (DD-8b) ──────────────────────────────────────────────
    # After the static walk: distribute leftover strip height among dynamic rows.
    # Proportionality basis: row_min_height_mm (spec DD-8b §"Distribution rule").
    # This is intentionally the designer-set minimum, NOT the post-wrap solved
    # height, so that a cell whose text happened to wrap at a given field value
    # does not receive a larger share of the leftover than intended.
    stack_bottom = y  # where static walk ended
    leftover = strip_rect.bottom() - stack_bottom
    if leftover > 1e-9:
        # row_info stores (first_cell_idx, is_dynamic, solved_row_h, row_min_h)
        # Use enumeration index as the row identifier throughout.
        dyn_rows = [(row_i, row_min_h)
                    for row_i, (_, dyn, _rh, row_min_h) in enumerate(row_info)
                    if dyn]
        if dyn_rows:
            # Proportional distribution by min_height_mm (spec DD-8b)
            total_min = sum(mh for _, mh in dyn_rows)
            if total_min <= 0:
                # Equal shares fallback when all dynamic rows have zero min height
                share = leftover / len(dyn_rows)
                extras = {row_i: share for row_i, _ in dyn_rows}
            else:
                extras = {row_i: leftover * mh / total_min
                          for row_i, mh in dyn_rows}

            # Rebuild rects: second pass with extra heights
            new_cell_rects: list[QRectF] = []
            new_y = strip_rect.top()
            for row_i, (first_cell_idx, row_dynamic, old_row_h, _) in enumerate(row_info):
                extra_h = extras.get(row_i, 0.0) if row_dynamic else 0.0
                new_row_h = old_row_h + extra_h
                # Find how many cells are in this row
                if row_i + 1 < len(row_info):
                    next_first = row_info[row_i + 1][0]
                    n_cells = next_first - first_cell_idx
                else:
                    n_cells = len(cell_rects) - first_cell_idx
                # Distribute row width equally
                row_cw = strip_rect.width() / n_cells
                x = strip_rect.left()
                for ci in range(first_cell_idx, first_cell_idx + n_cells):
                    new_cell_rects.append(QRectF(x, new_y, row_cw, new_row_h))
                    x += row_cw
                new_y += new_row_h
            cell_rects = new_cell_rects

    if cell_rects and cell_rects[-1].bottom() > strip_rect.bottom() + 1e-6:
        warnings.append(
            "Cells overflow the strip bottom and will be clipped.")
    return SolvedLayout(area_rect=area_rect, strip_rect=strip_rect,
                        cell_rects=cell_rects, cell_lines=cell_lines,
                        cell_revision_rows=cell_revision_rows,
                        warnings=warnings)


# ── Validation ───────────────────────────────────────────────────────────────

def validate(variant: TemplateLayout, paper_w_mm: float,
             paper_h_mm: float) -> list[str]:
    """Save-blocking validation floors (spec §Layout Solver).

    Args:
        variant: The template layout to validate.
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


# ── User-library I/O ─────────────────────────────────────────────────────────

def _library_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "FirePro3D", "titleblocks")


def _library_path(uuid: str) -> str:
    """Validated library file path for *uuid* (rejects path separators/empty).

    Args:
        uuid: The template UUID to resolve to a file path.

    Returns:
        Absolute path ``<library_dir>/<uuid>.json``.

    Raises:
        ValueError: If *uuid* is empty, contains path separators, or is a
            reserved name (``"."`` or ``".."``).
    """
    if not uuid or os.path.basename(uuid) != uuid or uuid in (".", ".."):
        raise ValueError(f"Invalid template uuid for library storage: {uuid!r}")
    return os.path.join(_library_dir(), f"{uuid}.json")


def save_to_library(template: TitleBlockTemplate) -> str:
    """Write *template* to the user library; returns the file path.

    Uses an atomic write (tmp → replace) so a crash mid-write never leaves a
    truncated file that the skip guard would silently drop.

    Args:
        template: The template to persist.

    Returns:
        Absolute path of the written ``.json`` file.

    Raises:
        ValueError: If ``template.uuid`` is not safe for use as a file name.
        OSError: If the library directory cannot be created or the file cannot
            be written.
    """
    path = _library_path(template.uuid)
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(template.to_dict(), fh, indent=2)
    os.replace(tmp, path)
    return path


def load_library() -> list[TitleBlockTemplate]:
    """All parseable library templates; corrupt files are skipped with a log."""
    d = _library_dir()
    out: list[TitleBlockTemplate] = []
    if not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        if not name.lower().endswith(".json"):
            continue
        path = os.path.join(d, name)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                out.append(TitleBlockTemplate.from_dict(json.load(fh)))
        except Exception as exc:
            _log.warning("Skipping unreadable title block template %s: %s",
                         name, exc)
    return out


def delete_from_library(uuid: str) -> None:
    """Remove the library file for *uuid* (no-op when absent).

    Args:
        uuid: UUID of the template to remove.

    Raises:
        ValueError: If *uuid* is not safe for use as a file name.
    """
    path = _library_path(uuid)
    if os.path.isfile(path):
        os.remove(path)


def library_diverges(embedded: TitleBlockTemplate) -> bool:
    """True when the library holds the same uuid with a different modified stamp."""
    try:
        path = _library_path(embedded.uuid)
    except ValueError:
        return False
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        lib_modified = data.get("modified", "")
    except Exception:
        return False
    return lib_modified != embedded.modified


# ── Default template factory + legacy migration ──────────────────────────────

# Project-scoped legacy keys → Project Info home ("" = custom row of same name)
_LEGACY_PROJECT_KEYS = {"Company": "", "Project": "name",
                        "Drawn By": "", "Checked By": ""}

# Sheet-scoped keys that stay per-sheet after migration (public for scene_io tests).
LEGACY_SHEET_KEYS = ("Title", "Drawing No", "Rev", "Date")

# Bump this string whenever the shipped seed design changes so divergence checks
# pick up the new layout.
DEFAULT_SEED_MODIFIED = "2026-07-22"

# Accent fill colour shared by the two highlighted cells in the default template.
_ACCENT_FILL = "#eef2f7"


def migrate_legacy_fields(
    sheet_field_dicts: list[dict],
    project_info: dict,
    skip_values: dict | None = None,
) -> None:
    """One-way, idempotent migration of legacy 9-key title_block_fields.

    Project-scoped keys seed Project Info only where empty/absent; sheet-scoped
    keys (see ``LEGACY_SHEET_KEYS``) stay per-sheet; "Scale" drops
    (auto-computed). Mutates in place.

    Donor values are coerced to ``str`` and stripped; empty-after-strip values
    are skipped (guards against non-string junk in hand-edited project files).

    If *skip_values* is provided, a donor value that equals
    ``skip_values.get(legacy_key)`` is **not** treated as a real donor — it is
    considered "never edited from the shipped default".  Pass the app's shipped
    ``DEFAULT_TITLE_BLOCK_FIELDS`` here so that factory strings like
    "Celerity Engineering Limited" never seed Project Info.  The key is still
    popped from each sheet dict regardless.

    Args:
        sheet_field_dicts: Each sheet's title_block_fields dict (mutated).
        project_info: The project metadata dict (mutated).
        skip_values: Optional mapping of legacy key → shipped-default value.
            Donor entries that match are treated as absent.
    """
    skip_values = skip_values or {}
    donors = [d for d in sheet_field_dicts if d]
    for legacy_key, std_key in _LEGACY_PROJECT_KEYS.items():
        # Find first non-empty, non-skipped donor value across all sheets.
        value = ""
        for d in donors:
            raw = d.get(legacy_key)
            if raw is None:
                continue
            candidate = str(raw).strip()
            if not candidate:
                continue
            if candidate == str(skip_values.get(legacy_key, "")).strip():
                continue
            value = candidate
            break
        if not value:
            continue
        if std_key:                                  # standard field
            if not project_info.get(std_key):
                project_info[std_key] = value
        else:
            # Key-absence (not value-emptiness) guards the custom-row insert:
            # legacy projects predate custom rows entirely, so an absent key
            # means "never had one" — we must not overwrite a row the user
            # already created with this key.
            custom = project_info.setdefault("custom", [])
            if not any(c.get("key") == legacy_key for c in custom):
                custom.append({"key": legacy_key, "value": value})
    for d in sheet_field_dicts:
        d.pop("Scale", None)
        for k in list(d):
            if k in _LEGACY_PROJECT_KEYS:
                d.pop(k)


def _field(key: str, label: str, *, h: float = 10.0, cap: float = 2.6,
           pair: bool = False, fill: str = "",
           sizing: str = "static") -> CellSpec:
    """Shorthand CellSpec factory for the default template's field cells."""
    return CellSpec(kind="field", field_key=key, label=label,
                    min_height_mm=h, cap_height_mm=cap,
                    pair_with_next=pair, fill_color=fill, sizing=sizing)


def make_default_template() -> TitleBlockTemplate:
    """Seeded default: arrangement A 'Corporate top-down', filleted frames.

    Single ANSI D landscape template; stamp cell is dynamic (fills to strip
    bottom).
    """
    cells: list[CellSpec] = [
        CellSpec(kind="logo", min_height_mm=25.0),
        _field("Company", "Company", h=12.0, fill=_ACCENT_FILL),
        _field("Project", "Project", h=12.0),
        _field("Address", "Address", h=10.0),
        _field("Title", "Sheet Title", h=14.0, cap=3.2),
        _field("Scale", "Scale", pair=True),
        _field("Date", "Date"),
        _field("Drawn By", "Drawn", pair=True),
        _field("Checked By", "Checked"),
        _field("Drawing No", "Drawing No", h=14.0, cap=4.0, pair=True,
               fill=_ACCENT_FILL),
        _field("Rev", "Rev", h=14.0, cap=4.0),
        CellSpec(kind="revision_table", label="Revisions",
                 min_height_mm=25.0, revision_rows=3),
        CellSpec(kind="stamp", min_height_mm=60.0, sizing="dynamic"),
    ]
    layout = TemplateLayout(strip_width_mm=90.0, cells=cells)
    return TitleBlockTemplate(
        name="FirePro Default",
        uuid=str(_uuid.uuid4()),
        modified=DEFAULT_SEED_MODIFIED,
        paper_size="ANSI D",
        orientation="landscape",
        layout=layout,
    )
