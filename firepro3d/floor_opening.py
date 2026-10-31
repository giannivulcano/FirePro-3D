"""
floor_opening.py
================
Floor-hosted blank Opening (floor void) for FirePro 3D.

A ``FloorOpening`` is a closed polygon in absolute scene coordinates, owned by
exactly one :class:`~firepro3d.floor_slab.FloorSlab` (``host``; listed in
``host.openings``). It never re-hosts and is deleted with its host. The slab's
material is ``FloorSlab.cut_region()`` (slab polygon minus the union of its
voids). Design: docs/superpowers/specs/2026-10-30-floor-opening-design.md
(A1, A2, A7).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QColor, QPainterPath, QPainterPathStroker, QPen, QPolygonF
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QStyle

from .colour_tokens import resolve_colour
from .constants import Z_OPENING_ABOVE_HOST
from .displayable_item import DisplayableItemMixin
from .feature import DEFAULT_FLOOR_OPENING_FEATURE, FEATURE_LABEL
from .paper_display import shows_selection
from .view_scale import scene_hit_width

if TYPE_CHECKING:
    from .floor_slab import FloorSlab

# Outline colour with no Display-Manager override (= WallOpening's blank default).
FLOOR_VOID_DEFAULT_COLOR = "#888888"
_SELECTION_COLOR = QColor("red")


def _scene_hit_width(item) -> float:
    """~12 screen px at the visible view's zoom (see view_scale)."""
    return scene_hit_width(item, 12.0, 6.0)


class FloorOpening(DisplayableItemMixin, QGraphicsPathItem):
    """A void cut through one floor slab, drawn as a polygon.

    Args:
        points: Polygon vertices, absolute scene coordinates.
        host: The owning slab. The caller appends the void with
            ``host.add_opening(op)``.
        feature_id: Frozen Feature Type id (feature-system F4).
        mark: Instance Mark (minted by ``marks``; "" until then).
    """

    HALO_AREA = True   # HALO: cursor inside = direct hit

    def __init__(self, points: list[QPointF], host: "FloorSlab",
                 feature_id: str = DEFAULT_FLOOR_OPENING_FEATURE, mark: str = ""):
        QGraphicsPathItem.__init__(self)
        self.init_displayable()
        self.feature_id: str = feature_id
        self._points: list[QPointF] = [QPointF(p) for p in points]
        self.host = host
        self._mark: str = mark
        # Pure z-range visibility, exactly as the host (z_range_mm delegates).
        self._visibility_by_zrange: bool = True
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(host.zValue() + Z_OPENING_ABOVE_HOST)
        self._rebuild_path()

    # -- Category / extent ----------------------------------------------------

    @property
    def display_category(self) -> str:
        """Display Manager category key: the tier-1 Feature label "Opening"."""
        return FEATURE_LABEL.get("blank", "Opening")

    def z_range_mm(self) -> tuple[float, float] | None:
        """The host's resolved (bot, top) world-mm Z: a void spans its host."""
        return self.host.z_range_mm() if self.host is not None else None

    # -- Points ---------------------------------------------------------------

    @property
    def points(self) -> list[QPointF]:
        """Copies of the polygon vertices (scene coords)."""
        return [QPointF(p) for p in self._points]

    def set_points(self, pts: list[QPointF]) -> None:
        """Replace the polygon vertices (scene coords)."""
        self._points = [QPointF(p) for p in pts]
        self._rebuild_path()

    def _rebuild_path(self) -> None:
        """Rebuild the outline path and invalidate the host's cut region."""
        path = QPainterPath()
        if len(self._points) >= 2:
            path.moveTo(self._points[0])
            for p in self._points[1:]:
                path.lineTo(p)
            if len(self._points) >= 3:
                path.closeSubpath()
        self.setPath(path)
        if self.host is not None:
            self.host.invalidate_cut()

    # -- Paint / hit-test -----------------------------------------------------

    def paint(self, painter, option, widget=None):
        """Outline as drawn, in the Opening Display-Manager colour, no fill."""
        option.state &= ~QStyle.StateFlag.State_Selected
        if len(self._points) < 3:
            return
        dc = self._display_color            # None = unset; "" = No stroke
        col = (QColor(FLOOR_VOID_DEFAULT_COLOR) if dc is None
               else resolve_colour(dc, item=self))
        painter.setPen(self._outline_pen(col, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(QPolygonF(self._points))
        if shows_selection(self):
            sel = QPen(_SELECTION_COLOR, 2)
            sel.setCosmetic(True)
            painter.setPen(sel)
            painter.drawPolygon(QPolygonF(self._points))

    def shape(self) -> QPainterPath:
        """Polygon area plus a screen-width stroke (HALO_AREA)."""
        path = self.path()
        if path.isEmpty():
            return path
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        return stroker.createStroke(path) | path

    # -- Grips / transforms (A7) ----------------------------------------------

    def grip_points(self) -> list[QPointF]:
        """The polygon vertices, in order (one grip each)."""
        return [QPointF(p) for p in self._points]

    def apply_grip(self, index: int, new_pos: QPointF) -> None:
        """Move vertex *index* to *new_pos*."""
        if 0 <= index < len(self._points):
            self._points[index] = QPointF(new_pos)
            self._rebuild_path()

    def manip_handles(self):
        """Closed-chain round vertex grips (FloorSlab twin)."""
        from .manip_handle import vertex_chain_grip_handles
        return vertex_chain_grip_handles(self, closed=True)

    def translate(self, dx: float, dy: float) -> None:
        """Shift every vertex by (dx, dy) scene units."""
        self._points = [QPointF(p.x() + dx, p.y() + dy) for p in self._points]
        self._rebuild_path()

    def manip_rotate(self, angle_deg: float, pivot: QPointF) -> None:
        """Baked rigid rotate about *pivot* (Y-up CCW+), as FloorSlab.manip_rotate."""
        from .cad_math import CAD_Math
        self._points = [CAD_Math.rotate_point(p, pivot, -angle_deg)
                        for p in self._points]
        self._rebuild_path()

    # -- Serialisation (nested in the host slab's record) ---------------------

    def to_dict(self) -> dict:
        """``{"feature_id", "points", "mark", "display_overrides"?}`` (spec A2)."""
        d = {
            "feature_id": self.feature_id,
            "points": [[p.x(), p.y()] for p in self._points],
            "mark": self._mark,
        }
        return self.display_overrides_to_dict(d)

    @classmethod
    def from_dict(cls, data: dict, host: "FloorSlab") -> "FloorOpening":
        """Rebuild a void for *host* (the caller appends it via ``add_opening``)."""
        op = cls(points=[QPointF(p[0], p[1]) for p in data.get("points", [])],
                 host=host,
                 feature_id=data.get("feature_id", DEFAULT_FLOOR_OPENING_FEATURE),
                 mark=data.get("mark", ""))
        op.display_overrides_from_dict(data)
        return op

    # ── Property panel (floor-opening design A8) ─────────────────────────────

    def get_properties(self) -> dict:
        """Placed floor-void panel rows.

        Feature / Type / Host / Points are read-only labels; Mark is the one
        editable row (``set_property`` requests its undo step).

        Returns:
            dict: Ordered property-key -> descriptor (property-panel protocol).
        """
        from .feature import FEATURE_REGISTRY, feature_label
        fdef = FEATURE_REGISTRY.get(self.feature_id)
        return {
            "Feature": {"type": "label",
                        "value": feature_label(fdef) if fdef is not None else "Opening"},
            "Type": {"type": "label",
                     "value": fdef.type_name if fdef is not None else self.feature_id},
            "Host": {"type": "label", "value": (self.host.name if self.host is not None else "") or "Floor"},
            "Points": {"type": "label", "value": str(len(self._points))},
            "Mark": {"type": "string", "value": self._mark},
        }

    def set_property(self, key: str, value) -> None:
        """Apply a panel edit.  Only Mark is editable; a changed Mark requests
        one undo step (coalesced by the panel's deferred push).

        Args:
            key: Property key from ``get_properties()``.
            value: New value (str for Mark); other keys are ignored.
        """
        if key != "Mark":
            return
        new = str(value)
        if new == self._mark:
            return
        self._mark = new
        sc = self.scene()
        if sc is not None and hasattr(sc, "request_undo_push"):
            sc.request_undo_push()  # A8 Mark undo


def drop_carried_voids(items: list) -> list:
    """*items* without any FloorOpening whose host is also in *items*.

    A slab's translate / rotate carries its voids, so a void selected together
    with its host must not be transformed a second time.
    """
    ids = {id(i) for i in items}
    return [i for i in items
            if not (isinstance(i, FloorOpening) and id(i.host) in ids)]
