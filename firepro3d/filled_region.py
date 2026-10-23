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

from .constants import TOKEN_AUTO, Z_FILLED_REGION
from .displayable_item import DisplayableItemMixin
from .fill_layers import BackgroundLayer, FillLayers
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
        return self._geom2d_to_dict(d)

    @classmethod
    def from_dict(cls, data: dict) -> "FilledRegionItem":
        obj = cls(data.get("loops", []), data.get("color", TOKEN_AUTO),
                  data.get("lineweight", 1.0))
        obj.outline = bool(data.get("outline", False))
        obj._geom2d_from_dict(data)
        return obj

    # -- panel -------------------------------------------------------------
    def get_properties(self) -> dict:
        props = {"Type": {"type": "label", "value": "Filled Region"},
                 "Loops": {"type": "label", "value": str(len(self._loops))},
                 "Outline": {"type": "toggle", "value": bool(self.outline)}}
        props.update(self._geom2d_properties())
        return props

    def _set_outline(self, on: bool) -> None:
        if on == self.outline:
            return
        self.prepareGeometryChange()
        self.outline = on
        self.update()

    def set_property(self, key: str, value):
        if key == "Outline":
            self._dim_edit(lambda v: self._set_outline(bool(v)), value)
            return
        if self._geom2d_set(key, value):
            self.update()
