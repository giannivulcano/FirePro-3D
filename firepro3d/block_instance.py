"""BlockInstance — a lightweight placed reference to a BlockDefinition.

One QGraphicsObject per placement; no child items. Paints the definition's
SHARED render-ops under this instance's (position, rotation) pose, so N
instances of one block share a single geometry object. See
docs/specs/block-system.md.

The pose is baked into the *geometry* (applied in paint/boundingRect/shape),
NOT into the item's Qt ``transform()``/``pos()`` — those stay identity/origin.
This matches the construction-geometry items (``RectangleItem`` etc.) the
SelectionManipulator was built for, so the block moves in harmony with the
selection frame during a drag (the manipulator's held-transform preview
assumes ``transform()`` carries no pose).
"""

from __future__ import annotations

import math
import uuid
from typing import Callable, Optional
from PyQt6.QtCore import QRectF, QPointF, Qt
from PyQt6.QtGui import (QBrush, QPainterPath, QPainterPathStroker, QPen,
                         QColor, QPolygonF, QTransform)
from PyQt6.QtWidgets import QGraphicsObject, QGraphicsItem

from . import crisp_stroke as _cs
from . import end_render as _er
from . import hatch_render as _hr
from . import linetype_render as _lr
from . import paper_display as _pd
from . import theme as _theme
from .block_definition import BlockDefinition
from .block_pose import (check_scale, is_upright, pose_matrix, reflect_pose,
                         valid_scale)
from .colour_tokens import paint_resolver, resolve_colour
from .constants import (FILL_LEGACY_COLOUR, LINETYPE_WINDOW_MIN_PERIODS,
                        TOKEN_AUTO)
from .geometry_2d import constraint_tint
from .render_op import (STROKE, FILL, PATTERN, TEXT, RenderOp, apply_overrides,
                        pattern_orient as _pattern_orient)
from .scale_manager import ScaleManager
from .view_scale import scene_hit_width
from .stroke_style import (BY_CATEGORY, BY_LINETYPE, NO_ENDS, NONE,
                           canvas_px, has_ends, is_as_authored, is_end_ref,
                           is_linetype_ref, is_named_weight, linetype_block,
                           normalize_overrides, override_args, resolve_ends,
                           resolve_stroke)

_PLACEHOLDER_MM = 200.0


def _record_scale(rec: dict) -> float:
    """A record's ``"scale"`` (design DD7) via ``block_pose.valid_scale``.

    A corrupt value (non-numeric, non-finite or <= 0) loads as 1.0 with a
    warning rather than failing the whole load.

    Args:
        rec: An instance record (``to_dict`` / ``to_nested_dict`` shape).

    Returns:
        The stored scale, 1.0 when absent or corrupt.
    """
    raw = rec.get("scale", 1.0)
    s = valid_scale(raw, default=math.nan)
    if math.isnan(s):
        import logging
        logging.getLogger(__name__).warning(
            "block instance %r: invalid scale %r loaded as 1.0",
            rec.get("uid"), raw)
        return 1.0
    return s


class _PoseXf:
    """Per-paint world-transform toggle for ``BlockInstance`` ops (MW-7).

    The posed transform (pose x item frame) is composed once per paint and
    switched to / from with ``setWorldTransform`` -- no per-op painter
    ``save`` / ``restore``. Crisp stroke ops draw under it; every other op
    (fills, text, linetype expansions, paper strokes) calls ``unposed`` first.
    """

    __slots__ = ("_painter", "_base", "_pose", "_posed", "_on")

    def __init__(self, painter, pose: QTransform):
        self._painter = painter
        self._base = painter.worldTransform()
        self._pose = pose
        self._posed = None
        self._on = False

    def posed(self) -> None:
        """Switch the painter to the posed transform (composed once)."""
        if not self._on:
            if self._posed is None:
                self._posed = self._pose * self._base
            self._painter.setWorldTransform(self._posed)
            self._on = True

    def unposed(self) -> None:
        """Switch the painter back to the item frame it had at paint start."""
        if self._on:
            self._painter.setWorldTransform(self._base)
            self._on = False


class BlockInstance(QGraphicsObject):
    """A placed instance of a BlockDefinition (flyweight consumer)."""

    def __init__(self, *, block_id: str,
                 resolver: Callable[[str], Optional[BlockDefinition]],
                 level: str = "Level 1", level_offset_mm: float = 0.0):
        super().__init__()
        self.block_id = block_id
        self._resolver = resolver
        # Stable primitive id (parametric-constraint-system.md §6.1).
        self._uid: str = uuid.uuid4().hex
        # Level scope lives on the placed instance (containment C3): the block
        # definition's primitives are level-less; the instance carries a level +
        # Z/elevation offset and is filtered by the active level / view-range
        # exactly like any placed model entity (mirrors wall.z_range_mm).
        self.level = level
        self._level_offset_mm = float(level_offset_mm)
        # Gridline hosting (hosted-blocks D2): None for a level-scoped
        # instance; else the host record, single source of truth -- the plan
        # pose is derived from it (C3 amendment: gridline-scoped).
        self.host: Optional[dict] = None
        self._display_overrides: dict = {}   # LevelManager user-hidden guard reads this
        self.attributes: dict = {}
        # Placement Weight / Linetype override (linetypes.md WM2): As
        # Authored x2 by default; _ov_args is None while nothing overrides
        # (render_ops' fast path returns the definition's list itself).
        self.overrides: dict = normalize_overrides(None)
        self._ov_args = None
        self._ov_cache = None      # (base ops list, args, derived list)
        self._bound_cache = None   # (bound_prims list, key, bound ops) -- SB1a S2
        self._combined_cache = None  # (static list, bound list, static + bound)
        self._bound_builds = 0     # rebuild counter (G1 guard)
        self._pose_x = 0.0
        self._pose_y = 0.0
        self._pose_rot = 0.0   # Y-up CCW degrees
        self._pose_mirrored = False   # local x -> -x, innermost (design DD2)
        self._pose_scale = 1.0        # uniform, > 0
        self._posed_cache = None   # (ops list, pose, posed path) — see _posed_path
        self._snap_prims_cache = None  # (ops list, full pose, stand-ins) — see snap_primitives
        self._nested_handles_cache = None  # (ops, mirrored, scale, table) — sketch_adapters._nested_table
        self._area_cache = None        # (ops list, full pose, area path) — see halo_area_path
        self._shape_cache = None       # (ops list, (pose, hit width), shape) — see shape
        # Paper-render hooks (linetypes.md LT1-2 / H5): set only during a
        # viewport pass by paper_display._apply_block, None on the model canvas.
        self._paper_pen_width: Optional[float] = None
        self._paper_pen_color: Optional[QColor] = None
        # Paper mm per model mm during a viewport pass (LT2-5); None on canvas.
        self._paper_scale: Optional[float] = None
        # Placement-ghost preview (Model_Space._place_block_make_ghost): draws
        # on the continuous base geometry, no missing badge (LT3-6).
        self._is_ghost: bool = False
        self._lt_ref_cache = None   # (ops list, frozenset of stroke linetype ids)
        self._lt_exp_cache = None   # (ops list, {op index: (lt, factor, expansion, window, trims)})
        self._crisp_ops = None      # (ops list, {op index: SplitCache}) -- MW-7
        self._end_ops_cache = None  # (ops list, frozenset of explicit-end op indices) -- LT5
        self._end_trim_ops = None   # (ops list, {op index: (trims, trimmed path)}) -- LT5
        self._end_pad_cache = None  # (ops, registry, deps, rows) -- LT5 bounds (_end_pad_rows)
        self._drew_screen = False   # this paint drew a Fixed-size end at the screen factor (ET1)
        self._paint_sf = None       # this paint's end screen factor (None: not read / paper)
        self._screen_ends = False   # last model paint drew a Fixed-size end (ET1 spec C)
        # Missing id named in the tooltip (linetype_render.sync_missing_tooltip);
        # set here so paint reads a plain attribute (no getattr miss).
        self._lt_tip_id: Optional[str] = None
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        # ItemIsMovable off: native Qt drag is dead in plan view; the
        # SelectionManipulator drives movement via translate().
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

    # ── Definition access ────────────────────────────────────────────────
    def definition(self) -> Optional[BlockDefinition]:
        return self._resolver(self.block_id)

    def host_values(self) -> Optional[dict]:
        """The host-value provider seam (SB1a A2): ``{host_key: raw}`` or
        None (no host -> placeholders). SB2 / SB3 override on host-aware
        subclasses; a test stub returns a dict."""
        return None

    def set_attributes(self, values: dict) -> None:
        """Replace the instance's attribute values / host overrides (A4 / D4:
        a host key's presence is its override); repaint. Undo is the
        caller's (the dialog's one ``deferred_undo_push``)."""
        self.prepareGeometryChange()
        self.attributes = dict(values)
        self.update()

    def _bound_ops(self) -> list:
        """The per-instance bound text ops (design S2): one TEXT op per
        ``BoundPrim``, text resolved through ``resolve_values``, glyphs built
        by ``TextItem`` + ``_local_path``, mapped through the prim's
        definition-local transform then this pose's S.M. Memoised on (bound
        prim list identity, resolved strings, mirror, scale); the upright
        turn (A5) is applied at paint by ``_text_path`` via ``readable``."""
        d = self.definition()
        if d is None:
            return []
        bps = d.bound_prims()
        if not bps:
            return []
        from .block_attributes import resolve_fields, resolve_values
        values = resolve_values(d.effective_attributes(), self.attributes,
                                self.host_values())
        strings = tuple(resolve_fields(str(b.prim.get("text", "")), values)[0]
                        for b in bps)
        key = (strings, self._pose_mirrored, float(f"{self._pose_scale:.9g}"))
        c = self._bound_cache
        if c is not None and c[0] is bps and c[1] == key:
            return c[2]
        from .block_definition import _local_path
        from .text_item import TextItem
        sm = pose_matrix(0.0, 0.0, 0.0, self._pose_mirrored, self._pose_scale)
        out = []
        for b, s in zip(bps, strings):
            rec = dict(b.prim)
            rec["text"] = s
            item = TextItem.from_dict(rec)
            path = item.mapToParent(_local_path(item))
            centre = item.grip_points()[8]
            op = RenderOp(TEXT, path, colour=item.data.color,
                          text_frame=(centre.x(), centre.y(), float(item._angle)),
                          readable=bool(rec.get("keep_upright", False)))
            out.append(op.mapped(b.transform * sm))
        self._bound_cache = (bps, key, out)
        self._bound_builds += 1
        return out

    def render_ops(self):
        """The definition's compiled ops under this placement's mirror / scale
        variant (design DD4) with the override applied (WM2 H2) -- the
        variant list itself while As Authored; else one derived list memoised
        on (variant list identity, override args), held so its identity can't
        be recycled (the ``_posed_cache`` idiom). Followed by this instance's
        bound text ops (SB1a S2) when the definition has any -- the combined
        list is memoised so identity-keyed caches (posed path, shape, snap
        stand-ins) rebuild only when the static or bound part changes."""
        d = self.definition()
        base = (d.render_ops_variant(self._pose_mirrored, self._pose_scale)
                if d is not None else [])
        a = self._ov_args
        if a is None:
            static = base
        else:
            c = self._ov_cache
            if c is not None and c[0] is base and c[1] == a:
                static = c[2]
            else:
                static = apply_overrides(base, *a)
                self._ov_cache = (base, a, static)
        bound = self._bound_ops()
        if not bound:
            return static
        cc = self._combined_cache
        if cc is not None and cc[0] is static and cc[1] is bound:
            return cc[2]
        out = static + bound
        self._combined_cache = (static, bound, out)
        return out

    def set_overrides(self, ov, canonical: bool = True) -> None:
        """Replace the placement override (normalised); repaint.

        Args:
            ov: The override dict.
            canonical: False stores a named weight raw (not alias-mapped) --
                the Display Manager Cancel replay of a weight rename.
        """
        self.prepareGeometryChange()
        self.overrides = normalize_overrides(ov, canonical)
        a = override_args(self.overrides, canonical)
        self._ov_args = None if a == (None, None) else a
        self._ov_cache = None
        self.update()

    def on_definition_changed(self) -> None:
        """Called by the definition when its geometry changes: repaint."""
        self.prepareGeometryChange()
        self.update()

    # ── Pose (baked into geometry, not Qt transform) ─────────────────────
    def pose_transform(self) -> QTransform:
        """Local→scene mapping for this instance's (position, rotation)."""
        t = QTransform()
        t.translate(self._pose_x, self._pose_y)
        t.rotate(-self._pose_rot)          # Qt CW+, app Y-up CCW+
        return t

    def full_pose_transform(self) -> QTransform:
        """Local -> scene map incl. mirror + scale (design DD2). The painter
        stays on the rigid ``pose_transform``: mirror / scale live in the
        variant ops (``render_ops``)."""
        return pose_matrix(self._pose_x, self._pose_y, self._pose_rot,
                           self._pose_mirrored, self._pose_scale)

    def set_block_mirrored(self, mirrored: bool) -> None:
        """Set the mirror flag (local x -> -x, innermost -- design DD2).

        Args:
            mirrored: The new flag.
        """
        self.prepareGeometryChange()
        self._pose_mirrored = bool(mirrored)
        self.update()

    def block_mirrored(self) -> bool:
        """Whether this placement is mirrored (design DD2).

        Returns:
            The mirror flag.
        """
        return self._pose_mirrored

    def set_block_scale(self, scale: float) -> None:
        """Set the uniform scale (``block_pose.check_scale``).

        Args:
            scale: The new scale.

        Raises:
            ValueError: *scale* is not a finite number > 0.
        """
        s = check_scale(scale)
        self.prepareGeometryChange()
        self._pose_scale = s
        self.update()

    def block_scale(self) -> float:
        """This placement's uniform scale (design DD2).

        Returns:
            The scale (> 0).
        """
        return self._pose_scale

    def set_block_pos(self, x: float, y: float) -> None:
        self.prepareGeometryChange()
        self._pose_x, self._pose_y = float(x), float(y)
        self.update()

    def block_pos(self) -> tuple[float, float]:
        return (self._pose_x, self._pose_y)

    def to_nested_dict(self) -> dict:
        """Record for this instance nested inside a definition (no level — C3).

        Returns:
            A D2 ``block_instance`` primitive record (definition-local pose).
        """
        d = {"type": "block_instance", "block_id": self.block_id,
             "pos": [self._pose_x, self._pose_y], "rotation": self._pose_rot,
             "uid": self._uid}
        if self._pose_mirrored:
            d["mirrored"] = True
        if self._pose_scale != 1.0:
            d["scale"] = self._pose_scale
        if not is_as_authored(self.overrides):
            d["overrides"] = dict(self.overrides)
        return d

    def set_block_rotation(self, deg: float) -> None:
        self.prepareGeometryChange()
        self._pose_rot = float(deg)
        self.update()

    def block_rotation(self) -> float:
        return self._pose_rot

    def translate(self, dx: float, dy: float) -> None:
        """Move by (dx, dy) in scene mm (SelectionManipulator bake contract)."""
        self.prepareGeometryChange()
        self._pose_x += dx
        self._pose_y += dy
        self.update()

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        """Baked rotate by ``angle_deg`` (Y-up CCW+) about scene ``pivot``.

        The block's own rotation pivot is its insertion point, so turning by
        ``a2`` about ``pivot`` after ``a1`` about the insertion point equals
        turning the insertion point about ``pivot`` and rotating by
        ``a1 + a2`` about it. Rotating about the insertion point itself only
        changes the rotation. Not normalised (matches ``set_block_rotation``).
        """
        from .cad_math import CAD_Math
        p = CAD_Math.rotate_point(QPointF(self._pose_x, self._pose_y),
                                  pivot, -angle_deg)
        self.prepareGeometryChange()
        self._pose_x, self._pose_y = p.x(), p.y()
        self._pose_rot += float(angle_deg)
        self.update()

    def manip_reflect(self, p1: "QPointF", p2: "QPointF") -> None:
        """Baked mirror across the infinite line p1-p2 (design DD3).

        Degenerate axis = no-op (``geometry_2d._degenerate_axis``). The
        insertion point is mirrored; ``(rotation, mirrored)`` follow
        ``block_pose.reflect_pose``.
        """
        from .arc_math import yup_angle
        from .cad_math import CAD_Math
        from .geometry_2d import _degenerate_axis
        if _degenerate_axis(p1, p2):
            return
        p = CAD_Math.mirror_point(QPointF(self._pose_x, self._pose_y), p1, p2)
        rot, mir = reflect_pose(self._pose_rot, self._pose_mirrored,
                                yup_angle(p1, p2))
        self.prepareGeometryChange()
        self._pose_x, self._pose_y = p.x(), p.y()
        self._pose_rot, self._pose_mirrored = rot, mir
        self.update()

    def manip_scale_about(self, base: "QPointF", factor: float) -> None:
        """Baked uniform scale about scene *base* (design DD3). Never named
        ``manip_scale`` -- that name enables manipulator resize handles."""
        f = check_scale(factor, "scale factor")
        from .cad_math import CAD_Math
        p = CAD_Math.scale_point(QPointF(self._pose_x, self._pose_y), base, f)
        self.prepareGeometryChange()
        self._pose_x, self._pose_y = p.x(), p.y()
        self._pose_scale *= f
        self.update()

    def _text_path(self, op) -> QPainterPath:
        """A TEXT op's glyph path, turned 180 deg about its box centre when a
        mirror left it reading upside down under this rotation (DD6)."""
        fr = op.text_frame
        if not op.readable or fr is None:
            return op.path
        if is_upright(fr[2] + self._pose_rot):
            return op.path
        t = QTransform()
        t.translate(fr[0], fr[1])
        t.rotate(180.0)
        t.translate(-fr[0], -fr[1])
        return t.map(op.path)

    # ── Geometry (pose-baked) ────────────────────────────────────────────
    def _local_path(self) -> QPainterPath:
        """Combined path of the posed ops before the rigid pose: TEXT ops as
        paint draws them (``_text_path``, DD6), so bounds / shape / halo /
        ghosts cover a turned glyph; an orphan's placeholder under this
        placement's mirror / scale (S.M -- the caller adds T.R)."""
        ops = self.render_ops()
        combined = QPainterPath()
        if not ops:
            if self.definition() is None:      # orphan placeholder
                h = _PLACEHOLDER_MM / 2.0
                combined.addRect(-h, -h, _PLACEHOLDER_MM, _PLACEHOLDER_MM)
                combined.moveTo(-h, -h)
                combined.lineTo(h, h)
                if self._pose_mirrored or self._pose_scale != 1.0:
                    combined = pose_matrix(0.0, 0.0, 0.0, self._pose_mirrored,
                                           self._pose_scale).map(combined)
            return combined
        for op in ops:
            combined.addPath(self._text_path(op) if op.kind == TEXT else op.path)
        return combined

    def _posed_path(self, ops=None) -> QPainterPath:
        """Pose-mapped combined path, memoised on (compiled ops, pose).

        boundingRect / shape / paint ask for it several times per frame; the
        key is the definition's compiled op list (a new list on every content
        change, held here so its identity can't be recycled) plus the pose, so
        a stale path can't be served and no explicit invalidation is needed.
        *ops* is this call's ``render_ops()`` when the caller already has it.
        """
        if ops is None:
            ops = self.render_ops()
        pose = (self._pose_x, self._pose_y, self._pose_rot)
        c = self._posed_cache
        if c is not None and c[0] is ops and c[1] == pose and ops:
            return c[2]
        path = self.pose_transform().map(self._local_path())
        self._posed_cache = (ops, pose, path)
        return path

    def _pose_key(self) -> tuple:
        """The full pose as a cache key (mirror / scale included)."""
        return (self._pose_x, self._pose_y, self._pose_rot,
                self._pose_mirrored, self._pose_scale)

    def snap_primitives(self) -> tuple:
        """Posed scene-space stand-ins of this placement's primitives.

        ``((bounds, item), ...)`` -- *bounds* is the item's scene bounding
        rect padded by 1 mm (a horizontal line's rect is never empty), used
        by the snap engine to cull. Nested blocks' primitives included; text
        and scaffolding excluded (``block_snap_geometry.posed_primitives``).
        Memoised on (compiled ops, full pose) -- the ``_posed_path`` idiom:
        a content change compiles a new op list, so no explicit
        invalidation is needed.
        """
        ops = self.render_ops()
        key = self._pose_key()
        c = self._snap_prims_cache
        if c is not None and c[0] is ops and c[1] == key:
            return c[2]
        from .block_snap_geometry import posed_primitives
        items = posed_primitives(self.definition(), key)
        out = tuple((it.sceneBoundingRect().adjusted(-1.0, -1.0, 1.0, 1.0), it)
                    for it in items)
        self._snap_prims_cache = (ops, key, out)
        return out

    def geometric_rect(self) -> QRectF:
        """Pen-free posed geometry bounds (for origin / bbox computations)."""
        return self._posed_path().boundingRect()

    def boundingRect(self) -> QRectF:
        """The frame rect, grown to hold :meth:`shape`'s ~10 px hit band.

        Qt rejects an item by its bounding rect before testing ``shape()``,
        so the strokes' fattened band (half of ``scene_hit_width``) must fit
        inside -- zoomed out it outgrows the frame's fixed 2 mm pen margin.
        The selection frame keeps the un-grown rect (:meth:`manip_bounds`).
        """
        r = self._frame_rect()
        extra = scene_hit_width(self, 10.0, 6.0) / 2.0 - 2.0
        if extra > 0.0:
            r = r.adjusted(-extra, -extra, extra, extra)
        return r

    def manip_bounds(self) -> QRectF:
        """Scene box the selection frame wraps (selection-manipulator
        ``manip_bounds``): the frame rect, independent of the hit band."""
        return self.sceneTransform().mapRect(self._frame_rect())

    def _frame_rect(self) -> QRectF:
        """Posed geometry + 2 mm pen margin (+ missing-linetype badge and
        end-glyph pads): the bounds before the hit band."""
        ops = self.render_ops()
        r = self._posed_path(ops).boundingRect()
        m = 2.0  # pen margin (mm)
        r = r.adjusted(-m, -m, m, m)
        lc = self._lt_ref_cache               # inline hit of _linetype_ids
        ids = lc[1] if lc is not None and lc[0] is ops else self._linetype_ids(ops)
        if ids and self._has_missing_linetype(ops):
            # A missing linetype (LT3-10) draws its canvas glyph at the
            # insertion point, a fixed device size: bound it at this zoom only
            # while a reference is unresolved (a resolving linetype keeps the
            # Continuous bounds -- manipulator frame, copy base point).
            from .view_scale import scene_hit_width
            px = _lr.badge_pad_px()
            h = scene_hit_width(self, px, px)
            c = self.pose_transform().map(QPointF(0.0, 0.0))
            r = r.united(QRectF(c.x() - h, c.y() - h, 2 * h, 2 * h))
        ec = self._end_ops_cache              # inline hit of _end_ref_ops
        eo = ec[1] if ec is not None and ec[0] is ops else self._end_ref_ops(ops)
        if eo or ids:
            pad = self._ends_pad(ops, eo, ids)   # LT5: 0.0 when nothing draws
            if pad > 0.0:
                r = r.adjusted(-pad, -pad, pad, pad)
        return r

    def _end_ref_ops(self, ops) -> frozenset:
        """Indices of *ops*' stroke ops naming an explicit, visible end id
        (LT5), memoised on the compiled op list's identity (the
        ``_lt_ref_cache`` idiom). Empty for every legacy block -- its paint
        and bounds keep the pre-LT5 path."""
        c = self._end_ops_cache
        if c is None or c[0] is not ops:
            idx = frozenset(
                i for i, op in enumerate(ops)
                if op.ends is not None and any(
                    is_end_ref(r.get("end")) and r.get("visible", True)
                    for r in op.ends))
            c = self._end_ops_cache = (ops, idx)
        return c[1]

    def _ends_pad(self, ops, end_ops, lt_ids) -> float:
        """Scene-mm radius covering every end these ops draw (LT5 bounds).

        On a model canvas a Fixed-size end is bounded by its screen reach
        alone (unit reach x px/mm x scene mm per px at the current zoom; the
        zoom hook re-prepares, spec C) and a Scale-with-zoom end by its unit
        reach x the printed factor; off a model canvas (paper pass, sheet)
        every drawn end takes the printed factor. A missing end is bounded
        by the badge pad. Radial around the posed rect (ends attach at path
        endpoints inside it). 0.0 when nothing draws.
        """
        if self._is_ghost:
            return 0.0
        sc = self.scene()
        reg = getattr(sc, "block_registry", None) if sc is not None else None
        rows = self._end_pad_rows(ops, end_ops, lt_ids, reg)
        if not rows:
            return 0.0
        from .constants import FIXED_END_PX_PER_MM
        from .view_scale import scene_hit_width
        unit = scene_hit_width(self, 1.0, 1.0)      # scene mm per device px (linear)
        a = self._lt_args()
        on_screen = _lr.screen_fixed_here(paper_scale=a["paper_scale"], role=a["role"])
        ff = None
        pad = 0.0
        fixed = False
        for printed_all, printed_scale, scr, model, miss in rows:
            # On a model canvas a Fixed-size end draws at the screen factor
            # and a Model-scaled end at its own N (ET1 Q12, *model* is
            # already painter units), so only the Project Scale-with-zoom
            # ends take the printed factor.
            printed = printed_scale if on_screen else printed_all
            if model > 0.0 and on_screen:
                pad = max(pad, model)
            if printed > 0.0:
                if ff is None:
                    ff = _lr.printed_factor(**a)
                if ff > 0.0 and math.isfinite(ff):
                    pad = max(pad, printed * ff)
            if scr > 0.0 and on_screen:
                pad = max(pad, scr * FIXED_END_PX_PER_MM * unit)
                fixed = True
            if miss:
                pad = max(pad, _lr.badge_pad_px() * unit)
        if fixed:
            # Bounds follow the zoom from the first read, not the first
            # paint (an editor / load can zoom before any paint, spec C).
            _er.mark_screen_ends(self, True)
        return pad

    def _end_pad_rows(self, ops, end_ops, lt_ids, reg) -> tuple:
        """``(printed reach of every end, printed reach of the Project
        Scale-with-zoom ends, screen reach of the Fixed-size ends, model-
        canvas reach of the Model-scaled ends, missing)`` of every op of
        *ops* that draws an end (LT5 / ET1 bounds): the first three unscaled
        (``end_render.ends_reach`` at unit factors -- a zero factor skips an
        end), so ``_ends_pad`` only scales them per call; the fourth already
        at each end's own Model scale N (ET1 Q12).

        Candidates: the explicit-end ops (*end_ops*) plus -- only when one
        of *lt_ids* carries a default end -- the ops on such a linetype.
        boundingRect runs several times a frame, so the cascade is memoised
        on (compiled op list identity, *reg*) and the registry entries it
        read: each consulted id's definition object, version and compiled
        op list -- an end / linetype edit, add or removal re-resolves; a
        valid hit costs one registry get per consulted id.
        """
        c = self._end_pad_cache
        if c is not None and c[0] is ops and c[1] is reg:
            for i, d, v, o in c[2]:
                g = reg.get(i) if reg is not None else None
                if g is not d or (d is not None and (d.version != v
                                                     or d.render_ops() is not o)):
                    break
            else:
                return c[3]
        seen = {}

        def dep(i):
            if i and i not in seen:
                d = reg.get(i) if reg is not None else None
                seen[i] = (i, d, d.version if d is not None else None,
                           d.render_ops() if d is not None else None)

        for i in lt_ids:
            dep(i)
        dflt = (frozenset(i for i in lt_ids if _er.linetype_has_default_end(i, reg))
                if lt_ids else frozenset())
        rows = []
        if end_ops or dflt:
            for i in (range(len(ops)) if dflt else sorted(end_ops)):
                op = ops[i]
                if op.ends is None or (i not in end_ops and op.linetype not in dflt):
                    continue
                for r in op.ends:
                    if is_end_ref(r.get("end")):
                        dep(r.get("end"))
                rs = (resolve_stroke({"linetype": op.linetype,
                                      "weight": op.weight or BY_LINETYPE}, reg)
                      if is_linetype_ref(op.linetype) else None)
                lt = rs.lt if rs is not None else None
                if lt is not None:
                    dep(lt.start_end)
                    dep(lt.finish_end)
                ends = self._op_ends(op, lt, reg)
                if has_ends(ends):
                    rows.append((_er.ends_reach(ends, printed=1.0, screen=None),
                                 _er.ends_reach(ends, printed=1.0, screen=0.0,
                                                model=False),
                                 _er.ends_reach(ends, printed=0.0, screen=1.0,
                                                model=False),
                                 _er.ends_reach(ends, printed=0.0, screen=0.0),
                                 any(e.missing_id for e in ends)))
        rows = tuple(rows)
        self._end_pad_cache = (ops, reg, tuple(seen.values()), rows)
        return rows

    def _linetype_ids(self, ops) -> frozenset:
        """The distinct linetype ids *ops*' stroke ops name, memoised on the
        compiled op list's identity (held: a new list on every content
        change). Empty for a block with no linetype refs -- the pre-LT3
        paint / bounds path (LT3-11)."""
        c = self._lt_ref_cache
        if c is None or c[0] is not ops:
            ids = frozenset(op.linetype for op in ops
                            if op.kind == STROKE and is_linetype_ref(op.linetype))
            c = self._lt_ref_cache = (ops, ids)
        return c[1]

    def _has_missing_linetype(self, ops=None) -> bool:
        """True when a compiled stroke op names a linetype id that does not
        resolve to a linetype block (LT3-10, ``linetype_ref_missing``).

        The distinct ids are memoised on the compiled op list's identity; the
        registry lookup itself runs every call (a few dict gets), so a
        linetype added / removed later is seen without invalidation.
        """
        ids = self._linetype_ids(self.render_ops() if ops is None else ops)
        if not ids or self._is_ghost:
            return False
        sc = self.scene()
        reg = getattr(sc, "block_registry", None) if sc is not None else None
        return any(linetype_block(i, reg) is None for i in ids)

    def halo_trace_path(self, scene_scale=None) -> QPainterPath:
        """HALO / ghost trace: the drawn geometry (selection-mode §4.1).

        Unchanged from the ``shape()`` fallback it replaces (so Move / Paste
        ghosts and ``distance_to_item`` keep the block's look); its presence
        makes the block a non-area item -- interior hits come only from
        :meth:`halo_area_path`.
        """
        return QPainterPath(self._posed_path())

    def halo_area_path(self) -> QPainterPath:
        """Closed areas that count as a direct HALO hit.

        Fill / pattern clips (posed like the paint) and text frame boxes
        (full pose, DD2). A bound text op (SB1a S2) adds the box of its
        *resolved* glyphs as paint draws them (``_text_path``) -- the
        definition's frame boxes below are sized to the authored ``@[key]``
        token. Memoised on (compiled ops, full pose).
        """
        ops = self.render_ops()
        key = self._pose_key()
        c = self._area_cache
        if c is None or c[0] is not ops or c[1] != key:
            area = QPainterPath()
            pose = self.pose_transform()
            for op in ops:
                if op.kind in (FILL, PATTERN):
                    area = area.united(pose.map(op.path))
            for op in self._bound_ops():
                if op.kind != TEXT:
                    continue
                r = self._text_path(op).boundingRect()
                if r.isEmpty():
                    continue
                p = QPainterPath()
                p.addPolygon(QPolygonF([pose.map(r.topLeft()), pose.map(r.topRight()),
                                        pose.map(r.bottomRight()), pose.map(r.bottomLeft())]))
                p.closeSubpath()
                area = area.united(p)
            d = self.definition()
            if d is not None:
                full = self.full_pose_transform()
                for box in d.text_snap_points():
                    p = QPainterPath()
                    p.addPolygon(QPolygonF([full.map(box[i]) for i in (0, 2, 4, 6)]))
                    p.closeSubpath()
                    area = area.united(p)
            c = self._area_cache = (ops, key, area)
        return QPainterPath(c[2])

    def shape(self) -> QPainterPath:
        """Hit shape like loose primitives: the strokes fattened to ~10 px
        plus the :meth:`halo_area_path` areas -- an empty interior is no hit
        (click, crossing band). An orphan / empty block keeps its placeholder
        path. Memoised on (compiled ops, full pose, hit width); returns a
        copy (callers may mutate it)."""
        ops = self.render_ops()
        if not ops:
            return QPainterPath(self._posed_path(ops))
        w = scene_hit_width(self, 10.0, 6.0)
        key = (self._pose_key(), round(w, 6))
        c = self._shape_cache
        if c is not None and c[0] is ops and c[1] == key:
            return QPainterPath(c[2])
        strokes = QPainterPath()
        pose = self.pose_transform()
        for op in ops:
            if op.kind == STROKE:
                strokes.addPath(pose.map(op.path))
        st = QPainterPathStroker()
        st.setWidth(w)
        path = st.createStroke(strokes)
        area = self.halo_area_path()
        if not area.isEmpty():
            path = path.united(area)
        self._shape_cache = (ops, key, path)
        return QPainterPath(path)

    # ── Paint ────────────────────────────────────────────────────────────
    def paint(self, painter, option, widget=None):
        pose = self.pose_transform()
        ops = self.render_ops()
        self._drew_screen = False               # ET1 spec C: set by _draw_op_ends
        self._paint_sf = None                   # set where the ends' factors are read
        if not ops:
            if self.definition() is None:      # orphan placeholder
                p = QPen(QColor("#c0392b"))  # theme-exempt: missing-definition error red
                p.setCosmetic(True)
                painter.setPen(p)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(self._posed_path())
            return
        override = self._display_pen_color()   # display-manager / pre-highlight hook
        tint = constraint_tint(self)           # D39: stroke ops only (H-MW-g)
        selected = self.isSelected()
        lc = self._lt_ref_cache               # inline hit of _linetype_ids
        if not (lc[1] if lc is not None and lc[0] is ops else self._linetype_ids(ops)):
            # No linetype refs: the pre-LT3 path, zero LT3 bookkeeping (LT3-11);
            # LT5: only ops naming an explicit end id resolve ends there.
            ec = self._end_ops_cache          # inline hit of _end_ref_ops
            eo = ec[1] if ec is not None and ec[0] is ops else self._end_ref_ops(ops)
            miss = self._paint_plain_ops(painter, pose, ops, override, selected,
                                         tint, eo)
            if self._paint_sf is not None:     # paper passes never touch the mark
                _er.mark_screen_ends(self, self._drew_screen)
            if (miss or self._lt_tip_id is not None) and not self._is_ghost:
                _lr.sync_missing_tooltip(self, None, end_ids=miss)  # refs edited away
            return
        sc = self.scene()
        registry = getattr(sc, "block_registry", None) if sc is not None else None
        routed = not self._is_ghost             # ghosts stay continuous (LT3-6)
        on_paper = self._paper_pen_width is not None
        missing = None                          # first unresolvable linetype id
        # Per-paint memo (LT3-11 perf): every input below is global or
        # instance state that cannot change inside one paint, so each
        # distinct (linetype, weight) resolves once per paint and nothing
        # resolved here outlives it -- weight table / alias / Model Blocks /
        # Thin Lines / registry / drawing-scale edits reach the next paint.
        strokes = {}        # (linetype, weight) -> [rs, width, lt, factor, lod, fixed]
        dev_scale = None    # device px per local unit under the pose (lazy)
        win = False         # view_window key under the pose (LTS-8; lazy, Fixed only)
        paper_pass = None   # paper_display.paper_pass_active() (lazy)
        ff = None           # LT5 printed factor of the ends (lazy)
        sf = None           # ET1 screen factor of Fixed-size ends (lazy, with ff)
        miss_e = []         # LT5 missing end ids, in op order
        ec = self._end_ops_cache            # LT5 explicit-end ops (inline hit)
        eo = ec[1] if ec is not None and ec[0] is ops else self._end_ref_ops(ops)
        xf = _PoseXf(painter, pose)   # posed world transform, toggled per op (MW-7)
        rc = paint_resolver(self)     # each distinct colour once per paint (G12)
        sel = (QColor(_theme.detect().accent)       # canvas selection (R5)
               if selected and not on_paper else None)
        for i, op in enumerate(ops):
            if op.kind in (FILL, PATTERN):
                xf.unposed()
                self._paint_fill_op(painter, pose, op)
                continue
            if op.kind == TEXT:
                xf.unposed()
                # Text op: the fill carries the colour, so selection/override
                # tint applies to the BRUSH.
                b = QBrush(rc(op.colour or TOKEN_AUTO))
                if override is not None:
                    b.setColor(override)
                # Selection is canvas feedback -- never plots (LT1-2).
                if sel is not None:
                    b.setColor(sel)  # theme accent (R5)
                if self._paper_pen_color is not None:
                    b.setColor(self._paper_pen_color)   # paper B&W/Custom (LT1-2)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(b)
            else:
                key = (op.linetype, op.weight)
                ent = strokes.get(key)
                if ent is None:
                    ent = strokes[key] = self._resolve_op_stroke(
                        op, routed, registry, on_paper)
                rs, width, lt, factor, ok, fixed = ent
                if rs is not None and rs.missing_id and missing is None:
                    missing = rs.missing_id
                # Copy — the compiled op pen is shared by every instance.
                p = QPen(op.pen)
                if op.colour is not None:
                    p.setColor(rc(op.colour))
                if on_paper:
                    p.setCosmetic(False)          # true mm on paper (LT1-2)
                    p.setWidthF(width)
                else:
                    p.setCosmetic(True)           # canvas (LT2-4)
                    if width is not None:
                        p.setWidthF(width)
                if override is not None:
                    p.setColor(override)
                if tint is not None:
                    p.setColor(tint)              # pen COPY (MW-12)
                if sel is not None:
                    p.setColor(sel)  # theme accent (R5)
                if self._paper_pen_color is not None:
                    p.setColor(self._paper_pen_color)
                # LT5: this op's resolved ends and the trims they cut. Inline
                # gate (the _item_ends idiom): only an explicit-end op or one
                # on a linetype with a default end resolves; every other op
                # pays one frozenset test + two attribute reads.
                ends = NO_ENDS
                if routed and op.ends is not None:
                    rlt = rs.lt if rs is not None else None
                    if i in eo or (rlt is not None
                                   and (rlt.start_end or rlt.finish_end)):
                        ends = self._op_ends(op, rlt, registry)
                trims = _er.NO_TRIMS
                if ends is not NO_ENDS and has_ends(ends):
                    if dev_scale is None:
                        dev_scale = self._posed_device_scale(painter, pose, xf)
                    if ff is None:
                        a = self._lt_args()
                        ff = _lr.printed_factor(**a)
                        sf = _er.screen_factor(paper_scale=a["paper_scale"],
                                               role=a["role"], device_scale=dev_scale)
                    trims = _er.end_trims(ends, printed=ff, screen=sf)
                    if _er.short_on_screen(op.pieces, ends, trims, sf):   # ET1 Q7
                        trims = _er.NO_TRIMS
                        ends = _er.badges_only(ends)
                else:
                    ends = None
                if lt is not None and op.pieces:
                    # Expand definition-local under the pose (H3-f): one
                    # cached expansion shared by every instance.
                    xf.unposed()
                    if ok is None:              # LOD: once per entry per paint
                        if paper_pass is None:
                            paper_pass = _pd.paper_pass_active()
                        if paper_pass:
                            ok = True             # paper/PDF always expands
                        else:
                            if dev_scale is None:
                                painter.save()
                                painter.setWorldTransform(pose, True)
                                dev_scale = _hr._device_scale(painter)
                                painter.restore()
                            if factor is None:    # LTS-3 Fixed: this paint's scale
                                factor = ent[3] = self._linetype_factor(lt, dev_scale)
                            ok = (_lr.period_ok(lt, factor)
                                  and _lr.lod_ok_at(lt.period * factor, dev_scale))
                        ent[4] = ok
                    n = (_lr.periods_on(op.pieces, lt, factor)
                         if ok and fixed else None)
                    if ok and not (n is not None and n < 1.0):
                        # (LTS-7 / delta 2: a short op falls through to its plain
                        # stroke; LTS-8: a long Fixed op expands near the view)
                        w = None
                        if n is not None and n > LINETYPE_WINDOW_MIN_PERIODS:
                            if win is False:      # once per paint, long Fixed ops only
                                painter.save()
                                painter.setWorldTransform(pose, True)
                                win = _lr.view_window(painter)
                                painter.restore()
                            w = win
                        dash, dot = self._op_expansion(ops, i, op, lt, factor, w,
                                                       trims)
                        painter.save()
                        try:
                            painter.setWorldTransform(pose, True)
                            _lr.draw_expansion(painter, dash, dot, p)
                        finally:
                            painter.restore()
                        if ends is not None:
                            self._draw_op_ends(painter, op, ends, p, xf, ff, sf,
                                               miss_e)
                        continue
                self._stroke_op(painter, ops, i, op, pose, p, xf,
                                path=(None if trims == _er.NO_TRIMS else
                                      self._trimmed_op_path(ops, i, op, trims)))
                if ends is not None:
                    self._draw_op_ends(painter, op, ends, p, xf, ff, sf, miss_e)
                continue
            painter.drawPath(pose.map(self._text_path(op)))
        xf.unposed()
        if sf is not None:                      # paper passes never touch the mark
            _er.mark_screen_ends(self, self._drew_screen)
        miss_e = tuple(dict.fromkeys(miss_e))
        if routed and (missing or self._lt_tip_id or miss_e):
            _lr.sync_missing_tooltip(self, missing, end_ids=miss_e)  # names the ids (LT3-10)
        if missing:
            # Canvas-only glyph, once at the insertion point (LT3-10).
            if not _pd.paper_pass_active():
                _lr.paint_missing_badge(painter, pose.map(QPointF(0.0, 0.0)))

    def _paint_plain_ops(self, painter, pose, ops, override, selected,
                         tint=None, end_ops=frozenset()) -> tuple:
        """Paint *ops* of a block with no linetype refs (every stroke solid).

        The pre-LT3 loop: no linetype cascade, expansion memo or paper-pass
        read. The canvas width is reused while consecutive ops share a
        weight. LT5: stroke ops in *end_ops* (``_end_ref_ops``: an explicit
        end id) resolve their ends -- the registry, printed factor and posed
        device scale are read once per paint, lazily, only when such an op
        is met -- and draw trimmed + their ends; with *end_ops* empty (every
        legacy block) none of that is read and the loop is the pre-LT5 one.

        Returns:
            The missing end ids met, in op order (``()`` when none).
        """
        on_paper = self._paper_pen_width is not None
        last_w, last_px = None, None
        xf = _PoseXf(painter, pose)   # posed world transform, toggled per op (MW-7)
        rc = paint_resolver(self)     # each distinct colour once per paint (G12)
        sel = (QColor(_theme.detect().accent)       # canvas selection (R5)
               if selected and not on_paper else None)
        miss = []
        ff = sf = reg = None          # LT5 / ET1 lazies (ff None = not read yet)
        for i, op in enumerate(ops):
            if op.kind in (FILL, PATTERN):
                xf.unposed()
                self._paint_fill_op(painter, pose, op)
                continue
            if op.kind == TEXT:
                xf.unposed()
                # Text op: the fill carries the colour, so selection/override
                # tint applies to the BRUSH.
                b = QBrush(rc(op.colour or TOKEN_AUTO))
                if override is not None:
                    b.setColor(override)
                # Selection is canvas feedback -- never plots (LT1-2).
                if sel is not None:
                    b.setColor(sel)  # theme accent (R5)
                if self._paper_pen_color is not None:
                    b.setColor(self._paper_pen_color)   # paper B&W/Custom (LT1-2)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(b)
            else:
                # Copy — the compiled op pen is shared by every instance.
                p = QPen(op.pen)
                if op.colour is not None:
                    p.setColor(rc(op.colour))
                w = op.weight
                if on_paper:
                    p.setCosmetic(False)          # true mm on paper (LT1-2)
                    p.setWidthF(self._paper_op_width(w))
                else:
                    p.setCosmetic(True)           # canvas (LT2-4)
                    if w is not None:
                        if w != last_w or last_px is None:
                            last_w, last_px = w, canvas_px(w)
                        p.setWidthF(last_px)
                if override is not None:
                    p.setColor(override)
                if tint is not None:
                    p.setColor(tint)              # pen COPY (MW-12)
                if sel is not None:
                    p.setColor(sel)  # theme accent (R5)
                if self._paper_pen_color is not None:
                    p.setColor(self._paper_pen_color)
                if end_ops and i in end_ops and not self._is_ghost:
                    if ff is None:
                        sc = self.scene()
                        reg = (getattr(sc, "block_registry", None)
                               if sc is not None else None)
                        a = self._lt_args()
                        ff = _lr.printed_factor(**a)
                        dev = self._posed_device_scale(painter, pose, xf)
                        sf = self._paint_sf = _er.screen_factor(
                            paper_scale=a["paper_scale"], role=a["role"],
                            device_scale=dev)
                    ends = self._op_ends(op, None, reg)
                    if has_ends(ends):
                        trims = _er.end_trims(ends, printed=ff, screen=sf)
                        if _er.short_on_screen(op.pieces, ends, trims, sf):   # ET1 Q7
                            trims = _er.NO_TRIMS
                            ends = _er.badges_only(ends)
                        self._stroke_op(painter, ops, i, op, pose, p, xf,
                                        path=(None if trims == _er.NO_TRIMS else
                                              self._trimmed_op_path(ops, i, op, trims)))
                        self._draw_op_ends(painter, op, ends, p, xf, ff, sf, miss)
                        continue
                self._stroke_op(painter, ops, i, op, pose, p, xf)
                continue
            painter.drawPath(pose.map(self._text_path(op)))
        xf.unposed()
        return tuple(dict.fromkeys(miss))

    def _stroke_op(self, painter, ops, i, op, pose, pen, xf=None,
                   path=None) -> None:
        """Stroke op *i* of *ops* with *pen* (MW-7 / H-MW-f).

        Canvas (cosmetic) pens draw crisp: the op's definition-local path
        under the pose, its split cached per (ops list, op index, pose 2x2)
        -- never per paint, never on zoom. Paper (non-cosmetic) pens and paper
        passes keep the exact pre-MW call, gated before any split. *pen* is
        the painter-local copy (MW-12 tints it). *xf* is the paint's
        ``_PoseXf`` (None: a one-off posed transform for this op); the posed
        transform is left on for the next stroke op -- the caller switches
        back (``xf.unposed()``) before any other op and after its loop.
        *path* (LT5) replaces the op's own path -- its stroke trimmed for
        its ends -- with a split cache slot of its own; an empty one (over-
        trimmed) draws nothing.
        """
        if path is None:
            path, slot = op.path, i
        else:
            if path.isEmpty():
                return
            slot = -1 - i
        if not pen.isCosmetic() or _pd.paper_pass_active():
            if xf is not None:
                xf.unposed()
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(pose.map(path))
            return
        c = self._crisp_ops
        if c is None or c[0] is not ops:
            c = self._crisp_ops = (ops, {})
        cache = c[1].get(slot)
        if cache is None:
            cache = c[1][slot] = _cs.SplitCache()
        own = xf is None
        if own:
            xf = _PoseXf(painter, pose)
        xf.posed()
        try:
            _cs.stroke(painter, path, pen,
                       cache.get(path, painter.worldTransform()))
        finally:
            if own:
                xf.unposed()

    @staticmethod
    def _posed_device_scale(painter, pose, xf) -> float:
        """Device px per definition-local unit under *pose* (LT5; read once
        per paint). Switches *xf* back first so the pose is not applied
        twice."""
        xf.unposed()
        painter.save()
        try:
            painter.setWorldTransform(pose, True)
            return _hr._device_scale(painter)
        finally:
            painter.restore()

    def _op_ends(self, op, lt, registry):
        """Op *op*'s resolved ends (LT5) -- ``NO_ENDS`` for closed / unstyled
        ops (``op.ends`` None), ops without pieces, and -- with no visible
        explicit end id -- both slots None, or a linetype *lt* (the op's
        ``LinetypeDef``, None = Continuous) with no default (the cheap
        common case; the ``Geometry2DMixin._item_ends`` gate)."""
        e = op.ends
        if e is None or not op.pieces:
            return NO_ENDS
        s, f = e
        es, ef = s.get("end"), f.get("end")
        if not ((is_end_ref(es) and s.get("visible", True))
                or (is_end_ref(ef) and f.get("visible", True))):
            if es == NONE and ef == NONE:
                return NO_ENDS
            if lt is None or not (lt.start_end or lt.finish_end):
                return NO_ENDS
        return resolve_ends({"start": s, "finish": f}, lt, registry)

    def _draw_op_ends(self, painter, op, ends, pen, xf, ff, sf, missing) -> None:
        """Draw stroke op *op*'s resolved *ends* under the pose (LT5) with its
        painter-local *pen* -- every surface, never LOD-dropped; a missing
        end's canvas badge sits at that end -- and append its missing ids to
        *missing*. A Fixed-size end at the screen factor *sf* flags the paint
        (ET1 spec C). Leaves the posed transform on (the ``_stroke_op`` rule)."""
        xf.posed()
        if _er.paint_ends(painter, op.pieces, ends, pen, printed=ff, screen=sf,
                          scene=self.scene()):
            self._drew_screen = True
        missing.extend(e.missing_id for e in ends if e.missing_id)

    def _trimmed_op_path(self, ops, i, op, trims) -> QPainterPath:
        """Op *i*'s stroke with *trims* cut from its ends (LT5), held across
        paints on (compiled op list identity, op index, trims) -- the
        ``_op_expansion`` idiom."""
        c = self._end_trim_ops
        if c is None or c[0] is not ops:
            c = self._end_trim_ops = (ops, {})
        hit = c[1].get(i)
        if hit is not None and hit[0] == trims:
            return hit[1]
        path = _er.trimmed_path(op.pieces, *trims)
        c[1][i] = (trims, path)
        return path

    def _resolve_op_stroke(self, op, routed, registry, on_paper) -> list:
        """``[rs, width, lt, factor, None, fixed]`` for a stroke op -- once per distinct
        (linetype, weight) per paint (``paint``'s memo).

        LT3-8 cascade: linetype + resolved weight (By Linetype -> the
        linetype's dash weight when it has one). Continuous /
        unstyled ops never reach the resolver (LT3-11). *width* is the paper
        width on a viewport pass, else the cosmetic canvas px (None for an
        unweighted op: keep the compiled pen's width). *lt* is the linetype
        to expand (None: plain stroke) and *factor* its LT3-5 length factor;
        a non-positive / non-finite scaled period draws plain. The fifth slot
        is ``paint``'s lazily decided screen LOD for this entry; *fixed* marks a
        Fixed linetype on a model canvas (LTS-3), whose *factor* stays None
        until ``paint`` reads its device scale.
        """
        rs = None
        if routed and is_linetype_ref(op.linetype):
            rs = resolve_stroke({"linetype": op.linetype,
                                 "weight": op.weight or BY_LINETYPE}, registry)
        weight = rs.weight if rs is not None else op.weight
        if on_paper:
            width = self._paper_op_width(weight)
        else:
            width = canvas_px(weight) if weight is not None else None
        lt = rs.lt if rs is not None else None
        factor, fixed = None, False
        if lt is not None:
            a = self._lt_args()
            fixed = _lr.fixed_on_canvas(lt, paper_scale=a["paper_scale"],
                                        role=a["role"])
            if not fixed:                 # Fixed waits for this paint's scale
                factor = self._linetype_factor(lt)
                if not _lr.period_ok(lt, factor):
                    lt = None
        return [rs, width, lt, factor, None, fixed]

    def _op_expansion(self, ops, i, op, lt, factor, window=None,
                      trims=(0.0, 0.0)):
        """``linetype_render.expand`` for op *i* of *ops*, held across paints.

        Keyed on the compiled op list (held, so its identity can't be
        recycled -- the ``_posed_cache`` idiom; a new list on every content
        change), the op index, the linetype reading itself (a new object on
        a definition edit / version bump), the exact length factor and the
        visible window (LTS-8) and the LT5 end *trims* (dashes outside them
        dropped, phase untouched) -- every input of ``expand``, so a hit
        returns what ``expand`` would.
        """
        c = self._lt_exp_cache
        if c is None or c[0] is not ops:
            c = self._lt_exp_cache = (ops, {})
        hit = c[1].get(i)
        if (hit is not None and hit[0] is lt and hit[1] == factor
                and hit[3] == window and hit[4] == trims):
            return hit[2]
        a = op.origin or QPointF(0.0, 0.0)
        res = _lr.expand(op.pieces, lt, factor, (a.x(), a.y()), window=window,
                         trims=trims)
        c[1][i] = (lt, factor, res, window, trims)
        return res

    def _lt_args(self) -> dict:
        """Surface inputs of ``linetype_render.length_factor`` (LT3-5)."""
        sc = self.scene()
        sm = self._scale_manager()
        return {"paper_scale": self._paper_scale,
                "role": getattr(sc, "scene_role", None),
                "drawing_scale": sm.drawing_scale if sm is not None else None}

    def _linetype_factor(self, lt, device_scale=None) -> float:
        """LT3-5 length factor (``linetype_render.length_factor``)."""
        return _lr.length_factor(lt, device_scale=device_scale, **self._lt_args())

    def _paper_op_width(self, weight) -> float:
        """Non-cosmetic paper width for a stroke op's resolved *weight* (LT2-5).

        By Linetype (and a legacy un-migrated By Block), a placement By
        Category and unweighted ops take the category weight
        (``_paper_pen_width``); a named weight plots at its own mm divided by
        the viewport scale (the §9.9.1 pattern).
        """
        if not is_named_weight(weight) or not self._paper_scale:
            return self._paper_pen_width
        return _pd.resolve_line_weight_mm(weight) / max(self._paper_scale, 1e-9)

    def _paint_fill_op(self, painter, pose, op) -> None:
        """Fill / pattern op: boundary posed; pattern stamped in the pose's
        rotation / mirror frame, never its scale (D-A11 block-pose exception)."""
        paint_fill = _hr.paint_fill              # module import (hot path)
        col = resolve_colour(op.colour or FILL_LEGACY_COLOUR, item=self)
        col.setAlpha(op.alpha)
        if op.kind == FILL:
            paint_fill(painter, pose.map(op.path), scene=self.scene(),
                       background=col, to_scene=self.sceneTransform())
        else:
            st = self.sceneTransform()
            origin = pose.map(op.origin if op.origin is not None else QPointF(0, 0))
            paint_fill(painter, pose.map(op.path), scene=self.scene(),
                       tile_ref=op.tile_ref, colour=col,
                       origin=st.map(origin), scale=op.scale, to_scene=st,
                       orient=_pattern_orient(op.pattern_frame, pose, st))

    def _display_pen_color(self) -> Optional[QColor]:
        """Hook for display-manager 'Blocks' category colour + pre-highlight.

        v1 returns None (use each render-op's authored pen). Full display-manager
        wiring lands with S2/S4.
        """
        return None

    # ── Level scope (C3 — placed-instance property) ──────────────────────
    def z_range_mm(self) -> tuple[float, float] | None:
        """Elevation of this placed block in absolute mm, as a point ``(e, e)``.

        A block is a flat 2D graphic pinned to its level plane; ``e`` is the
        level elevation plus the instance offset. ``None`` when no LevelManager
        is reachable (mirrors ``wall.z_range_mm``).
        """
        if self.host:
            e = float(self.host["elevation_mm"])
            return (e, e)
        sc = self.scene()
        lm = getattr(sc, "_level_manager", None) if sc else None
        if lm is None:
            return None
        lvl = lm.get(self.level)
        e = (lvl.elevation if lvl is not None else 0.0) + self._level_offset_mm
        return (e, e)

    def _scale_manager(self):
        sc = self.scene()
        return getattr(sc, "scale_manager", None) if sc else None

    def _fmt(self, mm: float) -> str:
        sm = self._scale_manager()
        return sm.format_length(mm) if sm else f"{mm:.1f}"

    def _parse_dim(self, value) -> Optional[float]:
        if isinstance(value, (int, float)):
            return float(value)
        sm = self._scale_manager()
        if sm is not None:
            try:
                return sm.parse_dimension(str(value))
            except Exception:
                return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _fmt_factor(f: float) -> str:
        """The Scale row's text: the Scale HUD's FACTOR grammar (G8)."""
        return ScaleManager.format_factor(f)

    @staticmethod
    def _parse_factor(value) -> Optional[float]:
        """A Scale row entry as a block scale, or None when refused.

        Text goes through ``ScaleManager.parse_factor`` (the HUD grammar: no
        sign, no exponent, a trailing ``x`` tolerated); a number arrives as
        the row's committed ``value_mm``. Either way the result must satisfy
        ``block_pose.valid_scale`` (finite, > 0) -- the one scale rule.
        """
        if isinstance(value, bool):
            return None
        if not isinstance(value, (int, float)):
            value = ScaleManager.parse_factor("" if value is None else str(value))
            if value is None:
                return None
        return valid_scale(value, default=None)

    def get_properties(self) -> dict:
        props = {
            "Type":         {"type": "label",     "value": "Block"},
            "Level":        {"type": "level_ref", "value": self.level},
            "Level Offset": {"type": "dimension", "value": self._fmt(self._level_offset_mm),
                             "value_mm": self._level_offset_mm},
            # "string" type → editable numeric line-edit (matches the
            # RegularPolygonItem / EllipseItem Rotation convention).
            "Rotation":     {"type": "string",    "value": f"{self._pose_rot:.1f}"},
            # Design DD8 / G8: the pose rows stay together.
            "Mirrored":     {"type": "bool",      "value": self._pose_mirrored},
            # DimensionEdit seeds from value_mm and commits the parser's float;
            # minimum is strict (> 0), so "0" reverts in the widget.
            "Scale":        {"type": "dimension",
                             "value": self._fmt_factor(self._pose_scale),
                             "value_mm": self._pose_scale,
                             "parser": ScaleManager.parse_factor,
                             "formatter": self._fmt_factor, "minimum": 0.0},
        }
        # WM2 Q4: placement Linetype / Weight overrides; Q12: locked inside a
        # pattern-tile / linetype-unit Block Editor (strokes draw Continuous
        # at the pattern's own pen there).
        from .geometry_2d import _LOCKED_PLACEMENT_TIP, stroke_rows
        from .hatch_patterns import picker_exclude
        sc = self.scene()
        reg = getattr(sc, "block_registry", None) if sc is not None else None
        rows = stroke_rows(self.overrides, reg, picker_exclude(sc), placement=True)
        if self._overrides_locked():
            for k in ("Linetype", "Weight"):
                rows[k]["disabled"] = True
                rows[k]["tooltip"] = _LOCKED_PLACEMENT_TIP
        props.update(rows)
        # A1/D10: a nested child inside the Block Editor carries no instance
        # values (the nested record drops ``attributes``), so the row is off --
        # the scene's can_edit_attributes gate, shared with the context menus.
        has_attrs = bool(sc is not None and hasattr(sc, "can_edit_attributes")
                         and sc.can_edit_attributes(self))
        props["Edit attributes"] = {
            "type": "button", "value": "Edit attributes\u2026",
            "callback": self._open_edit_attributes, "enabled": has_attrs}
        return props

    def _open_edit_attributes(self) -> None:
        sc = self.scene()
        if sc is not None and hasattr(sc, "open_edit_attributes"):
            sc.open_edit_attributes(self)

    def _panel_state(self) -> tuple:
        """The values the Level / Level Offset / Rotation / Mirrored / Scale
        rows edit, compared before and after a commit (G9)."""
        return (self.level, self._level_offset_mm, self._pose_rot,
                self._pose_mirrored, self._pose_scale)

    def set_property(self, key: str, value) -> None:
        """Apply one panel row commit.

        Every row that changed something requests ONE undo step from the
        scene (G9): ``PropertyManager._apply_property`` runs inside
        ``Model_Space.deferred_undo_push``, which pushes only when a setter
        asks, so a row that stayed silent produced no step at all. A no-op
        commit (same value) stays silent. The Weight / Linetype path requests
        its own step (``_set_override_from_panel``).
        """
        before = self._panel_state()
        if key == "Level":
            self.level = str(value)
        elif key == "Level Offset":
            parsed = self._parse_dim(value)
            if parsed is not None:
                self._level_offset_mm = parsed
        elif key == "Rotation":
            try:
                self.set_block_rotation(float(value))
            except (TypeError, ValueError):
                pass
        elif key == "Mirrored":
            # The checkbox always hands a bool; anything else is ignored.
            if not isinstance(value, bool):
                return
            self.set_block_mirrored(bool(value))
        elif key == "Scale":
            f = self._parse_factor(value)
            if f is not None:           # refused input: unchanged, no step
                self.set_block_scale(f)
        elif key in ("Weight", "Linetype"):
            if self._overrides_locked():
                return                  # Q12: a mixed selection can't bypass the lock
            self._set_override_from_panel(key, str(value))
            return                      # requests its own undo step
        else:
            return
        if self._panel_state() != before:
            sc = self.scene()
            req = getattr(sc, "request_undo_push", None) if sc is not None else None
            if callable(req):
                req()                   # G9: one step per panel commit (coalesced)

    def _overrides_locked(self) -> bool:
        """True inside a pattern-tile / linetype-unit Block Editor (WM2 Q12),
        where strokes draw Continuous at the pattern's own pen, so the
        placement Linetype / Weight rows are locked."""
        sc = self.scene()
        return sc is not None and (getattr(sc, "block_tile", None) is not None
                                   or getattr(sc, "block_repeat", None) is not None)

    def _set_override_from_panel(self, key: str, value: str) -> None:
        """Apply a panel pick to the placement override (WM2 Q4/Q5).

        A value outside this row's option set (a primitive's "By Linetype
        (...)", an unknown name, "Missing (<id>)") changes nothing. A
        Linetypes-folder pick is loaded into the project first (its load is
        the undo step); any other change requests one undo step.
        """
        from . import stroke_style as ss
        from .paper_display import weight_names
        from .linetype_choices import (ensure_linetype_available,
                                       is_missing_label,
                                       linetype_ref_from_value)
        from .hatch_patterns import picker_exclude
        new = dict(self.overrides)
        if key == "Weight":
            if value == ss.AS_AUTHORED_LABEL:
                new["weight"] = ss.AS_AUTHORED
            elif value.startswith(ss.BY_CATEGORY_LABEL):
                new["weight"] = ss.BY_CATEGORY
            elif value in weight_names():
                new["weight"] = value
            else:
                return
        else:
            if value == ss.AS_AUTHORED_LABEL:
                new["linetype"] = ss.AS_AUTHORED
            elif is_missing_label(value):
                return                       # LT3-10: never rewrite a missing ref
            else:
                sc = self.scene()
                reg = getattr(sc, "block_registry", None) if sc is not None else None
                ref = linetype_ref_from_value(value, reg, picker_exclude(sc))
                if ref is None:
                    return
                if ss.is_linetype_ref(ref) and reg is not None and reg.get(ref) is None:
                    # Set before the load so its one undo snapshot carries the
                    # new ref; a failed load restores the old override.
                    old = self.overrides
                    self.set_overrides({**new, "linetype": ref})
                    if not ensure_linetype_available(ref, sc):
                        self.set_overrides(old)
                    return
                new["linetype"] = ref
        if ss.normalize_overrides(new) == self.overrides:
            return                                   # no-op commit: no step
        self.set_overrides(new)
        sc = self.scene()
        req = getattr(sc, "request_undo_push", None) if sc is not None else None
        if callable(req):
            req()

    # ── Serialization ────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        d = {
            "type": "block_instance",
            "block_id": self.block_id,
            "pos": [self._pose_x, self._pose_y],
            "rotation": self._pose_rot,
            "level": self.level,
            "attributes": dict(self.attributes),
            "uid": self._uid,
        }
        if self._level_offset_mm != 0.0:
            d["level_offset_mm"] = self._level_offset_mm
        if self._pose_mirrored:
            d["mirrored"] = True
        if self._pose_scale != 1.0:
            d["scale"] = self._pose_scale
        if not is_as_authored(self.overrides):
            d["overrides"] = dict(self.overrides)
        if self.host:
            d["host"] = dict(self.host)
        return d

    @classmethod
    def from_dict(cls, data: dict,
                  resolver: Callable[[str], Optional[BlockDefinition]]) -> "BlockInstance":
        inst = cls(block_id=data["block_id"], resolver=resolver,
                   level=data.get("level", "Level 1"),
                   level_offset_mm=data.get("level_offset_mm", 0.0))
        pos = data.get("pos", [0.0, 0.0])
        inst._pose_x, inst._pose_y = float(pos[0]), float(pos[1])
        inst._pose_rot = float(data.get("rotation", 0.0))
        inst._pose_mirrored = bool(data.get("mirrored", False))
        inst._pose_scale = _record_scale(data)
        inst.attributes = dict(data.get("attributes", {}))
        inst.set_overrides(data.get("overrides"))
        if data.get("uid"):
            inst._uid = str(data["uid"])
        if data.get("host"):
            inst.host = dict(data["host"])
        return inst

    @classmethod
    def place_kwargs(cls, rec: dict, default_level: Optional[str] = None) -> dict:
        """``Model_Space.place_block_instance`` kwargs from an instance record
        (``.fpd`` dict, undo snapshot, clipboard, nested record) -- the one
        field-carrying choke point (design DD7).

        Args:
            rec: A ``to_dict`` / ``to_nested_dict`` record.
            default_level: Level when the record names none (a nested record
                never does -- C3); None lets the scene use its active level.

        Returns:
            The pose / level / override kwargs (``uid`` stays the caller's:
            only restore paths carry it).
        """
        return {"rotation": float(rec.get("rotation", 0.0)),
                "mirrored": bool(rec.get("mirrored", False)),
                "scale": _record_scale(rec),
                "level": rec.get("level", default_level),
                "level_offset_mm": float(rec.get("level_offset_mm", 0.0)),
                "overrides": rec.get("overrides"),
                "host": rec.get("host")}
