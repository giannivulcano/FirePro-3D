"""
detail_view.py
==============
Detail view marker and manager.

A detail view is a plan view with a rectangular crop boundary.  The marker
appears on the source plan as a dashed rectangle with a circular callout tag.
Opening the detail view creates a tab that shows only the content inside
the crop boundary.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QGraphicsRectItem, QGraphicsItem, QGraphicsEllipseItem,
    QGraphicsSimpleTextItem, QGraphicsLineItem, QGraphicsPathItem,
    QTabWidget, QStyle, QStyleOptionGraphicsItem,
)
from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer
from PyQt6.QtGui import QPen, QBrush, QColor, QPainter, QPainterPath

from .gridline import BUBBLE_RADIUS_MM
from .constants import DEFAULT_LEVEL, Z_ANNOT_MARKER
from .paper_display import shows_selection
from .view_marker_head import ViewMarkerHead

if TYPE_CHECKING:
    from .model_space import Model_Space
    from .level_manager import LevelManager
    from .scale_manager import ScaleManager


# ─────────────────────────────────────────────────────────────────────────────
# Detail Marker
# ─────────────────────────────────────────────────────────────────────────────

_MARKER_COLOR = "#4488cc"
_BUBBLE_DROP = BUBBLE_RADIUS_MM * 7.5    # default head origin below the crop rect (today's 2.5 x 3R)
_HIT_W = BUBBLE_RADIUS_MM * 1.5          # stroke width of the crop / leader hit shape (today's 0.5 x 3R)
_FILLET_RADIUS = BUBBLE_RADIUS_MM * 1.5  # corner radius for crop rect


class DetailMarker(QGraphicsPathItem):
    """Detail view crop boundary on a plan view.

    Visual: rounded-corner dashed rectangle + the callout head (``bubble``,
    a ``ViewMarkerHead`` drawing the Detail annotation block: ``@[Mark]``
    over the sheet number, SB4d D1) connected by a bespoke leader trimmed
    at the head outline. The head is draggable (grip 8).
    """

    def __init__(self, name: str, rect: QRectF, level_name: str = DEFAULT_LEVEL,
                 parent: QGraphicsItem | None = None):
        super().__init__(parent)
        self._name = name
        self._level_name = level_name
        self._crop_rect = rect.normalized()
        self._manager: DetailViewManager | None = None

        # View depth (mm) — None means inherit from plan
        self._view_height: float | None = None
        self._view_depth: float | None = None
        self._on_view_range = None  # callback set by main.py

        # Visual style (SB4d D7: the line colour only; the head is a block)
        self._tag_color = QColor(_MARKER_COLOR)

        pen = QPen(self._tag_color, 2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setZValue(Z_ANNOT_MARKER)

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self._exclude_from_bulk_select = True

        # For display manager categorization
        self.level = level_name
        self._display_overrides: dict = {}
        self._mark = ""                          # Detail Mark (SB4d D3)

        # Head origin (defaults to below center of rect)
        self._bubble_pos = QPointF(rect.center().x(), rect.bottom() + _BUBBLE_DROP)
        self._bubble_dragging = False
        self.bubble = ViewMarkerHead(self)       # SB4d D1: the Detail block
        self.bubble.set_anchor(self._bubble_pos)

        self._rebuild_path()

    # ── Head (SB4d D1) ───────────────────────────────────────────────────

    def heads(self) -> list:
        return [self.bubble]

    def _set_bubble_pos(self, pt: QPointF) -> None:
        """The one writer of the head origin: field + head anchor."""
        self._bubble_pos = QPointF(pt)
        self.bubble.set_anchor(self._bubble_pos)

    def refresh_heads(self) -> None:
        """Re-shape the head (mapping / registry / units / drawing scale /
        Mark / sheet change) and the bounds that hold the leader."""
        self.prepareGeometryChange()
        self.bubble.refresh()
        self.bubble.set_anchor(self._bubble_pos)
        self.update()

    def _update_label(self) -> None:
        """``marks.set_mark`` hook (SB2b): the head re-reads its Mark."""
        self.refresh_heads()

    def itemChange(self, change, value):
        if (change == QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged
                and value is not None):
            self.refresh_heads()                  # k resolves only in a scene
        return super().itemChange(change, value)

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str):
        self._name = value
        self.update()

    @property
    def level_name(self) -> str:
        return self._level_name

    @property
    def crop_rect(self) -> QRectF:
        return QRectF(self._crop_rect)

    @property
    def view_height(self) -> float | None:
        return self._view_height

    @view_height.setter
    def view_height(self, v: float | None):
        self._view_height = v

    @property
    def view_depth(self) -> float | None:
        return self._view_depth

    @view_depth.setter
    def view_depth(self, v: float | None):
        self._view_depth = v

    def z_range_mm(self):
        """Z-range for view filtering — use the detail's level elevation."""
        sc = self.scene()
        lm = getattr(sc, "_level_manager", None) if sc else None
        if lm is None:
            return None
        lvl = lm.get(self._level_name)
        if lvl is None:
            return None
        z = lvl.elevation
        return (z, z)

    # ── Path building ────────────────────────────────────────────────────

    def _rebuild_path(self):
        """Rebuild the rounded-rect + leader + bubble path."""
        path = QPainterPath()
        # Rounded rectangle crop boundary
        r = self._crop_rect
        fr = min(_FILLET_RADIUS, r.width() / 4, r.height() / 4)
        path.addRoundedRect(r, fr, fr)
        self.setPath(path)

    # ── Drawing ──────────────────────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # In a detail/clip view the marker paints NOTHING as an item: its callout
        # is redrawn bright by Model_View.drawForeground AFTER the crop mask
        # (exempt from the dim), and the crop rectangle is redundant there (the
        # mask edge already shows the crop). The crop rect is the box-native
        # bounding box in the PLAN view only.
        view = widget.parentWidget() if widget is not None else None
        if view is not None and getattr(view, "_clip_rect", None) is not None:
            return

        r = self._crop_rect
        fr = min(_FILLET_RADIUS, r.width() / 4, r.height() / 4)
        # Cosmetic width 1 dashed crop box — matches the placement reference line.
        crop_pen = QPen(self._tag_color, 1, Qt.PenStyle.DashLine)
        crop_pen.setCosmetic(True)
        painter.setPen(crop_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(r, fr, fr)

        self._paint_leader(painter)              # the head paints itself (a child item)

        if shows_selection(self):
            hl_pen = QPen(self._tag_color.lighter(150), max(1.0, _HIT_W * 0.16))
            painter.setPen(hl_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(r, fr, fr)   # the head rings itself (overlay_pens)

    def _leader(self) -> tuple[QPointF, QPointF]:
        """``(start, end)`` of the leader: from the crop edge point nearest
        the head to where that ray meets the head's block outline."""
        bp = self._bubble_pos
        start = self._closest_rect_point(self._crop_rect, bp)
        dx, dy = start.x() - bp.x(), start.y() - bp.y()
        L = math.hypot(dx, dy)
        if L <= 1e-9:
            return start, QPointF(bp)
        t = self.bubble.trim_distance(dx / L, dy / L)
        return start, QPointF(bp.x() + dx / L * t, bp.y() + dy / L * t)

    def _paint_leader(self, painter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        start, end = self._leader()
        painter.setPen(QPen(self._tag_color, max(1.0, _HIT_W * 0.08)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(start, end)

    def _paint_callout(self, painter):
        """Leader + head, NO crop rect -- for ``Model_View.drawForeground``
        in a detail view, so the own callout renders bright ON TOP of the
        crop mask (SB4d D6). Painter is in scene coordinates; the head paints
        through its own ``paint`` under its scene transform (widget None: the
        clip-view item skip does not apply here)."""
        self._paint_leader(painter)
        head = self.bubble
        if head.isVisible():
            painter.save()
            painter.setTransform(head.sceneTransform(), True)
            head.paint(painter, QStyleOptionGraphicsItem(), None)
            painter.restore()

    @staticmethod
    def _closest_rect_point(rect: QRectF, pt: QPointF) -> QPointF:
        """Find closest point on the edge of *rect* to *pt*."""
        cx = max(rect.left(), min(pt.x(), rect.right()))
        cy = max(rect.top(), min(pt.y(), rect.bottom()))
        # If point is inside rect, project to nearest edge
        if rect.contains(pt):
            dl = pt.x() - rect.left()
            dr = rect.right() - pt.x()
            dt = pt.y() - rect.top()
            db = rect.bottom() - pt.y()
            m = min(dl, dr, dt, db)
            if m == dl:
                return QPointF(rect.left(), pt.y())
            elif m == dr:
                return QPointF(rect.right(), pt.y())
            elif m == dt:
                return QPointF(pt.x(), rect.top())
            else:
                return QPointF(pt.x(), rect.bottom())
        return QPointF(cx, cy)

    # ── Grip protocol ────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        """8 grips for crop rect + 1 grip for bubble position."""
        r = self._crop_rect
        return [
            r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft(),
            QPointF(r.center().x(), r.top()),
            QPointF(r.right(), r.center().y()),
            QPointF(r.center().x(), r.bottom()),
            QPointF(r.left(), r.center().y()),
            self._bubble_pos,  # grip 8: bubble drag
        ]

    def apply_grip(self, index: int, new_pos: QPointF):
        """Resize crop rect (grips 0-7) or move bubble (grip 8)."""
        if index == 8:
            # Move the head
            self.prepareGeometryChange()
            self._set_bubble_pos(new_pos)
            self._rebuild_path()
            self.update()
            return

        old_center = self._crop_rect.center()
        r = QRectF(self._crop_rect)
        if index == 0:
            r.setTopLeft(new_pos)
        elif index == 1:
            r.setTopRight(new_pos)
        elif index == 2:
            r.setBottomRight(new_pos)
        elif index == 3:
            r.setBottomLeft(new_pos)
        elif index == 4:
            r.setTop(new_pos.y())
        elif index == 5:
            r.setRight(new_pos.x())
        elif index == 6:
            r.setBottom(new_pos.y())
        elif index == 7:
            r.setLeft(new_pos.x())

        r = r.normalized()
        # The bubble follows the resize by the crop-centre delta (constant offset,
        # radius unchanged → no warp) so the callout tracks the box.
        dc = r.center() - old_center
        self._set_bubble_pos(QPointF(self._bubble_pos.x() + dc.x(),
                                     self._bubble_pos.y() + dc.y()))
        self._crop_rect = r
        self.prepareGeometryChange()
        self._rebuild_path()
        self.update()

        # Update open detail tab's clip rect
        if self._manager is not None:
            self._manager._on_marker_resized(self._name, r)

    # ── Selection-manipulator adapter — PARAMETRIC editable crop ──────────
    # Governing spec: selection-manipulator.md + view-relationships.md.
    # PARAMETRIC (NOT box-native): the 8 crop grips (corners + edge midpoints)
    # live-mutate the crop rect via apply_grip each move, so resize is LIVE and
    # nothing warps. (Box-native's held-scale-transform preview stretched the
    # bubble circle into an ellipse and froze the frame — the 2026-09-11 smoke
    # bugs.) Grips 0-7 render SQUARE (resize handles); the bubble (grip 8) is a
    # ROUND move grip. Caps = {translate} (no manip_scale) → the manipulator
    # shows its dashed FRAME as the visible bounding box (NOT redundant) + the
    # grips. Axis-aligned (no manip_rotate).

    def manip_bounds(self) -> QRectF:
        return QRectF(self._crop_rect)       # the frame wraps the crop rect

    def manip_handles(self):
        from .manip_handle import default_grip_handles
        return default_grip_handles(self, circular={8})   # 0-7 square, bubble round

    def manip_translate(self, dx: float, dy: float):
        """Move the whole marker — crop rect + bubble — and refresh the tab clip."""
        self.prepareGeometryChange()
        self._crop_rect.translate(dx, dy)
        self._set_bubble_pos(QPointF(self._bubble_pos.x() + dx,
                                     self._bubble_pos.y() + dy))
        self._rebuild_path()
        self.update()
        if self._manager is not None:
            self._manager._on_marker_resized(self._name, QRectF(self._crop_rect))

    # ── Interaction ──────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event):
        """Double-click opens the detail view tab."""
        sc = self.scene()
        if sc is not None and hasattr(sc, "openViewRequested"):
            sc.openViewRequested.emit("detail", self._name)
        event.accept()

    def boundingRect(self):
        br = self.path().boundingRect()
        bubble = getattr(self, "bubble", None)    # None during __init__'s early pen / path calls
        if bubble is None:
            return br.adjusted(-10, -10, 10, 10)
        # Extend to include the leader and the head (a child: its own bounds)
        start = self._closest_rect_point(self._crop_rect, self._bubble_pos)
        lead = QRectF(start, self._bubble_pos).normalized()
        head = self.mapRectFromItem(bubble, bubble.boundingRect())
        return br.united(lead).united(head).adjusted(-10, -10, 10, 10)

    def shape(self) -> QPainterPath:
        """Hit-test shape: only the border stroke + leader + bubble.

        Clicking inside the crop area should NOT select the marker —
        only clicking the edge, the leader line, or the bubble should.
        """
        from PyQt6.QtGui import QPainterPathStroker
        # Stroke the rounded rect outline
        r = self._crop_rect
        fr = min(_FILLET_RADIUS, r.width() / 4, r.height() / 4)
        outline = QPainterPath()
        outline.addRoundedRect(r, fr, fr)
        stroker = QPainterPathStroker()
        stroker.setWidth(max(20.0, _HIT_W))      # generous hit margin
        path = stroker.createStroke(outline)

        # Leader line
        bp = self._bubble_pos
        leader_start = self._closest_rect_point(r, bp)
        leader = QPainterPath()
        leader.moveTo(leader_start)
        leader.lineTo(bp)
        stroker2 = QPainterPathStroker()
        stroker2.setWidth(max(20.0, _HIT_W))
        path.addPath(stroker2.createStroke(leader))

        # Head outline: a press on the head selects the marker
        bubble = getattr(self, "bubble", None)
        head = bubble.mapToParent(bubble.outline_path()) if bubble is not None else QPainterPath()
        if head.isEmpty():
            path.addEllipse(bp, BUBBLE_RADIUS_MM * 3.0, BUBBLE_RADIUS_MM * 3.0)
        else:
            path.addPath(head)
        return path

    # ── Properties (for property panel) ─────────────────────────────────

    def _fmt(self, mm: float) -> str:
        """Format mm in display units via the scene's ScaleManager."""
        sc = self.scene()
        sm = getattr(sc, "scale_manager", None) if sc else None
        if sm:
            return sm.format_length(mm)
        return f"{mm:.1f} mm"

    def get_properties(self) -> dict:
        """Return properties for the property panel."""
        props = {}
        props["Name"] = {"value": self._name, "type": "string"}
        props["Level"] = {"value": self._level_name, "type": "level_ref"}
        r = self._crop_rect
        props["Width"] = {"value": self._fmt(r.width()), "type": "string",
                          "readonly": True}
        props["Height"] = {"value": self._fmt(r.height()), "type": "string",
                           "readonly": True}
        props["── View Range ──"] = {"value": "", "type": "label"}
        vh_str = self._fmt(self._view_height) if self._view_height is not None else "(inherit)"
        vd_str = self._fmt(self._view_depth) if self._view_depth is not None else "(inherit)"
        props["Cut Plane Height"] = {"value": vh_str, "type": "string", "readonly": True}
        props["View Depth"] = {"value": vd_str, "type": "string", "readonly": True}
        if self._on_view_range is not None:
            props["Edit View Range"] = {
                "type": "button", "value": "View Range\u2026",
                "callback": self._on_view_range}
        return props

    def set_property(self, key: str, value):
        if key == "Name":
            self._name = str(value)
            self.update()
        elif key == "Level":
            self._level_name = str(value)
            self.level = self._level_name
            self.update()

    # ── Serialization ────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        r = self._crop_rect
        d = {
            "name": self._name,
            "level_name": self._level_name,
            "crop_rect": {
                "x": r.x(), "y": r.y(),
                "w": r.width(), "h": r.height(),
            },
            "bubble_pos": {"x": self._bubble_pos.x(),
                           "y": self._bubble_pos.y()},
        }
        if self._view_height is not None:
            d["view_height"] = self._view_height
        if self._view_depth is not None:
            d["view_depth"] = self._view_depth
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DetailMarker":
        cr = data["crop_rect"]
        rect = QRectF(cr["x"], cr["y"], cr["w"], cr["h"])
        marker = cls(
            name=data["name"],
            rect=rect,
            level_name=data.get("level_name", DEFAULT_LEVEL),
        )
        bp = data.get("bubble_pos")
        if bp:
            marker._set_bubble_pos(QPointF(bp["x"], bp["y"]))
            marker._rebuild_path()
        marker._view_height = data.get("view_height")
        marker._view_depth = data.get("view_depth")
        return marker


# ─────────────────────────────────────────────────────────────────────────────
# Detail View Manager
# ─────────────────────────────────────────────────────────────────────────────

class DetailViewManager:
    """Manages detail view markers and tabs.

    Parameters
    ----------
    model_space : Model_Space
        The 2D scene containing the model.
    level_manager : LevelManager
        Level elevation lookup.
    scale_manager : ScaleManager
        Coordinate conversion.
    tab_widget : QTabWidget
        Central tab widget for detail view tabs.
    """

    def __init__(self, model_space: "Model_Space",
                 level_manager: "LevelManager",
                 scale_manager: "ScaleManager",
                 tab_widget: QTabWidget):
        self._ms = model_space
        self._lm = level_manager
        self._sm = scale_manager
        self._tabs = tab_widget

        # name → DetailMarker
        self._markers: dict[str, DetailMarker] = {}
        # name → Model_View (open tabs only)
        self._open_views: dict[str, object] = {}
        self._counter = 0

    @property
    def detail_names(self) -> list[str]:
        return list(self._markers.keys())

    def next_name(self) -> str:
        """Generate the next auto-incremented detail name."""
        self._counter += 1
        return f"Detail {self._counter}"

    def create_detail(self, name: str, crop_rect: QRectF,
                      level_name: str = DEFAULT_LEVEL) -> DetailMarker:
        """Create a detail marker and add it to the scene."""
        from .display_manager import apply_category_defaults
        marker = DetailMarker(name, crop_rect, level_name)
        marker._manager = self
        self._markers[name] = marker
        self._ms.addItem(marker)
        apply_category_defaults(marker)
        return marker

    def open_detail(self, name: str):
        """Open or switch to a detail view tab."""
        tab_name = f"Detail: {name}"

        # If already open, switch to it
        if name in self._open_views:
            view = self._open_views[name]
            for i in range(self._tabs.count()):
                if self._tabs.widget(i) is view:
                    self._tabs.setCurrentIndex(i)
                    return view
            # Tab was removed externally
            del self._open_views[name]

        marker = self._markers.get(name)
        if marker is None:
            return None

        # Create a new plan view with clip rect
        from .model_view import Model_View
        view = Model_View(self._ms)
        view.setObjectName(f"detail_view_{name}")
        view._clip_rect = marker.crop_rect
        view._detail_name = name

        idx = self._tabs.addTab(view, tab_name)
        self._tabs.setCurrentIndex(idx)
        self._open_views[name] = view

        # Apply level and fit to clip rect
        QTimer.singleShot(50, lambda: self._fit_detail_view(view, marker))

        return view

    def _fit_detail_view(self, view, marker):
        """Fit the detail view to its crop rect."""
        rect = QRectF(marker.crop_rect)
        margin = max(rect.width(), rect.height()) * 0.05
        rect.adjust(-margin, -margin, margin, margin)
        view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def close_detail(self, name: str):
        """Close a detail view tab and remove its marker."""
        # Close tab
        view = self._open_views.pop(name, None)
        if view is not None:
            for i in range(self._tabs.count()):
                if self._tabs.widget(i) is view:
                    self._tabs.removeTab(i)
                    break

        # Remove marker from scene
        marker = self._markers.pop(name, None)
        if marker is not None and marker.scene() is self._ms:
            self._ms.removeItem(marker)

    def delete_detail(self, name: str):
        """Delete a detail (marker + tab). Used from project browser."""
        self.close_detail(name)

    def clear(self):
        """Remove all detail markers and close all open detail tabs.

        Safe to call on an already-empty manager. Called by :meth:`from_list`
        before loading and by ``MainWindow.new_file()`` to prevent stale
        detail entries leaking across projects.
        """
        for name in list(self._markers.keys()):
            self.close_detail(name)
        # Defensive reset in case close_detail left any orphans
        self._markers.clear()
        self._open_views.clear()
        self._counter = 0

    def _on_marker_resized(self, name: str, new_rect: QRectF):
        """Called when a marker's crop rect changes via grip drag."""
        view = self._open_views.get(name)
        if view is not None:
            view._clip_rect = new_rect

    def get_marker(self, name: str) -> DetailMarker | None:
        return self._markers.get(name)

    # ── Serialization ────────────────────────────────────────────────────

    def to_list(self) -> list[dict]:
        return [m.to_dict() for m in self._markers.values()]

    def from_list(self, data: list[dict]):
        """Restore detail markers from saved data.

        Clears any existing markers first so that loading a project does not
        accumulate details from a previously-loaded project.
        """
        self.clear()
        for d in data:
            name = d["name"]
            cr = d["crop_rect"]
            rect = QRectF(cr["x"], cr["y"], cr["w"], cr["h"])
            level = d.get("level_name", DEFAULT_LEVEL)
            marker = self.create_detail(name, rect, level)
            # Restore bubble position
            bp = d.get("bubble_pos")
            if bp:
                marker._set_bubble_pos(QPointF(bp["x"], bp["y"]))
                marker._rebuild_path()
            # Restore view range
            marker._view_height = d.get("view_height")
            marker._view_depth = d.get("view_depth")
            # Update counter to avoid name collisions
            parts = name.split()
            if len(parts) >= 2:
                try:
                    num = int(parts[-1])
                    self._counter = max(self._counter, num)
                except ValueError:
                    pass
