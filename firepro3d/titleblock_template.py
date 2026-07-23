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
import re
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

KINDS = ("field", "revision_table")

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


#: @[Key] token — one or more non-bracket chars between the brackets.
TOKEN_RE = re.compile(r"@\[([^\[\]]+)\]")


def resolve_text(text: str, values: dict) -> tuple[str, list[str]]:
    """Substitute @[Key] tokens in *text* from *values* (spec DD-13).

    Known key (present in *values*) → its value, even when empty.
    Unknown key → token left literally (doubles as the escape hatch) and the
    key is reported. Malformed tokens don't match and pass through untouched.

    Args:
        text: Field text template (may be multi-line).
        values: Resolved value dict; membership defines the known-key set.

    Returns:
        (resolved_text, unknown_keys) — unknown keys in first-appearance
        order, deduped.
    """
    unknown: list[str] = []

    def _sub(m: "re.Match[str]") -> str:
        key = m.group(1)
        if key in values:
            return str(values[key])
        if key not in unknown:
            unknown.append(key)
        return m.group(0)

    return TOKEN_RE.sub(_sub, text), unknown


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


def new_field_id() -> str:
    """Short unique id for a FieldDef (uuid4 hex prefix)."""
    return _uuid.uuid4().hex[:8]


@dataclass
class FieldDef:
    """Intrinsic field definition — everything that survives unplacement (DD-11/12)."""

    id: str
    kind: str = "field"                 # "field" | "revision_table"
    name: str = ""
    label: str = ""
    text: str = ""                      # multi-line; @[Key] tokens (DD-13)
    image_data: str = ""                # base64 PNG; "" = none
    image_fit: str = "contain"
    image_position: str = "top"         # reserved (future side-by-side)
    font_family: str = "Arial"
    cap_height_mm: float = 3.0
    bold: bool = True
    italic: bool = False
    alignment: str = "left"
    fill_color: str = ""
    border: BorderStyle = field(default_factory=_cell_border_default)
    revision_rows: int = 3

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["border"] = self.border.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "FieldDef":
        kind = d.get("kind", "field")
        return cls(
            id=d.get("id") or new_field_id(),
            kind=kind if kind in KINDS else "field",
            name=d.get("name", ""),
            label=d.get("label", ""),
            text=d.get("text", ""),
            image_data=d.get("image_data", ""),
            image_fit=d.get("image_fit", "contain"),
            image_position=d.get("image_position", "top"),
            font_family=d.get("font_family", "Arial"),
            cap_height_mm=float(d.get("cap_height_mm", 3.0)),
            bold=bool(d.get("bold", True)),
            italic=bool(d.get("italic", False)),
            alignment=d.get("alignment", "left"),
            fill_color=d.get("fill_color", ""),
            border=BorderStyle.from_dict(d.get("border", {})),
            revision_rows=int(d.get("revision_rows", 3)),
        )


@dataclass
class Slot:
    """One strip placement of a FieldDef (DD-11/14). Placement facts only."""

    field_id: str
    min_height_mm: float = 10.0
    sizing: str = "static"              # "static" | "dynamic" (DD-8b)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Slot":
        raw = d.get("sizing", "static")
        return cls(
            field_id=d.get("field_id", ""),
            min_height_mm=float(d.get("min_height_mm", 10.0)),
            sizing=raw if raw in ("static", "dynamic") else "static",
        )


def _frame_border_default() -> BorderStyle:
    return BorderStyle()


_KIND_FALLBACK_NAMES = {"logo": "Logo", "stamp": "Stamp",
                        "revision_table": "Revision Table",
                        "static_text": "Text", "field": "Field"}


def _migrate_cells(cells_raw: list[dict]) -> tuple[list[FieldDef], list[list[Slot]]]:
    """One-way rev-2 → rev-3 cell migration (spec DD-12/DD-14).

    field_key="X" → text "@[X]"; static_text → text; logo → image-only;
    stamp → empty field; pair_with_next chains → two-slot rows.
    Names: label → field_key → kind fallback, deduped with " 2", " 3"…
    """
    fields: list[FieldDef] = []
    rows: list[list[Slot]] = []
    used_names: set[str] = set()

    def _mk(cell: dict) -> tuple[FieldDef, Slot]:
        kind = cell.get("kind", "field")
        text, image = "", ""
        if kind == "field" and cell.get("field_key"):
            text = f'@[{cell["field_key"]}]'
        elif kind == "static_text":
            text = cell.get("static_text", "")
        elif kind == "logo":
            image = cell.get("logo_data", "")
        base = (cell.get("label", "") or cell.get("field_key", "")
                or _KIND_FALLBACK_NAMES.get(kind, "Field"))
        name, n = base, 1
        while name in used_names:
            n += 1
            name = f"{base} {n}"
        used_names.add(name)
        fd = FieldDef(
            id=new_field_id(),
            kind="revision_table" if kind == "revision_table" else "field",
            name=name,
            label=cell.get("label", ""),
            text=text,
            image_data=image,
            image_fit=cell.get("logo_fit", "contain"),
            font_family=cell.get("font_family", "Arial"),
            cap_height_mm=float(cell.get("cap_height_mm", 3.0)),
            bold=bool(cell.get("bold", True)),
            italic=bool(cell.get("italic", False)),
            alignment=cell.get("alignment", "left"),
            fill_color=cell.get("fill_color", ""),
            border=BorderStyle.from_dict(cell.get("border", {})),
            revision_rows=int(cell.get("revision_rows", 3)),
        )
        raw_sz = cell.get("sizing", "static")
        slot = Slot(field_id=fd.id,
                    min_height_mm=float(cell.get("min_height_mm", 10.0)),
                    sizing=raw_sz if raw_sz in ("static", "dynamic") else "static")
        return fd, slot

    i = 0
    while i < len(cells_raw):
        fd, slot = _mk(cells_raw[i])
        fields.append(fd)
        if cells_raw[i].get("pair_with_next") and i + 1 < len(cells_raw):
            fd2, slot2 = _mk(cells_raw[i + 1])
            fields.append(fd2)
            rows.append([slot, slot2])
            i += 2
        else:
            rows.append([slot])
            i += 1
    return fields, rows


@dataclass
class TemplateLayout:
    """Layout parameters for a single paper size: margins, strip width, field pool, and rows.

    Formerly named TemplateVariant (renamed 2026-07-22).  The ``paper_size``
    field was removed from this class and hoisted to ``TitleBlockTemplate``.
    Rev 3 (2026-07-22): ``cells`` replaced by ``fields`` (pool) + ``rows``
    (placement grid).  The ``cells`` attribute is still accepted by
    ``from_dict`` for back-compat via ``_migrate_cells``.
    """

    margin_edge_mm: float = TB_MARGIN_EDGE_DEFAULT_MM
    margin_strip_mm: float = TB_MARGIN_STRIP_DEFAULT_MM
    strip_width_mm: float = TB_STRIP_DEFAULT_MM
    strip_edge: str = "right"           # MVP fixed; reserved (spec DD-6)
    area_border: BorderStyle = field(default_factory=_frame_border_default)
    strip_border: BorderStyle = field(default_factory=_frame_border_default)
    fields: list[FieldDef] = field(default_factory=list)
    rows: list[list[Slot]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "margin_edge_mm": self.margin_edge_mm,
            "margin_strip_mm": self.margin_strip_mm,
            "strip_width_mm": self.strip_width_mm,
            "strip_edge": self.strip_edge,
            "area_border": self.area_border.to_dict(),
            "strip_border": self.strip_border.to_dict(),
            "fields": [f.to_dict() for f in self.fields],
            "rows": [[s.to_dict() for s in row] for row in self.rows],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TemplateLayout":
        if "cells" in d and "fields" not in d:
            fields, rows = _migrate_cells(d.get("cells", []))
        else:
            fields = [FieldDef.from_dict(f) for f in d.get("fields", [])]
            rows = [[Slot.from_dict(s) for s in row]
                    for row in d.get("rows", [])]
        return cls(
            margin_edge_mm=float(d.get("margin_edge_mm",
                                       TB_MARGIN_EDGE_DEFAULT_MM)),
            margin_strip_mm=float(d.get("margin_strip_mm",
                                        TB_MARGIN_STRIP_DEFAULT_MM)),
            strip_width_mm=float(d.get("strip_width_mm", TB_STRIP_DEFAULT_MM)),
            strip_edge=d.get("strip_edge", "right"),
            area_border=BorderStyle.from_dict(d.get("area_border", {})),
            strip_border=BorderStyle.from_dict(d.get("strip_border", {})),
            fields=fields,
            rows=rows,
        )

    # ── Roster helpers ────────────────────────────────────────────────────
    def field_map(self) -> dict[str, FieldDef]:
        """Return a dict mapping field id → FieldDef for all fields in the pool."""
        return {f.id: f for f in self.fields}

    def placed_ids(self) -> set[str]:
        """Return the set of field ids referenced by at least one Slot."""
        return {s.field_id for row in self.rows for s in row}

    def pool_fields(self) -> list[FieldDef]:
        """Return fields not referenced by any Slot (the unplaced pool)."""
        placed = self.placed_ids()
        return [f for f in self.fields if f.id not in placed]


# ---------------------------------------------------------------------------
# Arrangement-mutation helpers (DD-11 / DD-16)
# ---------------------------------------------------------------------------

def _take_slot(layout: TemplateLayout, field_id: str) -> "Slot | None":
    """Remove and return *field_id*'s slot; drops its row when emptied."""
    for ri, row in enumerate(layout.rows):
        for si, slot in enumerate(row):
            if slot.field_id == field_id:
                row.pop(si)
                if not row:
                    layout.rows.pop(ri)
                return slot
    return None


def place_field(layout: TemplateLayout, field_id: str, row_index: int) -> None:
    """Place *field_id* as a new full-width row at *row_index* (DD-16).

    A previously placed field is moved (one placement per definition, DD-11).
    *row_index* is interpreted AFTER any removal and clamped to the valid
    range. Unknown field_id -> no-op.

    Drop prediction: ``StripCanvas._drop_would_mutate`` dry-runs this op on a
    trial layout — new guards added here are picked up automatically.
    """
    if field_id not in layout.field_map():
        return
    slot = _take_slot(layout, field_id) or Slot(field_id)
    row_index = max(0, min(row_index, len(layout.rows)))
    layout.rows.insert(row_index, [slot])


def unplace_field(layout: TemplateLayout, field_id: str) -> None:
    """Return *field_id* to the pool; the definition survives (DD-11).

    Drop prediction: ``StripCanvas._drop_would_mutate`` dry-runs this op on a
    trial layout — new guards added here are picked up automatically.
    """
    _take_slot(layout, field_id)


def move_field(layout: TemplateLayout, field_id: str, row_index: int) -> None:
    """Reorder: alias of place_field (remove + insert as full-width row)."""
    place_field(layout, field_id, row_index)


def pair_field(layout: TemplateLayout, field_id: str, row_index: int,
               side: str) -> None:
    """Pair *field_id* into rows[row_index] on *side* ("left" | "right").

    Dropping onto a single-slot row inserts on that side; dropping a row
    member onto its own two-slot row swaps sides only when the requested
    *side* differs from the member's current side — dropping on the SAME
    half is a no-op (spec DD-16).  Dropping a member onto its own
    single-slot row is also a no-op (avoids a data-lossy unplace).
    A row already holding two OTHER fields is left unchanged (the canvas
    shows a "full" cue instead).  The target row is captured BEFORE the
    dragged field's slot is removed, so index shifts from the removal
    cannot retarget the drop.

    Drop prediction: ``StripCanvas._drop_would_mutate`` dry-runs this op on a
    trial layout — new guards added here are picked up automatically.
    """
    if not (0 <= row_index < len(layout.rows)):
        return
    target = layout.rows[row_index]
    member_ids = [s.field_id for s in target]
    if field_id in member_ids:
        if len(target) == 1:
            # Own single-slot row — no-op.  Data-loss hardening (not a DD-16
            # rule): falling through would _take_slot the field and drop its
            # row, silently unplacing it.
            return
        # Two-slot row: only swap when requested side differs from current side
        idx = member_ids.index(field_id)
        current_side = "left" if idx == 0 else "right"
        if side == current_side:
            return                # own half — no-op (DD-16)
        target.reverse()          # swap sides
        return
    if len(target) >= 2:
        return                    # full — no-op
    if field_id not in layout.field_map():
        return
    slot = _take_slot(layout, field_id) or Slot(field_id)
    if target not in layout.rows:
        # target row vanished as a side-effect (defensive; single-slot rows
        # can't vanish by removing a DIFFERENT field, but keep the guard)
        return
    if side == "left":
        target.insert(0, slot)
    else:
        target.append(slot)


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
    """Resolved geometry (paper mm) consumed by renderer, editor, and canvas."""

    area_rect: QRectF
    strip_rect: QRectF
    cell_rects: list[QRectF]                    # flat, row-major
    cell_field_ids: list[str]                   # flat index → FieldDef.id
    cell_lines: list[list[str]]                 # resolved+wrapped text lines
    cell_label_rects: list["QRectF | None"]     # sub-rects (spec DD-15)
    cell_image_rects: list["QRectF | None"]
    cell_text_rects: list["QRectF | None"]
    cell_revision_rows: dict[int, list[dict]]
    row_spans: list[tuple[int, int]]            # per row: (first flat idx, n)
    warnings: list[str]
    row_layout_indices: list[int] = field(default_factory=list)
    # Per solved row: index of the originating row in layout.rows.
    # Solved row k → layout.rows[row_layout_indices[k]].
    # Used by zone_at to return DropZone.row_index as a layout.rows index.


def _cell_font(cell: FieldDef) -> QFont:
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


def _wrapped_height_mm(cell: FieldDef, text: str,
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


def solve_layout(layout: TemplateLayout, paper_w_mm: float,
                 paper_h_mm: float, values: dict) -> SolvedLayout:
    """Solve the parametric layout on one paper size (rev-3).

    Args:
        layout: The template layout to solve (rev-3: fields + rows).
        paper_w_mm: Paper width (mm).
        paper_h_mm: Paper height (mm).
        values: Resolved field values; key ``"__revisions__"`` optionally
            carries the sheet's revision list (oldest-first).

    Returns:
        A SolvedLayout with all rects in paper-mm coordinates.
        ``cell_revision_rows`` lists are **newest-first**; the input
        ``__revisions__`` list is oldest-first.  Warnings are emitted for
        four conditions: unknown token key in field text, dangling slot
        dropped (field_id not in layout.fields), image band with no room
        (band ≤ 0), and cells overflowing the strip bottom.
    """
    m, ms, sw = (layout.margin_edge_mm, layout.margin_strip_mm,
                 layout.strip_width_mm)
    warnings: list[str] = []
    strip_rect = QRectF(paper_w_mm - m - sw, m, sw, paper_h_mm - 2 * m)
    area_rect = QRectF(m, m, paper_w_mm - 2 * m - sw - ms, paper_h_mm - 2 * m)

    fmap = layout.field_map()

    cell_rects: list[QRectF] = []
    cell_field_ids: list[str] = []
    cell_lines: list[list[str]] = []
    cell_revision_rows: dict[int, list[dict]] = {}
    # Per-cell wrapped text height (mm) — used by the sub-rect pass after the
    # dynamic pass finalises rect heights.
    cell_text_h: list[float] = []

    # Per-row info for dynamic pass:
    #   (first_cell_idx, is_dynamic, solved_row_h, row_min_height_mm)
    row_info: list[tuple[int, bool, float, float]] = []
    row_spans: list[tuple[int, int]] = []
    row_layout_indices: list[int] = []   # solved row k → layout.rows index

    y = strip_rect.top()

    for layout_row_i, row in enumerate(layout.rows):
        # ── Filter dangling slots ──────────────────────────────────────────
        kept: list[tuple["Slot", FieldDef]] = []
        for slot in row:
            f = fmap.get(slot.field_id)
            if f is None:
                warnings.append(
                    f"Arrangement references a missing field "
                    f"('{slot.field_id}'); slot dropped.")
            else:
                kept.append((slot, f))
        if not kept:
            continue  # empty row after dropping dangling slots

        cw = strip_rect.width() / len(kept)
        heights: list[float] = []
        lines_group: list[list[str]] = []
        text_heights: list[float] = []
        # Per-kept-cell revision rows (newest-first), or None for non-tables —
        # computed ONCE here and reused by the placement loop below.
        rev_shown_group: list["list | None"] = []

        for slot, fdef in kept:
            # Token resolution (DD-13)
            resolved, unknown_keys = resolve_text(fdef.text, values)
            for key in unknown_keys:
                warnings.append(
                    f"Unknown field key '@[{key}]' in "
                    f"'{fdef.name or fdef.id}'.")

            h_text, lines = _wrapped_height_mm(
                fdef, resolved, cw - 2 * TB_CELL_PAD_MM)
            extra = TB_LABEL_ROW_MM if fdef.label else 0.0
            min_h = max(0.0, slot.min_height_mm)
            h = max(min_h, (h_text + extra + 2 * TB_CELL_PAD_MM)
                    if resolved else min_h)

            if fdef.kind == "revision_table":
                revs = list(values.get("__revisions__", []))
                shown = list(reversed(revs))[: fdef.revision_rows]
                h = max(min_h,
                        TB_LABEL_ROW_MM + (len(shown) + 1) * TB_REV_ROW_MM)
                rev_shown_group.append(shown)
            else:
                rev_shown_group.append(None)

            heights.append(h)
            lines_group.append(lines)
            text_heights.append(h_text)

        row_h = max(heights)
        row_dynamic = any(s.sizing == "dynamic" for s, _f in kept)
        row_min_h = max(max(0.0, s.min_height_mm) for s, _f in kept)
        first_cell_idx = len(cell_rects)
        row_info.append((first_cell_idx, row_dynamic, row_h, row_min_h))
        row_spans.append((first_cell_idx, len(kept)))
        row_layout_indices.append(layout_row_i)

        x = strip_rect.left()
        for ki, (slot, fdef) in enumerate(kept):
            flat_idx = first_cell_idx + ki
            cell_rects.append(QRectF(x, y, cw, row_h))
            cell_field_ids.append(fdef.id)
            cell_lines.append(lines_group[ki])
            cell_text_h.append(text_heights[ki])
            if rev_shown_group[ki] is not None:
                cell_revision_rows[flat_idx] = rev_shown_group[ki]
            x += cw
        y += row_h

    # ── Dynamic pass (DD-8b) ──────────────────────────────────────────────
    # After the static walk: distribute leftover strip height among dynamic rows.
    # Proportionality basis: row_min_height_mm (spec DD-8b §"Distribution rule").
    stack_bottom = y
    leftover = strip_rect.bottom() - stack_bottom
    if leftover > 1e-9:
        dyn_rows = [(row_i, row_min_h)
                    for row_i, (_, dyn, _rh, row_min_h) in enumerate(row_info)
                    if dyn]
        if dyn_rows:
            total_min = sum(mh for _, mh in dyn_rows)
            if total_min <= 0:
                share = leftover / len(dyn_rows)
                extras = {row_i: share for row_i, _ in dyn_rows}
            else:
                extras = {row_i: leftover * mh / total_min
                          for row_i, mh in dyn_rows}

            new_cell_rects: list[QRectF] = []
            new_y = strip_rect.top()
            for row_i, (first_cell_idx, row_dynamic, old_row_h, _) in enumerate(row_info):
                extra_h = extras.get(row_i, 0.0) if row_dynamic else 0.0
                new_row_h = old_row_h + extra_h
                n_cells = row_spans[row_i][1]
                row_cw = strip_rect.width() / n_cells
                x = strip_rect.left()
                for ci in range(first_cell_idx, first_cell_idx + n_cells):
                    new_cell_rects.append(QRectF(x, new_y, row_cw, new_row_h))
                    x += row_cw
                new_y += new_row_h
            cell_rects = new_cell_rects

    # ── Sub-rect pass (DD-15): label / image / text bands ────────────────
    # Runs AFTER dynamic pass so bands use final cell heights.
    cell_label_rects: list["QRectF | None"] = []
    cell_image_rects: list["QRectF | None"] = []
    cell_text_rects: list["QRectF | None"] = []

    for i, rect in enumerate(cell_rects):
        fid = cell_field_ids[i]
        f = fmap[fid]
        th = cell_text_h[i]

        # Inner padded rect
        inner = QRectF(
            rect.left() + TB_CELL_PAD_MM,
            rect.top() + TB_CELL_PAD_MM,
            rect.width() - 2 * TB_CELL_PAD_MM,
            rect.height() - 2 * TB_CELL_PAD_MM,
        )

        # Label band (top of inner)
        if f.label:
            lbl: "QRectF | None" = QRectF(
                inner.left(), inner.top(), inner.width(), TB_LABEL_ROW_MM)
        else:
            lbl = None
        cell_label_rects.append(lbl)

        top = inner.top() + (TB_LABEL_ROW_MM if f.label else 0.0)

        if f.image_data:
            # Image gets band between label and text; text anchors at bottom.
            txt: "QRectF | None" = (
                QRectF(inner.left(), inner.bottom() - th,
                       inner.width(), th)
                if th > 0 else None
            )
            band_bottom = inner.bottom() - th if th > 0 else inner.bottom()
            if band_bottom - top > 1e-6:
                img: "QRectF | None" = QRectF(
                    inner.left(), top, inner.width(), band_bottom - top)
            else:
                img = None
                warnings.append(
                    f"Image has no room in '{f.name or f.id}'.")
        else:
            img = None
            # No image: text is top-aligned (rev-2 parity)
            txt = (
                QRectF(inner.left(), top, inner.width(),
                       max(0.0, inner.bottom() - top))
                if th > 0 else None
            )

        cell_image_rects.append(img)
        cell_text_rects.append(txt)

    if cell_rects and cell_rects[-1].bottom() > strip_rect.bottom() + 1e-6:
        warnings.append(
            "Cells overflow the strip bottom and will be clipped.")

    return SolvedLayout(
        area_rect=area_rect,
        strip_rect=strip_rect,
        cell_rects=cell_rects,
        cell_field_ids=cell_field_ids,
        cell_lines=cell_lines,
        cell_label_rects=cell_label_rects,
        cell_image_rects=cell_image_rects,
        cell_text_rects=cell_text_rects,
        cell_revision_rows=cell_revision_rows,
        row_spans=row_spans,
        warnings=warnings,
        row_layout_indices=row_layout_indices,
    )


# ── Validation ───────────────────────────────────────────────────────────────

def validate(layout: TemplateLayout, paper_w_mm: float,
             paper_h_mm: float) -> list[str]:
    """Save-blocking validation floors (spec §Layout Solver, rev 3).

    Args:
        layout: The template layout to validate.
        paper_w_mm: Paper width (mm).
        paper_h_mm: Paper height (mm).

    Returns:
        List of error strings; empty list means valid.
    """
    errs: list[str] = []
    if layout.margin_edge_mm < 0 or layout.margin_strip_mm < 0:
        errs.append("Margins must be >= 0.")
    if layout.strip_width_mm < TB_STRIP_MIN_MM:
        errs.append(f"Strip width must be >= {TB_STRIP_MIN_MM:g} mm.")
    area_w = (paper_w_mm - 2 * layout.margin_edge_mm
              - layout.strip_width_mm - layout.margin_strip_mm)
    area_h = paper_h_mm - 2 * layout.margin_edge_mm
    if area_w < TB_AREA_MIN_MM or area_h < TB_AREA_MIN_MM:
        errs.append(f"Drawing area must be >= {TB_AREA_MIN_MM:g} mm "
                    "in each dimension.")
    # Fillet check against the actual rect for each frame, not the paper dims.
    strip_h = paper_h_mm - 2 * layout.margin_edge_mm
    strip_w = layout.strip_width_mm
    if (layout.area_border.corner == "fillet"
            and layout.area_border.fillet_radius_mm > min(area_w, area_h) / 2):
        errs.append("Fillet radius too large for the drawing area rect.")
    if (layout.strip_border.corner == "fillet"
            and layout.strip_border.fillet_radius_mm
            > min(strip_w, strip_h) / 2):
        errs.append("Fillet radius too large for the info-strip rect.")
    # ── Rev-3 row/field floors ────────────────────────────────────────────
    if not layout.rows:
        errs.append("Template needs at least one placed field.")
    fmap = layout.field_map()
    for row in layout.rows:
        if len(row) > 2:
            errs.append("A row can hold at most two fields.")
            break
    for row in layout.rows:
        for slot in row:
            if slot.field_id not in fmap:
                errs.append(
                    "Arrangement references a missing field "
                    f"('{slot.field_id}').")
                break
        else:
            continue
        break
    for f in layout.fields:
        if f.cap_height_mm <= 0:
            errs.append("Field cap height must be > 0.")
            break
    for row in layout.rows:
        for slot in row:
            if slot.min_height_mm < 0:
                errs.append("Cell minimum height must be >= 0.")
                break
        else:
            continue
        break
    # Min-stack check: sum of per-row max-slot minimums must fit strip height
    strip_height = paper_h_mm - 2 * layout.margin_edge_mm
    min_total = 0.0
    for row in layout.rows:
        row_min = 0.0
        for slot in row:
            f = fmap.get(slot.field_id)
            cell_min = max(0.0, slot.min_height_mm)
            if f is not None and f.kind == "revision_table":
                cell_min = max(cell_min,
                               TB_LABEL_ROW_MM + (f.revision_rows + 1)
                               * TB_REV_ROW_MM)
            row_min = max(row_min, cell_min)
        min_total += row_min
    if min_total > strip_height:
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
DEFAULT_SEED_MODIFIED = "2026-07-23"

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


def _fdef(name: str, text: str, label: str, *, cap: float = 2.6,
          fill: str = "", image: str = "") -> FieldDef:
    """Shorthand FieldDef factory for the seeded default's field cells."""
    return FieldDef(id=new_field_id(), name=name, label=label, text=text,
                    cap_height_mm=cap, fill_color=fill, image_data=image)


def make_default_template() -> TitleBlockTemplate:
    """Seeded default: arrangement A 'Corporate top-down' (rev-3 native).

    Single ANSI D landscape template; stamp is dynamic (fills to strip
    bottom).
    """
    logo = FieldDef(id=new_field_id(), name="Logo")
    company = _fdef("Company", "@[Company]", "Company", fill=_ACCENT_FILL)
    project = _fdef("Project", "@[Project]", "Project")
    address = _fdef("Address", "@[Address]", "Address")
    title = _fdef("Sheet Title", "@[Title]", "Sheet Title", cap=3.2)
    scale = _fdef("Scale", "@[Scale]", "Scale")
    date = _fdef("Date", "@[Date]", "Date")
    drawn = _fdef("Drawn", "@[Drawn By]", "Drawn")
    checked = _fdef("Checked", "@[Checked By]", "Checked")
    dwg_no = _fdef("Drawing No", "@[Drawing No]", "Drawing No", cap=4.0,
                   fill=_ACCENT_FILL)
    rev = _fdef("Rev", "@[Rev]", "Rev", cap=4.0)
    revtable = FieldDef(id=new_field_id(), kind="revision_table",
                        name="Revision Table", label="Revisions")
    stamp = FieldDef(id=new_field_id(), name="Stamp")
    layout = TemplateLayout(
        strip_width_mm=90.0,
        fields=[logo, company, project, address, title, scale, date,
                drawn, checked, dwg_no, rev, revtable, stamp],
        rows=[
            [Slot(logo.id, 25.0)],
            [Slot(company.id, 12.0)],
            [Slot(project.id, 12.0)],
            [Slot(address.id, 10.0)],
            [Slot(title.id, 14.0)],
            [Slot(scale.id, 10.0), Slot(date.id, 10.0)],
            [Slot(drawn.id, 10.0), Slot(checked.id, 10.0)],
            [Slot(dwg_no.id, 14.0), Slot(rev.id, 14.0)],
            [Slot(revtable.id, 25.0)],
            [Slot(stamp.id, 60.0, sizing="dynamic")],
        ],
    )
    return TitleBlockTemplate(name="FirePro Default", uuid=str(_uuid.uuid4()),
                              modified=DEFAULT_SEED_MODIFIED,
                              paper_size="ANSI D", orientation="landscape",
                              layout=layout)
