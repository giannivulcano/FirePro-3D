"""FilledRegionItem -- the 10th 2D primitive (HF3 design, hatch-and-fill.md).

Boundary = loops of *parentless, scene-less* shape objects built from their
own ``to_dict`` records (design D1); loop 0 is the outer loop, the rest are
islands (OddEven). The region is Block-Editor-only (R1), fills with the UP1
two-layer record through ``Geometry2DMixin._paint_fill_layers`` and draws its
stroke only while ``outline`` is on (R11).
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QPainterPath, QPainterPathStroker, QPen
from PyQt6.QtWidgets import QGraphicsPathItem, QStyle

from . import fill_types
from .constants import FILL_TYPE_CUSTOM_LABEL, TOKEN_AUTO, Z_FILLED_REGION
from .displayable_item import DisplayableItemMixin
from .fill_layers import EMPTY, BackgroundLayer, FillLayers
from .geometry_2d import Geometry2DMixin, _manip_wraps, _scene_hit_width
from .paper_display import shows_selection

log = logging.getLogger(__name__)

TYPE_KEY = "draw_filled_region"

# Record types a loop may hold: the 8 shapes (+ the legacy reference-line key).
PIECE_TYPES = frozenset({
    "draw_line", "reference_line", "draw_rectangle", "draw_circle", "arc",
    "polyline", "polygon", "draw_ellipse", "draw_spline",
})
# Piece-record keys the region does not carry (pieces are boundary only).
_STRIP = ("fill", "reference", "printed")


def _piece_from_record(rec: dict):
    from .block_definition import _PRIMITIVE_FACTORY
    t = rec.get("type")
    cls = _PRIMITIVE_FACTORY.get(t) if t in PIECE_TYPES else None
    if cls is None:
        log.warning("FilledRegion: piece type %r unknown -- skipped", t)
        return None
    return cls.from_dict(rec)


def _piece_record(piece) -> dict:
    d = piece.to_dict()
    for k in _STRIP:
        d.pop(k, None)
    return d


class FilledRegionItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsPathItem):
    """A static-boundary area object (type ``"draw_filled_region"``)."""

    _REFERENCE_CAPABLE = False      # no Reference form (like text)
    HALO_AREA = True    # D-A26: halo measures the area even with no fill (flag list: selection-mode.md 4.1)

    def __init__(self, loops: list[list[dict]] | None = None,
                 color: str = TOKEN_AUTO, lineweight: float = 1.0):
        super().__init__()
        self.init_displayable(level=None)     # level-less primitive (C3)
        self.init_geometry2d()
        self._init_stroke(color, lineweight)  # the stroke record exists from creation (R11)
        self.outline: bool = False
        self.fill_layers = FillLayers(background=BackgroundLayer(TOKEN_AUTO, 1.0))  # R9
        self._loops: list[list] = []
        self._stroke_pieces_cache = None
        for loop in loops or []:
            pieces = [p for p in (_piece_from_record(r) for r in loop) if p is not None]
            if pieces:
                self._loops.append(pieces)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)
        self.setZValue(Z_FILLED_REGION)
        self._rebuild_path()

    # -- construction ------------------------------------------------------
    @classmethod
    def from_pieces(cls, loops: list[list]) -> "FilledRegionItem":
        """Region from live shape objects: each piece is copied through its
        record so the boundary is static (D-A1) and the sources untouched (R10)."""
        return cls([[_piece_record(p) for p in loop] for loop in loops])

    @property
    def pieces(self) -> list:
        return [p for loop in self._loops for p in loop]

    def _rebuild_path(self) -> None:
        from .curve_chain import loop_path
        self._stroke_pieces_cache = None
        self.prepareGeometryChange()
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        for loop in self._loops:
            path.addPath(loop_path(loop))
        self.setPath(path)
        self.update()

    def stroke_pieces(self) -> tuple:
        """Analytic stroke pieces in item-local coords (linetype renderer):
        one flattened ``Curve`` per boundary loop, memoised until the next
        ``_rebuild_path`` (the sole setPath site)."""
        cached = self._stroke_pieces_cache
        if cached is None:
            from .constants import LINETYPE_CURVE_FLATTEN_SCALE as k
            from PyQt6.QtGui import QTransform
            from .path_walk import Curve
            polys = self.path().toSubpathPolygons(QTransform.fromScale(k, k))
            out = []
            for poly in polys:
                pts = tuple((p.x() / k, p.y() / k) for p in poly)
                if len(pts) >= 2:
                    out.append(Curve(pts))
            cached = self._stroke_pieces_cache = tuple(out)
        return cached

    # -- HF5 fill type (R2/R3): typed = type look + sparse overrides --------
    _fill_type: str | None = None
    _fill_overrides: dict = {}      # never mutated in place (reassigned)
    _own_fill = None                # set via the fill_layers setter (custom regions)

    @property
    def fill_layers(self):
        """The fill that paints: the resolved type (+ overrides) or the region's own."""
        if self._fill_type:
            return fill_types.resolve(self._fill_type, self._fill_overrides)[0]
        return self._own_fill if self._own_fill is not None else EMPTY

    @fill_layers.setter
    def fill_layers(self, layers):
        if self._fill_type:
            t = fill_types.project_table().get(self._fill_type)
            if t is not None:
                self._fill_overrides = fill_types.diff_overrides(t.layers, layers)
            else:
                # Missing type: keep prior overrides of layers the edit leaves alone,
                # so they survive until the type returns.
                cur = fill_types.resolve(self._fill_type, self._fill_overrides)[0]
                vs_fallback = fill_types.diff_overrides(fill_types.FALLBACK_LAYERS, layers)
                ov = dict(self._fill_overrides)
                for k in ("background", "pattern"):
                    if getattr(cur, k) != getattr(layers, k):      # only the layer the edit changed
                        if k in vs_fallback:
                            ov[k] = vs_fallback[k]
                        else:
                            ov.pop(k, None)
                self._fill_overrides = ov
        else:
            self._own_fill = layers

    @property
    def fill_type(self) -> str | None:
        """The Fill Type id, or None for (Custom)."""
        return self._fill_type

    @property
    def fill_type_missing(self) -> bool:
        """True when typed but the id resolves to no type (fallback look)."""
        return bool(self._fill_type) and fill_types.project_table().get(self._fill_type) is None

    def set_fill_type(self, type_id: str | None) -> None:
        """Pick a type (overrides cleared) or None = (Custom) with the resolved look copied."""
        if type_id:
            self._fill_type, self._fill_overrides = type_id, {}
        else:
            look = self.fill_layers
            self._fill_type, self._fill_overrides = None, {}
            self._own_fill = look
        self.update()

    def reset_fill_layer(self, layer: str) -> None:
        """Drop the overrides of one layer ('background' | 'pattern')."""
        ov = dict(self._fill_overrides)
        ov.pop(layer, None)
        self._fill_overrides = ov
        self.update()

    # -- fill protocol (UP1 / halo) ----------------------------------------
    def is_closed(self) -> bool:
        return True

    def get_closed_path(self) -> QPainterPath | None:
        p = self.path()
        return None if p.isEmpty() else QPainterPath(p)

    # -- transforms: delegate to every piece (D-A13) -----------------------
    def translate(self, dx: float, dy: float) -> None:
        for p in self.pieces:
            p.translate(dx, dy)
        self._rebuild_path()

    def manip_rotate(self, angle_deg: float, pivot: QPointF) -> None:
        for p in self.pieces:
            p.manip_rotate(angle_deg, QPointF(pivot))
        self._rebuild_path()

    def manip_reflect(self, p1: QPointF, p2: QPointF) -> None:
        for p in self.pieces:
            p.manip_reflect(QPointF(p1), QPointF(p2))
        self._rebuild_path()

    def manip_scale_about(self, base: QPointF, factor: float) -> None:
        for p in self.pieces:
            p.manip_scale_about(QPointF(base), factor)
        self._rebuild_path()

    def manip_handles(self) -> list:
        return []                                    # no grips in v1

    # -- paint / hit -------------------------------------------------------
    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        if self._draws_fill():
            self._paint_fill_layers(painter, self.sceneTransform())
        if self.outline:
            rs = self._sync_stroke_pen()
            self._paint_routed_stroke(painter, option, widget, rs,
                                      lambda p: p.drawPath(self.path()))
            self._paint_lt_badge(painter)
        elif shows_selection(self) and not _manip_wraps(self):
            # Invisible outline: a dashed cosmetic trace is the only selection cue.
            pen = QPen(self.pen().color(), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.path())

    def shape(self) -> QPainterPath:
        area = QPainterPath(self.path())             # interior counts (click inside selects)
        if self.outline:
            stroker = QPainterPathStroker()
            stroker.setWidth(_scene_hit_width(self))
            area = area.united(stroker.createStroke(self.path()))
        return area

    # -- record (file, undo, clipboard: one record) ------------------------
    def to_dict(self) -> dict:
        d = {"type": TYPE_KEY,
             "loops": [[_piece_record(p) for p in loop] for loop in self._loops],
             "outline": bool(self.outline)}
        d = self._geom2d_to_dict(d)
        if self._fill_type:
            d["fill_type"] = self._fill_type
            if self._fill_overrides:
                d["fill"] = dict(self._fill_overrides)
            else:
                d.pop("fill", None)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "FilledRegionItem":
        obj = cls(data.get("loops", []), data.get("color", TOKEN_AUTO),
                  data.get("lineweight", 1.0))
        obj.outline = bool(data.get("outline", False))
        obj._geom2d_from_dict(data)
        tid = data.get("fill_type")
        if isinstance(tid, str) and tid:
            ov = data.get("fill") if isinstance(data.get("fill"), dict) else {}
            obj._own_fill = None
            obj._fill_type = fill_types.canonical_id(tid)     # name-duplicate -> kept id
            obj._fill_overrides = {k: v for k, v in ov.items()
                                   if k in ("background", "pattern")
                                   and (v is None or isinstance(v, dict))}
        return obj

    # -- panel -------------------------------------------------------------
    def get_properties(self) -> dict:
        props = {"Type": {"type": "label", "value": "Filled Region"},
                 "Loops": {"type": "label", "value": str(len(self._loops))},
                 "Outline": {"type": "toggle", "value": bool(self.outline)}}
        table = fill_types.project_table()
        names = [t.name for t in table.all()]
        if not self._fill_type:
            value = FILL_TYPE_CUSTOM_LABEL
        elif self.fill_type_missing:
            value = fill_types.missing_type_label(self._fill_type)
            names.append(value)
        else:
            value = table.get(self._fill_type).name
        props["Fill Type"] = {"type": "enum", "options": [FILL_TYPE_CUSTOM_LABEL, *names],
                              "value": value,
                              "tooltip": "Named fill style from the project's Fill Types "
                                         "(Display Manager). (Custom) = this region's own fill."}
        geom = self._geom2d_properties()
        if not self._fill_type:
            props.update(geom)
            return props
        # R3: each overridden layer gets a "Reset ... to type" row right after its fill row.
        after = {"Fill": ("background", "Fill"), "Fill Pattern": ("pattern", "Pattern")}
        for key, row in geom.items():
            props[key] = row
            hit = after.get(key)
            if hit is not None and hit[0] in self._fill_overrides:
                layer, label = hit
                ov = self._fill_overrides[layer]
                fields = ", ".join(sorted(ov)) if isinstance(ov, dict) else "layer off"
                props[f"Reset {label} to type"] = {
                    "type": "button", "value": "Reset to type",
                    "tooltip": "Overridden: " + fields,
                    "callback": lambda l=layer: self._dim_edit(
                        lambda _v: self.reset_fill_layer(l), None)}
        return props

    def _pick_fill_type_by_label(self, label) -> None:
        """Panel Fill Type pick: (Custom) -> None, else by name (unknown / '? <id8>' = no-op)."""
        if label == FILL_TYPE_CUSTOM_LABEL:
            tid = None
        else:
            hit = fill_types.project_table().by_name(label)
            if hit is None:             # also the '? <id8>' missing marker: not a pick
                return
            tid = hit.id
        self._dim_edit(self.set_fill_type, tid)

    def _set_outline(self, on: bool) -> None:
        if on == self.outline:
            return
        self.prepareGeometryChange()
        self.outline = on
        self.update()

    def set_property(self, key: str, value):
        if key == "Fill Type":
            self._pick_fill_type_by_label(value)
            return
        if key == "Outline":
            self._dim_edit(lambda v: self._set_outline(bool(v)), value)
            return
        if self._geom2d_set(key, value):
            self.update()
