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
import math
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
NONE = "none"                  # end keyword: no end block (LT5 Q3)
END_KEYWORDS = (BY_LINETYPE, NONE)   # end-slot keywords (never block ids)
END_SCALE_SUFFIX = "×"       # the Scale row's suffix (ET1 Q10-b)


def parse_end_scale(value) -> float | None:
    """A per-end Scale entry (``"2"``, ``"1.5 ×"``, ``"2×"``, ``"2x"``, a
    number) -> a float within [END_SCALE_MIN, END_SCALE_MAX], else None (the
    panel refresh shows the old value). Only a trailing suffix is stripped,
    so ``"0x5"`` / ``"x2x"`` are refused."""
    from .constants import END_SCALE_MAX, END_SCALE_MIN
    if isinstance(value, bool):
        return None
    s = str(value).strip().rstrip(END_SCALE_SUFFIX + "xX").strip()
    try:
        k = float(s)
    except ValueError:
        return None
    if not math.isfinite(k) or k < END_SCALE_MIN or k > END_SCALE_MAX:
        return None
    return k


MODEL_SCALE_BY_END_TYPE = "By End Type"   # a line end's Model scale head (Q12b)
MODEL_SCALE_PROJECT = "Project"           # an end type's Model scale head (Q12c)


def model_scale_value(v) -> float | None:
    """A stored Model scale denominator (ET1 Q12e: 30.0 = 1:30) -> a finite
    float within [END_MODEL_SCALE_MIN, END_MODEL_SCALE_MAX], else None
    (absent, a bool, non-numeric, non-finite or out of range = not set)."""
    from .constants import END_MODEL_SCALE_MAX, END_MODEL_SCALE_MIN
    if v is None or isinstance(v, bool):
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(n) or n < END_MODEL_SCALE_MIN or n > END_MODEL_SCALE_MAX:
        return None
    return n


def model_scale_from_label(label) -> float | None:
    """A Model scale pick (a ``paper_space.SCALE_PRESETS`` label, or any
    scale ``paper_space.scale_to_float`` reads) -> its denominator N
    (``1 / ratio``, rounded to 6 places so 1:30 stores 30.0), else None
    (unparseable or out of range -- refused)."""
    from .paper_space import scale_to_float
    try:
        ratio = scale_to_float(str(label))
    except (ValueError, ZeroDivisionError):
        return None
    if not (ratio > 0.0) or not math.isfinite(ratio):
        return None
    return model_scale_value(round(1.0 / ratio, 6))


def model_scale_label(n) -> str:
    """The scale label of denominator *n* (``paper_space.float_to_scale_str``:
    a preset label when one matches, else ``"1:N"``)."""
    from .paper_space import float_to_scale_str
    return float_to_scale_str(1.0 / float(n))


def model_scale_options() -> list:
    """The Model scale list: every ``paper_space.SCALE_PRESETS`` label."""
    from .paper_space import SCALE_PRESETS
    return [label for label, _ in SCALE_PRESETS]


def project_scale_label(drawing_scale) -> str:
    """``"Project 1:100"`` for the scene's *drawing_scale* (a denominator),
    or ``"Project"`` when there is none (no scene)."""
    n = model_scale_value(drawing_scale)
    return (f"{MODEL_SCALE_PROJECT} {model_scale_label(n)}" if n is not None
            else MODEL_SCALE_PROJECT)

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


def _end_scale(rec) -> float:
    """The per-end Scale stored on end record *rec* (ET1 Q5): a finite float
    within [END_SCALE_MIN, END_SCALE_MAX] (the UI range), else 1.0 -- absent,
    a bool, non-numeric, non-finite or out of range."""
    from .constants import END_SCALE_MAX, END_SCALE_MIN
    sc = rec.get("scale") if isinstance(rec, dict) else None
    if sc is None or isinstance(sc, bool):
        return 1.0
    try:
        sc = float(sc)
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(sc) or sc < END_SCALE_MIN or sc > END_SCALE_MAX:
        return 1.0
    return sc


def _end(d) -> dict:
    """A complete end record ``{"end", "visible"[, "mirrored"][, "scale"]
    [, "model_scale"]}`` (LT5 Q9 / ET1 Q5 / Q12e: ``mirrored`` is written
    only when true, ``scale`` only when ``_end_scale`` reads a value != 1,
    ``model_scale`` only when ``model_scale_value`` reads one -- absent = By
    End Type -- so default records and every pre-ET1 golden stay
    byte-identical)."""
    d = d if isinstance(d, dict) else {}
    end = d.get("end") or BY_LINETYPE
    if end == BY_BLOCK:                          # WM-9 migration
        end = BY_LINETYPE
    out = {"end": str(end), "visible": bool(d.get("visible", True))}
    if d.get("mirrored"):
        out["mirrored"] = True
    sc = _end_scale(d)
    if sc != 1.0:
        out["scale"] = sc
    n = model_scale_value(d.get("model_scale"))
    if n is not None:
        out["model_scale"] = n
    return out


normalize_end = _end     # public name for callers outside this module (ET1)


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
        new[end].pop("scale", None)         # ET1: a fresh end drops its Scale
        new[end].pop("model_scale", None)   # ... and its Model scale (Q12e)
    dst.style = new
    sync = getattr(dst, "_sync_stroke_pen", None)
    if callable(sync):
        sync()


def toggle_mirrored(style) -> None:
    """Flip both ends' ``mirrored`` flag in place (LT5 Q9: a reflection
    mirrors asymmetric ends). Written only when true -- toggling off drops
    the key. No-op for an unstyled item (``style`` None)."""
    if not isinstance(style, dict):
        return
    for end in ENDS:
        rec = style.get(end)
        if not isinstance(rec, dict):
            continue
        if rec.get("mirrored"):
            rec.pop("mirrored", None)
        else:
            rec["mirrored"] = True


def is_named_weight(w) -> bool:
    """True for a by-name weight reference (a non-empty string that is no
    keyword) -- the refs a rename must follow (LT2-8, WM2)."""
    return isinstance(w, str) and bool(w) and w not in _KEYWORDS


def linetype_block(ref, registry):
    """The registry block *ref* names when it is a linetype (has a ``repeat``
    record, malformed or not), else None -- the LT3-10 "missing" test shared
    by ``resolve_stroke`` and the badge bounds (``linetype_ref_missing``)."""
    d = registry.get(ref) if registry is not None else None
    if d is None:
        return None
    lt = getattr(d, "is_linetype", None)      # copy-free (hot: paint / bounds)
    return d if (lt if lt is not None else getattr(d, "repeat", None)) else None


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


# -- LT5: end types ---------------------------------------------------------

class ResolvedEnd(NamedTuple):
    """One stroke end after the LT5 cascade (design A; ET1 adds scale and
    the Model scale override)."""
    defn: object | None        # the end BlockDefinition, or None (no end)
    missing_id: str | None     # unresolvable / non-end id (badge, Q13)
    mirrored: bool             # draw flipped across the stroke axis (Q9)
    scale: float = 1.0         # the line's per-end Scale (ET1 Q5)
    model_scale: float | None = None   # the line's Model scale override N (Q12b)


NO_ENDS = (ResolvedEnd(None, None, False, 1.0),) * 2


def is_end_ref(e) -> bool:
    """True for an end block-id reference (a non-empty string that is no end
    keyword and not the legacy ``by_block``) -- the values an end slot
    resolves through the registry (and that can go missing, Q13)."""
    return (isinstance(e, str) and bool(e)
            and e not in END_KEYWORDS and e != BY_BLOCK)


def clear_explicit_ends(style) -> bool:
    """Reset *style*'s explicit end ids to By Linetype, in place (LT5).

    ``visible`` and ``mirrored`` are kept; ``none`` / By Linetype are left
    alone. Used where an end can never draw: a stroke that became closed
    (user ruling 2026-10-08) and the content of an end type, linetype unit
    or pattern tile (Q8 / seam I3), so the id stops counting as a use.

    Args:
        style: A style record (anything else is a no-op).

    Returns:
        True if any end changed.
    """
    if not isinstance(style, dict):
        return False
    changed = False
    for w in ENDS:
        rec = style.get(w)
        if isinstance(rec, dict) and is_end_ref(rec.get("end")):
            style[w] = {**rec, "end": BY_LINETYPE}
            changed = True
    return changed


def has_explicit_ends(style) -> bool:
    """True when *style* names an end block id at either end (LT5)."""
    return isinstance(style, dict) and any(
        isinstance(style.get(w), dict) and is_end_ref(style[w].get("end"))
        for w in ENDS)


def end_block(ref, registry):
    """The registry block *ref* names when it has an ``end`` capability,
    else None (absent, a linetype / pattern / plain block -> "missing")."""
    d = registry.get(ref) if registry is not None and is_end_ref(ref) else None
    if d is None:
        return None
    e = getattr(d, "is_end", None)            # copy-free (hot: paint / bounds)
    return d if (e if e is not None else getattr(d, "end", None)) else None


def _resolve_end(rec, default, registry) -> ResolvedEnd:
    rec = rec if isinstance(rec, dict) else {}
    m = bool(rec.get("mirrored"))
    k = _end_scale(rec)
    n = model_scale_value(rec.get("model_scale"))
    if not rec.get("visible", True):
        return ResolvedEnd(None, None, m, k, n)    # Visible off = None (Q10)
    ref = rec.get("end") or BY_LINETYPE
    if ref in (BY_LINETYPE, BY_BLOCK):
        ref = default                              # the linetype default (Q11)
    if not is_end_ref(ref):
        return ResolvedEnd(None, None, m, k, n)    # None / no default
    d = end_block(ref, registry)
    return (ResolvedEnd(d, None, m, k, n) if d is not None
            else ResolvedEnd(None, ref, m, k, n))


def resolve_ends(style: dict, lt, registry) -> tuple:
    """``(start, finish)`` ``ResolvedEnd`` for *style* (LT5 design A).

    Visible off -> no end; By Linetype -> *lt*'s ``start_end`` /
    ``finish_end`` (None for no linetype / no default: today's stroke, Q3);
    ``none`` -> no end; an id -> its end block, or ``missing_id`` when it
    does not name an end block in *registry*. ``mirrored`` is carried as
    stored. *lt* is a ``linetype_render.LinetypeDef`` or None.
    """
    st = style if isinstance(style, dict) else {}
    return (_resolve_end(st.get("start"), getattr(lt, "start_end", None), registry),
            _resolve_end(st.get("finish"), getattr(lt, "finish_end", None), registry))


def has_ends(ends) -> bool:
    """True when either resolved end draws something (a block or a badge)."""
    return any(e.defn is not None or e.missing_id for e in ends)


def open_stroke(item) -> bool:
    """True when *item* is a styled stroke with two free ends (LT5 Q2).

    The item's own closed predicate decides: open Line, Polyline (closed
    flag off -- a coincident-but-open one too), Arc (span < 360) and Spline;
    Rect / Circle / Ellipse / Polygon (no ``is_closed`` -> closed) never.
    """
    if getattr(item, "style", None) is None:
        return False
    f = getattr(item, "is_closed", None)
    return callable(f) and not f()


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


# -- LT5: end labels (Start End / Finish End rows) --------------------------

END_NONE_LABEL = "None"          # the explicit "no end type" pick (LT5 Q3)
MISSING_END_PREFIX = "Missing: "  # unresolvable end ref label (LT5 Q13)


def _end_name(ref, registry) -> str:
    """An end ref's picker name, or ``Missing: <name|id>`` (non-end / gone)."""
    e = end_block(ref, registry)
    if e is not None:
        return e.name or ref
    d = registry.get(ref) if registry is not None else None
    return MISSING_END_PREFIX + (getattr(d, "name", "") or str(ref))


def end_label(end, linetype, registry, which: str = "start") -> str:
    """Panel label for a stored end value (LT5 Q10).

    ``"None"``; By Linetype shows what it resolves to through *linetype*'s
    default for *which* end -- ``"By Linetype (Arrow)"`` / ``"By Linetype
    (None)"``; an end id its block name, or ``"Missing: <name|id>"``.
    UI paths only (reads the copying ``repeat`` property).

    Args:
        end: The stored end value (an id, ``none`` or ``by_linetype``).
        linetype: The item's effective linetype value.
        registry: The project block registry (or None).
        which: ``"start"`` / ``"finish"`` -- the linetype default shown.
    """
    if end == NONE:
        return END_NONE_LABEL
    if not is_end_ref(end):
        d = linetype_block(linetype, registry) if is_linetype_ref(linetype) else None
        ends = ((d.repeat or {}).get("ends") or {}) if d is not None else {}
        ref = ends.get(which)
        shown = _end_name(ref, registry) if is_end_ref(ref) else END_NONE_LABEL
        return f"{BY_LINETYPE_LABEL} ({shown})"
    return _end_name(end, registry)


def end_from_label(label) -> str | None:
    """The keyword a fixed end label stands for (None / By Linetype), else None
    (block names map through ``capabilities.end_ref_from_value``)."""
    v = str(label)
    if v == END_NONE_LABEL:
        return NONE
    if v == BY_LINETYPE_LABEL or v.startswith(BY_LINETYPE_LABEL + " ("):
        return BY_LINETYPE
    return None


# -- WM2: placement / nested-record overrides ------------------------------

def normalize_overrides(d, canonical: bool = True) -> dict:
    """A complete ``{"weight", "linetype"}`` override record (WM2 H1).

    Missing / blank / non-string / foreign keyword -> As Authored; a named weight is canonicalised through
    the rename aliases (legacy factory names keep resolving by mm at paint,
    MW-6); a linetype value is kept verbatim (``continuous`` or an id).

    Args:
        d: The raw override dict (anything else reads As Authored).
        canonical: False keeps a named weight raw -- the Display Manager
            Cancel replay writes a pre-rename name while its alias is live.
    """
    d = d if isinstance(d, dict) else {}
    w = d.get("weight")
    w = w.strip() if isinstance(w, str) else ""
    if not w or w in (BY_BLOCK, BY_LINETYPE, CONTINUOUS):
        w = AS_AUTHORED
    elif canonical and w != AS_AUTHORED and w != BY_CATEGORY:
        w = _pd.canonical_weight_name(w)
    lt = d.get("linetype")
    lt = lt.strip() if isinstance(lt, str) else ""
    if not lt or lt in (BY_BLOCK, BY_LINETYPE, BY_CATEGORY):
        lt = AS_AUTHORED
    return {"weight": w, "linetype": lt}


def is_as_authored(ov) -> bool:
    """True when *ov* overrides nothing (omitted from saved records)."""
    ov = normalize_overrides(ov)
    return ov["weight"] == AS_AUTHORED and ov["linetype"] == AS_AUTHORED


def override_args(ov, canonical: bool = True) -> tuple:
    """``(weight | None, linetype | None)`` for ``render_op.apply_overrides``
    (*canonical* as in :func:`normalize_overrides`)."""
    ov = normalize_overrides(ov, canonical)
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
    elif getattr(scene, "block_end", None) is not None:
        lt = CONTINUOUS          # LT5 Q8: end content is Continuous (current kept)
    st["linetype"] = lt
    st["weight"] = w
    sync = getattr(item, "_sync_stroke_pen", None)
    if callable(sync):
        sync()
