"""HF1 load migration (D-A20): legacy default colours -> ``token:auto``.

Payload-level, before any ``from_dict``: project files below version 11 and
``.fpdb`` files without the ``colour_tokens`` marker. An explicit hex in a
v11+ / marked file is never touched (hatch-and-fill.md § HF1 build design).
"""
from __future__ import annotations

from .constants import COLOUR_TOKENS_MARK, TOKEN_AUTO
from .stroke_style import STYLED_TYPES

TOKENS_SAVE_VERSION = 11
_WHITE = "#ffffff"
_BLACK = "#000000"
_TEXT_TYPE = "text"     # block_definition._PRIMITIVE_FACTORY key of TextItem
# Prim types whose flat (style-less) ``color`` key is a legacy default colour:
# pre-LT2 strokes, block text and legacy reference lines. Nested
# ``block_instance`` records carry no ``color`` and are left alone.
_FLAT_COLOUR_TYPES = STYLED_TYPES | {_TEXT_TYPE, "reference_line"}


def _is(value, hexc: str) -> bool:
    return isinstance(value, str) and value.strip().lower() == hexc


def _migrate_prim(p) -> None:
    if not isinstance(p, dict):
        return
    st = p.get("style")
    if isinstance(st, dict):
        if _is(st.get("colour"), _WHITE):
            st["colour"] = TOKEN_AUTO
    elif p.get("type") in _FLAT_COLOUR_TYPES and _is(p.get("color"), _WHITE):
        p["color"] = TOKEN_AUTO                # pre-LT2 stroke or block text


def migrate_definition_dict(d) -> None:
    """Convert one block-definition dict's default-white prims in place."""
    if isinstance(d, dict):
        for p in d.get("primitives", []) or []:
            _migrate_prim(p)


def migrate_project_payload(payload: dict) -> None:
    """In place: a < v11 project's block prims, paper annotation text and
    "2D Geometry" display colour become Automatic."""
    if int(payload.get("version", 1) or 1) >= TOKENS_SAVE_VERSION:
        return
    for d in (payload.get("block_definitions") or {}).values():
        migrate_definition_dict(d)
    for sheet in payload.get("sheets") or []:
        for a in (sheet or {}).get("annotations") or []:
            if isinstance(a, dict) and _is(a.get("color"), _BLACK):
                a["color"] = TOKEN_AUTO
    geo = (payload.get("display_settings") or {}).get("2D Geometry")
    if isinstance(geo, dict) and _is(geo.get("color"), _WHITE):
        geo["color"] = TOKEN_AUTO


def migrate_fpdb_dict(data: dict) -> None:
    """In place: an un-marked ``.fpdb`` (and every bundled nested
    definition) converts; a marked one is left alone."""
    if not isinstance(data, dict) or data.get(COLOUR_TOKENS_MARK):
        return
    migrate_definition_dict(data)
    for v in (data.get("bundled") or {}).values():
        migrate_definition_dict(v)
