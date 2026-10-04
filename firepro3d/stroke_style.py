"""Stroke style record for 2D primitives (linetypes.md LT2, concept LD1).

The record is the single source of truth for a primitive's linetype, weight,
ends and authored colour; the item's QPen is a render cache derived at paint
(H-c). Legacy dicts (``"color"`` + px ``"lineweight"``) migrate on load to
Continuous / By Block / By Linetype ends with the px dropped (D-L17a).
"""
from __future__ import annotations

import copy

CONTINUOUS = "continuous"      # reserved keyword, never a block id (LT2-1)
BY_BLOCK = "by_block"
BY_LINETYPE = "by_linetype"
ENDS = ("start", "finish")

# Primitive types that carry a style record (LT2-1). Text keeps border_weight;
# reference lines keep their fixed reference style; nested records get their
# slot in LT5.
STYLED_TYPES = frozenset({
    "polyline", "draw_line", "draw_rectangle", "draw_circle", "arc",
    "polygon", "draw_ellipse", "draw_spline",
})


def default_style(colour: str = "#ffffff") -> dict:
    """A fresh Continuous / By Block record with By Linetype ends."""
    return {
        "linetype": CONTINUOUS,
        "weight": BY_BLOCK,
        "start": {"end": BY_LINETYPE, "visible": True},
        "finish": {"end": BY_LINETYPE, "visible": True},
        "colour": _hex(colour),
    }


def _hex(colour) -> str:
    """Lower-case ``#rrggbb`` for a str / QColor (fallback white)."""
    name = getattr(colour, "name", None)
    if callable(name):
        colour = name()
    s = str(colour or "#ffffff").strip().lower()
    return s if s.startswith("#") else "#ffffff"


def _end(d) -> dict:
    d = d if isinstance(d, dict) else {}
    end = d.get("end") or BY_LINETYPE
    return {"end": str(end), "visible": bool(d.get("visible", True))}


def normalize_style(d: dict | None) -> dict:
    """A complete, deep-copied record from *d* (missing fields defaulted).

    Weight names are canonicalised through the rename alias map (H-g).
    """
    from .paper_display import canonical_weight_name
    d = d if isinstance(d, dict) else {}
    weight = d.get("weight") or BY_BLOCK
    if weight not in (BY_BLOCK, BY_LINETYPE):
        weight = canonical_weight_name(str(weight))
    return {
        "linetype": str(d.get("linetype") or CONTINUOUS),
        "weight": weight,
        "start": _end(d.get("start")),
        "finish": _end(d.get("finish")),
        "colour": _hex(d.get("colour")),
    }


def migrate_primitive(rec: dict) -> dict:
    """Return *rec* migrated to the LT2 record (a new dict; input untouched).

    Non-styled records (text, reference lines, nested blocks, unknown) are
    returned unchanged. A styled record without ``style`` takes its legacy
    ``"color"`` and drops ``"lineweight"`` (D-L17a); one with ``style`` is
    normalised (canonical weight names).
    """
    if not isinstance(rec, dict) or rec.get("type") not in STYLED_TYPES:
        return rec
    out = copy.deepcopy(rec)
    legacy_colour = out.pop("color", None)
    out.pop("lineweight", None)
    if "style" in out:
        out["style"] = normalize_style(out["style"])
    else:
        out["style"] = default_style(legacy_colour or "#ffffff")
    return out


def copy_style(src, dst, *, fresh_ends=()) -> None:
    """Copy *src*'s style record onto *dst* (deep), resetting *fresh_ends*.

    The one style-preserving copy for derive paths that build a new item from
    geometry (LT2-3). No-op when either side is unstyled (Text, ReferenceLine).
    """
    st = getattr(src, "style", None)
    if st is None or getattr(dst, "style", None) is None:
        return
    new = normalize_style(st)
    for end in fresh_ends:
        new[end]["end"] = BY_LINETYPE
    dst.style = new
    sync = getattr(dst, "_sync_stroke_pen", None)
    if callable(sync):
        sync()


def is_named_weight(w) -> bool:
    """True for a by-name weight reference (a non-empty string that is not
    ``by_block`` / ``by_linetype``) -- the refs a rename must follow (LT2-8)."""
    return isinstance(w, str) and bool(w) and w not in (BY_BLOCK, BY_LINETYPE)


def canvas_weight_name(weight: str) -> str:
    """The named weight a canvas stroke resolves to (LT2-4).

    By Block and, in LT2, By Linetype (Continuous has no weight) map to the
    Display Manager Model "Blocks" weight.
    """
    from .paper_display import model_blocks_weight
    if weight in (BY_BLOCK, BY_LINETYPE):
        return model_blocks_weight()
    return weight


def canvas_px(weight: str) -> float:
    """Cosmetic canvas width for a style weight (LT1-7 mapping)."""
    from .paper_display import canvas_weight_px, resolve_line_weight_mm
    return canvas_weight_px(resolve_line_weight_mm(canvas_weight_name(weight)))
