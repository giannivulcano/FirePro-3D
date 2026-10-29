"""annotation_choices.py -- the one list of blocks that may draw a category's
intrinsic label (SB3b AC3; system-blocks.md section 7).

Feeds Project Settings > Annotation (``settings.panes.AnnotationPane``) and the
Room panel's Tag row (``room.Room._tag_row``): eligible project blocks
("(Project)" / "(System)" when the embedded block's library is System), eligible
shipped blocks the project has not embedded ("(System)"), eligible user-library
files not embedded ("(Library)" -- picked, the Room row embeds them through
``blocks_browser.ensure_block_loaded``; the pane's resolver embeds outside
history), then, when *current* is none of these, one "(missing)" /
"(not eligible)" entry so a kept id is still shown (SB3 Q6). Eligibility is
``bound_label.eligible_definition``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from . import block_library
from .bound_label import eligible_definition

PROJECT_DEFAULT_PREFIX = "Project default"
LIBRARY_TIER = "Library"


@dataclass(frozen=True)
class Choice:
    """One picker entry. *path* is the user-library ``.fpdb`` to embed on a
    pick (Library entries only); None for project / System / kept entries."""
    label: str
    block_id: str
    path: str | None = None


_parsed: dict[str, tuple[float, object]] = {}   # path -> (mtime, BlockDefinition | None)


def parsed_file(path: str):
    """``block_library.load_block_file(path)`` parsed once per mtime.

    The property panel calls ``get_properties()`` on every target for every
    row of the form, so the walk must not re-parse files. The call goes through
    the module attribute (a test counts it)."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        _parsed.pop(path, None)
        return None
    hit = _parsed.get(path)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    d = block_library.load_block_file(path)
    _parsed[path] = (mtime, d)
    return d


def shipped_defs() -> dict:
    """``{id: BlockDefinition}`` for the System tier, in file-name order."""
    out: dict = {}
    for bid, path in sorted(block_library.shipped_index().items(), key=lambda kv: kv[1]):
        d = parsed_file(path)
        if d is not None:
            out[bid] = d
    return out


def library_defs(scene, root: str | None = None) -> list[tuple[str, object, str]]:
    """``[(id, BlockDefinition, path)]`` for user-library files whose block the
    project has not embedded (``blocks_browser.library_only_entries``, user
    tier only). A copied duplicate-id file is skipped: it would load under a
    fresh id neither picker could name beforehand."""
    from .blocks_browser import library_only_entries
    entries = [e for e in block_library.list_library(root, system=False)
               if not e.get("duplicate")]
    out = []
    for _lib, _ser, _name, bid, path in library_only_entries(scene, root, entries=entries):
        if not bid:
            continue
        d = parsed_file(path)
        if d is not None:
            out.append((bid, d, path))
    return out


def kept_label(scene, category: str, block_id: str, shipped: dict | None = None,
               library: list | None = None) -> str:
    """"<name> (not eligible)" when the block exists somewhere we looked, else
    "<id> (missing)" -- the kept-mapping entry (SB3 Q6)."""
    known = scene._block_definitions.get(block_id)
    if known is None and shipped is not None:
        known = shipped.get(block_id)
    if known is None and library is not None:
        known = next((d for b, d, _p in library if b == block_id), None)
    return f"{known.name} (not eligible)" if known is not None else f"{block_id} (missing)"


def choices(scene, category: str, *, shipped: dict | None = None,
            library: list | None = None, current: str | None = None) -> list[Choice]:
    """The pickable blocks for *category*, in picker order. Pass *shipped* /
    *library* (``shipped_defs()`` / ``library_defs(scene)``) when listing
    several categories (one disk walk). *current* = the id the picker must be
    able to show even when it is not pickable (appended last)."""
    if shipped is None:
        shipped = shipped_defs()
    if library is None:
        library = library_defs(scene)
    out: list[Choice] = []
    for bid, d in scene._block_definitions.items():
        if eligible_definition(d, category):
            tier = "System" if d.library == block_library.SYSTEM_LIBRARY else "Project"
            out.append(Choice(f"{d.name} ({tier})", bid))
    seen = {c.block_id for c in out}
    for bid, d in shipped.items():
        if bid not in seen and eligible_definition(d, category):
            out.append(Choice(f"{d.name} (System)", bid))
            seen.add(bid)
    for bid, d, path in library:
        if bid not in seen and eligible_definition(d, category):
            out.append(Choice(f"{d.name} ({LIBRARY_TIER})", bid, path))
            seen.add(bid)
    if current and current not in seen:
        out.append(Choice(kept_label(scene, category, current, shipped, library), current))
    return out


def default_label(scene, category: str) -> str:
    """"Project default (<resolved block name>)" -- the Room row's None entry
    (``scene.annotation_block(category)``; "none" when nothing resolves or the
    scene has no resolver)."""
    fn = getattr(scene, "annotation_block", None)
    d = fn(category) if callable(fn) else None
    return f"{PROJECT_DEFAULT_PREFIX} ({d.name if d is not None else 'none'})"
