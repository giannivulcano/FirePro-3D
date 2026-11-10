"""Block attribute schema and @[key] field resolution (SB1a, design S1/S3).

No Qt use of its own; it imports ``titleblock_template`` for the token
grammar, which pulls in PyQt6 (tests still run headless). The token
grammar and substitution are the title-block template's (``titleblock_template.resolve_text`` / ``TOKEN_RE``); this
module adds the attribute record, kind formatting (A8) and the three-source
resolution (instance value / override / host provider).
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .constants import DISPLAY_PRECISION_MAX
from .element_params import HostValue
from .scale_manager import DisplayUnit
from .titleblock_template import TOKEN_RE, resolve_text

ATTR_TYPES = ("text", "number")
ATTR_SOURCES = ("instance", "host")
_TEXT_TYPE = "text"
_UNIT_VALUES = frozenset(u.value for u in DisplayUnit)


def _whole(value):
    """*value* as an int when it is a whole number -- an int, an integral
    float or an ASCII digit string with an optional sign -- else None. A
    malformed precision is dropped, never raised (design D8, AC8)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        s = value.strip()
        body = s[1:] if s[:1] in ("+", "-") else s
        return int(s) if body.isascii() and body.isdigit() else None
    return None


def normalise_attr(rec: dict) -> dict:
    """A full attribute record from a possibly sparse one.

    Args:
        rec: Any mapping with at least a non-empty ``key``.

    Returns:
        ``{key, label, type, source, host_key, default, prefix, suffix,
        precision, placeholder}`` with defaults filled (label = key,
        type text, source instance, placeholder "?"; a precision that is
        not a whole number reads 0, a negative one 0), plus the optional D8
        override keys ``unit`` (a ``DisplayUnit`` value) and
        ``display_precision`` (0-5, clamped), kept only when valid -- absent
        = "Per project settings".

    Raises:
        ValueError: Empty key, or an unknown ``type`` / ``source``.
    """
    key = str(rec.get("key", "")).strip()
    if not key:
        raise ValueError("attribute key must not be empty")
    typ = str(rec.get("type", "text"))
    if typ not in ATTR_TYPES:
        raise ValueError(f"unknown attribute type {typ!r}")
    src = str(rec.get("source", "instance"))
    if src not in ATTR_SOURCES:
        raise ValueError(f"unknown attribute source {src!r}")
    prec = _whole(rec.get("precision", 0))
    out = {
        "key": key,
        "label": str(rec.get("label") or key),
        "type": typ,
        "source": src,
        "host_key": str(rec.get("host_key", "")),
        "default": "" if rec.get("default") is None else str(rec.get("default")),
        "prefix": str(rec.get("prefix", "")),
        "suffix": str(rec.get("suffix", "")),
        "precision": 0 if prec is None else max(0, prec),
        "placeholder": str(rec.get("placeholder", "?")),
    }
    # D8 override, sparse: absent = "Per project settings"; a bad value is dropped.
    unit = rec.get("unit")
    if isinstance(unit, str) and unit in _UNIT_VALUES:
        out["unit"] = unit
    dp = _whole(rec.get("display_precision"))
    if dp is not None:
        out["display_precision"] = max(0, min(DISPLAY_PRECISION_MAX, dp))
    return out


# Kinds a definition's Unit / Precision override reaches (D8, G7): area and
# volume follow the length family; hydraulic kinds take a precision only.
OVERRIDE_UNIT_KINDS = ("length", "area", "volume")
OVERRIDE_PRECISION_KINDS = OVERRIDE_UNIT_KINDS + ("pressure", "flow", "velocity")


def _overridden(rec: dict, hv: HostValue) -> HostValue:
    """*hv* re-pointed at a ``ScaleManager.with_overrides`` clone carrying
    the record's ``unit`` / ``display_precision`` (D8), each only for a kind
    it reaches; *hv* itself when nothing applies (= per project settings).
    A ``number`` attribute takes the unit only: it prints at its own
    ``precision`` (A8)."""
    unit = (rec.get("unit") or None) if hv.kind in OVERRIDE_UNIT_KINDS else None
    prec = (rec.get("display_precision")
            if hv.kind in OVERRIDE_PRECISION_KINDS and rec.get("type") != "number" else None)
    if unit is None and prec is None:
        return hv
    return replace(hv, sm=hv._sm().with_overrides(unit=unit, precision=prec))


def format_value(rec: dict, raw) -> str:
    """The display string of *raw* for attribute *rec* (A8).

    ``None`` / ``""`` -> ``placeholder``. ``type: number`` -> plain decimal
    with ``precision`` digits; a non-numeric value -> ``placeholder``.
    The prefix / suffix wrap a real value, never the placeholder. A host
    value (element-parameters.md E8) prints its unit-formatted ``text`` for
    a text attribute and its display-unit ``number`` for a number attribute,
    through the record's Unit / Precision override when it has one (D8).
    """
    if isinstance(raw, HostValue):
        if raw.raw is None:
            return rec.get("placeholder", "?")
        raw = _overridden(rec, raw)
        if rec.get("type") == "number":
            if raw.number is None:
                return rec.get("placeholder", "?")
            body = f"{raw.number:.{int(rec.get('precision', 0))}f}"
        else:
            body = raw.text
        return f"{rec.get('prefix', '')}{body}{rec.get('suffix', '')}"
    if raw is None or raw == "":
        return rec.get("placeholder", "?")
    if rec.get("type") == "number":
        try:
            num = float(raw)
        except (TypeError, ValueError):
            return rec.get("placeholder", "?")
        body = f"{num:.{int(rec.get('precision', 0))}f}"
    else:
        body = str(raw)
    return f"{rec.get('prefix', '')}{body}{rec.get('suffix', '')}"


def resolve_values(attrs: list, instance_values: dict,
                   host_values: dict | None) -> dict[str, str]:
    """Resolve every attribute to its display string (design S3).

    Host source: the instance value when the key is present (the override,
    D4), else the provider's ``host_key`` value, else None. Instance source:
    the instance value, else ``default``.
    """
    out: dict[str, str] = {}
    for rec in attrs:
        key = rec["key"]
        if rec.get("source") == "host":
            if key in instance_values:
                raw = instance_values[key]
            elif host_values is not None and rec.get("host_key") in host_values:
                raw = host_values[rec["host_key"]]
            else:
                raw = None
        else:
            raw = instance_values.get(key, rec.get("default", ""))
        out[key] = format_value(rec, raw)
    return out


def has_fields(text: str) -> bool:
    """True when *text* holds at least one ``@[key]`` token."""
    return bool(text) and TOKEN_RE.search(text) is not None


def field_keys(text: str) -> list[str]:
    """The ``@[key]`` keys in *text*, in order (duplicates kept)."""
    return [m.group(1) for m in TOKEN_RE.finditer(text or "")]


def resolve_fields(text: str, values: dict) -> tuple[str, list[str]]:
    """``resolve_text`` by another name: (resolved, unknown keys)."""
    return resolve_text(text, values)


def references_of(prims: list, key: str) -> list[int]:
    """Indices of the text prims whose text references ``@[key]``."""
    tok = f"@[{key}]"
    return [i for i, p in enumerate(prims)
            if p.get("type") == _TEXT_TYPE and tok in str(p.get("text", ""))]


def rename_keys_in_string(text: str, mapping: dict) -> str:
    """Rewrite ``@[old]`` to ``@[mapping[old]]`` in one pass over the token
    grammar, so a chain ``{A: B, B: C}`` or a swap ``{A: B, B: A}`` never
    re-renames an already-renamed token (A7)."""
    return TOKEN_RE.sub(
        lambda m: f"@[{mapping.get(m.group(1), m.group(1))}]", text)


def rename_keys_in_texts(prims: list, mapping: dict) -> int:
    """Apply *mapping* (old key -> new key) to every text prim in place, in
    one pass per prim (A7). Returns the number of prims changed."""
    n = 0
    for p in prims:
        if p.get("type") != _TEXT_TYPE:
            continue
        old = str(p.get("text", ""))
        new = rename_keys_in_string(old, mapping)
        if new != old:
            p["text"] = new
            n += 1
    return n


def rename_key_in_texts(prims: list, old: str, new: str) -> int:
    """Rewrite every ``@[old]`` to ``@[new]`` in place (A7). Returns the
    number of prims changed."""
    return rename_keys_in_texts(prims, {old: new})


def unknown_tokens(prims: list, attrs: list) -> list[str]:
    """Keys referenced by text prims that no attribute declares (AC9),
    first-appearance order, deduped."""
    known = {r["key"] for r in attrs}
    out: list[str] = []
    for p in prims:
        if p.get("type") != _TEXT_TYPE:
            continue
        for m in TOKEN_RE.finditer(str(p.get("text", ""))):
            k = m.group(1)
            if k not in known and k not in out:
                out.append(k)
    return out


def blank_keys(attrs: list, instance_values: dict, host_values: dict | None) -> frozenset:
    """Host-sourced attribute keys whose raw value is None (no instance
    override, no host value or a None one) -- 'empty' for Hide when empty."""
    out = set()
    for rec in attrs:
        if rec.get("source") != "host" or rec["key"] in instance_values:
            continue
        hv = (host_values or {}).get(rec.get("host_key"))
        if hv is None or getattr(hv, "raw", hv) is None:
            out.add(rec["key"])
    return frozenset(out)


def collapse_shifts(boxes: list) -> list:
    """Hide-when-empty layout (SB4a D7). *boxes*: ``(top, bottom, dropped)``
    in definition-local y, origin 0. Returns per box None (dropped) or the y
    shift toward the origin: each kept box beyond a dropped one on the same
    side of the origin (by centre) moves in by that box's slot -- its near
    edge to the near edge of the next box beyond it. A box centred on the
    origin closes nothing."""
    def side(b):
        c = (b[0] + b[1]) / 2.0
        return 0 if abs(c) < 1e-9 else (1 if c > 0 else -1)

    def near(b, s):
        return b[0] if s > 0 else -b[1]           # distance-like, grows away

    out = []
    for b in boxes:
        if b[2]:
            out.append(None)
            continue
        s = side(b)
        shift = 0.0
        if s:
            for d in boxes:
                if not d[2] or side(d) != s or near(d, s) >= near(b, s):
                    continue
                beyond = [near(o, s) for o in boxes
                          if o is not d and side(o) == s and near(o, s) > near(d, s)]
                if beyond:
                    shift += min(beyond) - near(d, s)
        out.append(-s * shift)
    return out


def hide_empty_shifts(entries: list, blank: frozenset) -> list:
    """Per ``(prim, transform)`` entry: None when the prim is dropped (Hide
    when empty, every field blank), else its y shift (SB4a D6/D7) -- the one
    rule ``bound_text_ops`` draws and ``block_explode`` explodes by.

    The boxes are each prim's authored box (round its placeholder) mapped
    through its definition-local transform; they are built only when
    something drops, so the common case costs a set test per prim."""
    drop = []
    for prim, _t in entries:
        keys = field_keys(str(prim.get("text", "")))
        drop.append(bool(prim.get("hide_empty")) and bool(keys) and set(keys) <= blank)
    if not any(drop):
        return [0.0] * len(entries)
    from .text_item import TextItem
    boxes = []
    for (prim, t), dropped in zip(entries, drop):
        # The AUTHORED box (Shrink off), not the hug round the placeholder.
        item = TextItem.from_dict({**prim, "shrink": False})
        r = t.mapRect(item.mapToParent(item._box_rect_local()).boundingRect())
        boxes.append((r.top(), r.bottom(), dropped))
    return collapse_shifts(boxes)


@dataclass(frozen=True)
class BoundPrim:
    """One text primitive kept out of the shared static op list (design S2).

    Attributes:
        prim: The text record (definition-local, un-shifted).
        transform: Definition-local transform applied after the prim's own
            pose -- the origin shift for a direct child, composed with the
            nested record poses for a nested one (a ``QTransform``; typed
            loosely to keep this module Qt-free).
        override_args: The WM2 ``override_args`` tuple in force -- applied to
            the text box's border (linetypes WM-12), as ``_nested_ops`` does.
    """
    prim: dict
    transform: object
    override_args: tuple = (None, None, None)


def hugged_text_record(rec: dict, value: str | None = None) -> dict:
    """*rec* (a text record carrying ``@[Field]``s) with its Wrap / Shrink to
    fit flags made explicit, and its text *value* when given: the record
    every path drawing or exploding bound text builds from.

    A bound text's absent flags default to the seeded hug (text-sizing G12:
    Shrink ON + Wrap OFF -- the SB3 U4 ruling, 2026-10-29), which
    ``TextItem`` lays out round the value keeping the authored box's
    alignment point (D5). They are written explicitly here because the
    substituted value no longer carries the ``@[Field]`` that seeds them.
    Static text (no fields, ``keep_upright`` included) comes back unchanged.
    """
    from .text_item import TextAnnotationData
    if not has_fields(str(rec.get("text", ""))):
        return rec
    data = TextAnnotationData.from_dict(rec)
    out = {**rec, "wrap": data.wrap_on(bound=True), "shrink": data.shrink_on(bound=True),
           "line_box_middle": True}
    if value is not None:
        out["text"] = value
    return out


def bound_text_ops(defn, attributes: dict, host_values: dict | None, mirrored: bool,
                   scale: float, ov_args, cache, patch: dict | None = None):
    """The per-placement bound text ops of *defn* (SB1a design S2; lifted from
    ``BlockInstance._bound_ops`` for the SB3 ``BoundLabelItem`` -- one
    implementation).

    One TEXT op per ``BoundPrim`` (its box fill before and border after,
    ``text_box_ops``), text resolved through ``resolve_values`` from
    *attributes* (instance values / host overrides) and *host_values*, glyphs
    built by ``TextItem`` + ``_local_path``, mapped through the prim's
    definition-local transform then the (mirror, scale) pose part, the
    placement override *ov_args* applied to the borders (WM-12). The upright
    turn (A5) is applied at paint via ``readable``.

    Args:
        defn: The ``BlockDefinition`` (None -> no ops).
        attributes: The placement's attribute values / host overrides.
        host_values: ``{host_key: HostValue}`` or None (placeholders).
        mirrored: The pose mirror flag.
        scale: The variant scale (pose scale x annotative k).
        ov_args: ``stroke_style.override_args`` tuple or None.
        cache: The caller's last ``(bound prim list, key, ops)`` triple or
            None. Memoised on (prim list identity, resolved strings, mirror,
            scale, override, patch).
        patch: A Note's per-placement text fields (box size, leader; design
            D8), merged into every text record. With a patch hugging is
            skipped -- the box is authored per placement. None for every
            ordinary placement.

    Returns:
        ``(ops, cache)`` -- *cache* is the same object as the argument on a
        hit, a new triple on a rebuild, None when the definition has no bound
        prims.
    """
    if defn is None:
        return [], None
    bps = defn.bound_prims()
    if not bps:
        return [], None
    values = resolve_values(defn.effective_attributes(), attributes, host_values)
    strings = tuple(resolve_fields(str(b.prim.get("text", "")), values)[0] for b in bps)
    blank = blank_keys(defn.effective_attributes(), attributes, host_values)
    key = (strings, blank, bool(mirrored), float(f"{scale:.9g}"), ov_args,
           repr(sorted(patch.items())) if patch else None)
    if cache is not None and cache[0] is bps and cache[1] == key:
        return cache[2], cache
    from PyQt6.QtGui import QTransform
    from .block_definition import _local_path, text_box_ops
    from .block_pose import pose_matrix
    from .render_op import TEXT, RenderOp, apply_overrides
    from .text_item import TextItem
    sm = pose_matrix(0.0, 0.0, 0.0, bool(mirrored), scale)
    shifts = hide_empty_shifts([(b.prim, b.transform) for b in bps], blank)
    out = []
    for b, s, dy in zip(bps, strings, shifts):
        if dy is None:
            continue                                 # Hide when empty (D6): glyphs, border, fill
        rec = dict(hugged_text_record(b.prim, s)) if patch is None else dict(b.prim)
        rec["text"] = s                              # hug round the value, then bind it
        if patch:
            rec.update(patch)                        # design D8: the box is authored per placement
        item = TextItem.from_dict(rec)
        path = item.mapToParent(_local_path(item))
        centre = item.grip_points()[8]
        op = RenderOp(TEXT, path, colour=item.data.color,
                      text_frame=(centre.x(), centre.y(), float(item._angle)),
                      readable=bool(rec.get("keep_upright", False)))
        t = b.transform * QTransform.fromTranslate(0.0, dy) * sm
        under, over = text_box_ops(item, QTransform())
        # A nested record's override reaches its child's glyphs and border
        # (WM-6; WM3: the Colour axis recolours both). The box fill rides
        # along but keeps its colour (keep_colour, R3).
        out += apply_overrides([*(o.mapped(t) for o in under), op.mapped(t),
                                *(o.mapped(t) for o in over)], *b.override_args)
    if ov_args is not None:
        out = apply_overrides(out, *ov_args)    # box borders (WM-12)
    return out, (bps, key, out)
