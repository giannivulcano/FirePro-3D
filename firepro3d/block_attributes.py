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
        override_args: The WM2 ``override_args`` tuple in force (unused by
            text today; carried for parity with ``_nested_ops``).
    """
    prim: dict
    transform: object
    override_args: tuple = (None, None)
