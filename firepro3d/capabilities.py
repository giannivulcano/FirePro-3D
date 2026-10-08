"""Block capability table (linetypes.md D-L12, LT5 Q12; hatch D-A9).

A block is at most one of a pattern tile (``tile``), a linetype
(``repeat``) or an end type (``end``): one Block Editor slot, mutually
exclusive. This table is the one home for each kind's noun, place refusal,
library flag, browser badge and toggle label; the place / drag / paste
refusals, the toggle exclusivity, the commit and symbol-refusal wording, the
library index, ``capability_folder.FLAGS`` and the Blocks browser read it
instead of keeping their own tile / repeat branches.
"""
from __future__ import annotations

from typing import NamedTuple

from .block_library import END_REASON, LINETYPE_REASON, PATTERN_REASON


class Cap(NamedTuple):
    """One capability kind's row.

    Attributes:
        noun: Message noun ("pattern" / "linetype" / "end type").
        place_reason: Status text refusing a symbol placement.
        flag: The ``BlockDefinition`` attribute / library index key.
        badge_name: ``blocks_browser`` badge key.
        label: Toggle name ("Pattern tile" / "Linetype" / "End type").
    """

    noun: str
    place_reason: str
    flag: str
    badge_name: str
    label: str


#: Capability kinds in their fixed precedence order.
CAPABILITY_KINDS = ("tile", "repeat", "end")

CAP_INFO = {
    "tile": Cap("pattern", PATTERN_REASON, "tile", "pattern", "Pattern tile"),
    "repeat": Cap("linetype", LINETYPE_REASON, "repeat", "linetype", "Linetype"),
    "end": Cap("end type", END_REASON, "end", "end", "End type"),
}


def kind_of(obj) -> str | None:
    """The capability kind of a definition or a library index entry.

    Args:
        obj: A ``BlockDefinition`` (attributes), a ``list_library`` /
            ``index.json`` entry (dict keys), or None.

    Returns:
        ``"tile"`` / ``"repeat"`` / ``"end"`` (first truthy in
        :data:`CAPABILITY_KINDS` order), or None for a plain block.
    """
    if obj is None:
        return None
    if isinstance(obj, dict):
        get = obj.get
    else:
        def get(key):
            return getattr(obj, key, None)
    for kind in CAPABILITY_KINDS:
        if get(CAP_INFO[kind].flag):
            return kind
    return None


def capability_place_reason(defn) -> str | None:
    """Why *defn* can't be placed as a symbol, or None (D-A34 / LT3-2 / LT5 Q12)."""
    kind = kind_of(defn)
    return CAP_INFO[kind].place_reason if kind else None


def with_article(kind: str) -> str:
    """``"a pattern"`` / ``"a linetype"`` / ``"an end type"``."""
    noun = CAP_INFO[kind].noun
    return ("an " if noun[:1] in "aeiou" else "a ") + noun


def exclusive_message(current: str, wanted: str) -> str:
    """Toggle refusal while another capability is on (LT4-11b, LT5 Q12).

    Args:
        current: The kind that is on.
        wanted: The kind the user tried to turn on.

    Returns:
        ``Turn <current label> off first — a block is <a x> or <a y>, not
        both`` with the two kinds in :data:`CAPABILITY_KINDS` order.
    """
    a, b = sorted((current, wanted), key=CAPABILITY_KINDS.index)
    return (f"Turn {CAP_INFO[current].label} off first — a block is "
            f"{with_article(a)} or {with_article(b)}, not both")
