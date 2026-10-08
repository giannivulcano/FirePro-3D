"""BlockDefinition — the reusable 2D block definition (flyweight).

A definition owns identity + metadata + captured 2D primitives, and (Task 2)
compiles those primitives once into a shared, origin-relative render-op list
consumed by every BlockInstance. See docs/specs/block-system.md.
"""

from __future__ import annotations

import copy
import math
import uuid

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QPainterPath, QPen

from .geometry_2d import (
    LineItem, ReferenceLineItem, RectangleItem, CircleItem, ArcItem, PolylineItem,
    RegularPolygonItem, EllipseItem, SplineItem,
)
from .render_op import RenderOp, STROKE, FILL, PATTERN, TEXT
from .text_item import TextItem

# Primitive-type key -> reconstruction class (same keys as the legacy factory)
_PRIMITIVE_FACTORY = {
    "draw_line": LineItem,
    "reference_line": ReferenceLineItem,
    "draw_rectangle": RectangleItem,
    "draw_circle": CircleItem,
    "arc": ArcItem,
    "polyline": PolylineItem,
    "polygon": RegularPolygonItem,
    "draw_ellipse": EllipseItem,
    "draw_spline": SplineItem,
    "text": TextItem,
}

_NESTED_TYPE = "block_instance"


def is_scaffold(prim: dict) -> bool:
    """A non-printed reference line: saved + re-seeded, never rendered (D23).

    Args:
        prim: A definition primitive dict.

    Returns:
        True for a ``reference_line`` record whose ``printed`` flag is unset.
    """
    return prim.get("type") == "reference_line" and not prim.get("printed", False)

_PLACEHOLDER_COLOR = "#c0392b"      # BlockInstance orphan placeholder colour
_PLACEHOLDER_MM = 200.0
_COMPILING: set[str] = set()        # re-entrancy guard (corrupt cyclic data)


def _nested_pose(rec: dict):
    """QTransform for a nested record: translate(pos) then rotate(-rot) (Y-up CCW).

    Matches ``BlockInstance.pose_transform`` (D2).

    Args:
        rec: A ``block_instance`` primitive record.

    Returns:
        The record's definition-local pose ``QTransform``.
    """
    from PyQt6.QtGui import QTransform
    x, y = rec.get("pos", [0.0, 0.0])
    t = QTransform()
    t.translate(float(x), float(y))
    t.rotate(-float(rec.get("rotation", 0.0)))
    return t


def _placeholder_op(t) -> RenderOp:
    """Red box-with-diagonal render op for an unresolvable nested block.

    Args:
        t: The nested record's full transform (pose, then origin shift).
    """
    h = _PLACEHOLDER_MM / 2.0
    path = QPainterPath()
    path.addRect(-h, -h, _PLACEHOLDER_MM, _PLACEHOLDER_MM)
    path.moveTo(-h, -h)
    path.lineTo(h, h)
    pen = QPen(QColor(_PLACEHOLDER_COLOR))
    pen.setCosmetic(True)               # match BlockInstance's orphan placeholder
    return RenderOp(STROKE, t.map(path), pen=pen)


def _local_path(item) -> QPainterPath:
    """Return the primitive's geometry as a QPainterPath in the item's own coords.

    Args:
        item: A construction-geometry primitive (QGraphicsItem subclass).

    Returns:
        A ``QPainterPath`` describing the primitive in its local coordinate frame.
    """
    # TextItem contributes filled glyph outlines (bake-at-rest rotation already
    # applied inside render_outline_path — see its docstring).
    if hasattr(item, "render_outline_path"):
        return item.render_outline_path()
    from PyQt6.QtWidgets import (
        QGraphicsLineItem, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem,
    )
    path = QPainterPath()
    if isinstance(item, QGraphicsLineItem):
        ln = item.line()
        path.moveTo(ln.p1())
        path.lineTo(ln.p2())
    elif isinstance(item, QGraphicsEllipseItem):
        path.addEllipse(item.rect())
    elif isinstance(item, QGraphicsRectItem):
        path.addRect(item.rect())
    elif isinstance(item, QGraphicsPathItem):
        path = QPainterPath(item.path())
    return path


def _fill_ops(item, prim: dict, ox: float, oy: float) -> list:
    """Fill / pattern op for a primitive's per-item ``fill`` record (fixes H1).

    The clip is the item's closed path through its pos/rotation, origin-relative;
    the pattern origin is the container origin (definition (0,0) -> (-ox, -oy)).
    """
    f = prim.get("fill")
    if not isinstance(f, dict) or f.get("type", "none") == "none":
        return []
    gcp = getattr(item, "get_closed_path", None)
    cp = gcp() if gcp is not None else None
    if cp is None or cp.isEmpty():
        return []
    clip = item.mapToParent(cp)
    clip.translate(-ox, -oy)
    colour = f.get("color") or "#888888"
    alpha = int(round(float(f.get("opacity", 0.45)) * 255))
    if f.get("type") == "solid":
        return [RenderOp(FILL, clip, colour=colour, alpha=alpha)]
    return [RenderOp(PATTERN, clip, colour=colour, alpha=alpha,
                     tile_ref=item.fill_pattern, origin=QPointF(-ox, -oy))]


def _norm_tile(tile) -> dict | None:
    """Normalised tile dict, or None (hatch HD4a tile schema)."""
    if not tile:
        return None
    return {"w": float(tile.get("w", 0.0)), "h": float(tile.get("h", 0.0)),
            "row_shift": float(tile.get("row_shift", 0.0)),
            "size": "model" if tile.get("size") == "model" else "drafting"}


def _norm_repeat(repeat) -> dict | None:
    """Normalised linetype repeat record, or None (linetypes.md LT3 H3-g).

    ``screen`` (LTS-1) is kept only when ``"fixed"``: an absent key means
    Scale with zoom (LTS-5), so Scale-mode records stay byte-identical.
    """
    if not repeat:
        return None
    out = {"length": float(repeat.get("length", 0.0)),
           "size": "model" if repeat.get("size") == "model" else "drafting"}
    if repeat.get("screen") == "fixed":
        out["screen"] = "fixed"
    ends = repeat.get("ends")
    if isinstance(ends, dict):
        # LT5 Q11: the linetype's default end ids; a key only for an id (a
        # keyword / blank is "no default"), the record only when non-empty,
        # so linetypes without defaults stay byte-identical.
        from .stroke_style import is_end_ref
        kept = {k: ends[k] for k in ("start", "finish") if is_end_ref(ends.get(k))}
        if kept:
            out["ends"] = kept
    return out


_END_SIZES = ("fixed", "weight_relative")


def _norm_end(end) -> dict | None:
    """Normalised end-type record, or None (LT5 design A).

    ``{"size": "fixed" | "weight_relative", "trim": mm >= 0}``: a non-dict
    is no capability; a bad size reads Fixed; a non-numeric, non-finite or
    negative trim reads 0.
    """
    if not isinstance(end, dict):
        return None
    size = end.get("size")
    try:
        trim = float(end.get("trim", 0.0))
    except (TypeError, ValueError):
        trim = 0.0
    if not math.isfinite(trim) or trim < 0.0:
        trim = 0.0
    return {"size": size if size in _END_SIZES else "fixed", "trim": trim}


def _load_prim(p):
    """Return a fresh, LT2-migrated copy of a stored primitive dict."""
    from .stroke_style import STYLED_TYPES, migrate_primitive
    from .paper_display import canonical_weight_name
    if not isinstance(p, dict):
        return p
    if p.get("type") in STYLED_TYPES:
        return migrate_primitive(p)
    out = copy.deepcopy(p)
    if out.get("type") == _NESTED_TYPE and "overrides" in out:
        from .stroke_style import is_as_authored, normalize_overrides
        ov = normalize_overrides(out["overrides"])      # canonical names (H-g)
        if is_as_authored(ov):
            out.pop("overrides")
        else:
            out["overrides"] = ov
    if out.get("type") == "text" and out.get("border_weight"):
        out["border_weight"] = canonical_weight_name(out["border_weight"])
    return out


class BlockDefinition:
    """A named, reusable 2D block definition.

    Attributes:
        id: Stable uuid4 hex identity (registry key + instance reference + library link).
        version: Monotonic revision, bumped on each edit; drives library divergence.
        name/library/series: Human-readable metadata (2-tier library taxonomy).
        scale_mode: v1 sole value "real_size" ("annotative" reserved for v2).
        origin: Definition-local insertion origin, in scene millimetres.
        attributes: Reserved slot list; no UI in v1.
        primitives: List of 2D-primitive dicts (geometry_2d to_dict form).
            Non-printed reference lines are kept as scaffolding (D23): saved
            and re-seeded, never compiled/exploded (see ``is_scaffold``).
        constraints: Sketch constraint record dicts (spec §6.3).
    """

    def __init__(self, *, id: str, version: int, name: str, library: str,
                 series: str, scale_mode: str, origin: tuple[float, float],
                 attributes: list, primitives: list[dict],
                 render_mode: str = "default", geoms: list[dict] | None = None,
                 constraints: list | None = None, tile: dict | None = None,
                 repeat: dict | None = None, end: dict | None = None):
        self.id = id
        self.version = int(version)
        self.name = name
        self.library = library
        self.series = series
        self.scale_mode = scale_mode
        # Set directly (not via the setter): the caches do not exist yet.
        self._origin = (float(origin[0]), float(origin[1]))
        self.attributes = list(attributes)
        self.primitives = list(primitives)
        # Sketch constraint records (parametric-constraint-system.md §6.3);
        # additive key, absent => [] (no schema bump).
        self.constraints: list[dict] = list(constraints or [])
        # Pattern-tile capability (hatch D-A9/HD4a): {"w","h","row_shift","size"}
        # or None. Additive key — absent => None (no schema bump).
        self._tile: dict | None = _norm_tile(tile)
        # Linetype capability (linetypes.md LT3 H3-g): {"length","size"} or
        # None. Additive key — absent => None (no schema bump).
        self._repeat: dict | None = _norm_repeat(repeat)
        # End-type capability (LT5): {"size","trim"} or None. Additive key --
        # absent => None (no schema bump).
        self._end: dict | None = _norm_end(end)
        # Reference definitions (render_mode="reference") own the curve-preserving,
        # layer-tagged import geom-dict list. This is the geometry data model for
        # imported references — rendered by the batched underlay builder (which
        # also handles text) and persisted via the underlay cache, NOT via
        # to_dict (keeps .fpd lean). Empty for authored blocks.
        self.geoms: list[dict] = list(geoms) if geoms else []
        # Render mode (reference-graphic unification, constraint #1):
        #   "default"   — one render op per primitive (authored blocks).
        #   "reference" — one render op per distinct source `layer` tag; the
        #                 batched-per-layer compile that keeps a 437k-geom DXF
        #                 interactive. See docs/specs/reference-graphic-model.md.
        self.render_mode = render_mode or "default"
        self._render_ops: list[RenderOp] | None = None
        # Cached origin-relative 9-point text frame boxes (S6 snap targets).
        self._text_snap_pts: list[list[QPointF]] | None = None
        self._instances: list = []   # BlockInstance backrefs (Task 4 wires notify)
        # Nested-block resolver (registry.get), injected by BlockRegistry (D5).
        self._resolve = None

    @classmethod
    def new(cls, *, name: str, library: str, series: str,
            primitives: list[dict], origin: tuple[float, float],
            render_mode: str = "default",
            constraints: list | None = None,
            tile: dict | None = None,
            repeat: dict | None = None,
            end: dict | None = None) -> "BlockDefinition":
        """Create a fresh definition with a new uuid and version 1."""
        return cls(id=uuid.uuid4().hex, version=1, name=name, library=library,
                   series=series, scale_mode="real_size", origin=origin,
                   attributes=[], primitives=primitives, render_mode=render_mode,
                   constraints=constraints, tile=tile, repeat=repeat, end=end)

    @classmethod
    def reference_from_geoms(cls, geoms: list[dict], *, name: str = "",
                             library: str = "", series: str = "") -> "BlockDefinition":
        """Build a reference definition from imported geom dicts (R1).

        The single import front-end (DXF/DWG/PDF) hands its curve-preserving,
        layer-tagged geom dicts here. Geometry lives in ``geoms`` (rendered by the
        batched underlay builder); ``primitives`` stays empty. Raster imports have
        no geoms and produce a valid empty reference. See
        docs/specs/reference-graphic-model.md.

        Args:
            geoms: import geom dicts (worker output; ``_preserve_curves`` path for
                curve fidelity, each carrying a ``layer`` tag).
            name/library/series: definition metadata.

        Returns:
            A ``BlockDefinition`` with ``render_mode="reference"`` and ``geoms`` set.
        """
        d = cls.new(name=name, library=library, series=series, primitives=[],
                    origin=(0.0, 0.0), render_mode="reference")
        d.geoms = list(geoms) if geoms else []
        return d

    def set_primitives(self, primitives: list[dict]) -> None:
        """Replace captured primitives, bump version, invalidate + notify instances.

        Args:
            primitives: The new list of 2D-primitive dicts (geometry_2d
                to_dict form) that replaces the definition's geometry.
        """
        self.primitives = list(primitives)
        self.version += 1
        self._render_ops = None
        self._text_snap_pts = None
        for inst in list(self._instances):
            inst.on_definition_changed()

    @property
    def origin(self) -> tuple[float, float]:
        """Definition-local insertion origin (scene mm); assigning clears caches."""
        return self._origin

    @origin.setter
    def origin(self, value) -> None:
        self._origin = (float(value[0]), float(value[1]))
        self.invalidate_cache()

    def invalidate_cache(self) -> None:
        """Drop the compiled render ops + text snap points (next read recompiles)."""
        self._render_ops = None
        self._text_snap_pts = None

    @property
    def tile(self) -> dict | None:
        """The pattern tile ``{w, h, row_shift, size}``; None = not a pattern."""
        return dict(self._tile) if self._tile else None

    def set_tile(self, tile, *, notify: bool = True) -> None:
        """Replace the tile, bump the version (pattern caches key on it).

        Args:
            tile: New tile dict or None.
            notify: Bump the version and repaint backref instances. False when
                the caller follows with ``set_primitives``, which does both
                (one edit = one version bump).
        """
        self._set_capability("_tile", _norm_tile(tile), notify)

    def _set_capability(self, attr: str, value, notify: bool) -> None:
        """The one capability setter body (``set_tile`` / ``set_repeat`` /
        ``set_end``): store the normalised record, drop the compiled caches
        and -- with *notify* -- bump the version (capability caches key on
        it) and repaint backref instances."""
        setattr(self, attr, value)
        self.invalidate_cache()
        if notify:
            self.version += 1
            for inst in list(self._instances):
                inst.on_definition_changed()

    @property
    def repeat(self) -> dict | None:
        """The linetype repeat ``{length, size[, screen][, ends]}``; None =
        not a linetype. A deep copy (``ends`` is a nested dict)."""
        return copy.deepcopy(self._repeat) if self._repeat else None

    @property
    def has_default_ends(self) -> bool:
        """True when this is a linetype whose repeat names a default end
        (LT5 Q11) -- the paint fast-path gate; no copy of the record."""
        return bool(self._repeat and self._repeat.get("ends"))

    @property
    def is_linetype(self) -> bool:
        """True when this block carries a linetype repeat record (malformed
        or not) -- ``bool(repeat)`` without the deep copy, for the paint /
        boundingRect paths (``stroke_style.linetype_block``,
        ``LinetypeDef.from_block``)."""
        return bool(self._repeat)

    def set_repeat(self, repeat, *, notify: bool = True) -> None:
        """Replace the repeat record, bump the version (linetype caches key on it).

        Args:
            repeat: New repeat dict or None.
            notify: Bump the version and repaint backref instances (as
                ``set_tile``).
        """
        self._set_capability("_repeat", _norm_repeat(repeat), notify)

    @property
    def end(self) -> dict | None:
        """The end-type record ``{size, trim}``; None = not an end type."""
        return dict(self._end) if self._end else None

    def set_end(self, end, *, notify: bool = True) -> None:
        """Replace the end-type record, bump the version (end caches key on it).

        Args:
            end: New end dict or None.
            notify: Bump the version and repaint backref instances (as
                ``set_tile``).
        """
        self._set_capability("_end", _norm_end(end), notify)

    def render_ops(self) -> list[RenderOp]:
        """Return the cached, shared ``RenderOp`` list.

        Returns:
            ``RenderOp``s in definition-local, origin-relative coordinates. Text
            is ``kind == "text"``; per-item fills are ``fill`` / ``pattern`` ops
            ordered before their stroke. The same list identity is returned on
            every call until :meth:`set_primitives` invalidates the cache.
        """
        if self._render_ops is None:
            self._render_ops = self._compile()
        return self._render_ops

    def text_snap_points(self) -> list[list[QPointF]]:
        """Origin-relative 9-point frame boxes of every text primitive.

        Point order per box is TL, TM, TR, RM, BR, BM, BL, LM, C (the
        ``TextItem.grip_points`` order, rotation-aware). These are the block's
        text snap targets (S6); glyph outlines are never snap targets. Cached
        and invalidated with the render ops. A geom-backed (imported)
        reference definition has empty ``primitives``, so its list is empty;
        an authored reference definition falls back to ``primitives`` and so
        still yields its text boxes.

        Returns:
            One list of 9 ``QPointF`` per text primitive.
        """
        if self._text_snap_pts is None:
            ox, oy = self.origin
            out: list[list[QPointF]] = []
            for prim in self.primitives:
                if prim.get("type") == _NESTED_TYPE:
                    child = self._resolve_nested(prim)
                    if child is None or child.id in _COMPILING or child.id == self.id:
                        continue
                    from PyQt6.QtGui import QTransform
                    t = _nested_pose(prim) * QTransform.fromTranslate(-ox, -oy)
                    _COMPILING.add(self.id)
                    try:
                        boxes = child.text_snap_points()
                    finally:
                        _COMPILING.discard(self.id)
                    out.extend([[t.map(p) for p in box] for box in boxes])
                    continue
                if is_scaffold(prim):
                    continue
                cls = _PRIMITIVE_FACTORY.get(prim.get("type"))
                if cls is None:
                    continue
                item = cls.from_dict(prim)
                if not hasattr(item, "render_outline_path"):
                    continue
                out.append([QPointF(p.x() - ox, p.y() - oy)
                            for p in item.grip_points()])
            self._text_snap_pts = out
        return self._text_snap_pts

    def _compile(self) -> list[RenderOp]:
        """Compile captured primitive dicts into origin-relative render ops.

        In ``reference`` mode the ops are batched per source layer (one op per
        distinct ``layer`` tag) — the binding perf constraint that keeps a
        large imported reference interactive. In ``default`` mode each primitive
        gets its own op (authored blocks, unchanged).
        """
        if self.render_mode == "reference":
            return self._compile_reference()
        ox, oy = self.origin
        ops: list[RenderOp] = []
        for prim in self.primitives:
            if prim.get("type") == _NESTED_TYPE:
                ops.extend(self._nested_ops(prim, ox, oy))
                continue
            if is_scaffold(prim):
                continue
            cls = _PRIMITIVE_FACTORY.get(prim.get("type"))
            if cls is None:
                continue
            item = cls.from_dict(prim)
            # _local_path returns the glyph outline for text (rotation baked);
            # mapToParent applies the item's pos (data.x/y) in both cases.
            path = item.mapToParent(_local_path(item))   # honor prim pos/rotation
            path.translate(-ox, -oy)                       # origin-relative
            if hasattr(item, "render_outline_path"):
                ops.append(RenderOp(TEXT, path, colour=item.data.color))
                continue
            ops.extend(_fill_ops(item, prim, ox, oy))      # fill draws under the stroke
            st = getattr(item, "style", None)
            pieces, lt, ends = (), None, None
            if st is not None and hasattr(item, "stroke_pieces"):
                # Same map as the path: mapToParent (Qt transform, then pos --
                # row-vector order) then the origin shift. Rect data rotation
                # is already inside its stroke_pieces().
                from PyQt6.QtGui import QTransform
                from .path_walk import map_piece
                t = item.transform() * QTransform.fromTranslate(
                    item.pos().x() - ox, item.pos().y() - oy)
                pieces = tuple(map_piece(p, t) for p in item.stroke_pieces())
                lt = st["linetype"]
                from .stroke_style import open_stroke
                if open_stroke(item):          # LT5 Q2: free ends only
                    ends = (dict(st["start"]), dict(st["finish"]))
            ops.append(RenderOp(STROKE, path, pen=QPen(item.pen()),
                                weight=st["weight"] if st else None,
                                pieces=pieces, linetype=lt,
                                # phase anchor: this definition's origin
                                origin=QPointF(0.0, 0.0) if pieces else None,
                                ends=ends))
        return ops

    def _resolve_nested(self, prim):
        """The nested definition for *prim*, or None (missing / unresolvable)."""
        if self._resolve is None:
            return None
        return self._resolve(prim.get("block_id", ""))

    def _nested_ops(self, prim, ox, oy) -> list:
        """B's cached ops mapped through the record pose, then A's origin shift.

        Qt ``QTransform`` composes row-vector style: ``p * (pose * shift)``
        applies the pose first, then the origin shift — the same order as
        ``mapToParent`` followed by ``translate(-ox, -oy)`` for primitives.
        An unresolvable or cyclic nested block yields the red placeholder.
        """
        from PyQt6.QtGui import QTransform
        t = _nested_pose(prim) * QTransform.fromTranslate(-ox, -oy)
        child = self._resolve_nested(prim)
        if child is None or child.id in _COMPILING or child.id == self.id:
            return [_placeholder_op(t)]
        _COMPILING.add(self.id)
        try:
            child_ops = child.render_ops()
        finally:
            _COMPILING.discard(self.id)
        from .render_op import apply_overrides
        from .stroke_style import override_args
        # WM2 H2: the record's override replaces what the child's own compile
        # (and its records) resolved -- outermost wins (WM-6). Raw names
        # (load already canonicalised them): a compile inside the Display
        # Manager Cancel replay must not bake the renamed-away alias target.
        return apply_overrides([op.mapped(t) for op in child_ops],
                               *override_args(prim.get("overrides"),
                                              canonical=False))

    def _compile_reference(self) -> list[RenderOp]:
        """Batched compile: accumulate each layer's geometry into one path.

        Groups by ``layer`` tag, unioning each layer's geometry into a single
        cosmetic ``QPainterPath`` (subpaths kept separate via ``addPath``). The
        result is one stroke ``RenderOp`` per distinct *geometry*
        layer — ``len(render_ops) == n_distinct_layers``, never ``n_primitives``.
        Per-layer colour/weight is applied downstream by the reference bundle's
        display pass, so the compile pen is a cosmetic default.

        A geom-backed reference (imported) compiles from ``geoms``; text geoms
        carry no geometry_2d primitive and are excluded here (the batched
        underlay builder renders them). An authored reference (rare) falls back
        to ``primitives``.
        """
        ox, oy = self.origin
        by_layer: dict[str, QPainterPath] = {}
        pens: dict[str, QPen] = {}
        for item, layer in self._reference_items():
            path = item.mapToParent(_local_path(item))
            path.translate(-ox, -oy)                       # origin-relative
            if layer not in by_layer:
                by_layer[layer] = QPainterPath()
                pen = QPen(item.pen())
                pen.setCosmetic(True)
                pens[layer] = pen
            by_layer[layer].addPath(path)
        return [RenderOp(STROKE, by_layer[layer], pen=pens[layer]) for layer in by_layer]

    def _reference_items(self):
        """Yield ``(primitive_item, layer)`` for the reference compile.

        Geom-backed definitions (imported references) compile from ``geoms`` via
        the shared ``geom_dicts_to_primitives`` converter (curve-preserving,
        layer-tagged); otherwise fall back to ``primitives`` (geometry_2d dicts).
        """
        if self.geoms:
            from .geometry_import import geom_dicts_to_primitives
            items, _ = geom_dicts_to_primitives(self.geoms)
            for it in items:
                yield it, getattr(it, "layer", "")
        else:
            for prim in self.primitives:
                if is_scaffold(prim):
                    continue
                cls = _PRIMITIVE_FACTORY.get(prim.get("type"))
                if cls is None:
                    continue
                yield cls.from_dict(prim), prim.get("layer", "")

    def to_dict(self) -> dict:
        d = {
            "schema": 1,
            "id": self.id,
            "version": self.version,
            "name": self.name,
            "library": self.library,
            "series": self.series,
            "scale_mode": self.scale_mode,
            "origin": [self.origin[0], self.origin[1]],
            "attributes": list(self.attributes),
            "primitives": copy.deepcopy(self.primitives),
            "render_mode": self.render_mode,
            "constraints": [dict(c) for c in self.constraints],
            "tile": dict(self._tile) if self._tile else None,
            "repeat": copy.deepcopy(self._repeat) if self._repeat else None,
        }
        if self._end:
            d["end"] = dict(self._end)      # omitted when None (byte-identical)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "BlockDefinition":
        origin = data.get("origin", [0.0, 0.0])
        return cls(
            id=data["id"], version=data.get("version", 1),
            name=data.get("name", ""), library=data.get("library", ""),
            series=data.get("series", ""),
            scale_mode=data.get("scale_mode", "real_size"),
            origin=(origin[0], origin[1]),
            attributes=data.get("attributes", []),
            primitives=[_load_prim(p) for p in data.get("primitives", [])],
            render_mode=data.get("render_mode", "default"),
            constraints=data.get("constraints", []),
            tile=data.get("tile"),
            repeat=data.get("repeat"),
            end=data.get("end"),
        )
