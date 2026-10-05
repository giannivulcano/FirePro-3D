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

import uuid
from typing import Callable, Optional
from PyQt6.QtCore import QRectF, QPointF, Qt
from PyQt6.QtGui import QBrush, QPainterPath, QPen, QColor, QTransform
from PyQt6.QtWidgets import QGraphicsObject, QGraphicsItem

from . import hatch_render as _hr
from . import linetype_render as _lr
from . import paper_display as _pd
from .block_definition import BlockDefinition
from .render_op import STROKE, FILL, PATTERN, TEXT
from .stroke_style import (BY_BLOCK, BY_LINETYPE, canvas_px, is_linetype_ref,
                           resolve_stroke)

_PLACEHOLDER_MM = 200.0


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
        self._lt_ref_cache = None   # (ops list, any stroke op with a linetype id)
        self._lt_exp_cache = None   # (ops list, {op index: (lt, factor, expansion)})
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        # ItemIsMovable off: native Qt drag is dead in plan view; the
        # SelectionManipulator drives movement via translate().
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

    # ── Definition access ────────────────────────────────────────────────
    def definition(self) -> Optional[BlockDefinition]:
        return self._resolver(self.block_id)

    def render_ops(self):
        d = self.definition()
        return d.render_ops() if d is not None else []

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
        return {"type": "block_instance", "block_id": self.block_id,
                "pos": [self._pose_x, self._pose_y], "rotation": self._pose_rot,
                "uid": self._uid}

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

    def _posed_path(self) -> QPainterPath:
        """Pose-mapped combined path, memoised on (compiled ops, pose).

        boundingRect / shape / paint ask for it several times per frame; the
        key is the definition's compiled op list (a new list on every content
        change, held here so its identity can't be recycled) plus the pose, so
        a stale path can't be served and no explicit invalidation is needed.
        """
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
        r = self._posed_path().boundingRect()
        m = 2.0  # pen margin (mm)
        r = r.adjusted(-m, -m, m, m)
        if self._has_linetype_ref():
            # A linetype id may go missing (LT3-10): the canvas glyph is drawn
            # at the insertion point, a fixed device size -- bound it at this
            # zoom whether or not it resolves (no geometry change on a flip).
            from .view_scale import scene_hit_width
            px = _lr.badge_pad_px()
            h = scene_hit_width(self, px, px)
            c = self.pose_transform().map(QPointF(0.0, 0.0))
            r = r.united(QRectF(c.x() - h, c.y() - h, 2 * h, 2 * h))
        return r

    def _has_linetype_ref(self) -> bool:
        """True when any compiled stroke op names a linetype block id
        (memoised on the compiled op list's identity)."""
        ops = self.render_ops()
        c = self._lt_ref_cache
        if c is not None and c[0] is ops:
            return c[1]
        has = any(op.kind == STROKE and is_linetype_ref(op.linetype) for op in ops)
        self._lt_ref_cache = (ops, has)
        return has

    def shape(self) -> QPainterPath:
        # Copy (implicitly shared, O(1)): callers may mutate what shape()
        # returns; the memoised path must stay intact.
        return QPainterPath(self._posed_path())

    # ── Paint ────────────────────────────────────────────────────────────
    def paint(self, painter, option, widget=None):
        pose = self.pose_transform()
        ops = self.render_ops()
        if not ops:
            if self.definition() is None:      # orphan placeholder
                p = QPen(QColor("#c0392b"))
                p.setCosmetic(True)
                painter.setPen(p)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(self._posed_path())
            return
        override = self._display_pen_color()   # display-manager / pre-highlight hook
        selected = self.isSelected()
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
        strokes = {}        # (linetype, weight) -> [rs, width, lt, factor, lod]
        dev_scale = None    # device px per local unit under the pose (lazy)
        paper_pass = None   # paper_display.paper_pass_active() (lazy)
        for i, op in enumerate(ops):
            if op.kind in (FILL, PATTERN):
                self._paint_fill_op(painter, pose, op)
                continue
            if op.kind == TEXT:
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
                rs, width, lt, factor, ok = ent
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
                if selected and not on_paper:
                    p.setColor(QColor("#63BE8B"))  # accent; icon-style-guide token
                if self._paper_pen_color is not None:
                    p.setColor(self._paper_pen_color)
                if lt is not None and op.pieces:
                    # Expand definition-local under the pose (H3-f): one
                    # cached expansion shared by every instance.
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
                            ok = _lr.lod_ok_at(lt.period * factor, dev_scale)
                        ent[4] = ok
                    if ok:
                        dash, dot = self._op_expansion(ops, i, op, lt, factor)
                        painter.save()
                        try:
                            painter.setWorldTransform(pose, True)
                            _lr.draw_expansion(painter, dash, dot, p)
                        finally:
                            painter.restore()
                        continue
                painter.setPen(p)
                painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(pose.map(op.path))
        if routed and (missing or getattr(self, "_lt_tip_id", None)):
            _lr.sync_missing_tooltip(self, missing)     # names the id (LT3-10)
        if missing:
            # Canvas-only glyph, once at the insertion point (LT3-10).
            if not _pd.paper_pass_active():
                _lr.paint_missing_badge(painter, pose.map(QPointF(0.0, 0.0)))

    def _resolve_op_stroke(self, op, routed, registry, on_paper) -> list:
        """``[rs, width, lt, factor, None]`` for a stroke op -- once per distinct
        (linetype, weight) per paint (``paint``'s memo).

        LT3-8 cascade: linetype + resolved weight (By Linetype -> the
        linetype's dash weight when it has one). Continuous / By Block /
        unstyled ops never reach the resolver (LT3-11). *width* is the paper
        width on a viewport pass, else the cosmetic canvas px (None for an
        unweighted op: keep the compiled pen's width). *lt* is the linetype
        to expand (None: plain stroke) and *factor* its LT3-5 length factor;
        a non-positive / non-finite scaled period draws plain. The last slot
        is ``paint``'s lazily decided screen LOD for this entry.
        """
        rs = None
        if routed and is_linetype_ref(op.linetype):
            rs = resolve_stroke({"linetype": op.linetype,
                                 "weight": op.weight or BY_BLOCK}, registry)
        weight = rs.weight if rs is not None else op.weight
        if on_paper:
            width = self._paper_op_width(weight)
        else:
            width = canvas_px(weight) if weight is not None else None
        lt = rs.lt if rs is not None else None
        factor = None
        if lt is not None:
            factor = self._linetype_factor(lt)
            if not _lr.period_ok(lt, factor):
                lt = None
        return [rs, width, lt, factor, None]

    def _op_expansion(self, ops, i, op, lt, factor):
        """``linetype_render.expand`` for op *i* of *ops*, held across paints.

        Keyed on the compiled op list (held, so its identity can't be
        recycled -- the ``_posed_cache`` idiom; a new list on every content
        change), the op index, the linetype reading itself (a new object on
        a definition edit / version bump) and the exact length factor -- every
        input of ``expand``, so a hit returns what ``expand`` would.
        """
        c = self._lt_exp_cache
        if c is None or c[0] is not ops:
            c = self._lt_exp_cache = (ops, {})
        hit = c[1].get(i)
        if hit is not None and hit[0] is lt and hit[1] == factor:
            return hit[2]
        a = op.origin or QPointF(0.0, 0.0)
        res = _lr.expand(op.pieces, lt, factor, (a.x(), a.y()))
        c[1][i] = (lt, factor, res)
        return res

    def _linetype_factor(self, lt) -> float:
        """LT3-5: Model -> 1; paper pass -> 1 / viewport scale; plan canvas ->
        drawing scale; anything else (Block Editor nested instance) -> 1."""
        if lt.size == "model":
            return 1.0
        if self._paper_scale:
            return 1.0 / self._paper_scale
        sc = self.scene()
        if getattr(sc, "scene_role", None) == "plan":
            sm = self._scale_manager()
            return float(sm.drawing_scale) if sm is not None else 1.0
        return 1.0

    def _paper_op_width(self, weight) -> float:
        """Non-cosmetic paper width for a stroke op's resolved *weight* (LT2-5).

        By Block / By Linetype / unweighted ops take the category weight
        (``_paper_pen_width``); a named weight plots at its own mm divided by
        the viewport scale (the §9.9.1 pattern).
        """
        w = weight
        if w is None or w in (BY_BLOCK, BY_LINETYPE) or not self._paper_scale:
            return self._paper_pen_width
        return _pd.resolve_line_weight_mm(w) / max(self._paper_scale, 1e-9)

    def _paint_fill_op(self, painter, pose, op) -> None:
        """Fill / pattern op: boundary posed, pattern stamped in scene axes (D-A11)."""
        from .hatch_render import paint_fill
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
        return {
            "Type":         {"type": "label",     "value": "Block"},
            "Level":        {"type": "level_ref", "value": self.level},
            "Level Offset": {"type": "dimension", "value": self._fmt(self._level_offset_mm),
                             "value_mm": self._level_offset_mm},
            # "string" type → editable numeric line-edit (matches the
            # RegularPolygonItem / EllipseItem Rotation convention).
            "Rotation":     {"type": "string",    "value": f"{self._pose_rot:.1f}"},
        }

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
        if data.get("uid"):
            inst._uid = str(data["uid"])
        return inst
