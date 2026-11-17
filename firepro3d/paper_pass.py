"""Paper pass protocol (paper-space.md s6.2 "Paper pass protocol").

Items enter and leave a sheet-viewport paper pass themselves:
``owner.enter_paper_pass(ctx, cat) -> token | None`` saves first, then
writes; ``owner.exit_paper_pass(token)`` undoes it. The driver here only
picks items, maps each to its paper owner, merges the row once, and unwinds
every token in reverse, each exit in its own try.

Until each family migrates, an owner not in :func:`_migrated` runs through
the legacy adapter in ``paper_display`` (today's per-entry save / apply /
restore code, as one token per owner).
"""
from __future__ import annotations

import logging

from . import phase_display

_log = logging.getLogger(__name__)


class PassTokens(list):
    """The opaque list ``apply_paper_overrides`` returns: (item, exit_fn, token)."""

    def push(self, item, exit_fn, token) -> None:
        self.append((item, exit_fn, token))


def enter_guarded(exit_fn, token, write):
    """Run *write*; on a raise, undo the partly-entered item, then re-raise."""
    try:
        write()
    except BaseException:
        try:
            exit_fn(token)
        except Exception:                       # the original error wins
            _log.exception("paper pass: unwinding a partly-entered item failed")
        raise
    return token


def unwind(saved) -> None:
    """Exit every token in reverse; log each failure, re-raise the first (D6)."""
    first = None
    while saved:
        item, exit_fn, token = saved.pop()
        try:
            exit_fn(token)
        except Exception as exc:               # noqa: BLE001 - per-entry tolerance (R3)
            _log.exception("paper pass: exit failed for %r", item)
            if first is None:
                first = exc
    if first is not None:
        raise first


def _vis_exit(token) -> None:
    item, visible = token
    try:
        item.setVisible(visible)
    except RuntimeError:                       # deleted mid-pass (section rebuild)
        pass


def hide_for_pass(saved, item) -> None:
    """A visibility-only token (pick rules, a row with Visible off; D4)."""
    saved.push(item, _vis_exit, (item, item.isVisible()))
    item.setVisible(False)


class PaperPassContext:
    """Pass-level state (D3): entered first and left FIRST on unwind (the
    base restore order; see :meth:`exit`). Its token is pushed both first
    (a no-op once left) and, after a complete enter, last."""

    def __init__(self, scene, source_rect, paper_scale: float = 1.0,
                 viewport_data=None):
        from .paper_display import load_paper_categories
        self.scene = scene
        self.source_rect = source_rect
        self.paper_scale = paper_scale
        self.viewport_data = viewport_data
        self.rows = load_paper_categories()
        self.text_scale = getattr(scene, "text_print_scale", None)   # N15
        self._tok_cache: dict = {}
        self._left = False

    # -- rows / weights ---------------------------------------------------
    def row(self, key):
        return self.rows.get(key)

    def lw_mm(self, cat) -> float:
        from .paper_display import resolve_line_weight_mm
        return resolve_line_weight_mm(cat["line_weight"])

    def paper_w(self, lw_mm: float) -> float:
        """True on-paper mm in model units, non-cosmetic (s9.9.1)."""
        return lw_mm / max(self.paper_scale, 1e-9)

    def merge(self, row, item, cat_key=None, keys=None):
        return phase_display.merge(row, item, keys=keys or self.phase_keys(cat_key))

    @staticmethod
    def phase_keys(cat_key):
        """D-PH13: sprinklers and water supplies (the plan SVG symbol and its
        section / elevation proxy alike) take visibility, colour and opacity only."""
        return (phase_display.SYMBOL_KEYS if cat_key in ("Sprinkler", "Water Supply")
                else phase_display.ALL_KEYS)

    # -- token colours (moved from apply_paper_overrides' closures) -------
    def auth_tok(self, it, key, authored):
        """Model-side token colour to re-resolve on paper (row ON only)."""
        from .paper_display import _model_colour_token
        return _model_colour_token(it, key, self._tok_cache) if authored else None

    def svg_paper_retint(self, it, owner, key) -> bool:
        """R6: a row-ON SVG symbol re-tints when its Model colour or fill is
        a token; each token resolves on the paper surface, a hex half keeps
        its canvas value. True when it re-tinted."""
        from .display_manager import _set_svg_tint
        from .paper_display import _model_colour_token
        c = _model_colour_token(owner, key, self._tok_cache)
        f = _model_colour_token(owner, key, self._tok_cache, "fill")
        if c is None and f is None:
            return False
        _set_svg_tint(it, c if c is not None else getattr(owner, "_display_color", None),
                      f if f is not None else getattr(owner, "_display_fill_color", None))
        return True

    def svg_phase_tint(self, it, owner, key, colour) -> None:
        """DD2: a row-ON SVG symbol whose status forces the colour -- the
        stroke takes *colour*, the fill keeps its authored value (a token
        fill re-resolves on the paper surface, as in svg_paper_retint)."""
        from .display_manager import _set_svg_tint
        from .paper_display import _model_colour_token
        f = _model_colour_token(owner, key, self._tok_cache, "fill")
        _set_svg_tint(it, colour,
                      f if f is not None else getattr(owner, "_display_fill_color", None))

    # -- pass-level enter / exit -----------------------------------------
    def enter(self):
        """Drafting-tile scale for the hatch renderer (D-A30) and the Thin
        Lines suspension (LT1-8) for this viewport render."""
        from . import paper_display as pd
        self.scene._hatch_paper_scale = self.paper_scale
        pd._THIN_SUSPEND += 1
        return self.scene

    def exit(self, scene) -> None:
        """Lift the pass-level state, once per pass (a second call is a no-op).

        Runs FIRST in the unwind, as the base restore did: item exits must
        see ``paper_pass_active()`` False, or a token colour re-latched on
        exit (a fitting's canvas tint) resolves on the paper surface.
        """
        from . import paper_display as pd
        if self._left:
            return
        self._left = True
        scene._hatch_paper_scale = None
        if pd._THIN_SUSPEND <= 0:
            pd._log.warning("restore_model_display: Thin Lines "
                            "suspension counter unbalanced (%d)",
                            pd._THIN_SUSPEND)
        pd._THIN_SUSPEND = max(0, pd._THIN_SUSPEND - 1)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def _migrated() -> tuple:
    """Classes whose enter / exit is on the new protocol. Each family task
    adds its classes; Task 15 deletes this and the legacy adapter."""
    from .filled_region import FilledRegionItem
    from .floor_opening import FloorOpening
    from .floor_slab import FloorSlab
    from .geometry_2d import (ArcItem, CircleItem, EllipseItem, LineItem,
                              PolylineItem, RectangleItem, RegularPolygonItem,
                              SplineItem)
    from .node import Node
    from .roof import RoofItem
    from .room import Room
    from .wall import WallSegment
    from .wall_opening import WallOpening
    return (WallSegment, WallOpening, FloorOpening, FloorSlab, RoofItem, Room, Node,
            # construction family (Task 4)
            PolylineItem, LineItem, RectangleItem, CircleItem, ArcItem,
            EllipseItem, SplineItem, RegularPolygonItem, FilledRegionItem)


def _owner_of(item):
    o = getattr(item, "paper_owner", None)
    return o if o is not None else item


def _pick(ctx, saved, item) -> bool:
    """D4 pick rules; True = the item was consumed (hidden).

    Order is today's: PAPER_EXCLUDED, the origin cross, scaffold, then (for
    anything but a printed-text item, which the owner's enter takes first)
    the detail-marker self-hide / per-sheet hide.
    """
    from PyQt6.QtWidgets import QGraphicsItem
    from .block_definition import is_scaffold_item
    from .paper_display import _is_detail_marker
    # Instance-aware: class flags (manipulator, markers) and per-item flags
    # (the block placement ghost) both exclude. QGraphicsItem.data(item, 0),
    # not item.data(0): TextItem shadows ``data`` (SV2). The origin cross is
    # an authoring aid (s9.9.1); scaffold never plots (RG11 / RG12).
    if getattr(item, "PAPER_EXCLUDED", False) \
            or QGraphicsItem.data(item, 0) == "origin" \
            or is_scaffold_item(item):
        hide_for_pass(saved, item)
        return True
    if ctx.text_scale:
        from .text_item import TextItem
        if isinstance(item, TextItem):         # printed text (N15) is entered first
            return False
    vd = ctx.viewport_data
    if vd is not None and _is_detail_marker(item):
        name = getattr(item, "name", None)
        if (vd.source_view_type == "detail" and name == vd.source_view_name) \
                or name in vd.hidden_detail_ids:
            hide_for_pass(saved, item)
            return True
    return False


def _enter_owner(ctx, saved, owner) -> None:
    from . import paper_display as pd
    if ctx.text_scale and hasattr(owner, "enter_print_pass") \
            and type(owner) in _migrated():
        saved.push(owner, owner.exit_print_pass, owner.enter_print_pass(ctx))
        return
    if type(owner) not in _migrated():
        entries: list = []
        try:
            pd._legacy_enter(ctx, owner, entries)
        finally:
            if entries:
                saved.push(owner, pd._legacy_exit, entries)
        return
    cat_key = pd._category_for_item(owner)
    if cat_key is None:
        pd._hide_phase_hidden_mask_token(owner, saved)
        return
    row = ctx.row(cat_key)
    if row is None:
        return
    cat = ctx.merge(row, owner, cat_key)
    if not cat.get("visible", True):
        for it in (owner, *getattr(owner, "paper_hidden_children", tuple)()):
            hide_for_pass(saved, it)
        return
    tok = owner.enter_paper_pass(ctx, cat)
    if tok is not None:
        saved.push(owner, owner.exit_paper_pass, tok)


def run_pass(scene, source_rect, paper_scale=1.0, viewport_data=None) -> PassTokens:
    """Enter the paper pass: the context first, then every picked owner once
    (first-hit order), then the legacy tail (fittings, underlays). A mid-pass
    raise unwinds everything entered so far, then re-raises (D6)."""
    from . import paper_display as pd
    ctx = PaperPassContext(scene, source_rect, paper_scale, viewport_data)
    saved = PassTokens()
    saved.push(scene, ctx.exit, ctx.enter())
    try:
        seen: set[int] = set()
        for hit in scene.items(source_rect):
            if not hit.isVisible():
                continue
            if _pick(ctx, saved, hit):
                continue
            owner = _owner_of(hit)
            if id(owner) in seen:
                continue
            seen.add(id(owner))
            if owner is not hit and not owner.isVisible():
                continue
            _enter_owner(ctx, saved, owner)
        pd._legacy_tail(ctx, saved)          # fittings + underlays until Tasks 13-14
    except BaseException:
        try:
            ctx.exit(scene)                    # left first, as on a normal unwind
        except Exception:
            _log.exception("paper pass: leaving the pass context failed")
        try:
            unwind(saved)
        except Exception:                      # the pass's own error wins
            _log.exception("paper pass: unwind after a failed enter also failed")
        raise
    saved.push(scene, ctx.exit, scene)         # unwinds first (see PaperPassContext.exit)
    return saved
