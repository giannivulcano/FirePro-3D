"""Stroke style record for 2D primitives (linetypes.md LT2, concept LD1).

The record is the single source of truth for a primitive's linetype, weight,
ends and authored colour; the item's QPen is a render cache derived at paint
(H-c). Legacy dicts (``"color"`` + px ``"lineweight"``) migrate on load to
Continuous / By Linetype weight / By Linetype ends with the px dropped
(D-L17a; WM-9: no By Block -- a legacy ``by_block`` migrates in
``normalize_style``).
"""
from __future__ import annotations

import copy
from typing import NamedTuple

from . import paper_display as _pd

CONTINUOUS = "continuous"      # reserved keyword, never a block id (LT2-1)
BY_BLOCK = "by_block"          # legacy input only -- migrated by normalize_style (WM-9)
BY_LINETYPE = "by_linetype"
AS_AUTHORED = "as_authored"    # placement / nested-record override: keep (WM2)
BY_CATEGORY = "by_category"    # placement weight: the "Blocks" category (WM-3)
AS_AUTHORED_LABEL = "As Authored"
BY_CATEGORY_LABEL = "By Category"
_KEYWORDS = (BY_BLOCK, BY_LINETYPE, AS_AUTHORED, BY_CATEGORY)
ENDS = ("start", "finish")

# Primitive types that carry a style record (LT2-1). Text keeps border_weight;
# reference lines keep their fixed reference style; nested records get their
# slot in LT5.
STYLED_TYPES = frozenset({
    "polyline", "draw_line", "draw_rectangle", "draw_circle", "arc",
    "polygon", "draw_ellipse", "draw_spline",
})


def default_style(colour: str = "#ffffff") -> dict:
    """A fresh Continuous / By Linetype record with By Linetype ends (WM-10)."""
    return {
        "linetype": CONTINUOUS,
        "weight": BY_LINETYPE,
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
    if end == BY_BLOCK:                          # WM-9 migration
        end = BY_LINETYPE
    return {"end": str(end), "visible": bool(d.get("visible", True))}


def normalize_style(d: dict | None) -> dict:
    """A complete, deep-copied record from *d* (missing fields defaulted).

    Weight names are canonicalised through the rename alias map (H-g).
    Legacy ``by_block`` migrates here (WM-9): weight -> By Linetype, linetype
    -> Continuous, ends -> By Linetype -- output is unchanged because By
    Linetype on Continuous resolves exactly as By Block did.
    """
    d = d if isinstance(d, dict) else {}
    weight = d.get("weight") or BY_LINETYPE
    if weight == BY_BLOCK:
        weight = BY_LINETYPE
    if weight != BY_LINETYPE:
        weight = _pd.canonical_weight_name(str(weight))
    linetype = str(d.get("linetype") or CONTINUOUS)
    if linetype == BY_BLOCK:
        linetype = CONTINUOUS
    return {
        "linetype": linetype,
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
    """True for a by-name weight reference (a non-empty string that is no
    keyword) -- the refs a rename must follow (LT2-8, WM2)."""
    return isinstance(w, str) and bool(w) and w not in _KEYWORDS


def linetype_block(ref, registry):
    """The registry block *ref* names when it is a linetype (has a ``repeat``
    record, malformed or not), else None -- the LT3-10 "missing" test shared
    by ``resolve_stroke`` and the badge bounds (``linetype_ref_missing``)."""
    d = registry.get(ref) if registry is not None else None
    return d if d is not None and getattr(d, "repeat", None) else None


def linetype_ref_missing(ref, registry) -> bool:
    """True when *ref* is a linetype id that does not resolve to a linetype
    block in *registry* -- the stroke draws Continuous + the badge (LT3-10)."""
    return is_linetype_ref(ref) and linetype_block(ref, registry) is None


def is_linetype_ref(lt) -> bool:
    """True for a linetype block-id reference (a non-empty string that is not
    ``continuous`` / ``by_block`` / a keyword) -- the values the LT3-8
    cascade resolves through the registry (and that can go missing, LT3-10)."""
    return (isinstance(lt, str) and bool(lt)
            and lt not in (CONTINUOUS, BY_BLOCK, AS_AUTHORED, BY_CATEGORY))


def canvas_weight_name(weight: str) -> str:
    """The named weight a canvas stroke resolves to (LT2-4).

    By Linetype with no dash weight (WM-5; a legacy un-migrated By Block
    too) and a placement By Category (WM-3) map to the Display Manager Model
    "Blocks" weight.
    """
    if weight in (BY_BLOCK, BY_LINETYPE, BY_CATEGORY):
        return _pd.model_blocks_weight()
    return weight


def canvas_px(weight: str) -> float:
    """Cosmetic canvas width for a style weight (MW H-MW-c mapping)."""
    return _pd.canvas_px_for_weight(canvas_weight_name(weight))


class ResolvedStroke(NamedTuple):
    """Result of the LT3-8 cascade."""
    lt: object | None          # linetype_render.LinetypeDef or None (solid)
    weight: str                # named weight or "by_linetype"
    missing_id: str | None     # unresolvable linetype id (badge, LT3-10)


def resolve_stroke(style: dict, registry) -> ResolvedStroke:
    """Resolve *style* against the project *registry* (linetypes.md LT3-8).

    Linetype: ``continuous`` draws solid (a legacy ``by_block`` is migrated
    before it gets here, WM-9); a block id
    resolves to its ``LinetypeDef`` (malformed -> solid, no badge) or reports
    ``missing_id`` -- also for an id naming a block that is not a linetype
    (no ``repeat``; ``linetype_block``). Weight: ``by_linetype`` takes the linetype's dash weight
    when it has one; otherwise the weight is returned unchanged (callers map
    By Linetype to the surface category as in LT2).
    """
    ref = style.get("linetype") or CONTINUOUS
    weight = style.get("weight") or BY_LINETYPE
    lt, missing = None, None
    if ref not in (CONTINUOUS, BY_BLOCK):
        d = linetype_block(ref, registry)
        if d is None:
            missing = ref
        else:
            from .linetype_render import LinetypeDef
            lt = LinetypeDef.from_block(d)
    if weight == BY_LINETYPE and lt is not None and lt.dash_weight:
        weight = lt.dash_weight
    return ResolvedStroke(lt, weight, missing)


# -- WM1: resolved weight labels -------------------------------------------

BY_LINETYPE_LABEL = "By Linetype"


def weight_label(weight: str, linetype: str, registry) -> str:
    """Panel label for a style weight (WM-3 "resolved value shown").

    A named weight is its own label; By Linetype shows what it resolves to:
    the effective linetype's dash weight, else the Model "Blocks" weight
    (WM-5 fallback) -- e.g. ``"By Linetype (Light)"``.
    """
    if weight != BY_LINETYPE:
        return weight
    rs = resolve_stroke({"linetype": linetype, "weight": BY_LINETYPE}, registry)
    # MW-6: label the row the weight draws as (a legacy name shows its row).
    name = _pd.picker_weight_name(
        rs.weight if rs.weight != BY_LINETYPE else _pd.model_blocks_weight())
    return f"{BY_LINETYPE_LABEL} ({name})"


def weight_from_label(label) -> str:
    """The style weight a panel label stands for (inverse of ``weight_label``)."""
    v = str(label)
    return BY_LINETYPE if v.startswith(BY_LINETYPE_LABEL) else v


# -- WM2: placement / nested-record overrides ------------------------------

def normalize_overrides(d) -> dict:
    """A complete ``{"weight", "linetype"}`` override record (WM2 H1).

    Missing / empty -> As Authored; a named weight is canonicalised through
    the rename aliases (legacy factory names keep resolving by mm at paint,
    MW-6); a linetype value is kept verbatim (``continuous`` or an id).
    """
    d = d if isinstance(d, dict) else {}
    w = str(d.get("weight") or AS_AUTHORED)
    if w not in (AS_AUTHORED, BY_CATEGORY):
        w = _pd.canonical_weight_name(w)
    lt = str(d.get("linetype") or AS_AUTHORED)
    return {"weight": w, "linetype": lt}


def is_as_authored(ov) -> bool:
    """True when *ov* overrides nothing (omitted from saved records)."""
    ov = normalize_overrides(ov)
    return ov["weight"] == AS_AUTHORED and ov["linetype"] == AS_AUTHORED


def override_args(ov) -> tuple:
    """``(weight | None, linetype | None)`` for ``render_op.apply_overrides``."""
    ov = normalize_overrides(ov)
    return (None if ov["weight"] == AS_AUTHORED else ov["weight"],
            None if ov["linetype"] == AS_AUTHORED else ov["linetype"])


def override_refs(ov) -> tuple[set, set]:
    """``(named weights, linetype ids)`` an override references (WM2 H4)."""
    ov = normalize_overrides(ov)
    w = {ov["weight"]} if is_named_weight(ov["weight"]) else set()
    lt = {ov["linetype"]} if is_linetype_ref(ov["linetype"]) else set()
    return w, lt


def compose_overrides(outer, inner) -> dict:
    """Per axis: *outer*'s value when it overrides, else *inner*'s (Q7)."""
    o, i = normalize_overrides(outer), normalize_overrides(inner)
    return {k: (o[k] if o[k] != AS_AUTHORED else i[k]) for k in o}


# -- WM1: the current Linetype / Weight for new primitives (WM-10) ----------

_FACTORY_CURRENT = {"linetype": CONTINUOUS, "weight": BY_LINETYPE}
_current: dict = dict(_FACTORY_CURRENT)
_KEY_LT = "template/geometry/linetype"
_KEY_W = "template/geometry/weight"


def current_style() -> dict:
    """A copy of the current ``{"linetype", "weight"}`` for the next primitive."""
    return dict(_current)


def set_current(*, linetype: str | None = None, weight: str | None = None) -> None:
    """Set the current linetype and/or weight (WM-10; a template pick)."""
    if linetype is not None:
        _current["linetype"] = CONTINUOUS if linetype == BY_BLOCK else str(linetype)
    if weight is not None:
        w = BY_LINETYPE if weight == BY_BLOCK else str(weight)
        _current["weight"] = (w if w == BY_LINETYPE
                              else _pd.canonical_weight_name(w))


def reset_current() -> None:
    """Back to the factory current (Continuous · By Linetype)."""
    _current.clear()
    _current.update(_FACTORY_CURRENT)


def current_to_settings(settings) -> None:
    """Persist the current (property-panel.md §3.7 template persistence)."""
    settings.setValue(_KEY_LT, _current["linetype"])
    settings.setValue(_KEY_W, _current["weight"])


def current_from_settings(settings) -> None:
    """Restore the current; a factory weight name the table lacks -> its
    nearest row by mm (MW-6); any other unknown name -> By Linetype."""
    reset_current()
    lt = settings.value(_KEY_LT, None)
    w = settings.value(_KEY_W, None)
    if lt:
        set_current(linetype=str(lt))
    if w:
        w = str(w)
        if w in (BY_LINETYPE, BY_BLOCK):
            set_current(weight=w)
        else:
            # MW-6: a factory name the table lacks -> its nearest row by mm.
            live = _pd.live_weight_name(w)
            if live is not None:
                set_current(weight=live)


def apply_current(item, scene) -> None:
    """Stamp the current onto a just-drawn primitive (draw-tool commits only).

    A linetype id that is not a linetype in *scene*'s project registry draws
    Continuous; a factory weight name this project lacks becomes its nearest
    row by mm (MW-6), any other unknown name By Linetype.
    """
    st = getattr(item, "style", None)
    if st is None:
        return
    lt = _current["linetype"]
    if is_linetype_ref(lt):
        reg = getattr(scene, "block_registry", None)
        if linetype_block(lt, reg) is None:
            lt = CONTINUOUS
    w = _current["weight"]
    if w != BY_LINETYPE:
        # MW-6: a factory name the table lacks -> its nearest row by mm.
        w = _pd.live_weight_name(w) or BY_LINETYPE
    if getattr(scene, "block_repeat", None) is not None:
        # LT4-4: inside a linetype unit every stroke is Continuous and a new
        # dash takes the linetype's Weight (the current is not changed).
        from .linetype_authoring import pattern_weight
        lt = CONTINUOUS
        w = pattern_weight(scene) or w
    st["linetype"] = lt
    st["weight"] = w
    sync = getattr(item, "_sync_stroke_pen", None)
    if callable(sync):
        sync()
