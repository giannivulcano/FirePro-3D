"""TagPlacementController -- the SB6 ``"tag"`` mode (design
docs/superpowers/specs/2026-11-15-sb6-placed-tags-design.md D7).

Hover over a wall, door, window or opening previews the host category's
resolved tag at the cursor (the place_block ghost: a free-standing
``_is_ghost`` ``BlockInstance`` traced into the scene's shared
``_move_ghost``); a click places one tag bound to that host
(``Model_Space.place_block_instance(..., host_uid=, tag=)``, one undo step);
the mode stays armed until Esc. Openings are hit before walls (a door sits
inside its wall). The Leader toggle lives on the scene (``tag_leader_on``,
D8). A plain behaviour home like ``FeaturePlacementController``: the only
state is the hover prototype.
"""
from __future__ import annotations

import math

from PyQt6.QtGui import QTransform

from . import hosted_tag
from .constants import (TAG_HOVER_HINT, TAG_INSTRUCTION, TAG_NO_BLOCK,
                        TAG_ORIENT_HORIZONTAL)


class TagPlacementController:
    """Behaviour home of the ``"tag"`` mode (see the module docstring)."""

    def __init__(self, scene):
        self._scene = scene
        self.ghost = None        # the free-standing prototype (never in the scene)
        self._ghost_key = None   # (block id, host uid) it was traced for
        self._hint = None        # the instruction last emitted (no repeat per move)

    # -- Host lookup ------------------------------------------------------------
    @staticmethod
    def _on_opening(op, pos) -> bool:
        """*pos* lies on *op*'s footprint in its wall (width x wall thickness)
        or on its drawn symbol (``shape()``, the swing included)."""
        w = op.wall
        if w is None:
            return False
        c = op.center_on_wall()
        a = w.centerline_angle_rad()
        dx, dy = pos.x() - c.x(), pos.y() - c.y()
        along = dx * math.cos(a) + dy * math.sin(a)
        cross = -dx * math.sin(a) + dy * math.cos(a)
        if abs(along) <= op.width_scene() / 2.0 and abs(cross) <= w.half_thickness_scene():
            return True
        return op.contains(op.mapFromScene(pos))

    def find_host_at(self, pos):
        """The taggable element under *pos*: a wall opening first, else a wall
        (the ``_find_wall_at`` hit test, but only a wall that is on this scene and
        visible -- a hidden wall on another level is not taggable), else None."""
        s = self._scene
        for wall in s._walls:
            for op in wall.openings:
                if op.scene() is s and op.isVisible() and self._on_opening(op, pos):
                    return op
        for wall in s._walls:
            if wall.scene() is s and wall.isVisible() and wall.shape().contains(pos):
                return wall
        return None

    # -- Hover / place ------------------------------------------------------------
    def _instruct(self, text: str) -> None:
        if text != self._hint:
            self._hint = text
            self._scene.instructionChanged.emit(text)

    def move(self, snapped) -> None:
        """Mouse move in ``"tag"`` mode: preview the resolved tag at the cursor
        over a taggable host; nothing elsewhere (status hint)."""
        s = self._scene
        host = self.find_host_at(snapped)
        bid = hosted_tag.resolve(hosted_tag.new_record(), host, s) if host is not None else None
        if bid is None:
            self.clear_ghost()
            self._instruct(TAG_HOVER_HINT)
            return
        from .transform_ghost import GhostFrame, ghost_base_paths
        key = (bid, host._uid)
        if self.ghost is None or self._ghost_key != key:
            from .block_instance import BlockInstance
            g = BlockInstance(block_id=bid, resolver=s.get_block_definition,
                              level=s.active_level)
            g._is_ghost = True                  # continuous base geometry (LT3-6)
            g.element_host = host               # off-scene: the cached ref feeds the Mark
            g.refresh_bound()
            g.set_block_pos(0.0, 0.0)
            self.ghost, self._ghost_key = g, key
            # Off-scene the prototype has no annotative factor of its own
            # (it would trace at authored mm, a sub-pixel dot): scale its
            # trace about the origin to the size the placed tag gets here.
            from .annotative import factor_on
            k = factor_on(g.definition(), s)
            sx = QTransform.fromScale(k, k)
            s._move_ghost_base = [sx.map(p) for p in ghost_base_paths([g])]
        s._move_ghost = GhostFrame(s._move_ghost_base,
                                   QTransform.fromTranslate(snapped.x(), snapped.y()))
        for v in s.views():
            v.viewport().update()
        self._instruct(TAG_INSTRUCTION)

    def press(self, snapped):
        """Click in ``"tag"`` mode: tag the host under the click; the ghost
        stays at the cursor so the next click tags again (R5)."""
        host = self.find_host_at(snapped)
        if host is None:
            self._scene._show_status(TAG_HOVER_HINT, timeout=2000)
            return None
        inst = self.place_at(host, snapped)
        self.move(snapped)
        return inst

    def place_at(self, host, pt):
        """Place one tag on *host* at scene *pt* (D7): Horizontal, offset from
        the host anchor, a straight leader when the scene's Leader toggle is
        on; one undo step. Returns the instance, or None."""
        s = self._scene
        from .hosted_blocks import ppm_of
        ppm = ppm_of(s)
        uv = hosted_tag.offset_from_scene(host, ppm, pt)
        if uv is None:
            return None
        rec = hosted_tag.new_record(uv, TAG_ORIENT_HORIZONTAL,
                                    leader=bool(getattr(s, "tag_leader_on", False)))
        bid = hosted_tag.resolve(rec, host, s)
        if bid is None:
            s._show_status(TAG_NO_BLOCK, timeout=3000)
            return None
        if rec["leader"] is not None:
            from .capabilities import ensure_end_available
            from .paper_display import tag_leader_end
            ensure_end_available(tag_leader_end(), s, outside_history=True)
        x, y, rot = hosted_tag.pose(rec, host, ppm)
        inst = s.place_block_instance(bid, (x, y), rotation=rot, level=host.level,
                                      host_uid=host._uid, tag=rec)
        if inst is None:
            return None
        inst.refresh_bound()
        s.push_undo_state()
        return inst

    # -- Teardown ---------------------------------------------------------------
    def clear_ghost(self) -> None:
        """Drop the hover preview (no-op without one)."""
        s = self._scene
        self.ghost = None
        self._ghost_key = None
        if s._move_ghost or s._move_ghost_base:
            s._move_ghost = []
            s._move_ghost_base = []
            for v in s.views():
                v.viewport().update()

    def clear(self, new_mode) -> None:
        """Idempotent teardown on every mode change (``Model_Space.set_mode``);
        the shared ghost itself is emptied by ``ModifyToolsController.clear``."""
        if new_mode != "tag":
            self.ghost = None
            self._ghost_key = None
            self._hint = None
