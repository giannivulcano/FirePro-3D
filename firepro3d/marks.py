"""Element Marks (SB2b) -- patterns, minting, duplicates and Renumber.

Governing spec: docs/specs/element-parameters.md "Marks (SB2b)".
The top half of this module is pure (no scene, no Qt); the scene adapters
below it read and write the real element fields.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

MARK_CATEGORIES = ("Door", "Window", "Opening", "Wall", "Pipe", "Sprinkler", "Room")
RENUMBER_CATEGORIES = MARK_CATEGORIES + ("Gridline",)

DEFAULT_PATTERNS = {
    "Door": "D{n}", "Window": "W{n}", "Opening": "O{n}", "Wall": "WL{n}",
    "Pipe": "P{n}", "Sprinkler": "S{n}", "Room": "{level}{n:02}",
}

_TOKEN_RE = re.compile(r"\{n(?::0(\d+))?\}|\{level\}")


def _level_text(level_number: Optional[int]) -> str:
    return "" if level_number is None else str(level_number)


def format_mark(pattern: str, n: int, level_number: Optional[int]) -> str:
    """The Mark *pattern* prints for counter *n* on a level numbered *level_number*.

    Tokens: ``{n}``, ``{n:0W}`` (zero-padded to at least W digits, never
    truncated) and ``{level}``; everything else is literal. A blank pattern
    gives a blank Mark.
    """
    def _sub(m: re.Match) -> str:
        if m.group(0) == "{level}":
            return _level_text(level_number)
        width = m.group(1)
        return f"{n:0{int(width)}d}" if width else str(n)
    return _TOKEN_RE.sub(_sub, pattern or "")


def _resolved_regex(pattern: str, level_number: Optional[int]) -> Optional[re.Pattern]:
    """Full-match regex for *pattern* with ``{level}`` resolved; the first
    counter token is group ``n``. None when the pattern has no counter."""
    parts, pos, have_n = [], 0, False
    for m in _TOKEN_RE.finditer(pattern or ""):
        parts.append(re.escape(pattern[pos:m.start()]))
        if m.group(0) == "{level}":
            parts.append(re.escape(_level_text(level_number)))
        else:
            width = m.group(1)
            digits = r"\d{%d,}" % int(width) if width else r"\d+"
            parts.append(f"(?P<n>{digits})" if not have_n else digits)
            have_n = True
        pos = m.end()
    parts.append(re.escape((pattern or "")[pos:]))
    if not have_n:
        return None
    return re.compile("".join(parts))


def mark_number(pattern: str, level_number: Optional[int], mark: str) -> Optional[int]:
    """The counter value *mark* carries under the resolved *pattern*, or None."""
    rx = _resolved_regex(pattern, level_number)
    if rx is None or not mark:
        return None
    m = rx.fullmatch(mark)
    return int(m.group("n")) if m else None


def next_number(pattern: str, level_number: Optional[int], existing: Iterable[str]) -> int:
    """Highest counter among *existing* Marks matching the resolved pattern, + 1 (Q5).
    Gaps are never refilled; 1 when nothing matches or the pattern has no counter."""
    nums = [v for v in (mark_number(pattern, level_number, m) for m in existing) if v is not None]
    return max(nums) + 1 if nums else 1


def duplicate_groups(marks_by_key: dict) -> dict:
    """``{mark: {keys}}`` for every non-blank Mark held by two or more keys (exact match)."""
    groups: dict = {}
    for key, mark in marks_by_key.items():
        if mark:
            groups.setdefault(mark, set()).add(key)
    return {m: ks for m, ks in groups.items() if len(ks) > 1}


def reading_order(points: dict, tol: float) -> list:
    """Keys of *points* (``key -> (x, y)`` in scene coords, y downward) in
    reading order: rows top -> bottom, a row = elements within *tol* below the
    row's first element; then left -> right inside the row."""
    by_y = sorted(points, key=lambda k: (points[k][1], points[k][0]))
    rows, row, row_y = [], [], None
    for k in by_y:
        y = points[k][1]
        if row_y is None or y - row_y > tol:
            if row:
                rows.append(row)
            row, row_y = [], y
        row.append(k)
    if row:
        rows.append(row)
    out = []
    for r in rows:
        out.extend(sorted(r, key=lambda k: points[k][0]))
    return out


@dataclass
class RenumberEntry:
    """One element as Renumber sees it (scene-free)."""
    key: object
    level_order: int                 # 0 = lowest elevation
    level_number: Optional[int]      # Level.number, for {level}
    point: tuple                     # sort point, scene coords
    mark: str
    in_scope: bool = True


def renumber_entries(entries: list, pattern: str, *, restart_per_level: bool,
                     keep_order: bool, tol: float = 600.0) -> dict:
    """``{key: new_mark}`` for every in-scope entry (spec M12).

    Level by level (lowest first); inside a level reading order, or the
    existing Mark number with *keep_order* (unparsable Marks follow, in
    reading order). Out-of-scope entries keep their Marks and the counter
    starts above the highest out-of-scope number of the resolved pattern;
    *restart_per_level* restarts the counter (and that floor) per level.
    """
    in_scope = [e for e in entries if e.in_scope]
    out_scope = [e for e in entries if not e.in_scope]
    levels = sorted({(e.level_order, e.level_number) for e in in_scope},
                    key=lambda t: t[0])

    def _floor(level_number):
        nums = [mark_number(pattern, level_number, e.mark) for e in out_scope]
        nums = [v for v in nums if v is not None]
        return max(nums) if nums else 0

    if not restart_per_level:
        counter = max([_floor(ln) for _, ln in levels] or [0])
    out = {}
    for order, level_number in levels:
        group = [e for e in in_scope if e.level_order == order]
        pts = {e.key: e.point for e in group}
        ordered = reading_order(pts, tol)
        if keep_order:
            num = {e.key: mark_number(pattern, level_number, e.mark) for e in group}
            parsed = sorted((k for k in ordered if num[k] is not None), key=lambda k: num[k])
            ordered = parsed + [k for k in ordered if num[k] is None]
        if restart_per_level:
            counter = _floor(level_number)
        for k in ordered:
            counter += 1
            out[k] = format_mark(pattern, counter, level_number)
    return out


def letter_label(idx: int) -> str:
    """0 -> A ... 25 -> Z, 26 -> AA (the gridline letter sequence)."""
    if idx < 26:
        return chr(65 + idx)
    return chr(65 + (idx // 26) - 1) + chr(65 + (idx % 26))


def gridline_labels(verticals: dict, horizontals: dict) -> dict:
    """Gridline Renumber (R3): verticals ``key -> x`` numbered 1, 2, 3 left -> right;
    horizontals ``key -> scene y`` lettered A, B, C bottom -> top."""
    out = {}
    for i, k in enumerate(sorted(verticals, key=lambda k: verticals[k])):
        out[k] = str(i + 1)
    for i, k in enumerate(sorted(horizontals, key=lambda k: -horizontals[k])):
        out[k] = letter_label(i)
    return out


# ---------------------------------------------------------------- scene adapters

def category_of(item) -> Optional[str]:
    """Element category (element_params E1) -- re-exported for callers here."""
    from .element_params import category_of as _cat
    return _cat(item)


def get_mark(item) -> str:
    """The Mark stored on *item* ("" when none). Gridline: its Label (Q3)."""
    from .gridline import GridlineItem
    if isinstance(item, GridlineItem):
        return item.grid_label
    props = getattr(item, "_properties", None)
    if isinstance(props, dict) and "Mark" in props:
        return str(props["Mark"]["value"] or "")
    return str(getattr(item, "_mark", "") or "")


def set_mark(item, value: str) -> None:
    """Write *item*'s Mark field directly (no undo, no refresh)."""
    from .gridline import GridlineItem
    if isinstance(item, GridlineItem):
        item.grid_label = value
        return
    props = getattr(item, "_properties", None)
    if isinstance(props, dict) and "Mark" in props:
        props["Mark"]["value"] = value
        return
    item._mark = value
    if hasattr(item, "_update_label"):
        item._update_label()


def item_level_name(item) -> Optional[str]:
    """Level name an element sits on (a sprinkler's is its node's)."""
    node = getattr(item, "node", None)
    if node is not None:                  # Sprinkler: the node is authoritative
        return getattr(node, "level", None)
    return getattr(item, "level", None)


def items_of_category(scene, category: str) -> list:
    """Every live element of *category* in *scene*, in a stable order."""
    if category == "Wall":
        return list(scene._walls)
    if category in ("Door", "Window", "Opening"):
        return [op for w in scene._walls for op in w.openings
                if category_of(op) == category]
    if category == "Room":
        return list(scene._rooms)
    if category == "Pipe":
        return list(scene.sprinkler_system.pipes)
    if category == "Sprinkler":
        return [n.sprinkler for n in scene.sprinkler_system.nodes if n.has_sprinkler()]
    if category == "Gridline":
        return list(scene._gridlines)
    return []


def patterns(scene) -> dict:
    """The scene's per-category Mark patterns, defaults filled in."""
    out = dict(DEFAULT_PATTERNS)
    out.update(getattr(scene, "mark_patterns", None) or {})
    return out


def level_number_of(scene, item) -> Optional[int]:
    """``Level.number`` of the level *item* sits on, or None (no level / unassigned)."""
    lm = getattr(scene, "_level_manager", None)
    name = item_level_name(item)
    if lm is None or not name:
        return None
    lvl = lm.get(name)
    num = getattr(lvl, "number", 0) if lvl is not None else 0
    return num or None


def mint(scene, item) -> str:
    """Give a newly created *item* the next Mark of its category (spec A1 / M7).

    Called explicitly at each creation site; never on load, undo, move or edit.
    Returns the Mark written ("" for a blank pattern or a non-Mark item).
    """
    cat = category_of(item)
    if cat not in MARK_CATEGORIES or scene is None:
        return ""
    pattern = patterns(scene).get(cat, "")
    level_number = level_number_of(scene, item)
    existing = [get_mark(i) for i in items_of_category(scene, cat) if i is not item]
    mark = format_mark(pattern, next_number(pattern, level_number, existing), level_number)
    set_mark(item, mark)
    return mark
