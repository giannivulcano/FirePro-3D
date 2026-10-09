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
    """The kind's message noun with its indefinite article.

    Args:
        kind: A :data:`CAPABILITY_KINDS` kind.

    Returns:
        ``"a pattern"`` / ``"a linetype"`` / ``"an end type"``.
    """
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


# ── picker source (hatch D-A36/D-A37, LT3-12, LT5 Q10) ──────────────────────

def capability_choices(flag, folder_fn, registry=None, exclude=(), *,
                       fixed=(), valid=None, include_folder=True,
                       reserved=None):
    """``[(label, ref)]`` for a capability picker -- the one source behind
    the pattern, linetype and end pickers.

    *fixed* first, then the project's blocks carrying *flag* (and passing
    *valid*) by name, then *folder_fn()*'s blocks not already in the project.
    Labels are unique: a name colliding with an earlier label gets
    `` (project)`` / `` (library)`` (then `` (project 2)`` ...), so every ref
    is reachable by label. UI paths only -- never paint.

    Args:
        flag: ``"tile"`` / ``"repeat"`` / ``"end"`` (the definition attribute).
        folder_fn: Zero-arg callable -> ``[(name, block_id, path)]`` (a
            ``capability_folder.scan``), looked up by the caller at call time.
        registry: Project block registry, or None (fixed + folder only).
        exclude: Block ids to leave out (``hatch_patterns.picker_exclude``).
        fixed: Leading ``(label, ref)`` pairs (Continuous / None).
        valid: Optional extra predicate on a project definition.
        include_folder: Append the folder blocks.
        reserved: Optional predicate on a block's label: True when it reads
            as a keyword label of this picker (``"None"``, ``"By Linetype
            (...)"``); such a block is offered as ``"<name> (block)"`` so it
            stays pickable.

    Returns:
        The ``(label, ref)`` pairs in picker order.
    """
    from .hatch_patterns import _unique
    out = list(fixed)
    used = {label for label, _ in out}

    def _name(name):
        return f"{name} (block)" if reserved is not None and reserved(name) else name
    if registry is not None:
        project = []
        for bid in registry.ids():
            if bid in exclude:
                continue
            d = registry.get(bid)
            if (d is not None and getattr(d, flag, None)
                    and (valid is None or valid(d))):
                project.append((d.name or bid, bid))
        for name, bid in sorted(project, key=lambda x: x[0].lower()):
            out.append((_unique(_name(name), used, "project"), bid))
    if include_folder:
        for name, bid, _path in folder_fn():
            if bid in exclude or (registry is not None
                                  and registry.get(bid) is not None):
                continue
            out.append((_unique(_name(name or bid), used, "library"), bid))
    return out


def ensure_capability_available(ref, scene, folder_fn, *, keywords=()) -> bool:
    """Load a folder block into the project before its id is stored.

    A keyword, an id already in the project registry, or a ref no folder
    holds needs nothing. The load targets the PROJECT scene (a Block Editor
    scene's ``_block_registry_owner``) as one undoable batch via
    ``blocks_browser.ensure_block_loaded``.

    Args:
        ref: The picked ref (a block id or a keyword).
        scene: The scene the picked value lives in (plan or Block Editor).
        folder_fn: Zero-arg callable -> ``[(name, block_id, path)]``.
        keywords: Refs that are never block ids (nothing to load).

    Returns:
        False only when *ref* is a folder block that failed to load (the
        caller must not keep it); True otherwise.
    """
    if not ref or ref in keywords or scene is None:
        return True
    project = getattr(scene, "_block_registry_owner", None) or scene
    reg = getattr(project, "block_registry", None)
    if reg is None or reg.get(ref) is not None:
        return True
    for name, bid, path in folder_fn():
        if bid == ref:
            from .blocks_browser import ensure_block_loaded
            return ensure_block_loaded(project, bid, path, name)
    return True


def _folder_ends() -> list:
    """``[(name, block_id, path)]`` -- the ``end`` blocks of the End Types
    folder (``capability_folder.scan``: folder + two levels, mtime cache)."""
    from .app_data import end_types_dir
    from .capability_folder import scan
    return scan(end_types_dir(), "end")


def end_choices(registry=None, exclude=()) -> list:
    """The Start End / Finish End picker rows (LT5 Q10).

    None, the project's end types by name, then End Types folder ends not yet
    loaded. The By Linetype row is the caller's (its label shows the
    resolved default).

    Args:
        registry: Project block registry, or None (None + folder only).
        exclude: Block ids to leave out (``hatch_patterns.picker_exclude``).

    Returns:
        ``[(label, ref)]`` with unique labels (see :func:`capability_choices`).
    """
    from .stroke_style import (END_NONE_LABEL, MISSING_END_PREFIX, NONE,
                               end_from_label)
    return capability_choices(
        "end", _folder_ends, registry, exclude,
        fixed=((END_NONE_LABEL, NONE),),
        reserved=lambda v: (end_from_label(v) is not None
                            or v.startswith(MISSING_END_PREFIX)))


def end_ref_from_value(value, registry=None, exclude=()) -> str | None:
    """The stored end value a picked label stands for (LT5 Q10 / Q13).

    Args:
        value: The picked label ("None", "By Linetype (...)", a block name).
        registry: Project block registry, or None.
        exclude: Block ids the picker left out.

    Returns:
        ``none`` / ``by_linetype`` / an end block id, or None for an unknown
        or ``Missing: ...`` label (the caller then changes nothing).
    """
    from .stroke_style import end_from_label
    v = str(value)
    # Picker labels first (None + blocks; a keyword-like block name is
    # suffixed there), then the By Linetype head.
    ref = next((r for label, r in end_choices(registry, exclude)
                if label == v), None)
    return ref if ref is not None else end_from_label(v)


def ensure_end_available(ref, scene) -> bool:
    """Load an End Types folder end into the project before its id is stored.

    Args:
        ref: The picked end value (an id or an end keyword).
        scene: The scene the picked line lives in (plan or Block Editor).

    Returns:
        False only when *ref* is a folder end that failed to load (the
        caller must not keep it); True otherwise.
    """
    from .stroke_style import END_KEYWORDS
    return ensure_capability_available(ref, scene, _folder_ends,
                                       keywords=END_KEYWORDS)
