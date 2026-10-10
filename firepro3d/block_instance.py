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
from PyQt6.QtGui import QBrush, QPainterPath, QPen, QColor, QTransform
from PyQt6.QtWidgets import QGraphicsObject, QGraphicsItem

from . import crisp_stroke as _cs
from . import end_render as _er
from . import hatch_render as _hr
from . import linetype_render as _lr
from . import paper_display as _pd
from .block_definition import BlockDefinition
from .constants import LINETYPE_WINDOW_MIN_PERIODS
from .geometry_2d import constraint_tint
from .render_op import STROKE, FILL, PATTERN, TEXT, apply_overrides
from .stroke_style import (BY_BLOCK, BY_CATEGORY, BY_LINETYPE, NO_ENDS, NONE,
                           canvas_px, has_ends, is_as_authored, is_end_ref,
                           is_linetype_ref, linetype_block,
                           normalize_overrides, override_args, resolve_ends,
                           resolve_stroke)

_PLACEHOLDER_MM = 200.0


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
        self._display_overrides: dict = {}   # LevelManager user-hidden guard reads this
        self.attributes: dict = {}
        # Placement Weight / Linetype override (linetypes.md WM2): As
        # Authored x2 by default; _ov_args is None while nothing overrides
        # (render_ops' fast path returns the definition's list itself).
        self.overrides: dict = normalize_overrides(None)
        self._ov_args = None
        self._ov_cache = None      # (base ops list, args, derived list)
        self._pose_x = 0.0
        self._pose_y = 0.0
        self._pose_rot = 0.0   # Y-up CCW degrees
        self._posed_cache = None   # (ops list, pose, posed path) — see _posed_path
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

    def render_ops(self):
        """The definition's compiled ops with this placement's override
        applied (WM2 H2) -- the base list itself while As Authored; else one
        derived list memoised on (base list identity, override args), held
        so its identity can't be recycled (the ``_posed_cache`` idiom)."""
        d = self.definition()
        base = d.render_ops() if d is not None else []
        a = self._ov_args
        if a is None:
            return base
        c = self._ov_cache
        if c is not None and c[0] is base and c[1] == a:
            return c[2]
        out = apply_overrides(base, *a)
        self._ov_cache = (base, a, out)
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

    # ── Geometry (pose-baked) ────────────────────────────────────────────
    def _local_path(self) -> QPainterPath:
        ops = self.render_ops()
        combined = QPainterPath()
        if not ops:
            if self.definition() is None:      # orphan placeholder
                h = _PLACEHOLDER_MM / 2.0
                combined.addRect(-h, -h, _PLACEHOLDER_MM, _PLACEHOLDER_MM)
                combined.moveTo(-h, -h)
                combined.lineTo(h, h)
            return combined
        for op in ops:
            combined.addPath(op.path)
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

    def geometric_rect(self) -> QRectF:
        """Pen-free posed geometry bounds (for origin / bbox computations)."""
        return self._posed_path().boundingRect()

    def boundingRect(self) -> QRectF:
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
        for printed_all, printed_scale, scr, miss in rows:
            # On a model canvas a Fixed-size end draws at the screen factor,
            # so only the Scale-with-zoom ends take the printed factor.
            printed = printed_scale if on_screen else printed_all
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
        """``(printed reach of every end, printed reach of the Scale-with-zoom
        ends, screen reach of the Fixed-size ends, missing)`` of every op of
        *ops* that draws an end (LT5 / ET1 bounds): the reaches unscaled
        (``end_render.ends_reach`` at unit factors -- a zero factor skips an
        end), so ``_ends_pad`` only scales them per call.

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
                                 _er.ends_reach(ends, printed=1.0, screen=0.0),
                                 _er.ends_reach(ends, printed=0.0, screen=1.0),
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

    def shape(self) -> QPainterPath:
        # Copy (implicitly shared, O(1)): callers may mutate what shape()
        # returns; the memoised path must stay intact.
        return QPainterPath(self._posed_path())

    # ── Paint ────────────────────────────────────────────────────────────
    def paint(self, painter, option, widget=None):
        pose = self.pose_transform()
        ops = self.render_ops()
        self._drew_screen = False               # ET1 spec C: set by _draw_op_ends
        self._paint_sf = None                   # set where the ends' factors are read
        if not ops:
            if self.definition() is None:      # orphan placeholder
                p = QPen(QColor("#c0392b"))
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
        for i, op in enumerate(ops):
            if op.kind in (FILL, PATTERN):
                xf.unposed()
                self._paint_fill_op(painter, pose, op)
                continue
            if op.kind == TEXT:
                xf.unposed()
                # Text op: the fill carries the colour, so selection/override
                # tint applies to the BRUSH.
                b = QBrush(QColor(op.colour or "#ffffff"))
                if override is not None:
                    b.setColor(override)
                # Selection is canvas feedback -- never plots (LT1-2).
                if selected and not on_paper:
                    b.setColor(QColor("#63BE8B"))  # accent; icon-style-guide token
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
                if selected and not on_paper:
                    p.setColor(QColor("#63BE8B"))  # accent; icon-style-guide token
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
            painter.drawPath(pose.map(op.path))
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
                b = QBrush(QColor(op.colour or "#ffffff"))
                if override is not None:
                    b.setColor(override)
                # Selection is canvas feedback -- never plots (LT1-2).
                if selected and not on_paper:
                    b.setColor(QColor("#63BE8B"))  # accent; icon-style-guide token
                if self._paper_pen_color is not None:
                    b.setColor(self._paper_pen_color)   # paper B&W/Custom (LT1-2)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(b)
            else:
                # Copy — the compiled op pen is shared by every instance.
                p = QPen(op.pen)
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
                if selected and not on_paper:
                    p.setColor(QColor("#63BE8B"))  # accent; icon-style-guide token
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
            painter.drawPath(pose.map(op.path))
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
        w = weight
        if w is None or w in (BY_BLOCK, BY_LINETYPE, BY_CATEGORY) or not self._paper_scale:
            return self._paper_pen_width
        return _pd.resolve_line_weight_mm(w) / max(self._paper_scale, 1e-9)

    def _paint_fill_op(self, painter, pose, op) -> None:
        """Fill / pattern op: boundary posed, pattern stamped in scene axes (D-A11)."""
        paint_fill = _hr.paint_fill              # module import (hot path)
        col = QColor(op.colour or "#888888")
        col.setAlpha(op.alpha)
        if op.kind == FILL:
            paint_fill(painter, pose.map(op.path), scene=self.scene(),
                       background=col, to_scene=self.sceneTransform())
        else:
            origin = pose.map(op.origin if op.origin is not None else QPointF(0, 0))
            paint_fill(painter, pose.map(op.path), scene=self.scene(),
                       tile_ref=op.tile_ref, colour=col,
                       origin=self.sceneTransform().map(origin), scale=op.scale,
                       to_scene=self.sceneTransform())

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

    def get_properties(self) -> dict:
        props = {
            "Type":         {"type": "label",     "value": "Block"},
            "Level":        {"type": "level_ref", "value": self.level},
            "Level Offset": {"type": "dimension", "value": self._fmt(self._level_offset_mm),
                             "value_mm": self._level_offset_mm},
            # "string" type → editable numeric line-edit (matches the
            # RegularPolygonItem / EllipseItem Rotation convention).
            "Rotation":     {"type": "string",    "value": f"{self._pose_rot:.1f}"},
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
        return props

    def set_property(self, key: str, value) -> None:
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
        elif key in ("Weight", "Linetype"):
            if self._overrides_locked():
                return                  # Q12: a mixed selection can't bypass the lock
            self._set_override_from_panel(key, str(value))

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
        if not is_as_authored(self.overrides):
            d["overrides"] = dict(self.overrides)
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
        inst.attributes = dict(data.get("attributes", {}))
        inst.set_overrides(data.get("overrides"))
        if data.get("uid"):
            inst._uid = str(data["uid"])
        return inst
