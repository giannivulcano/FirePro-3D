"""Block attribute schema and @[key] field resolution (SB1a, design S1/S3).

No Qt use of its own; it imports ``titleblock_template`` for the token
grammar, which pulls in PyQt6 (tests still run headless). The token
grammar and substitution are the title-block template's (``titleblock_template.resolve_text`` / ``TOKEN_RE``); this
module adds the attribute record, kind formatting (A8) and the three-source
resolution (instance value / override / host provider).
"""
from __future__ import annotations

from dataclasses import dataclass

from .element_params import HostValue
from .titleblock_template import TOKEN_RE, resolve_text

ATTR_TYPES = ("text", "number")
ATTR_SOURCES = ("instance", "host")
_TEXT_TYPE = "text"


def normalise_attr(rec: dict) -> dict:
    """A full attribute record from a possibly sparse one.

    Args:
        rec: Any mapping with at least a non-empty ``key``.

    Returns:
        ``{key, label, type, source, host_key, default, prefix, suffix,
        precision, placeholder}`` with defaults filled (label = key,
        type text, source instance, placeholder "?").

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
    return {
        "key": key,
        "label": str(rec.get("label") or key),
        "type": typ,
        "source": src,
        "host_key": str(rec.get("host_key", "")),
        "default": "" if rec.get("default") is None else str(rec.get("default")),
        "prefix": str(rec.get("prefix", "")),
        "suffix": str(rec.get("suffix", "")),
        "precision": max(0, int(rec.get("precision", 0) or 0)),
        "placeholder": str(rec.get("placeholder", "?")),
    }


def format_value(rec: dict, raw) -> str:
    """The display string of *raw* for attribute *rec* (A8).

    ``None`` / ``""`` -> ``placeholder``. ``type: number`` -> plain decimal
    with ``precision`` digits; a non-numeric value -> ``placeholder``.
    The prefix / suffix wrap a real value, never the placeholder. A host
    value (element-parameters.md E8) prints its unit-formatted ``text`` for
    a text attribute and its display-unit ``number`` for a number attribute.
    """
    if isinstance(raw, HostValue):
        if raw.raw is None:
            return rec.get("placeholder", "?")
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
    override_args: tuple = (None, None)


# align / valign -> the fraction of the box width / height at which the
# alignment anchor sits: the point an auto-sized box keeps when it re-fits.
_ANCHOR_X = {"L": 0.0, "C": 0.5, "R": 1.0}
_ANCHOR_Y = {"T": 0.0, "M": 0.5, "B": 1.0}


def hugged_text_item(text_item_cls, rec: dict):
    """A text item for a bound record whose box hugs the resolved value.

    An author sizes a bound text's box (``wrap_width_mm`` / ``box_height_mm``)
    round the ``@[Field]`` placeholder, so a wider value would wrap and a
    shorter one would sit in a loose box. Both are dropped (0 = auto-fit) and
    the auto box is re-anchored where the authored box's alignment point sat
    (its centre for a centred tag), so the box follows the value without
    moving off its host (SB3 visual gate, 2026-10-29). An axis authored
    auto-fit (0) is left where it is; a record auto-fit on both axes is built
    as-is.
    """
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtGui import QTransform
    w_mm = float(rec.get("wrap_width_mm") or 0.0)
    h_mm = float(rec.get("box_height_mm") or 0.0)
    if w_mm <= 0 and h_mm <= 0:
        return text_item_cls.from_dict(rec)
    hug = text_item_cls.from_dict({**rec, "wrap_width_mm": 0.0, "box_height_mm": 0.0})
    s = hug.scale() or 1.0
    hb = hug._box_rect_local()                       # the auto box, local unscaled
    ab = QRectF(0.0, 0.0, w_mm / s if w_mm > 0 else hb.width(),
                h_mm / s if h_mm > 0 else hb.height())   # the authored box, same frame
    fx = _ANCHOR_X.get(str(rec.get("align", "L")), 0.0)
    fy = _ANCHOR_Y.get(str(rec.get("valign", "T")), 0.0)

    def _anchor(r):
        """The alignment point of box *r*, rotated the way the item bakes its
        angle: about the box's own centre (``_rotation_transform``)."""
        p = QPointF(r.left() + fx * r.width(), r.top() + fy * r.height())
        o = r.center()
        m = QTransform()
        m.translate(o.x(), o.y())
        m.rotate(-hug._angle)
        m.translate(-o.x(), -o.y())
        return m.map(p)

    delta = _anchor(ab) - _anchor(hb)                # local, rotated frame
    hug.setPos(hug.pos() + hug.mapToParent(delta) - hug.mapToParent(QPointF(0.0, 0.0)))
    return hug


def bound_text_ops(defn, attributes: dict, host_values: dict | None, mirrored: bool,
                   scale: float, ov_args, cache):
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
            scale, override).

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
    key = (strings, bool(mirrored), float(f"{scale:.9g}"), ov_args)
    if cache is not None and cache[0] is bps and cache[1] == key:
        return cache[2], cache
    from PyQt6.QtGui import QTransform
    from .block_definition import _local_path, text_box_ops
    from .block_pose import pose_matrix
    from .render_op import TEXT, RenderOp, apply_overrides
    from .text_item import TextItem
    sm = pose_matrix(0.0, 0.0, 0.0, bool(mirrored), scale)
    out = []
    for b, s in zip(bps, strings):
        rec = dict(b.prim)
        rec["text"] = s
        item = hugged_text_item(TextItem, rec)
        path = item.mapToParent(_local_path(item))
        centre = item.grip_points()[8]
        op = RenderOp(TEXT, path, colour=item.data.color,
                      text_frame=(centre.x(), centre.y(), float(item._angle)),
                      readable=bool(rec.get("keep_upright", False)))
        t = b.transform * sm
        under, over = text_box_ops(item, QTransform())
        out += [o.mapped(t) for o in under]
        out.append(op.mapped(t))
        # A nested record's override reaches its child's border (WM-6).
        out += apply_overrides([o.mapped(t) for o in over], *b.override_args)
    if ov_args is not None:
        out = apply_overrides(out, *ov_args)    # box borders (WM-12)
    return out, (bps, key, out)
