"""Element Marks (SB2b) -- patterns, minting, duplicates and Renumber.

Governing spec: docs/specs/element-parameters.md "Marks (SB2b)".
The top half of this module is pure (no scene, no Qt); the scene adapters
below it read and write the real element fields.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Iterable, Optional

from .constants import MARK_ROW_TOLERANCE_MM

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


def _number_in(rx: Optional[re.Pattern], mark: str) -> Optional[int]:
    """The counter *mark* carries under the prebuilt regex *rx*, or None."""
    if rx is None or not mark:
        return None
    m = rx.fullmatch(mark)
    return int(m.group("n")) if m else None


def mark_number(pattern: str, level_number: Optional[int], mark: str) -> Optional[int]:
    """The counter value *mark* carries under the resolved *pattern*, or None."""
    return _number_in(_resolved_regex(pattern, level_number), mark)


def next_number(pattern: str, level_number: Optional[int], existing: Iterable[str]) -> int:
    """Highest counter among *existing* Marks matching the resolved pattern, + 1 (Q5).
    Gaps are never refilled; 1 when nothing matches or the pattern has no counter."""
    rx = _resolved_regex(pattern, level_number)      # built once, not per Mark
    nums = [v for v in (_number_in(rx, m) for m in existing) if v is not None]
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
                     keep_order: bool, tol: float = MARK_ROW_TOLERANCE_MM) -> dict:
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
        rx = _resolved_regex(pattern, level_number)
        nums = [_number_in(rx, e.mark) for e in out_scope]
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
            rx = _resolved_regex(pattern, level_number)
            num = {e.key: _number_in(rx, e.mark) for e in group}
            parsed = sorted((k for k in ordered if num[k] is not None), key=lambda k: num[k])
            ordered = parsed + [k for k in ordered if num[k] is None]
        if restart_per_level:
            counter = _floor(level_number)
        for k in ordered:
            counter += 1
            out[k] = format_mark(pattern, counter, level_number)
    return out


def letter_label(idx: int) -> str:
    """Bijective base-26: 0 -> A ... 25 -> Z, 26 -> AA, 701 -> ZZ, 702 -> AAA.

    The one gridline letter sequence (``gridline`` reuses it)."""
    out = ""
    n = idx + 1
    while n > 0:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


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
    from .floor_opening import FloorOpening
    if isinstance(item, FloorOpening):    # a floor void sits on its host's top level (A8)
        host = item.host
        if host is None or host._top_mode != "level":
            return None
        return host._top_level
    node = getattr(item, "node", None)
    if node is not None:                  # Sprinkler: the node is authoritative
        return getattr(node, "level", None)
    level = getattr(item, "level", None)
    if not level:                         # Pipe with no level of its own: node1's
        level = getattr(getattr(item, "node1", None), "level", None)
    return level


def items_of_category(scene, category: str) -> list:
    """Every live element of *category* in *scene*, in a stable order."""
    if category == "Wall":
        return list(scene._walls)
    if category in ("Door", "Window", "Opening"):
        out = [op for w in scene._walls for op in w.openings
               if category_of(op) == category]
        if category == "Opening":       # floor voids follow the walls' openings (A8)
            out += [op for s in scene._floor_slabs for op in s.openings]
        return out
    if category == "Room":
        return list(scene._rooms)
    if category == "Pipe":
        return list(scene.sprinkler_system.pipes)
    if category == "Sprinkler":
        return [n.sprinkler for n in scene.sprinkler_system.nodes if n.has_sprinkler()]
    if category == "Gridline":
        return list(scene._gridlines)
    return []


_PLURAL = {"Door": "doors", "Window": "windows", "Opening": "openings", "Wall": "walls",
           "Pipe": "pipes", "Sprinkler": "sprinklers", "Room": "rooms", "Gridline": "gridlines"}


def duplicate_info(scene, item) -> Optional[str]:
    """Tooltip text when *item*'s non-blank Mark is shared in its category, else None (Q9/Q10)."""
    cat = category_of(item)
    mark = get_mark(item)
    if not mark or cat is None or scene is None:
        return None
    count = sum(1 for i in items_of_category(scene, cat) if get_mark(i) == mark)
    if count < 2:
        return None
    return f"{count} {_PLURAL.get(cat, cat.lower() + 's')} share Mark {mark}"


def hold_duplicate_refresh(scene) -> None:
    """Defer :func:`request_duplicate_refresh` until the matching release (Array
    pastes once per copy; the panel rebuild is synchronous)."""
    scene._dup_hold = getattr(scene, "_dup_hold", 0) + 1


def release_duplicate_refresh(scene) -> None:
    """End a hold; the outermost release runs one refresh if any was requested.

    Callers release from a ``finally``: while an exception is propagating a
    refresh failure is swallowed so it cannot mask the original error. Never
    release from an ``except`` block on a normal path: ``sys.exc_info`` is set
    there too, so a real refresh failure would be swallowed."""
    scene._dup_hold = max(0, getattr(scene, "_dup_hold", 1) - 1)
    if scene._dup_hold == 0 and getattr(scene, "_dup_pending", False):
        scene._dup_pending = False
        if sys.exc_info()[0] is not None:
            try:
                refresh_duplicates(scene)
            except Exception:
                pass
        else:
            refresh_duplicates(scene)


def request_duplicate_refresh(scene) -> None:
    """:func:`refresh_duplicates` now, or once at the end of the current hold."""
    if getattr(scene, "_dup_hold", 0) > 0:
        scene._dup_pending = True
    else:
        refresh_duplicates(scene)


def refresh_duplicates(scene) -> None:
    """Re-run duplicate detection after a bulk Mark change: the gridline bubbles
    (their own orange path) and a property-panel rebuild of the current selection.

    Nothing is painted on the canvas for model elements, so paper / PDF stay clean.
    """
    from .gridline import apply_duplicate_warnings
    apply_duplicate_warnings(list(scene._gridlines))
    sig = getattr(scene, "requestPropertyUpdate", None)
    if sig is not None:
        sel = list(scene.selectedItems())
        if sel:        # no selection: leave the panel alone (it may show a template)
            sig.emit(sel)


def clean_patterns(raw) -> dict:
    """*raw* (a loaded ``mark_patterns`` value) reduced to its str -> str entries
    ({} when it is not a dict), so a corrupt file falls back to the defaults."""
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)}


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
    return num or None        # Level.number 0 = unassigned (plan reconciliation 6)


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


def preview_next(scene, category: str, pattern: str) -> str:
    """What the next *category* element would get under *pattern* (Marks pane Next).

    ``{level}`` resolves to the active level's number; a blank result shows ``(blank)``.
    """
    lm = getattr(scene, "_level_manager", None)
    lvl = lm.get(getattr(scene, "active_level", "")) if lm is not None else None
    level_number = (getattr(lvl, "number", 0) or None) if lvl is not None else None
    existing = [get_mark(i) for i in items_of_category(scene, category)]
    if not (pattern or "").strip():              # mockup: a whitespace-only pattern is blank
        return "(blank)"
    out = format_mark(pattern, next_number(pattern, level_number, existing), level_number)
    return out or "(blank)"


# ---------------------------------------------------------------- Renumber (scene side)

def sort_point(item) -> tuple:
    """Renumber sort point in scene coords (spec M12): wall / pipe midpoint,
    opening centre, floor-void centroid, room centroid, sprinkler node."""
    from .pipe import Pipe
    from .room import Room
    from .wall import WallSegment
    from .wall_opening import WallOpening
    from .floor_opening import FloorOpening
    if isinstance(item, FloorOpening):            # floor void: its outline centroid
        pts = item.points
        return (sum(q.x() for q in pts) / len(pts), sum(q.y() for q in pts) / len(pts))
    if isinstance(item, WallOpening):
        p = item.center_on_wall() if item.wall is not None else item.scenePos()
        return (p.x(), p.y())
    if isinstance(item, WallSegment):
        a, b = item.pt1, item.pt2
        return ((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
    if isinstance(item, Pipe):
        a, b = item.node1.scenePos(), item.node2.scenePos()
        return ((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
    if isinstance(item, Room):
        pts = list(item._boundary)
        if not pts:
            p = item.scenePos()
            return (p.x(), p.y())
        return (sum(q.x() for q in pts) / len(pts), sum(q.y() for q in pts) / len(pts))
    node = getattr(item, "node", None)          # Sprinkler
    p = (node if node is not None else item).scenePos()
    return (p.x(), p.y())


def renumber_plan(scene, category: str, scope: str, level_name: Optional[str] = None, *,
                  restart_per_level: bool, keep_order: bool) -> dict:
    """``{item: new_mark}`` for the in-scope elements of *category* (no writes).

    *scope*: ``"project"`` | ``"selected"`` | ``"level"`` (with *level_name*).
    Gridlines carry no level and are numbered as one project-wide set, so any
    scope renumbers all of them.
    """
    items = items_of_category(scene, category)
    if category == "Gridline":
        in_scope = lambda i: True
    elif scope == "selected":
        sel = {id(i) for i in scene.selectedItems()}
        in_scope = lambda i: id(i) in sel or id(getattr(i, "node", None)) in sel
    elif scope == "level":
        in_scope = lambda i: item_level_name(i) == level_name
    else:
        in_scope = lambda i: True
    if category == "Gridline":
        vert, horiz = {}, {}
        for g in items:
            if not in_scope(g):
                continue
            a, b = g.grip_points()[0], g.grip_points()[1]
            if abs(b.y() - a.y()) >= abs(b.x() - a.x()):
                vert[g] = (a.x() + b.x()) / 2
            else:
                horiz[g] = (a.y() + b.y()) / 2
        return gridline_labels(vert, horiz)
    lm = getattr(scene, "_level_manager", None)
    order = ({l.name: i for i, l in enumerate(sorted(lm.levels, key=lambda l: l.elevation))}
             if lm is not None else {})
    sm = getattr(scene, "scale_manager", None)
    tol = sm.mm_to_scene(MARK_ROW_TOLERANCE_MM) if sm is not None else MARK_ROW_TOLERANCE_MM
    entries = [RenumberEntry(key=i, level_order=order.get(item_level_name(i), len(order)),
                             level_number=level_number_of(scene, i),
                             point=sort_point(i), mark=get_mark(i), in_scope=in_scope(i))
               for i in items]
    return renumber_entries(entries, patterns(scene).get(category, ""),
                            restart_per_level=restart_per_level,
                            keep_order=keep_order, tol=tol)


def apply_marks(scene, mapping: dict) -> bool:
    """Write a Renumber result as ONE undo step, then refresh duplicates.

    Only elements whose Mark changes are written; no change pushes nothing.
    Returns True when anything changed.
    """
    changed = {i: m for i, m in mapping.items() if get_mark(i) != m}
    if not changed:
        return False
    hold_duplicate_refresh(scene)
    try:
        for item, mark in changed.items():
            set_mark(item, mark)
        scene.push_undo_state()
        request_duplicate_refresh(scene)
    finally:
        release_duplicate_refresh(scene)
    return True
