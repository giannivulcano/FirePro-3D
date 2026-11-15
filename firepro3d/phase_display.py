"""Sheet viewport phasing: the per-viewport phase display and the paper-pass merge (PH3).

Governing spec: docs/specs/project-phasing.md (D-PH3, D-PH8, D-PH9, D-PH10,
D-PH13, D-PH17); build design:
docs/superpowers/specs/2026-11-14-ph3-sheet-phasing-design.md (DD1, DD2, DD3).

A sheet viewport stores a :class:`PhaseDisplay`. ``SheetViewport.paint`` opens
a pass context (:func:`begin_pass` / :func:`end_pass`) around
``paper_display.apply_paper_overrides``, which calls :func:`merge` at each
paper-row lookup. An inactive context returns the row itself, so Phasing off
plots exactly as before phasing (D-PH6); an active one returns a copy carrying
the item's status graphics and names, under :data:`FORCED`, the slots the
status set, so an As Authored row overrides only those (DD2).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import phase_registry

#: Every paper-row slot a status can drive (DD1).
ALL_KEYS = frozenset(("visible", "color", "fill", "line_weight", "opacity"))
#: SVG symbols (sprinkler, water supply, fitting): no fill / weight until they are blocks (D-PH13).
SYMBOL_KEYS = frozenset(("visible", "color", "opacity"))
#: Host-bound labels and tags: hidden with the host, its colour and opacity (R4).
LABEL_KEYS = SYMBOL_KEYS
#: Underlays: hide, colour and opacity (R5).
UNDERLAY_KEYS = SYMBOL_KEYS
#: Row-copy key: frozenset of the slots the status set (DD2).
FORCED = "_phase_forced"
_PERCENT = 100.0

# One entry per open pass (None = inactive); end_pass pops (finally-paired).
_STACK: list = []


@dataclass(frozen=True)
class PhaseDisplay:
    """One viewport's phasing: the Phasing tick and the hidden status ids (D-PH8).

    Attributes:
        enabled: The Phasing tick. False plots exactly as before phasing (D-PH6).
        hidden: Status ids whose Show tick is off: not drawn (D-PH17).
    """

    enabled: bool = False
    hidden: frozenset = frozenset()

    def to_dict(self) -> dict:
        """The viewport record's ``"phase_display"`` value."""
        return {"enabled": bool(self.enabled), "hidden": sorted(self.hidden)}

    @classmethod
    def from_dict(cls, d) -> "PhaseDisplay":
        """Parse a stored value.

        Args:
            d: The record's ``"phase_display"`` value (may be missing / malformed).

        Returns:
            Disabled for a missing or malformed value; ids the project registry
            does not have are dropped (concept edge case).
        """
        if not isinstance(d, dict):
            return cls()
        reg = phase_registry.project_table()
        raw = d.get("hidden")
        ids = raw if isinstance(raw, (list, tuple)) else ()
        return cls(enabled=d.get("enabled") is True,
                   hidden=frozenset(s for s in ids
                                    if isinstance(s, str) and reg.get(s) is not None))

    def with_enabled(self, on: bool) -> "PhaseDisplay":
        """A copy with the Phasing tick set to *on*."""
        return PhaseDisplay(bool(on), self.hidden)

    def with_shown(self, sid: str, shown: bool) -> "PhaseDisplay":
        """A copy with status *sid*'s Show tick set to *shown*."""
        hidden = set(self.hidden)
        if shown:
            hidden.discard(sid)
        else:
            hidden.add(sid)
        return PhaseDisplay(self.enabled, frozenset(hidden))


def begin_pass(viewport_data) -> None:
    """Open the pass context for *viewport_data* (a ``SheetViewData``).

    Active only when the viewport's Phasing is on and it is not a schematic
    viewport (D-PH8). Always paired with :func:`end_pass` in a ``finally``.
    """
    disp = getattr(viewport_data, "phase_display", None)
    kind = getattr(viewport_data, "source_view_type", "")
    on = isinstance(disp, PhaseDisplay) and disp.enabled and kind != "schematic"
    _STACK.append(disp if on else None)


def end_pass() -> None:
    """Close the innermost pass context."""
    if _STACK:
        _STACK.pop()


def active() -> "PhaseDisplay | None":
    """The open pass's PhaseDisplay, or None when no Phasing-on pass is open."""
    return _STACK[-1] if _STACK else None


def merge(cat, item, *, keys=ALL_KEYS):
    """*cat* (a paper category row) with *item*'s status graphics merged in.

    Args:
        cat: The paper row dict (never written).
        item: The element (or fitting / underlay record) being plotted.
        keys: The slots this kind takes (:data:`ALL_KEYS`, :data:`SYMBOL_KEYS`, ...).

    Returns:
        *cat* itself when no Phasing-on pass is open or *item* carries no phase
        (D-PH3). Otherwise a shallow copy: ``visible`` False for a hidden status;
        each status graphic that is set (not "--") replaces the row's colour /
        fill (+ section body) / line weight / opacity (R1-R3); ``FORCED`` names
        the slots set.
    """
    disp = active()
    if disp is None or cat is None:
        return cat
    sid = phase_registry.effective_phase(item)
    if sid is None:
        return cat
    out = dict(cat)
    forced_slots = set()
    if "visible" in keys and sid in disp.hidden:
        out["visible"] = False
    g = phase_registry.project_table().graphics_of(sid)
    colour, fill = g.get("colour"), g.get("fill")
    if "color" in keys and colour is not None:
        out["color"] = colour
        forced_slots.add("color")
    if "fill" in keys and fill is not None:
        out["fill"] = fill
        out["section_color"] = fill
        forced_slots.add("fill")
    if "line_weight" in keys and g.get("weight") is not None:
        out["line_weight"] = g["weight"]
        forced_slots.add("line_weight")
    if "opacity" in keys and g.get("opacity") is not None:
        out["opacity"] = g["opacity"]
        forced_slots.add("opacity")
    out[FORCED] = frozenset(forced_slots)
    return out


def forced(cat, slot: str) -> bool:
    """True when the status set *slot* in this merged row (DD2)."""
    return slot in ((cat or {}).get(FORCED) or ())


def writes(cat, authored: bool, slot: str) -> bool:
    """DD2: the paper pass writes colour *slot* ("color" / "fill") when the row
    is not As Authored or the status forced that slot."""
    return not authored or forced(cat, slot)


def label_opacity(cat) -> float:
    """A host label's opacity (R4): the status opacity when set, else 1.0."""
    return cat["opacity"] / _PERCENT if forced(cat, "opacity") else 1.0
