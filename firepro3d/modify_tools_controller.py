"""Modify-tool behaviour home (scene-tools.md I1).

Owns NO state (model-space-architecture.md §5.3): every transient lives on the
scene and is reached via ``self._scene``. Dispatch rows on ``Model_Space``
point at thin scene shells that forward here.

Slice 1 relocates the Move / Paste gesture (press, move, preview, handle-snap,
typed-displacement applier, ghost-silhouette builders) verbatim. Calls between
relocated methods go back through the scene shells (``s._move_handle_snap``
etc.), so a test or caller that patches the scene attribute still reaches the
behaviour it patched.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainterPath, QTransform

from .cad_math import CAD_Math
from .constants import ARRAY_GHOST_FULL_MAX
from .gridline import GridlineItem
from .handle_snap import HandleSnapSession
from .scale_manager import ScaleManager
from .sprinkler import Sprinkler

# Tools whose originals are dimmed while they run (D11; paste has no originals).
DIM_ORIGINAL_TOOLS = frozenset({"move", "duplicate", "rotate", "array",
                                "flip", "mirror", "scale"})


class ModifyToolsController:
    """Behaviour for the 2D modify tools. See docs/specs/scene-tools.md."""

    # tool name -> scene mode entered by start()
    _TOOL_MODE = {"copy": "copy_base", "cut": "copy_base", "paste": "paste",
                  "duplicate": "duplicate", "move": "move", "rotate": "rotate",
                  "offset": "offset", "array": "array",
                  "flip": "flip", "mirror": "mirror", "scale": "scale"}
    _SELECT_FIRST = {"copy", "cut", "duplicate", "move", "rotate", "array",
                     "flip", "mirror", "scale"}
    # Cut shares Copy's ``copy_base`` mode (``_copy_is_cut`` tells them
    # apart), so its modal button is registered under this pseudo-mode key
    # and ``button_key`` resolves which button a live copy_base lights (DD10).
    CUT_BUTTON_KEY = "copy_base:cut"
    # Extra modes a tool passes through after its entry mode.
    _TOOL_EXTRA_MODES = {"offset": ("offset_side",)}
    # Modes an Undo / Redo must cancel first: their transient state (base
    # point, captured selection, armed payload) would outlive the restore.
    CANCEL_ON_UNDO_MODES = frozenset({"copy_base", "paste", "duplicate", "move",
                                      "rotate", "offset", "offset_side",
                                      "array", "flip", "mirror", "scale"})

    @classmethod
    def tool_modes(cls, tool: str):
        """Ribbon-registry key(s) that mean *tool* is running (light its button).

        A key is the scene mode the tool enters plus any extra modes it
        passes through — except Cut, keyed by :attr:`CUT_BUTTON_KEY` because
        it shares Copy's ``copy_base`` mode (DD10).

        Args:
            tool: A ``_TOOL_MODE`` key.

        Returns:
            A tuple of registry keys, or None for an unknown tool.
        """
        if tool not in cls._TOOL_MODE:
            return None
        if tool == "cut":
            return (cls.CUT_BUTTON_KEY,)
        return (cls._TOOL_MODE[tool],) + cls._TOOL_EXTRA_MODES.get(tool, ())

    @classmethod
    def button_key(cls, mode, scene):
        """The ribbon-registry / badge key a live *mode* on *scene* means.

        ``copy_base`` entered by Cut (``scene._copy_is_cut``) is Cut's key;
        every other mode is its own key.

        Args:
            mode: The mode ``modeChanged`` just carried ('' for None).
            scene: The emitting scene (None tolerated).

        Returns:
            The key.
        """
        if mode == "copy_base" and getattr(scene, "_copy_is_cut", False):
            return cls.CUT_BUTTON_KEY
        return mode

    def __init__(self, scene):
        self._scene = scene

    def start(self, tool: str) -> bool:
        """Enter *tool* (scene-tools.md D3 select-first).

        Args:
            tool: One of the ``_TOOL_MODE`` keys.

        Returns:
            True if a mode was entered.
        """
        s = self._scene
        if not getattr(s, "view_available", True):
            # Empty canvas (view-3d.md I5) — the ONE refusal home for every
            # Edit/Modify entry (ribbon + shortcuts). Refuse before any tool
            # state is touched: paste/offset mutate state after set_mode.
            from .model_space import NO_VIEW_HINT
            s.instructionChanged.emit(NO_VIEW_HINT)
            return False
        sel = list(s.selectedItems())
        if tool in self._SELECT_FIRST and not sel:
            s._show_status("Select items first", 3000)
            return False
        if tool == "paste":
            return self.begin_paste()
        if tool == "offset":
            return self.begin_offset(sel)      # Task 12
        capable = {"flip": self._reflectable, "mirror": self._reflectable,
                   "scale": self._scalable}.get(tool)
        if capable is not None and not capable(sel):
            # DD4: only 2D drafting geometry carries manip_reflect /
            # manip_scale_about (text, blocks, pipes, walls, gridlines… don't).
            s._show_status(self.nothing_to_hint(tool), 3000)
            return False
        if tool == "array" and not self._array_copyable(sel):
            # Review I3: paste_items can't re-create walls, rooms, floors,
            # roofs or design areas — refuse up front, not "Nothing arrayed".
            s._show_status(self.ARRAY_NOTHING_COPYABLE, 3000)
            return False
        s._copy_is_cut = (tool == "cut")
        s._selected_items = sel
        s.set_mode(self._TOOL_MODE[tool])
        # D11: dim the originals. After set_mode — its clear() restores any
        # previous dim first, so entering a mode never undoes its own dim.
        if tool in DIM_ORIGINAL_TOOLS and s.mode == self._TOOL_MODE[tool]:
            from .transform_ghost import dim_items
            # Dim exactly what the tool acts on: Rotate turns only the
            # rotatable subset, Flip / Mirror only the reflectable one, so
            # nothing a tool leaves alone looks "in flight".
            acted = (self._rotatable(sel) if tool == "rotate"
                     else self._reflectable(sel) if tool in ("flip", "mirror")
                     else self._scalable(sel) if tool == "scale"
                     else self._array_copyable(sel) if tool == "array"
                     else self._transformable(sel))
            s._ghost_dimmed = dim_items(acted)
        if tool in ("flip", "mirror") and s.mode == tool:
            # DD3: the acted-on silhouettes, mirrored per hovered axis.
            s._move_ghost_base = self._shape_paths_for_move(
                self._reflectable(sel))
            # Re-entry (Shift+F twice, Flip <-> Mirror) keeps the hovered
            # axis (clear() spares it), so its ghost is rebuilt here — the
            # next aim at the same segment is a no-op.
            if not self._axis_live(s._mirror_axis):
                s._mirror_axis = None
            s._move_ghost = self._reflected_ghost(s._mirror_axis)
        return True

    _PAST = {"flip": "flipped", "mirror": "mirrored", "scale": "scaled"}

    def nothing_to_hint(self, tool: str) -> str:
        """Refusal status when no selected item can take *tool* (DD4)."""
        return (f"Nothing to {tool} — only 2D drafting geometry can be "
                f"{self._PAST[tool]}")

    @staticmethod
    def _transformable(items) -> list:
        """The items a transform acts on — ``move_items``' filter (D11 dim).

        A Sprinkler resolves to its Node; otherwise an item qualifies if it
        is a Node or has ``translate`` / ``manip_translate``. Selectable items
        a Move cannot move (underlays) are left out, so they are never dimmed
        (their opacity is persisted by save).

        Args:
            items: Candidate items (usually the captured selection).

        Returns:
            The de-duplicated transformable items, in order.
        """
        from .node import Node
        out, seen = [], set()
        for it in items or ():
            if isinstance(it, Sprinkler) and it.node is not None:
                it = it.node
            if id(it) in seen:
                continue
            if (isinstance(it, Node) or hasattr(it, "translate")
                    or hasattr(it, "manip_translate")):
                seen.add(id(it))
                out.append(it)
        return out

    # ── Copy / Cut (D4) ─────────────────────────────────────────────────────

    CLIPBOARD_UNAVAILABLE = "Clipboard unavailable — nothing copied"

    def write_clipboard(self, items, base: QPointF):
        """Write *items* + *base* to the system clipboard (I1 payload).

        The write is read back: the OS clipboard can refuse it (another
        process holding it, a locked session), and Cut must never delete
        what it failed to copy.

        Args:
            items: Scene items to serialise.
            base: The copy base point (scene coordinates).

        Returns:
            The number of records written, or None if the write did not land.
        """
        import json
        from PyQt6.QtWidgets import QApplication
        from .constants import CLIPBOARD_FORMAT_VERSION
        s = self._scene
        data = s._clipboard_item_dicts(items)
        payload = {"fp3d_clipboard": CLIPBOARD_FORMAT_VERSION,
                   "base": [base.x(), base.y()],
                   "scene_role": s.scene_role, "items": data}
        text = json.dumps(payload)
        clip = QApplication.clipboard()
        clip.setText(text)
        if clip.text() != text:
            return None
        return len(data)

    def press_copy_base(self, event, pos, snapped, *_):
        """``copy_base`` click: the snapped base point commits Copy / Cut.

        Copy returns to Select with the selection intact; Cut deletes the
        selection in the same (single) undo step.
        """
        s = self._scene
        items = [it for it in (s._selected_items or s.selectedItems())
                 if it.scene() is s]
        n = self.write_clipboard(items, snapped)
        was_cut = s._copy_is_cut and n is not None
        if n is None:
            s._show_status(self.CLIPBOARD_UNAVAILABLE, 5000)
        elif was_cut:
            sel = list(items)
            s.blockSignals(True)
            try:
                s._bulk_delete(sel, set(sel))
            finally:
                s.blockSignals(False)
            s.selectionChanged.emit()
            s.push_undo_state()
            s._show_status(f"Cut {n} item(s)")
        else:
            s._show_status(f"Copied {n} item(s)")
        s._copy_is_cut = False
        s._selected_items = []
        s.set_mode(None)
        if not was_cut:
            for it in items:
                if it.scene() is s:
                    it.setSelected(True)

    # ── Paste (D5, D13) ─────────────────────────────────────────────────────

    def begin_paste(self) -> bool:
        """Validate the clipboard and arm ``paste`` with the ghost on the cursor.

        Refusals (empty / foreign clipboard, containment D13) leave the mode
        untouched and only post a status message.

        Returns:
            True if ``paste`` was entered.
        """
        s = self._scene
        payload = s.clipboard_payload()
        if not payload or not payload.get("items"):
            s._show_status("Nothing to paste", 3000)
            return False
        types = {d.get("type", "") for d in payload["items"]}
        if s.scene_role != "block_editor" and types & set(s._GEOM_TYPE_REGISTRY):
            s._show_status("2D geometry can only be pasted in the Block Editor", 4000)
            return False
        # D13 allow-list: the Block Editor accepts only what _add_from_dict
        # registers; anything else (plan entities, gridline records with no
        # type key, openings, view markers, …) refuses the whole paste.
        if s.scene_role == "block_editor" and not types <= (set(s._GEOM_TYPE_REGISTRY)
                                                            | {"block_instance"}):
            s._show_status("Plan elements can't be pasted into the Block Editor", 4000)
            return False
        s.set_mode("paste")
        s._paste_payload = payload
        # The copied base point is the anchor of the ghost and the dX/dY HUD.
        s.node_start_pos = QPointF(*payload["base"])
        s._move_ghost_base = self._clipboard_ghost_paths(payload["items"])
        s._move_ghost = []
        # D5: the ghost rides the cursor from the moment Paste is entered.
        if s._last_scene_pos is not None:
            self._preview_from_move(QPointF(s._last_scene_pos))
        return True

    def commit_paste(self, offset: QPointF) -> None:
        """Paste the armed payload once, translated by *offset*; one undo step."""
        s = self._scene
        records = s._paste_payload["items"]
        s.clearSelection()
        new_items = s.paste_items(offset, data=records)
        skipped = len(records) - len(new_items)
        if new_items:
            s.push_undo_state()
        s._paste_payload = None
        s.node_start_pos = None
        s._move_ghost = []
        s._move_ghost_base = []
        s.clear_placement_state()
        s.set_mode(None)
        if not new_items:
            s._show_status("Nothing pasted", 3000)
            return
        for it in new_items:
            it.setSelected(True)
        msg = f"Pasted {len(new_items)} item(s)"
        s._show_status(msg + (f" ({skipped} skipped)" if skipped else ""))

    def _apply_paste_displacement(self, params: dict) -> bool:
        """Typed dX/dY for ``paste`` (D5): commit one paste at base + offset.

        Args:
            params: ``resolve_displacement``'s output — ``{"offset": QPointF}``.

        Returns:
            True — the paste is unconditional.
        """
        self.commit_paste(params["offset"])
        return True

    # ── Offset (D9) ─────────────────────────────────────────────────────────
    # Scene transients: _offset_source (armed item), _offset_dist (magnitude),
    # _offset_side (+1 outward / left normal, -1 otherwise), _offset_typed
    # (distance locked by the HUD), _offset_sticky (last committed distance),
    # _offset_sticky_locked (that distance was typed, so it stays locked for
    # the next pick). The ghost is the candidate item's trace in _move_ghost.

    OFFSET_TOO_LARGE = "Offset too large"
    OFFSET_NO_DISTANCE = "Move the cursor or type a distance"
    OFFSET_SOURCE_GONE = "Offset source no longer exists — pick object to offset"

    def _fmt_len(self, mm: float) -> str:
        """Display-unit length (units-and-formatting.md: ScaleManager owns it)."""
        sm = getattr(self._scene, "scale_manager", None)
        return sm.format_length(mm) if sm is not None else f"{mm:.1f} mm"

    def _drop_dead_source(self) -> bool:
        """M-1: the armed source left the scene -> clear it, re-arm the pick.

        Returns:
            True when the source was dead (and has been dropped).
        """
        s = self._scene
        src = s._offset_source
        if src is None or src.scene() is s:
            return False
        s._move_ghost = []
        s.clear_placement_state()
        s.set_mode("offset")
        s._show_status(self.OFFSET_SOURCE_GONE, 3000)
        for v in s.views():
            v.viewport().update()
        return True

    @staticmethod
    def _offsettable(it) -> bool:
        """True for loose 2D geometry Offset can act on (D9: not Text)."""
        from .geometry_2d import Geometry2DMixin
        from .text_item import TextItem
        return (isinstance(it, Geometry2DMixin) and not isinstance(it, TextItem)
                and it.parentItem() is None)

    def begin_offset(self, sel) -> bool:
        """Enter Offset: arm the single selected offsettable item, else pick.

        Args:
            sel: The current selection.

        Returns:
            True — Offset never requires a selection (D3 exemption).
        """
        s = self._scene
        cands = [it for it in sel if self._offsettable(it)]
        s.set_mode("offset")
        if len(cands) == 1:
            self._arm_offset_source(cands[0])
        return True

    def _arm_offset_source(self, item) -> None:
        s = self._scene
        s.set_mode("offset_side")
        s._offset_source = item
        s._offset_side = 1.0
        locked = bool(s._offset_sticky_locked and s._offset_sticky)
        s._offset_typed = locked
        s._offset_dist = (s._offset_sticky or 0.0) if locked else 0.0
        s._move_ghost = []
        s.instructionChanged.emit(
            "Pick side to offset towards (or type a distance)")

    def press_offset(self, event, pos, snapped, *_):
        """``offset`` click: pick the offsettable item nearest the cursor."""
        from . import tool_geometry as tg
        s = self._scene
        hit = [i for i in s.items(pos) if self._offsettable(i)]
        if hit:
            self._arm_offset_source(
                min(hit, key=lambda i: tg.distance_to_item(i, pos)))

    def move_offset_side(self, event, snapped):
        """``offset_side`` cursor: side (+ distance unless locked); ghost follows."""
        from . import tool_geometry as tg
        s = self._scene
        s.preview_node.hide()
        s.preview_pipe.hide()
        src = s._offset_source
        if src is None or self._drop_dead_source():
            return
        if not s._offset_typed:
            s._offset_dist = tg.distance_to_item(src, snapped)
        s._offset_side = tg.offset_side_sign(src, snapped)
        self._refresh_offset_ghost()
        # Feed the Distance HUD its live seed (_transform_seed_values).
        s.publish_placement_state(snapped, snapped)

    def _offset_candidate(self):
        """The item a commit would create now, or None (degenerate / unarmed)."""
        from . import tool_geometry as tg
        s = self._scene
        if s._offset_source is None or s._offset_dist <= 0:
            return None
        return tg.offset_item(s._offset_source, s._offset_side * s._offset_dist)

    def _refresh_offset_ghost(self) -> None:
        from .transform_ghost import ghost_base_paths
        s = self._scene
        cand = self._offset_candidate()
        s._move_ghost = ghost_base_paths([cand]) if cand is not None else []
        if cand is None and s._offset_dist > 0:
            s._show_status(self.OFFSET_TOO_LARGE, 0)
        elif cand is not None:
            s._show_status(f"Offset: {self._fmt_len(s._offset_dist)}", 0)
        for v in s.views():
            v.viewport().update()

    def commit_offset(self) -> bool:
        """Create the offset item (source kept), one undo step, re-arm ``offset``.

        Returns:
            True when an item was created; False when unarmed, at zero
            distance, or too large inward ("Offset too large", nothing made).
        """
        s = self._scene
        if s._offset_source is None or self._drop_dead_source():
            return False
        if s._offset_dist <= 0:
            s._show_status(self.OFFSET_NO_DISTANCE, 3000)
            return False
        new = self._offset_candidate()
        if new is None:
            s._show_status(self.OFFSET_TOO_LARGE, 3000)
            return False
        # Register through the one deserialise-and-register helper (I1),
        # keyed by the item's own to_dict()["type"] (RefLine -> _reference_lines).
        if s._add_from_dict(new.to_dict()) is None:
            return False
        s.push_undo_state()
        s._offset_sticky = s._offset_dist
        s._offset_sticky_locked = bool(s._offset_typed)
        s._offset_source = None
        s._move_ghost = []
        s.clear_placement_state()
        s.set_mode("offset")                    # re-arm (D9 step 5)
        s._show_status(f"Offset {self._fmt_len(s._offset_sticky)}", 3000)
        return True

    def press_offset_side(self, event, pos, snapped, *_):
        """``offset_side`` click: commit on the cursor's side."""
        self.commit_offset()

    def apply_offset_distance(self, params: dict) -> bool:
        """Typed Distance (``distance`` schema): commit at that distance on the
        side the cursor last picked; a refusal keeps the HUD open."""
        from . import tool_geometry as tg
        s = self._scene
        typed = float(params["distance"])
        if typed < 0:
            s._show_status("Distance must be positive (0 = follow the cursor)", 3000)
            return False
        if typed == 0:
            # D-2: 0 releases a typed (locked) distance — the cursor drives
            # the distance again, from where it is now.
            s._offset_typed = False
            s._offset_sticky_locked = False
            p = s.get_resolved_point()
            src = s._offset_source
            s._offset_dist = (tg.distance_to_item(src, p)
                              if p is not None and src is not None else 0.0)
            self._refresh_offset_ghost()
            return True
        prev = (s._offset_dist, s._offset_typed)
        s._offset_dist = typed
        s._offset_typed = True
        if self.commit_offset():
            return True
        # Refused (commit_offset posted the reason): back to the cursor state,
        # whose ghost is still the one on screen.
        s._offset_dist, s._offset_typed = prev
        return False

    def clear(self, new_mode) -> None:
        """Idempotent teardown on every mode change (called from set_mode)."""
        s = self._scene
        # D11: every mode change (commit, Esc, tool switch) ends in set_mode,
        # so this is the one place the dimmed originals get their exact
        # prior opacity back.
        from .transform_ghost import restore_items
        restore_items(getattr(s, "_ghost_dimmed", None))
        s._ghost_dimmed = []
        # Every tool that paints into the shared ghost (Move / Duplicate /
        # Paste, Rotate, Flip / Mirror, Scale, Array, Offset) builds it AFTER
        # its set_mode — base click, begin_paste, begin_move_from, start() —
        # so no mode change ever hands a ghost on: a kept one is the previous
        # tool's silhouette painted under the next tool (seam review I-1).
        s._move_ghost = []
        s._move_ghost_base = []
        if new_mode != "paste":
            s._paste_payload = None
        if new_mode != "rotate":
            s._rotate_pivot = None
            s._rotate_start_deg = None
            s._rotate_ray = None
        if new_mode != "array":
            s._array_base = None
            s._array_dir = None
            s._array_spacing = 0.0
            s._array_row_spacing = 0.0
            s._array_total = None
            s._array_start_deg = None
        if new_mode not in ("flip", "mirror"):
            # The axis paints in drawForeground; set_mode repaints every view
            # (detail views share the scene) right after this clear().
            s._mirror_axis = None
        if new_mode != "scale":
            s._scale_base = None
            s._scale_ref = None
        if new_mode not in ("offset", "offset_side"):
            s._offset_source = None
            s._offset_dist = 0.0
            s._offset_typed = False
            s._offset_sticky = None
            s._offset_sticky_locked = False
        if new_mode in (None, "select"):
            s._copy_is_cut = False
            s._selected_items = None

    # ── Move / Paste gesture ────────────────────────────────────────────────

    def _press_paste_move(self, event, pos, snapped, item_under, node_under, pipe_under):
        s = self._scene
        if s.mode == "paste":
            # D5: the base is armed by begin_paste — one click commits.
            if s._paste_payload is None or s.node_start_pos is None:
                s.set_mode(None)          # entered without begin_paste
                return
            self.commit_paste(CAD_Math.get_vector(s.node_start_pos, snapped))
            return
        if s.node_start_pos is None:
            s.node_start_pos = snapped
            s._move_ghost_base = s._build_move_ghost_base()
            s._begin_move_handle_snap(snapped)
        else:
            snapped = s._move_handle_snap(event, snapped)
            offset = CAD_Math.get_vector(s.node_start_pos, snapped)
            if s.mode == "duplicate":
                self.commit_duplicate(offset)
                return
            moved = list(s._selected_items or [])
            if s.mode == "move":
                s.move_items(offset)
            s.push_undo_state()
            s.node_start_pos = None
            s._move_ghost = []
            s._move_ghost_base = []
            s.set_mode(None)
            self._reselect(moved)         # D3: Select with the originals

    def _preview_from_move(self, target) -> None:
        """Slide the move/paste ghost silhouette so the base point lands on
        ``target``.

        Rebuilds ``_move_ghost`` (read by ``drawForeground`` block 8) as the
        base silhouette translated by ``target - node_start_pos`` and repaints.
        A no-op before the base point is set.
        """
        s = self._scene
        if s.node_start_pos is None:
            return
        offset = QPointF(target.x() - s.node_start_pos.x(),
                         target.y() - s.node_start_pos.y())
        s._move_ghost = [p.translated(offset.x(), offset.y())
                         for p in s._move_ghost_base]
        for v in s.views():
            v.viewport().update()

    def _move_paste_move(self, event, snapped):
        """Ghost preview for paste/move: silhouette rides the cursor after the
        base point is set. Before that, show the plain cursor marker."""
        s = self._scene
        if s.node_start_pos is None:
            s.update_preview_node(snapped)
            s.preview_pipe.hide()
            return
        snapped = s._move_handle_snap(event, snapped)
        s.preview_node.hide()
        s.preview_pipe.hide()
        offset = QPointF(snapped.x() - s.node_start_pos.x(),
                         snapped.y() - s.node_start_pos.y())
        s._preview_from_move(snapped)
        # Feed the dynamic-input HUD its live dX/dY seed (measured from the
        # base point in ``_transform_seed_values``).  The status-bar readout
        # below is a separate surface and stays: S1 retired the painted
        # on-canvas Dim HUD, which move never used, not the status line — and
        # it carries ``dist``, which the two-field HUD does not.  A no-op while
        # a field has focus, so a mid-edit reseed cannot land.  ``paste``
        # seeds its dX/dY from the copied base point the same way (D5).
        s.publish_placement_state(s.node_start_pos, snapped)
        s._show_status(
            f"dx={offset.x():.1f}  dy={-offset.y():.1f}  "
            f"dist={math.hypot(offset.x(), offset.y()):.1f}", timeout=0)

    def begin_move_from(self, base: QPointF) -> None:
        """Enter the Move tool on the current selection with *base* preset.

        Skips Move's first (base-point) click: the selection immediately rides
        the cursor from *base*, and the next click places it (same commit /
        undo / Esc as an ordinary Move). Used by Block Editor import to place
        geometry by its picked base point.

        Args:
            base: Scene point that tracks the cursor.
        """
        s = self._scene
        s.set_mode("move")
        # D11: the imported geometry rides the cursor like any Move — dim it.
        from .transform_ghost import dim_items
        s._ghost_dimmed = dim_items(self._transformable(s._selected_items or []))
        s.node_start_pos = QPointF(base)
        s._move_ghost_base = s._build_move_ghost_base()
        s._begin_move_handle_snap(s.node_start_pos)

    def _begin_move_handle_snap(self, base: QPointF) -> None:
        """S2: build the Move tool's HandleSnapSession once the base is set.

        Move and Duplicate only (a paste has no scene items yet). The moving
        set is what ``move_items`` will move (``_selected_items``, else the
        live selection) plus each Sprinkler's Node; for Move none of it is a
        target, for Duplicate the originals stay targets (D6). The
        picked base point is itself a handle (rest = the base): the
        destination has no cursor snap, so this is how "base onto a point"
        still lands.

        Args:
            base: The Move base point — the handle offsets' anchor.
        """
        s = self._scene
        s._move_handle_session = None
        view = s._snap_view()
        # Built regardless of the snap toggles (items are at rest until the
        # commit); _move_handle_snap gates its use per frame.
        if s.mode not in ("move", "duplicate") or view is None:
            return
        moving = list(s._selected_items or s.selectedItems())
        moving += [it.node for it in moving
                   if isinstance(it, Sprinkler) and it.node is not None]
        if moving:
            # Duplicate's originals stay put, so they remain targets (D6).
            s._move_handle_session = HandleSnapSession(
                s._snap_engine, s, view, moving, QPointF(base),
                extra_handles=[QPointF(base)],
                exclude_moving=(s.mode == "move"))

    def _move_handle_snap(self, event, snapped: QPointF) -> QPointF:
        """S2: after the Move base point, the selection's own snap points
        (and the base point) snap to geometry — handles only: the destination
        has no cursor snap (``get_effective_position`` returns the raw cursor
        in this step), so without a hit the destination is the raw cursor.

        *event* is the scene's ``QGraphicsSceneMouseEvent`` (dispatched from
        ``mousePressEvent`` / ``mouseMoveEvent``), so the raw cursor is
        ``event.scenePos()``; direct callers without one fall back to
        *snapped*.

        Returns:
            The corrected destination (winning handle exactly on its target;
            marker published to ``_snap_result``), else *snapped* unchanged
            (the raw cursor from a real mouse event).
        """
        s = self._scene
        hs = s._move_handle_session
        if (hs is None or s.mode not in ("move", "duplicate")
                or s.node_start_pos is None
                or not s._snap_enabled or not s._snap_engine.enabled):
            return snapped
        # Zoom/pan between the base click and here: re-collect the targets
        # (visible rect + aperture scale). Safe — the moved items are at rest
        # until the commit (the preview is a ghost).
        hs.sync_view(s._snap_view())
        scene_pos = getattr(event, "scenePos", None)
        raw = scene_pos() if scene_pos is not None else snapped
        hit = hs.best(raw)
        if hit is None:
            return snapped
        corrected, res = hit
        s._snap_result = res          # marker only (never a hysteresis held)
        # No ALIGN in the destination step (handles only); kept defensive for
        # direct callers that computed *snapped* through the picker.
        s._align_result = None
        s._align_track_ray = None
        return corrected

    def _apply_move_displacement(self, params: dict) -> bool:
        """Apply a typed dX/dY displacement (transform schema — dict, not point).

        The commit half of the ``move`` branch of :meth:`_press_paste_move`,
        so a typed displacement and a dragged one share ``move_items`` and one
        undo push.  ``paste`` has its own applier
        (:meth:`_apply_paste_displacement`, D5).

        Every displacement commits: unlike the length/radius/spacing schemas
        there is no magnitude floor, so this always reports success (decision
        D2's verdict is still returned for the dispatcher's sake).

        Args:
            params: ``resolve_displacement``'s output — ``{"offset": QPointF}``,
                already Y-flipped into scene coordinates.

        Returns:
            True — the move is unconditional.
        """
        s = self._scene
        if s.mode == "duplicate":
            self.commit_duplicate(params["offset"])
            return True
        moved = list(s._selected_items or [])
        s.move_items(params["offset"])
        s.push_undo_state()
        s.node_start_pos = None
        s._move_ghost = []
        s._move_ghost_base = []
        s.clear_placement_state()
        s.set_mode(None)
        self._reselect(moved)             # D3: Select with the originals
        return True

    def _reselect(self, items) -> None:
        """Re-select *items* after ``set_mode(None)`` auto-deselected them (D3).

        Skips items that were deleted (sip) or are no longer in this scene.
        """
        from PyQt6 import sip
        s = self._scene
        for it in items:
            if not sip.isdeleted(it) and it.scene() is s:
                it.setSelected(True)

    # ── Duplicate (D6) ──────────────────────────────────────────────────────

    def commit_duplicate(self, offset: QPointF) -> None:
        """Place one copy of the selection at *offset*; originals untouched.

        One undo step; returns to Select with the copies selected (D3).
        """
        s = self._scene
        src = [it for it in (s._selected_items or s.selectedItems())
               if it.scene() is s]
        # The same per-item serialiser + paste path as Copy/Paste, so every
        # selectable kind (2D geometry, text, nodes, gridlines, blocks) copies.
        records = s._clipboard_item_dicts(src)
        s.clearSelection()
        new_items = s.paste_items(offset, data=records)
        if new_items:
            s.push_undo_state()
        s._selected_items = []
        s.node_start_pos = None
        s._move_ghost = []
        s._move_ghost_base = []
        s.clear_placement_state()
        s.set_mode(None)
        if not new_items:
            s._show_status("Nothing duplicated", 3000)
            return
        for new in new_items:
            new.setSelected(True)
        skipped = len(records) - len(new_items)
        msg = f"Duplicated {len(new_items)} item(s)"
        s._show_status(msg + (f" ({skipped} skipped)" if skipped else ""))

    # ── Rotate (D8) ─────────────────────────────────────────────────────────
    # Angles are Y-up, CCW+ (scene Y is down): a +X point turned +90° about
    # the origin lands at scene (0, -100), visually up.

    @staticmethod
    def _heading(pivot: QPointF, p: QPointF) -> float:
        """Y-up heading (degrees, CCW+ from +X) of the ray *pivot* -> *p*."""
        return math.degrees(math.atan2(-(p.y() - pivot.y()), p.x() - pivot.x()))

    @staticmethod
    def _norm(d: float) -> float:
        """Normalise a sweep to (-180, 180]."""
        d = (d + 180.0) % 360.0 - 180.0
        return 180.0 if d == -180.0 else d

    def _rotatable(self, items) -> list:
        """The transformable *items* that can rotate right now.

        Uses the manipulator's ``item_capabilities`` (``manip_rotate`` plus
        any dynamic ``manip_capabilities()`` narrowing) — one source of truth
        for "can this item rotate".
        """
        from .selection_manipulator import item_capabilities
        return [it for it in self._transformable(items)
                if "rotate" in item_capabilities(it)]

    def rotate_delta_to(self, point) -> float:
        """Live relative sweep for *point* (0 until the start ray is picked).

        The one formula the ghost, the status readout and the HUD seed share.

        Args:
            point: The cursor (resolved) point, or None.

        Returns:
            The Y-up CCW+ sweep from the start ray to the pivot->*point* ray.
        """
        s = self._scene
        if (s._rotate_pivot is None or s._rotate_start_deg is None
                or point is None):
            return 0.0
        return self._norm(self._heading(s._rotate_pivot, point)
                          - s._rotate_start_deg)

    def press_rotate(self, event, pos, snapped, *_):
        """Rotate click: pivot, then start ray, then the end ray commits."""
        s = self._scene
        if s._rotate_pivot is None:
            s._rotate_pivot = QPointF(snapped)
            s._move_ghost_base = self._shape_paths_for_move(
                self._rotatable(s._selected_items))
            s._move_ghost = list(s._move_ghost_base)
            s.instructionChanged.emit(
                "Pick start of rotation (or type an angle)")
            return
        if s._rotate_start_deg is None:
            if (abs(snapped.x() - s._rotate_pivot.x()) < 1e-9
                    and abs(snapped.y() - s._rotate_pivot.y()) < 1e-9):
                return                    # a ray needs a direction
            s._rotate_start_deg = self._heading(s._rotate_pivot, snapped)
            s.instructionChanged.emit("Pick end of rotation (or type an angle)")
            return
        self.commit_rotate(self.rotate_delta_to(snapped))

    def move_rotate(self, event, snapped):
        """Rotate cursor: the ghost sweeps, the pivot->cursor ray follows."""
        s = self._scene
        s.preview_pipe.hide()
        if s._rotate_pivot is None:
            s.update_preview_node(snapped)
            return
        s.preview_node.hide()
        delta = self.rotate_delta_to(snapped)
        s._rotate_ray = (QPointF(s._rotate_pivot), QPointF(snapped))
        self.preview_rotate(delta)
        # Feed the HUD its live relative-angle seed (_transform_seed_values).
        s.publish_placement_state(s._rotate_pivot, snapped)
        s._show_status(f"Angle: {delta:.1f}°", timeout=0)

    def preview_rotate(self, delta_deg: float) -> None:
        """Rebuild the ghost as the base silhouette turned by *delta_deg*.

        ``QTransform.rotate`` is visually clockwise in the Y-down scene, so a
        Y-up CCW+ sweep maps to ``rotate(-delta_deg)``.
        """
        from PyQt6.QtGui import QTransform
        s = self._scene
        p = s._rotate_pivot
        if p is None:
            return
        t = (QTransform().translate(p.x(), p.y()).rotate(-delta_deg)
             .translate(-p.x(), -p.y()))
        s._move_ghost = [t.map(path) for path in s._move_ghost_base]
        for v in s.views():
            v.viewport().update()

    def commit_rotate(self, delta_deg: float) -> bool:
        """Rotate the selection by *delta_deg* (Y-up CCW+) about the pivot.

        Every item turns through its own ``manip_rotate`` (rectangles stay
        rectangles, D8). One undo step; returns to Select with the rotated
        items selected.

        Args:
            delta_deg: The relative sweep.

        Returns:
            True when something rotated; False with no pivot or when nothing
            selected can rotate ("Nothing to rotate", no undo step).
        """
        s = self._scene
        pivot = s._rotate_pivot
        if pivot is None:
            return False
        items = [it for it in (s._selected_items or [])
                 if it.scene() is s]
        targets = self._rotatable(items)
        if not targets:
            # Mirror Duplicate's "nothing created" path: no undo step.
            s._move_ghost = []
            s._move_ghost_base = []
            s.clear_placement_state()
            s._selected_items = []
            s.set_mode(None)
            for it in items:
                if it.scene() is s:
                    it.setSelected(True)
            s._show_status("Nothing to rotate", 3000)
            return False
        for it in targets:
            it.manip_rotate(float(delta_deg), QPointF(pivot))
        for it in targets:
            fitting = getattr(it, "fitting", None)
            if fitting is not None:
                fitting.update()
        tools = getattr(s, "_tools", None)
        if tools is not None:
            tools._solve_constraints()
        s.push_undo_state()
        s._move_ghost = []
        s._move_ghost_base = []
        s.clear_placement_state()
        s._selected_items = []
        s.set_mode(None)
        for it in items:
            if it.scene() is s:
                it.setSelected(True)
        skipped = len(items) - len(targets)
        msg = f"Rotated {len(targets)} item(s) {delta_deg:.1f}°"
        s._show_status(msg + (f" ({skipped} skipped)" if skipped else ""))
        return True

    def apply_rotate_by(self, params: dict) -> bool:
        """Typed relative angle (``rotate_by``): commit about the pivot."""
        return self.commit_rotate(float(params["delta_deg"]))

    # ── Flip / Mirror (P1 batch DD4) ────────────────────────────────────────
    # Select-first; ONE axis step: every move picks the nearest existing
    # straight segment (axis_picker.pick_axis; cursor SNAP + ALIGN are off in
    # get_effective_position — snapping-engine §3); click / Enter commits.
    # Flip reflects the originals in place; Mirror reflects copies. No HUD.

    NO_AXIS_HINT = "Pick a straight edge or reference line"

    def _reflectable(self, items) -> list:
        """The transformable *items* with a per-item ``manip_reflect`` (DD1).

        Text and block instances define none, so they are skipped.
        """
        return [it for it in self._transformable(items)
                if hasattr(it, "manip_reflect")]

    def _pick_tolerance(self) -> float:
        """Pick radius (scene units) for the transform tools' own picks — the
        Flip / Mirror axis and Scale's "reference = base" refusal: the snap
        aperture in px at the ACTIVE view's zoom (``_active_view_scale``,
        never ``views()[0]``)."""
        from . import snap_engine
        return snap_engine.px_to_scene(snap_engine.SNAP_TOLERANCE_PX,
                                       self._scene._active_view_scale())

    def _axis_live(self, axis) -> bool:
        """Whether *axis*'s source segment still exists: its item is alive,
        in this scene and visible (what ``pick_axis`` would accept)."""
        from PyQt6 import sip
        src = getattr(axis, "source", None)
        return (src is not None and not sip.isdeleted(src)
                and src.scene() is self._scene and src.isVisible())

    def _reflected_ghost(self, axis) -> list:
        """The ghost base reflected across *axis* ([] without an axis)."""
        from .transform_ghost import reflect_transform
        if axis is None:
            return []
        t = reflect_transform(axis.p1, axis.p2)
        return [t.map(p) for p in self._scene._move_ghost_base]

    @staticmethod
    def _same_axis(a, b) -> bool:
        """Whether two ``AxisPick``s (or None) are the same segment."""
        if a is None or b is None:
            return a is b
        return (a.source is b.source and a.p1 == b.p1 and a.p2 == b.p2)

    def aim_axis(self, point):
        """Pick the axis under *point*; store it scene-side; rebuild the ghost.

        Args:
            point: The raw cursor (scene).

        Returns:
            The ``AxisPick`` (painted by ``Model_View`` block 8a), or None —
            then no axis and no ghost are shown.
        """
        from .axis_picker import pick_axis
        s = self._scene
        # pick_axis only returns live, visible segments, so a stale axis
        # (its source removed) never survives an aim.
        axis = pick_axis(s, QPointF(point), self._pick_tolerance())
        if self._same_axis(axis, s._mirror_axis):
            return s._mirror_axis
        s._mirror_axis = axis
        s._move_ghost = self._reflected_ghost(axis)
        # MinimalViewportUpdate: the axis spans the whole view and lives in
        # drawForeground, so every view (detail views share the scene) is
        # repainted on each axis change — here, not only by the caller's
        # mouseMoveEvent sweep, because a click can change it too.
        for v in s.views():
            v.viewport().update()
        return axis

    def move_reflect(self, event, snapped):
        """Flip / Mirror cursor: detect the axis under the (raw) cursor."""
        s = self._scene
        s.preview_pipe.hide()
        s.preview_node.hide()
        self.aim_axis(snapped)

    def press_reflect(self, event, pos, snapped, *_):
        """Flip / Mirror click: commit on the axis under the click."""
        if self.aim_axis(snapped) is None:
            self._scene._show_status(self.NO_AXIS_HINT, 3000)
            return
        self.commit_reflect()

    def commit_reflect(self) -> bool:
        """Reflect across the hovered axis: Flip in place, Mirror as copies.

        One undo step; returns to Select with the originals (Flip) or the
        copies (Mirror) selected (D3). Text / blocks are skipped with a count.

        Returns:
            True when something was reflected; False with no axis (status
            hint, the tool stays live) or nothing reflectable (no undo step).
        """
        s = self._scene
        axis = s._mirror_axis
        if axis is not None and not self._axis_live(axis):
            # The source segment was removed (or hidden) since the last aim:
            # never reflect across a vanished edge — drop the stale axis.
            s._mirror_axis = axis = None
            s._move_ghost = []
            for v in s.views():
                v.viewport().update()
        if axis is None:
            s._show_status(self.NO_AXIS_HINT, 3000)
            return False
        mirror = s.mode == "mirror"
        p1, p2 = QPointF(axis.p1), QPointF(axis.p2)
        items = [it for it in (s._selected_items or []) if it.scene() is s]
        targets = self._reflectable(items)
        if mirror:
            result = []
            for it in targets:
                copy = s._add_from_dict(it.to_dict())
                if copy is not None:
                    copy.manip_reflect(p1, p2)
                    result.append(copy)
        else:
            for it in targets:
                it.manip_reflect(p1, p2)
            result = list(targets)
            tools = getattr(s, "_tools", None)
            if tools is not None and result:
                tools._solve_constraints()
        if result:
            s.push_undo_state()
        s._move_ghost = []
        s._move_ghost_base = []
        s.clear_placement_state()
        s._selected_items = []
        s.set_mode(None)
        s.clearSelection()
        self._reselect(result if mirror else items)
        # Non-reflectable items AND Mirror copies that failed to rebuild.
        skipped = len(items) - len(result)
        msg = f"{'Mirrored' if mirror else 'Flipped'} {len(result)} item(s)"
        s._show_status(msg + (f" ({skipped} skipped)" if skipped else ""))
        return bool(result)

    # ── Scale (P1 batch DD4) ────────────────────────────────────────────────
    # Uniform, in place: base (SNAP + ALIGN) -> reference point (= 1x) -> the
    # cursor distance from the base sets the factor (live ghost) -> click; or
    # type Factor (``scale_factor`` HUD) once the base is set.

    SCALE_REF_HINT = "Reference point must differ from the base point"
    SCALE_FACTOR_HINT = "Scale factor must be greater than 0"
    SCALE_NOOP_HINT = "Scale factor is 1 — nothing changed"

    def _scalable(self, items) -> list:
        """The transformable *items* with a per-item ``manip_scale_about``
        (DD1); text and block instances define none and are skipped."""
        return [it for it in self._transformable(items)
                if hasattr(it, "manip_scale_about")]

    def scale_factor_to(self, point) -> float:
        """Live factor for *point*: |point − base| / |ref − base| (1.0 until
        the reference is picked). The one formula the ghost, the status
        readout and the HUD seed share."""
        s = self._scene
        base, ref = s._scale_base, s._scale_ref
        if base is None or ref is None or point is None:
            return 1.0
        d_ref = math.hypot(ref.x() - base.x(), ref.y() - base.y())
        if d_ref < 1e-9:
            return 1.0
        return math.hypot(point.x() - base.x(), point.y() - base.y()) / d_ref

    def press_scale(self, event, pos, snapped, *_):
        """Scale click: base, then reference (≠ base), then the commit."""
        s = self._scene
        if s._scale_base is None:
            s._scale_base = QPointF(snapped)
            s._move_ghost_base = self._shape_paths_for_move(
                self._scalable(s._selected_items))
            s._move_ghost = []
            s.instructionChanged.emit("Pick reference point (or type a factor)")
            return
        if s._scale_ref is None:
            # Within the pick aperture (screen px at the active view's zoom)
            # of the base, |ref - base| is too short to measure a factor
            # against — cursor jitter would swing it wildly.
            if (math.hypot(snapped.x() - s._scale_base.x(),
                           snapped.y() - s._scale_base.y())
                    <= self._pick_tolerance()):
                s._show_status(self.SCALE_REF_HINT, 3000)
                return
            s._scale_ref = QPointF(snapped)
            s.instructionChanged.emit("Pick new size (or type a factor)")
            return
        self.commit_scale(self.scale_factor_to(snapped))

    def move_scale(self, event, snapped):
        """Scale cursor: after the reference, the ghost scales live."""
        s = self._scene
        s.preview_pipe.hide()
        if s._scale_base is None:
            s.update_preview_node(snapped)
            return
        s.preview_node.hide()
        # Feed the HUD its live Factor seed (_transform_seed_values).
        s.publish_placement_state(s._scale_base, snapped)
        if s._scale_ref is None:
            return
        f = self.scale_factor_to(snapped)
        self.preview_scale(f)
        s._show_status(f"Factor: {ScaleManager.format_factor(f)}", timeout=0)

    def preview_scale(self, factor: float) -> None:
        """Rebuild the ghost as the base silhouette scaled about the base."""
        from .transform_ghost import scale_transform
        s = self._scene
        if s._scale_base is None:
            return
        t = scale_transform(s._scale_base, factor)
        s._move_ghost = [t.map(p) for p in s._move_ghost_base]
        for v in s.views():
            v.viewport().update()

    def commit_scale(self, factor: float) -> bool:
        """Scale the selection by *factor* about the base (one undo step).

        Returns to Select with the originals selected (D3); text / blocks are
        skipped with a count.

        Args:
            factor: The uniform factor (strictly > 0).

        Returns:
            True when something scaled; False when refused (no base, or factor
            <= 0 — status hint, the tool stays live), nothing scalable, or
            a factor of 1 (a no-op: the tool ends, no undo step).
        """
        s = self._scene
        base = s._scale_base
        if base is None:
            return False
        factor = float(factor)
        if not math.isfinite(factor) or factor <= 0.0:
            s._show_status(self.SCALE_FACTOR_HINT, 3000)
            return False
        items = [it for it in (s._selected_items or []) if it.scene() is s]
        noop = abs(factor - 1.0) <= 1e-9
        # Factor 1 changes nothing: end the tool like a commit, but push no
        # undo step (P1 DD4 review M4).
        targets = [] if noop else self._scalable(items)
        for it in targets:
            it.manip_scale_about(QPointF(base), factor)
        if targets:
            tools = getattr(s, "_tools", None)
            if tools is not None:
                tools._solve_constraints()
            s.push_undo_state()
        s._move_ghost = []
        s._move_ghost_base = []
        s.clear_placement_state()
        s._selected_items = []
        s.set_mode(None)
        self._reselect(items)
        if noop:
            s._show_status(self.SCALE_NOOP_HINT, 3000)
            return False
        skipped = len(items) - len(targets)
        msg = (f"Scaled {len(targets)} item(s) by "
               f"{ScaleManager.format_factor(factor)}")
        s._show_status(msg + (f" ({skipped} skipped)" if skipped else ""))
        return bool(targets)

    def apply_scale_factor(self, params: dict) -> bool:
        """Typed Factor (``scale_factor``): commit about the base.

        Returns:
            True when the tool ended (scaled, or a factor-1 no-op); False
            when refused and still live, which keeps the HUD open with a red
            field (``reject_commit``).
        """
        self.commit_scale(float(params["factor"]))
        return self._scene.mode != "scale"

    # ── Array (D10 + P1 DD5) ────────────────────────────────────────────────
    # Base point, then the cursor aims and a click / Enter commits; the HUD
    # types the variant's fields. Counts are TOTALS incl. the original. Copies
    # are independent (not associative); one undo step; back to Select with
    # the ORIGINAL selection. Transient scene state (_array_base, _array_dir,
    # _array_spacing) is cleared on leaving the mode; the session-sticky
    # _array_variant / _array_memory are never cleared (per canvas tab).

    # HUD fields remembered per variant after a typed commit: (field, param).
    # Cursor-driven fields (spacings, the polar sweep) are re-set by every aim
    # and never remembered — Polar Total is the cursor sweep (user decision
    # 2026-10-01, review I1): a typed Total commits as typed, nothing more.
    ARRAY_SCHEMA_FOR_VARIANT = {"linear": "array_linear", "grid": "array_grid",
                                "polar": "array_polar"}
    _ARRAY_MEMORY_FIELDS = {"linear": (("Count", "count"),),
                            "grid": (("Cols", "cols"), ("Rows", "rows")),
                            "polar": (("Count", "count"),)}
    _ARRAY_STEP2 = {
        "linear": "Pick spacing + direction (or type Angle / Spacing / Count)",
        "grid": "Pick the first cell's far corner (or type the grid)",
        "polar": "Sweep the fill angle (or type Count / Total)",
    }
    ARRAY_LINEAR_REFUSED = "Array needs a direction, Spacing > 0 and Count ≥ 2"
    ARRAY_GRID_REFUSED = ("2D array needs Cols × Rows ≥ 2 and a non-zero "
                          "spacing along every axis with more than one")
    ARRAY_POLAR_REFUSED = "Polar array needs Count ≥ 2 and 0° < Total ≤ 360°"
    ARRAY_POLAR_NOTHING = "Nothing to array — no selected item can rotate"
    ARRAY_NOTHING_COPYABLE = ("Nothing to array — the selection has nothing "
                              "Array can copy (e.g. walls, rooms, floors, roofs)")

    @staticmethod
    def _unit(deg: float) -> QPointF:
        """Scene unit vector of a Y-up CCW+ heading (scene Y is down)."""
        r = math.radians(deg)
        return QPointF(math.cos(r), -math.sin(r))

    def array_seed_angle(self) -> float:
        """The Angle the HUD shows: the lock, else the live Linear aim, else 0."""
        s = self._scene
        if s._array_angle_locked is not None:
            return s._array_angle_locked
        if s._array_variant == "linear" and s._array_dir is not None:
            return self._heading(QPointF(0.0, 0.0), s._array_dir)
        return 0.0

    def note_typed_angle(self, angle) -> None:
        """Lock or release the array direction from a committed HUD Angle (DD5).

        The HUD never reports an empty field — a blank ``DimensionEdit``
        keeps its seeded value — so typed-vs-untouched is decided against the
        seed: 0 releases the lock; a value equal to the unlocked seed is the
        untouched readout and changes nothing; any other value locks.

        Args:
            angle: The resolved ``angle`` param, or None (Polar has none).
        """
        s = self._scene
        if angle is None:
            return
        angle = float(angle)
        if abs(angle) < 1e-9:
            # 0 releases the lock — and so does any multiple of 360 (360,
            # -360, 720 …), which ScaleManager.parse_angle normalises to 0
            # (review S5).
            s._array_angle_locked = None
            return
        if (s._array_angle_locked is None
                and abs(self._norm(angle - self.array_seed_angle())) < 1e-6):
            return
        s._array_angle_locked = angle
        if s._array_variant == "linear":
            s._array_dir = self._unit(angle)

    def _array_linear_dir(self):
        """Linear copy direction: the locked heading, else the cursor aim."""
        s = self._scene
        if s._array_angle_locked is not None:
            return self._unit(s._array_angle_locked)
        return s._array_dir

    def _array_grid_axes(self):
        """2D axes in scene coords: û along the lock (else +X) and v̂ = û
        turned +90° CCW in Y-up, i.e. scene ``(û.y, −û.x)`` — rows go UP."""
        u = self._unit(self._scene._array_angle_locked or 0.0)
        return u, QPointF(u.y(), -u.x())

    @staticmethod
    def polar_step(total_deg: float, count: int) -> float:
        """Polar pitch: a full 360° fills evenly (no copy lands on the
        original); a partial fill puts the last copy at ``total_deg``."""
        if abs(total_deg - 360.0) < 1e-9:
            return 360.0 / count
        return total_deg / (count - 1)

    def _array_copyable(self, items) -> list:
        """The transformable *items* a paste can re-create (review I3).

        Array copies through ``paste_items``, which has no branch for walls,
        rooms, floors, roofs or design areas; those are left out so the
        ghost, the dim and the "(k skipped)" count match what is created.
        """
        s = self._scene
        return [it for it in self._transformable(items)
                if all(s._paste_accepts(r)
                       for r in s._clipboard_item_dicts([it]) or [{}])]

    def _array_targets(self, items) -> list:
        """What the current variant arrays (and ghosts).

        Linear / 2D: every copyable item (:meth:`_array_copyable`). Polar:
        the copyable items Rotate can turn (``manip_rotate``) minus Nodes —
        a zero-offset node paste lands on its own original and dedupes
        (``add_node``).
        """
        from .node import Node
        copyable = self._array_copyable(items)
        if self._scene._array_variant == "polar":
            return [it for it in self._rotatable(copyable)
                    if not isinstance(it, Node)]
        return copyable

    def _array_refusal(self, targets) -> "str | None":
        """Why the base / centre pick is refused for *targets*, or None."""
        if targets:
            return None
        s = self._scene
        if (s._array_variant == "polar"
                and self._array_copyable(s._selected_items or [])):
            return self.ARRAY_POLAR_NOTHING
        return self.ARRAY_NOTHING_COPYABLE

    def _aim_array(self, snapped: QPointF) -> None:
        """Update the live aim from the base -> *snapped* ray.

        Linear unlocked: direction + spacing from the ray. Linear locked: the
        spacing is the ray's projection onto the locked direction (≤ 0 keeps
        the previous spacing — the direction never flips). A zero-length ray
        keeps the previous aim. 2D: the cursor is the first cell's diagonal
        corner — signed projections onto the column / row axes. Polar: the
        CCW sweep from the start ray sets Total; on the start ray it is a
        full 360°.
        """
        s = self._scene
        dx = snapped.x() - s._array_base.x()
        dy = snapped.y() - s._array_base.y()
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            return
        if s._array_variant == "grid":
            u, v = self._array_grid_axes()
            s._array_spacing = dx * u.x() + dy * u.y()
            s._array_row_spacing = dx * v.x() + dy * v.y()
            return
        if s._array_variant == "polar":
            sweep = (self._heading(s._array_base, snapped)
                     - (s._array_start_deg or 0.0)) % 360.0
            s._array_total = sweep if sweep > 1e-9 else 360.0
            return
        if s._array_angle_locked is not None:
            u = self._unit(s._array_angle_locked)
            s._array_dir = u
            proj = dx * u.x() + dy * u.y()
            if proj > 1e-9:
                s._array_spacing = proj
            return
        s._array_dir = QPointF(dx / length, dy / length)
        s._array_spacing = length

    def _array_live_params(self) -> dict:
        """Resolver-shaped params of a click / Enter commit: the cursor aim
        plus the remembered (typed or default) counts of the variant."""
        s = self._scene
        v = s._array_variant
        mem = s._array_memory[v]
        if v == "polar":
            total = (s._array_total if s._array_total is not None
                     else float(mem["Total"]))
            return {"count": int(mem["Count"]), "total_deg": total}
        if v == "grid":
            return {"angle": self.array_seed_angle(),
                    "col_spacing": s._array_spacing, "cols": int(mem["Cols"]),
                    "row_spacing": s._array_row_spacing,
                    "rows": int(mem["Rows"])}
        return {"angle": self.array_seed_angle(), "spacing": s._array_spacing,
                "count": int(mem["Count"])}

    def array_seed_values(self, schema_name: str) -> dict:
        """HUD seeds for an array schema: the live aim + remembered counts.

        Args:
            schema_name: The active array schema's name.

        Returns:
            Values keyed by field name (scene units).
        """
        p = self._array_live_params()
        if schema_name == "array_polar":
            return {"Count": max(2, p["count"]), "Total": p["total_deg"]}
        if schema_name == "array_grid":
            return {"Angle": p["angle"], "ColSpacing": p["col_spacing"],
                    "Cols": p["cols"], "RowSpacing": p["row_spacing"],
                    "Rows": p["rows"]}
        return {"Angle": p["angle"], "Spacing": p["spacing"],
                "Count": max(2, p["count"])}

    def _array_transforms(self, p: dict):
        """Per-copy transforms of the current variant, or the refusal reason.

        The one formula the ghost and the commit share (D11): the ghost maps
        the cached base paths through each transform; the commit pastes each
        copy at the transform's offset.

        Args:
            p: Resolver-shaped params (HUD-typed or the live aim).

        Returns:
            ``(transforms, None)`` or ``(None, reason)``.
        """
        if self._scene._array_variant == "polar":
            n, total = int(p["count"]), float(p["total_deg"])
            if n < 2 or not 0.0 < total <= 360.0 + 1e-9:
                return None, self.ARRAY_POLAR_REFUSED
            c = self._scene._array_base
            step = self.polar_step(total, n)
            # QTransform.rotate is visually CW in the Y-down scene, so the
            # Y-up CCW+ pose maps to rotate(-deg) — preview_rotate's sign.
            return [QTransform().translate(c.x(), c.y()).rotate(-k * step)
                    .translate(-c.x(), -c.y()) for k in range(1, n)], None
        if self._scene._array_variant == "grid":
            cols, rows = int(p["cols"]), int(p["rows"])
            csp, rsp = float(p["col_spacing"]), float(p["row_spacing"])
            if (cols < 1 or rows < 1 or cols * rows < 2
                    or (cols > 1 and abs(csp) < 1e-9)
                    or (rows > 1 and abs(rsp) < 1e-9)):
                return None, self.ARRAY_GRID_REFUSED
            u, v = self._array_grid_axes()
            return [QTransform.fromTranslate(
                        c * csp * u.x() + r * rsp * v.x(),
                        c * csp * u.y() + r * rsp * v.y())
                    for r in range(rows) for c in range(cols)
                    if (r, c) != (0, 0)], None
        n, sp = int(p["count"]), float(p["spacing"])
        d = self._array_linear_dir()
        if n < 2 or sp <= 0 or d is None:
            return None, self.ARRAY_LINEAR_REFUSED
        return [QTransform.fromTranslate(d.x() * sp * k, d.y() * sp * k)
                for k in range(1, n)], None

    def press_array(self, event, pos, snapped, *_):
        """Array click: the base point (Polar: the centre), then the next
        click commits."""
        s = self._scene
        if s._array_base is None:
            targets = self._array_targets(s._selected_items or [])
            why = self._array_refusal(targets)
            if why is not None:
                # Refused at the pick (review I3 / S3): the tool stays live
                # at step 0, so ←/→ can still pick another variant.
                s._show_status(why, 3000)
                return
            s._array_base = QPointF(snapped)
            s._move_ghost_base = self._shape_paths_for_move(targets)
            s._move_ghost = []
            if s._array_variant == "polar":
                # Start ray: centre -> centre of what is arrayed (0° when they
                # coincide); the cursor's CCW sweep from it is Total.
                box = QRectF()
                for path in s._move_ghost_base:
                    box = box.united(path.boundingRect())
                c = box.center()
                far = math.hypot(c.x() - snapped.x(), c.y() - snapped.y()) > 1e-9
                s._array_start_deg = self._heading(snapped, c) if far else 0.0
            s.instructionChanged.emit(self._ARRAY_STEP2[s._array_variant])
            return
        self._aim_array(snapped)
        self.commit_array()

    def move_array(self, event, snapped):
        """Array cursor: aim from the base; the ghost shows every copy."""
        s = self._scene
        s.preview_pipe.hide()
        if s._array_base is None:
            s.update_preview_node(snapped)
            return
        s.preview_node.hide()
        self._aim_array(snapped)
        self.preview_array()
        # Feed the HUD its live seeds (_transform_seed_values).
        s.publish_placement_state(s._array_base, snapped)
        s._show_status(self._array_readout(), timeout=0)

    def _array_readout(self) -> str:
        """Status-bar readout of what a click would commit now."""
        s = self._scene
        p = self._array_live_params()
        if s._array_variant == "polar":
            return (f"Count: {p['count']}  "
                    f"Total: {ScaleManager.format_span(p['total_deg'])}")
        # Review S4: the session-sticky Angle lock is always visible.
        lock = ("" if s._array_angle_locked is None else
                f"  Angle: {ScaleManager.format_angle(s._array_angle_locked)}"
                " (locked)")
        if s._array_variant == "grid":
            return (f"Cols: {p['cols']} × Rows: {p['rows']}  "
                    f"Col: {self._fmt_len(p['col_spacing'])}  "
                    f"Row: {self._fmt_len(p['row_spacing'])}" + lock)
        return (f"Spacing: {self._fmt_len(p['spacing'])}  Count: {p['count']}"
                + lock)

    def preview_array(self, params: dict | None = None,
                      typed: bool = False) -> None:
        """Rebuild the ghost: one transformed copy of the base paths per copy.

        D11: every copy the commit would create is ghosted (no cap) — and
        nothing the commit would refuse (no aim yet, Spacing 0, Count < 2).

        Args:
            params: HUD-resolved params (Tab field-commit), else the live aim.
            typed: True on a HUD field-commit — a typed Angle locks /
                releases the direction first (DD5).
        """
        s = self._scene
        if typed and params is not None:
            self.note_typed_angle(params.get("angle"))
        p = params if params is not None else self._array_live_params()
        transforms, _why = self._array_transforms(p)
        base = s._move_ghost_base
        if transforms and len(transforms) * len(base) > ARRAY_GHOST_FULL_MAX:
            # Review I2: a big array previews as one merged 1 px trace (no
            # HALO glow) — same geometry, a fraction of the paint cost.
            from .transform_ghost import LiteGhostPath
            lite = LiteGhostPath()
            for t in transforms:
                for path in base:
                    lite.addPath(t.map(path))
            s._move_ghost = [lite]
        else:
            s._move_ghost = ([t.map(path) for t in transforms for path in base]
                             if transforms else [])
        for v in s.views():
            v.viewport().update()

    def commit_array(self, params: dict | None = None) -> bool:
        """Create the current variant's copies of the selection; one undo step.

        Copies go through the same serialiser + ``paste_items(data=)`` path
        as Duplicate (the OS clipboard is never touched). Linear / 2D paste
        each copy at its offset; Polar pastes in place and turns each copy
        through its own ``manip_rotate`` about the centre (Rotate's loop),
        skipping what cannot rotate (counted in the status). Returns to
        Select with the ORIGINAL selection (D10).

        Args:
            params: HUD-resolved params, else the live aim + remembered counts.

        Returns:
            True when copies were created; False when refused (the tool stays
            live) or when nothing could be copied (no undo step, Select).
        """
        s = self._scene
        p = params if params is not None else self._array_live_params()
        transforms, why = self._array_transforms(p)
        if transforms is None:
            s._show_status(why, 3000)
            return False
        v = s._array_variant
        src = [it for it in (s._selected_items or []) if it.scene() is s]
        # The ghost's own targets (review I3): what paste_items can create,
        # and for Polar what can also turn.
        copy_src = self._array_targets(src)
        why_empty = self._array_refusal(copy_src)  # before _selected_items clears
        records = s._clipboard_item_dicts(copy_src)
        created = []
        if v == "polar":
            centre = QPointF(s._array_base)
            step = self.polar_step(float(p["total_deg"]), int(p["count"]))
            for k in range(1, int(p["count"])):
                new = s.paste_items(QPointF(0, 0), data=records) or []
                for it in self._rotatable(new):
                    it.manip_rotate(k * step, QPointF(centre))
                for it in new:
                    fitting = getattr(it, "fitting", None)
                    if fitting is not None:
                        fitting.update()
                created += new
            tools = getattr(s, "_tools", None)
            if tools is not None and created:
                tools._solve_constraints()
        else:
            for t in transforms:
                created += s.paste_items(QPointF(t.dx(), t.dy()),
                                         data=records) or []
        if created:
            s.push_undo_state()
        s._move_ghost = []
        s._move_ghost_base = []
        s.clear_placement_state()
        s._selected_items = []
        s.set_mode(None)
        # paste_items selects what it creates; D10 keeps the ORIGINALS.
        s.clearSelection()
        for it in src:
            if it.scene() is s:
                it.setSelected(True)
        if not created:
            s._show_status(why_empty or "Nothing arrayed", 3000)
            return False
        # A selected Sprinkler is arrayed through its Node (_transformable).
        covered = {id(it) for it in copy_src}
        skipped = sum(
            1 for it in src
            if id(it.node if isinstance(it, Sprinkler) and it.node is not None
                  else it) not in covered)
        msg = f"Arrayed {len(created)} item(s) ({len(transforms) + 1} total)"
        s._show_status(msg + (f" ({skipped} skipped)" if skipped else ""))
        return True

    def apply_array(self, params: dict) -> bool:
        """Typed HUD commit for the current array variant (DD5 router).

        On success the variant's non-cursor fields are remembered for the
        next Array on this canvas. A typed Angle locks / releases the
        direction first (it stays locked for the next Array).

        Args:
            params: The active array schema's resolver output.

        Returns:
            The commit verdict (False keeps the HUD open, flagged).
        """
        s = self._scene
        self.note_typed_angle(params.get("angle"))
        v = s._array_variant
        if not self.commit_array(params):
            return False
        mem = s._array_memory[v]
        for field, key in self._ARRAY_MEMORY_FIELDS[v]:
            mem[field] = params[key]
        return True

    # ── Ghost silhouettes ───────────────────────────────────────────────────

    def _shape_paths_for_move(self, items):
        """Scene-coord QPainterPath silhouettes for live scene *items*.
        Nodes have no useful shape() — emit a small cross marker."""
        from .model_space import _GHOST_NODE_MARKER_MM
        from .node import Node
        from .sprinkler import Sprinkler
        from .transform_ghost import ghost_base_paths
        paths = []
        for item in items:
            if isinstance(item, Sprinkler) and item.node is not None:
                item = item.node
            if isinstance(item, Node):
                c = item.scenePos()
                r = _GHOST_NODE_MARKER_MM
                p = QPainterPath()
                p.moveTo(c.x() - r, c.y()); p.lineTo(c.x() + r, c.y())
                p.moveTo(c.x(), c.y() - r); p.lineTo(c.x(), c.y() + r)
                paths.append(p)
                continue
            if isinstance(item, GridlineItem):
                # Ghost the centerline (grip endpoints), not the fat hit-strip
                # + bubbles that shape() returns.
                pts = item.grip_points()
                p = QPainterPath()
                p.moveTo(pts[0]); p.lineTo(pts[1])
                paths.append(p)
                continue
            # D11: trace the drawn geometry (halo_scene_path), not the fat
            # shape() hit region (double-rotated for rotated rects).
            traced = ghost_base_paths([item])
            if traced:
                paths.extend(traced)
                continue
            if hasattr(item, "sceneBoundingRect"):
                p = QPainterPath(); p.addRect(item.sceneBoundingRect())
                paths.append(p)
        return paths

    def _clipboard_ghost_paths(self, data):
        """Scene-coord silhouettes reconstructed from clipboard *data* dicts,
        without adding anything to the scene. Covers the copyable types."""
        from .model_space import _GHOST_NODE_MARKER_MM
        from .transform_ghost import ghost_base_paths
        paths = []
        if not data:
            return paths
        # One home for the type → class table (the scene's _add_from_dict
        # registry): the ghost can never disagree with what a paste creates.
        geom_ctors = {t: cls for t, (cls, _attr)
                      in self._scene._GEOM_TYPE_REGISTRY.items()}
        for obj in data:
            t = obj.get("type", "")
            if not t and "origin" in obj and "angle" in obj:
                # Gridline record: GridlineItem.to_dict() carries no "type".
                ox, oy = obj.get("origin", [0.0, 0.0])
                length = float(obj.get("length", 0.0))
                th = math.radians(float(obj.get("angle", 0.0)))
                p = QPainterPath(); p.moveTo(ox, oy)
                p.lineTo(ox + length * math.cos(th), oy - length * math.sin(th))
                paths.append(p)
            elif t == "node":
                c = QPointF(obj.get("x", 0.0), obj.get("y", 0.0))
                r = _GHOST_NODE_MARKER_MM
                p = QPainterPath()
                p.moveTo(c.x() - r, c.y()); p.lineTo(c.x() + r, c.y())
                p.moveTo(c.x(), c.y() - r); p.lineTo(c.x(), c.y() + r)
                for seg in obj.get("pipes", []):
                    p.moveTo(c.x(), c.y()); p.lineTo(seg.get("x", 0.0), seg.get("y", 0.0))
                paths.append(p)
            elif t in geom_ctors:
                try:
                    item = geom_ctors[t].from_dict(obj)
                except Exception:
                    continue
                paths.extend(ghost_base_paths([item]))
        return paths

    def _build_move_ghost_base(self):
        """Base silhouettes (offset 0) of the live selection (Move/Duplicate).
        Paste builds its own from the payload (``begin_paste``)."""
        s = self._scene
        return s._shape_paths_for_move(s._selected_items or s.selectedItems())
