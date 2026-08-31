"""
construction_geometry.py
=========================
Reference-geometry items for FirePro 3D.

PolylineItem      — a multi-click open polyline on the active user layer.
"""

from __future__ import annotations

import math

from PyQt6.QtWidgets import (
    QGraphicsLineItem, QGraphicsPathItem,
    QGraphicsRectItem, QGraphicsEllipseItem,
    QStyle,
)
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import (QPen, QColor, QPainterPath, QBrush, QPainterPathStroker,
                         QPolygonF, QTransform)
from .constants import DEFAULT_LEVEL, Z_CAT_CONSTRUCTION
from .displayable_item import DisplayableItemMixin
from .hatch_patterns import PATTERN_NAMES

_DEFAULT_FILL_PATTERN = PATTERN_NAMES[0] if PATTERN_NAMES else "diagonal"


def _manip_wraps(item) -> bool:
    """True when the scene's selection manipulator currently boxes *item*.

    Governing spec: docs/specs/selection-manipulator.md — the manipulator
    frame is the single selection boundary, so a wrapped item must NOT also
    paint its own ``isSelected()`` highlight (grip squares are drawn separately
    by Model_View and are unaffected).  Cheap and headless-safe (no view/manip
    → False, i.e. the pre-manipulator boundary still paints).
    """
    manip = getattr(item.scene(), "_manipulator", None) if item.scene() else None
    if manip is None:
        return False
    from PyQt6 import sip
    if sip.isdeleted(manip):     # scene rebuild (load/new/sheet) deleted it
        return False
    return manip.wraps(item)


# ─────────────────────────────────────────────────────────────────────────────
# Geometry2DMixin
# ─────────────────────────────────────────────────────────────────────────────

class Geometry2DMixin:
    """Shared level-plane placement + fill for 2D draw geometry.

    MRO: ``class X(Geometry2DMixin, DisplayableItemMixin, <QtBase>)``.
    Call ``init_displayable()`` then ``init_geometry2d()`` in ``__init__``.
    Fill fields are defined here but fill RENDERING is deferred to a later
    task — do not render fill in paint().
    """

    def init_geometry2d(self, level: str = DEFAULT_LEVEL):
        """Initialise placement + fill state.  Call after init_displayable()."""
        self.level = level
        self._level_offset_mm: float = 0.0
        self.fill_type: str = "none"          # "none" | "solid" | "hatch"
        self.fill_pattern: str = _DEFAULT_FILL_PATTERN
        self.fill_opacity: float = 0.45       # solid-fill opacity (0.0–1.0)
        # fill colour lives in DisplayableItemMixin._display_fill_color

    def z_range_mm(self):
        """Return ``(elevation, elevation)`` in mm, or ``None`` if unavailable."""
        sc = self.scene()
        lm = getattr(sc, "_level_manager", None) if sc else None
        if lm is None:
            return None
        lvl = lm.get(getattr(self, "level", None))
        if lvl is None:
            return None
        e = lvl.elevation + self._level_offset_mm
        return (e, e)

    def is_fillable(self) -> bool:
        """True if this item has a closed path (rectangle, circle, closed polyline)."""
        gcp = getattr(self, "get_closed_path", None)
        return gcp is not None and gcp() is not None

    def _g2d_sm(self):
        sc = self.scene()
        return getattr(sc, "scale_manager", None) if sc else None

    def _parse_dim(self, value):
        """Parse a display-formatted or raw numeric value to mm (float or None)."""
        if isinstance(value, (int, float)):
            return float(value)
        sm = self._g2d_sm()
        if sm is not None:
            try:
                return sm.parse_dimension(str(value))
            except Exception:
                return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _fmt(self, mm: float) -> str:
        """Format *mm* as a display string using the scene ScaleManager."""
        sm = self._g2d_sm()
        return sm.format_length(mm) if sm else f"{mm:.1f}"

    def _elevation_str(self) -> str:
        zr = self.z_range_mm()
        if zr is None:
            return "—"  # em dash
        return self._fmt(zr[1])

    def _geom2d_properties(self) -> dict:
        props = {
            "Level":        {"type": "level_ref", "value": self.level},
            "Level Offset": {"type": "dimension",
                             "value": self._fmt(self._level_offset_mm),
                             "value_mm": self._level_offset_mm},
            "Elevation":    {"type": "string", "value": self._elevation_str(),
                             "readonly": True},
        }
        if self.is_fillable():
            props["Fill"] = {"type": "enum",
                             "options": ["none", "solid", "hatch"],
                             "value": self.fill_type}
            if self.fill_type == "hatch":
                props["Pattern"] = {"type": "enum",
                                    "options": list(PATTERN_NAMES),
                                    "value": self.fill_pattern}
            if self.fill_type in ("solid", "hatch"):
                props["Fill Colour"] = {"type": "color",
                                        "value": self._display_fill_color or "#888888"}
            if self.fill_type == "solid":
                props["Fill Opacity"] = {
                    "type":  "string",
                    "value": str(round(self.fill_opacity * 100)),
                    "suffix": "%",
                }
        return props

    def _geom2d_set(self, key: str, value) -> bool:
        """Handle a property set for mixin-owned keys.  Returns True if consumed."""
        if key == "Level":
            self.level = str(value)
            return True
        if key == "Level Offset":
            parsed = self._parse_dim(value)
            if parsed is not None:
                self._level_offset_mm = parsed
            return True
        if key == "Fill":
            self.fill_type = str(value)
            self.update()
            return True
        if key == "Pattern":
            self.fill_pattern = str(value)
            self.update()
            return True
        if key == "Fill Colour":
            self._display_fill_color = str(value)
            self.update()
            return True
        if key == "Fill Opacity":
            try:
                pct = float(value)
            except (TypeError, ValueError):
                return True  # reject non-numeric; keep prior
            pct = max(0.0, min(100.0, pct))
            self.fill_opacity = pct / 100.0
            self.update()
            return True
        return False

    def _geom2d_to_dict(self, d: dict) -> dict:
        """Stamp mixin fields onto *d* and return it."""
        d["level"] = self.level
        if self._level_offset_mm != 0.0:
            d["level_offset_mm"] = self._level_offset_mm
        if self.fill_type != "none":
            d["fill"] = {
                "type":    self.fill_type,
                "pattern": self.fill_pattern,
                "color":   self._display_fill_color or "#888888",
                "opacity": self.fill_opacity,
            }
        return d

    def _geom2d_from_dict(self, data: dict):
        """Restore mixin fields from *data*."""
        self.level = data.get("level", DEFAULT_LEVEL)
        self._level_offset_mm = data.get("level_offset_mm", 0.0)
        f = data.get("fill")
        if f:
            self.fill_type = f.get("type", "none")
            self.fill_pattern = f.get("pattern", _DEFAULT_FILL_PATTERN)
            self._display_fill_color = f.get("color")
            self.fill_opacity = f.get("opacity", 0.45)


def _scene_hit_width(item) -> float:
    """Viewport-scale-aware hit width — always ~10 screen pixels regardless of zoom.

    Cosmetic pens have a fixed screen-pixel width but their shape() is in scene
    units.  At high zoom the two coincide; at low zoom a 1px cosmetic pen maps to
    a tiny fraction of a scene unit, making the item nearly impossible to click.
    This helper returns a scene-unit width that is always ~10 screen pixels.
    """
    sc = item.scene()
    if sc:
        views = sc.views()
        if views:
            scale = views[0].transform().m11()
            return max(2.0, 10.0 / max(scale, 1e-6))
    return 6.0


# ─────────────────────────────────────────────────────────────────────────────
# PolylineItem
# ─────────────────────────────────────────────────────────────────────────────

class PolylineItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsPathItem):
    """
    A multi-segment polyline (optionally flagged closed via `close()`) drawn by successive mouse clicks.

    The path is rebuilt each time a new point is appended so the
    partial line is always visible in the scene.

    Parameters
    ----------
    color : str | QColor
        Stroke color, typically derived from the active user layer.
    lineweight : float
        Cosmetic pixel width (default 1.0).
    """

    def __init__(self, start: QPointF, color: str | QColor = "#ffffff",
                 lineweight: float = 1.0):
        super().__init__()
        self._points: list[QPointF] = [start]
        self._closed: bool = False

        self.init_displayable(DEFAULT_LEVEL)
        self.init_geometry2d(DEFAULT_LEVEL)

        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        self.setZValue(Z_CAT_CONSTRUCTION)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)

        self._rebuild_path()

    # ── Properties ─────────────────────────────────────────────────────────

    def get_properties(self) -> dict:
        props = {
            "Type": {"type": "label", "value": "Polyline"},
            "Colour": {"type": "label", "value": self.pen().color().name()},
            "Line Weight": {"type": "label", "value": f"{self.pen().widthF():.1f}"},
            "Vertices": {"type": "label", "value": str(len(self._points))},
        }
        props.update(self._geom2d_properties())
        return props

    def set_property(self, key: str, value):
        if self._geom2d_set(key, value):
            return

    # ── Public API ────────────────────────────────────────────────────────────

    def append_point(self, pt: QPointF):
        """Add the next vertex and rebuild the path."""
        self._points.append(pt)
        self._rebuild_path()

    def update_preview(self, pt: QPointF):
        """Temporarily extend path to *pt* for the cursor-follow preview."""
        # Rebuild with the tentative last point
        path = QPainterPath(self._points[0])
        for p in self._points[1:]:
            path.lineTo(p)
        path.lineTo(pt)
        if self._closed and len(self._points) >= 3:
            path.closeSubpath()
        self.setPath(path)

    def finalize(self):
        """Snap the path to the committed points and stop accepting input."""
        self._rebuild_path()

    # ── Grip protocol ─────────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        """Return all vertex positions as grip handles (one per vertex)."""
        return list(self._points)

    def apply_grip(self, index: int, pos: QPointF):
        """Move vertex *index* to *pos* and rebuild the path."""
        if 0 <= index < len(self._points):
            self._points[index] = pos
            self._rebuild_path()

    def translate(self, dx: float, dy: float):
        """Move all vertices by (dx, dy)."""
        self._points = [QPointF(p.x() + dx, p.y() + dy) for p in self._points]
        self._rebuild_path()

    # ── Closed-path protocol ─────────────────────────────────────────────────

    def is_closed(self) -> bool:
        """Return True if this polyline is flagged closed (≥3 vertices)."""
        return self._closed and len(self._points) >= 3

    def close(self):
        """Flag the polyline closed (needs ≥3 vertices).  Idempotent."""
        if len(self._points) >= 3:
            self._closed = True
            self._rebuild_path()

    def get_closed_path(self) -> QPainterPath | None:
        """Return a closed QPainterPath if flagged closed, else None."""
        if not self.is_closed():
            return None
        poly = QPolygonF(self._points)
        path = QPainterPath()
        path.addPolygon(poly)
        path.closeSubpath()
        return path

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        pen_color = self.pen().color().name()
        d = {
            "type":       "polyline",
            "color":      pen_color,
            "lineweight": self.pen().widthF(),
            "points":     [[p.x(), p.y()] for p in self._points],
            "closed":     self._closed,
        }
        return self._geom2d_to_dict(d)

    @classmethod
    def from_dict(cls, data: dict) -> "PolylineItem":
        pts = [QPointF(p[0], p[1]) for p in data["points"]]
        color = data.get("color", "#ffffff")
        lw = data.get("lineweight", 1.0)
        closed = data.get("closed")
        if closed is None:
            # Legacy: closure was a duplicated last vertex coincident with the
            # first.  Detect, flag closed, and drop the duplicate.
            if (len(pts) >= 4
                    and abs(pts[0].x() - pts[-1].x()) < 1e-3
                    and abs(pts[0].y() - pts[-1].y()) < 1e-3):
                pts = pts[:-1]
                closed = True
            else:
                closed = False
        obj = cls(pts[0], color, lw)
        for p in pts[1:]:
            obj.append_point(p)
        obj._closed = bool(closed)
        obj._geom2d_from_dict(data)
        obj._rebuild_path()
        return obj

    # ── Internal ─────────────────────────────────────────────────────────────

    def _rebuild_path(self):
        if not self._points:
            return
        path = QPainterPath(self._points[0])
        for p in self._points[1:]:
            path.lineTo(p)
        if self._closed and len(self._points) >= 3:
            path.closeSubpath()
        self.setPath(path)

    # ── Paint (selection highlight) ──────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        # Apply effective display colour (category or per-instance override).
        dc = getattr(self, "_display_color", None)
        if dc:
            pen = QPen(self.pen())
            pen.setColor(QColor(dc))
            self.setPen(pen)
        # Draw fill FIRST (behind the outline)
        if getattr(self, "fill_type", "none") != "none":
            cp = self.get_closed_path()
            if cp is not None:
                from .displayable_item import draw_fill
                draw_fill(painter, cp, self.scene(), self.fill_type,
                          self.fill_pattern, self._display_fill_color or "#888888",
                          alpha=int(round(self.fill_opacity * 255)))
        super().paint(painter, option, widget)
        if self.isSelected() and not _manip_wraps(self):
            highlight = QPen(self.pen().color().lighter(150), self.pen().widthF() + 1.5)
            highlight.setCosmetic(True)
            painter.setPen(highlight)
            painter.drawPath(self.path())

    # ── Shape / hit-test ─────────────────────────────────────────────────────

    def shape(self) -> QPainterPath:
        """Return a viewport-scale-aware stroked path so thin polylines are clickable.

        When the polyline is closed and filled, the interior is also included
        so the shape is interior-clickable.
        """
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        path = stroker.createStroke(self.path())
        if getattr(self, "fill_type", "none") != "none":
            cp = self.get_closed_path()
            if cp is not None:
                path = path.united(cp)
        return path


# ─────────────────────────────────────────────────────────────────────────────
# LineItem  — finite 2-point line (AutoCAD-style Line tool)
# ─────────────────────────────────────────────────────────────────────────────

class LineItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsLineItem):
    """
    A finite 2-point line with configurable colour and lineweight.

    Parameters
    ----------
    pt1, pt2    : QPointF  — start and end points
    color       : str | QColor — stroke colour (default white for dark theme)
    lineweight  : float — cosmetic pixel width (default 1.0)
    """

    def __init__(self, pt1: QPointF, pt2: QPointF,
                 color: str | QColor = "#ffffff", lineweight: float = 1.0):
        super().__init__()
        self._pt1 = pt1
        self._pt2 = pt2

        self.init_displayable(DEFAULT_LEVEL)
        self.init_geometry2d(DEFAULT_LEVEL)

        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)

        self.setZValue(Z_CAT_CONSTRUCTION)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)

        self.setLine(pt1.x(), pt1.y(), pt2.x(), pt2.y())

    # ── Properties ─────────────────────────────────────────────────────────

    def get_properties(self) -> dict:
        props = {
            "Type": {"type": "label", "value": "Line"},
            "Colour": {"type": "label", "value": self.pen().color().name()},
            "Line Weight": {"type": "label", "value": f"{self.pen().widthF():.1f}"},
            "Length": {"type": "label", "value": f"{self.line().length():.1f}"},
        }
        props.update(self._geom2d_properties())
        return props

    def set_property(self, key: str, value):
        if self._geom2d_set(key, value):
            return

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = {
            "type":        "draw_line",
            "pt1":         [self._pt1.x(), self._pt1.y()],
            "pt2":         [self._pt2.x(), self._pt2.y()],
            "color":       self.pen().color().name(),
            "lineweight":  self.pen().widthF(),
        }
        return self._geom2d_to_dict(d)

    @classmethod
    def from_dict(cls, data: dict) -> "LineItem":
        pt1 = QPointF(data["pt1"][0], data["pt1"][1])
        pt2 = QPointF(data["pt2"][0], data["pt2"][1])
        obj = cls(pt1, pt2, data.get("color", "#ffffff"),
                  data.get("lineweight", 1.0))
        obj._geom2d_from_dict(data)
        return obj

    # ── Grip protocol ─────────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        """Return [pt1, midpoint, pt2] as grip handles."""
        mid = QPointF((self._pt1.x() + self._pt2.x()) / 2,
                      (self._pt1.y() + self._pt2.y()) / 2)
        return [self._pt1, mid, self._pt2]

    def apply_grip(self, index: int, pos: QPointF):
        """Move a grip handle to *pos*.  index 0=pt1, 1=midpoint, 2=pt2."""
        if index == 0:
            self._pt1 = pos
        elif index == 1:
            # Mid-grip: translate entire line
            dx = pos.x() - (self._pt1.x() + self._pt2.x()) / 2
            dy = pos.y() - (self._pt1.y() + self._pt2.y()) / 2
            self._pt1 = QPointF(self._pt1.x() + dx, self._pt1.y() + dy)
            self._pt2 = QPointF(self._pt2.x() + dx, self._pt2.y() + dy)
        elif index == 2:
            self._pt2 = pos
        self.setLine(self._pt1.x(), self._pt1.y(), self._pt2.x(), self._pt2.y())

    def translate(self, dx: float, dy: float):
        """Move the entire line by (dx, dy)."""
        self._pt1 = QPointF(self._pt1.x() + dx, self._pt1.y() + dy)
        self._pt2 = QPointF(self._pt2.x() + dx, self._pt2.y() + dy)
        self.setLine(self._pt1.x(), self._pt1.y(), self._pt2.x(), self._pt2.y())

    # ── Closed-path protocol ─────────────────────────────────────────────────

    def is_closed(self) -> bool:
        """Lines are never closed shapes."""
        return False

    def get_closed_path(self) -> None:
        """Lines have no closed path."""
        return None

    # ── Paint (selection highlight) ──────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        # Apply effective display colour (category or per-instance override).
        dc = getattr(self, "_display_color", None)
        if dc:
            pen = QPen(self.pen())
            pen.setColor(QColor(dc))
            self.setPen(pen)
        super().paint(painter, option, widget)
        if self.isSelected() and not _manip_wraps(self):
            ln = self.line()
            highlight = QPen(self.pen().color().lighter(150), self.pen().widthF() + 1.5)
            highlight.setCosmetic(True)
            painter.setPen(highlight)
            painter.drawLine(ln.p1(), ln.p2())

    # ── Shape / hit-test ─────────────────────────────────────────────────────

    def shape(self) -> QPainterPath:
        """Return a viewport-scale-aware stroked path so the line is easily clickable."""
        path = QPainterPath()
        path.moveTo(self._pt1)
        path.lineTo(self._pt2)
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        return stroker.createStroke(path)


# ─────────────────────────────────────────────────────────────────────────────
# RectangleItem  — axis-aligned rectangle (two corner clicks)
# ─────────────────────────────────────────────────────────────────────────────

class RectangleItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsRectItem):
    """
    An axis-aligned rectangle defined by two opposite corners.

    Parameters
    ----------
    pt1, pt2    : QPointF — opposite corners (order does not matter)
    color       : str | QColor
    lineweight  : float — cosmetic pixel width
    """

    def __init__(self, pt1: QPointF, pt2: QPointF,
                 color: str | QColor = "#ffffff", lineweight: float = 1.0):
        rect = QRectF(pt1, pt2).normalized()
        super().__init__(rect)

        self.init_displayable(DEFAULT_LEVEL)
        self.init_geometry2d(DEFAULT_LEVEL)

        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        self.setZValue(Z_CAT_CONSTRUCTION)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)

        # Rotation state (baked-at-rest — selection-manipulator.md).  The rect
        # stays axis-aligned in local coords; the rotation is stored as DATA
        # (``_angle``/``_pivot``), NOT a held Qt item transform.  ``rotation()``
        # is always 0 at rest.  ``_pivot`` is None when the origin should track
        # the rect centre on resize; an explicit pivot is stored and left fixed.
        # paint/shape/boundingRect/grip_points and the map* overrides all read
        # the rotation from ``_rotation_transform()`` so the rendered/hit
        # footprint matches the old held-transform footprint byte-for-byte.
        self._angle: float = 0.0
        self._pivot: QPointF | None = None

    # ── Rotation ───────────────────────────────────────────────────────────

    def set_angle(self, angle_deg: float, pivot: "QPointF | None" = None) -> None:
        """Rotate the rectangle to ``angle_deg`` (from +x) about ``pivot``.

        Bake-at-rest: the angle/pivot are stored as DATA — NO Qt item transform
        is applied (``rotation()`` stays 0).  ``paint``/``shape``/``boundingRect``
        and the ``mapToScene``/``mapFromScene``/``mapRectToScene`` overrides read
        this state so the rotated rect renders and hit-tests exactly as the old
        ``setRotation``/``setTransformOriginPoint`` path did.  ``pivot`` defaults
        to the rect centre (tracked on resize when ``_pivot is None``).
        """
        self._angle = float(angle_deg)
        if pivot is not None:
            self._pivot = QPointF(pivot)
        else:
            self._pivot = None          # origin follows rect centre on resize
        # Data-only: drop any held transform (a load path or legacy caller may
        # have left one) and refresh the cached rotated footprint.
        self.prepareGeometryChange()
        self.update()

    # ── Rotation helpers (data-only footprint) ────────────────────────────

    def _rotation_origin(self) -> QPointF:
        """Resolved rotation pivot: the explicit ``_pivot`` or the rect centre."""
        return QPointF(self._pivot) if self._pivot is not None else self.rect().center()

    def _rotation_transform(self) -> QTransform:
        """Local→scene rotation matrix equivalent to the retired held transform.

        Mirrors the old ``setRotation(-_angle)`` about the resolved pivot: a
        Y-up CCW ``_angle`` becomes Qt's CW-positive ``rotate(-_angle)`` about
        the origin.  Identity at angle 0, so unrotated rects keep the plain
        local==scene contract.
        """
        m = QTransform()
        if self._angle == 0.0:
            return m
        o = self._rotation_origin()
        m.translate(o.x(), o.y())
        m.rotate(-self._angle)          # Y-up CCW → Qt CW negate
        m.translate(-o.x(), -o.y())
        return m

    # ── map* overrides (route rotation through data, not a held transform) ──

    def mapToScene(self, *args):
        """Local→scene through the data rotation (item pos is identity).

        Overridden so external callers that historically relied on the held Qt
        rotation (snap_engine, tool_geometry, grip_points…) keep working after
        the bake-at-rest migration.  Accepts the same overloads used in-tree:
        a ``QPointF``, an ``(x, y)`` pair, or a ``QPainterPath``.
        """
        t = self._rotation_transform()
        if len(args) == 2:                       # (x, y)
            return t.map(QPointF(args[0], args[1]))
        obj = args[0]
        if isinstance(obj, QPainterPath):
            return t.map(obj)
        return t.map(QPointF(obj))

    def mapFromScene(self, *args):
        """Scene→local inverse of :meth:`mapToScene`."""
        inv, ok = self._rotation_transform().inverted()
        if not ok:
            inv = QTransform()
        if len(args) == 2:
            return inv.map(QPointF(args[0], args[1]))
        obj = args[0]
        if isinstance(obj, QPainterPath):
            return inv.map(obj)
        return inv.map(QPointF(obj))

    def mapRectToScene(self, rect: QRectF) -> QRectF:
        """Bounding rect of ``rect`` after the data rotation.

        Matches Qt's held-transform ``mapRectToScene`` (returns the axis-aligned
        bounds of the rotated rect), preserving offset/snap-distance callers.
        """
        return self._rotation_transform().mapRect(rect)

    # ── Properties ─────────────────────────────────────────────────────────

    def get_properties(self) -> dict:
        r = self.rect()
        props = {
            "Type": {"type": "label", "value": "Rectangle"},
            "Width": {"type": "label", "value": f"{r.width():.1f}"},
            "Height": {"type": "label", "value": f"{r.height():.1f}"},
            "Angle": {"type": "label", "value": f"{self._angle:.1f}"},
            "Colour": {"type": "label", "value": self.pen().color().name()},
            "Line Weight": {"type": "label", "value": f"{self.pen().widthF():.1f}"},
        }
        props.update(self._geom2d_properties())
        return props

    def set_property(self, key: str, value):
        if self._geom2d_set(key, value):
            return

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        r = self.rect()
        # Persist ``pivot`` as null when the rotation follows the rect centre
        # (``_pivot is None``) and as [x, y] only for an explicit pinned pivot.
        # Storing the resolved centre instead would round-trip the render but
        # pin the origin, so a later resize (reachable via undo, which uses this
        # same path) would rotate about the stale point instead of re-centring.
        pivot = None if self._pivot is None else [self._pivot.x(), self._pivot.y()]
        d = {
            "type":        "draw_rectangle",
            "x":           r.x(),
            "y":           r.y(),
            "w":           r.width(),
            "h":           r.height(),
            "color":       self.pen().color().name(),
            "lineweight":  self.pen().widthF(),
            "angle":       self._angle,
            "pivot":       pivot,
        }
        return self._geom2d_to_dict(d)

    @classmethod
    def from_dict(cls, data: dict) -> "RectangleItem":
        pt1 = QPointF(data["x"], data["y"])
        pt2 = QPointF(data["x"] + data["w"], data["y"] + data["h"])
        obj = cls(pt1, pt2, data.get("color", "#ffffff"),
                  data.get("lineweight", 1.0))
        obj._geom2d_from_dict(data)
        # Back-compat: pre-rotation records have no "angle"/"pivot" — default to
        # 0° about the rect centre, an identity transform (renders axis-aligned
        # exactly as before).  A stored null pivot means "follow the centre", so
        # it restores as _pivot=None (set_angle re-derives + keeps tracking).
        angle = data.get("angle", 0.0)
        pivot = QPointF(*data["pivot"]) if data.get("pivot") else None
        obj.set_angle(angle, pivot)
        return obj

    # ── Grip protocol ─────────────────────────────────────────────────────────
    # Grip indices (clockwise from top-left):
    #   0=TL  1=TM  2=TR  3=RM  4=BR  5=BM  6=BL  7=LM  8=Centre

    def grip_points(self) -> list[QPointF]:
        """Return the 9 grips in SCENE coords.

        Corners are computed in the axis-aligned LOCAL rect, then mapped through
        the item transform (``mapToScene``) so a rotated rectangle reports its
        grips in scene space.  At angle 0 the transform is identity and this is a
        no-op, preserving the original scene-coord contract for consumers.
        """
        r = self.rect()
        cx, cy = r.center().x(), r.center().y()
        local = [
            QPointF(r.left(),  r.top()),                  # 0 TL
            QPointF(cx,        r.top()),                  # 1 TM
            QPointF(r.right(), r.top()),                  # 2 TR
            QPointF(r.right(), cy),                       # 3 RM
            QPointF(r.right(), r.bottom()),               # 4 BR
            QPointF(cx,        r.bottom()),               # 5 BM
            QPointF(r.left(),  r.bottom()),               # 6 BL
            QPointF(r.left(),  cy),                       # 7 LM
            QPointF(cx,        cy),                       # 8 Centre
        ]
        return [self.mapToScene(p) for p in local]

    def apply_grip(self, index: int, pos: QPointF):
        """Resize or translate the rectangle by dragging one of its 9 grips.

        ``pos`` arrives in SCENE coords; it is mapped to LOCAL first so the
        resize runs in the rectangle's own (rotated) frame.  At angle 0 the
        map is identity and behaviour matches the pre-rotation implementation.
        """
        local = self.mapFromScene(pos)
        r = self.rect()
        l, t, ri, b = r.left(), r.top(), r.right(), r.bottom()

        if   index == 0:  new_r = QRectF(QPointF(local.x(), local.y()), QPointF(ri,  b )).normalized()
        elif index == 1:  new_r = QRectF(QPointF(l,  local.y()), QPointF(ri,  b )).normalized()
        elif index == 2:  new_r = QRectF(QPointF(l,  local.y()), QPointF(local.x(), b )).normalized()
        elif index == 3:  new_r = QRectF(QPointF(l,  t ), QPointF(local.x(), b )).normalized()
        elif index == 4:  new_r = QRectF(QPointF(l,  t ), QPointF(local.x(), local.y())).normalized()
        elif index == 5:  new_r = QRectF(QPointF(l,  t ), QPointF(ri,  local.y())).normalized()
        elif index == 6:  new_r = QRectF(QPointF(local.x(), t ), QPointF(ri,  local.y())).normalized()
        elif index == 7:  new_r = QRectF(QPointF(local.x(), t ), QPointF(ri,  b )).normalized()
        elif index == 8:
            # Centre grip → translate (in local frame)
            dx, dy = local.x() - r.center().x(), local.y() - r.center().y()
            new_r = r.translated(dx, dy)
        else:
            return
        self.prepareGeometryChange()
        self.setRect(new_r)
        # A centre-following pivot (``_pivot is None``) re-derives from the new
        # rect centre automatically (see ``_rotation_origin``); no held origin
        # to update now that rotation is baked-at-rest data.

    def translate(self, dx: float, dy: float):
        self.prepareGeometryChange()
        self.setRect(self.rect().translated(dx, dy))
        # Carry an explicit pivot with the rect (every rotate-step rect has one)
        # so a rotated rect keeps swinging about the same relative origin after a
        # move.  A centre-following pivot re-derives from the new centre.
        if self._pivot is not None:
            self._pivot = QPointF(self._pivot.x() + dx, self._pivot.y() + dy)

    # ── Closed-path protocol ─────────────────────────────────────────────────

    def is_closed(self) -> bool:
        """Rectangles are always closed shapes."""
        return True

    def get_closed_path(self) -> QPainterPath:
        """Return a QPainterPath rectangle for hatching / fill operations."""
        path = QPainterPath()
        path.addRect(self.rect())
        return path

    # ── Paint (selection highlight) ──────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        # Apply effective display colour (category or per-instance override).
        dc = getattr(self, "_display_color", None)
        if dc:
            pen = QPen(self.pen())
            pen.setColor(QColor(dc))
            self.setPen(pen)
        # Bake-at-rest: rotation is DATA, not a held item transform, so rotate
        # the painter about the pivot here (local rect stays axis-aligned).
        # save/restore keeps the rotation local to this paint call.
        painter.save()
        if self._angle != 0.0:
            painter.setWorldTransform(self._rotation_transform(), True)
        # Draw fill FIRST (behind the outline).
        if getattr(self, "fill_type", "none") != "none":
            cp = self.get_closed_path()
            if cp is not None:
                from .displayable_item import draw_fill
                draw_fill(painter, cp, self.scene(), self.fill_type,
                          self.fill_pattern, self._display_fill_color or "#888888",
                          alpha=int(round(self.fill_opacity * 255)))
        super().paint(painter, option, widget)
        if self.isSelected() and not _manip_wraps(self):
            highlight = QPen(self.pen().color().lighter(150), self.pen().widthF() + 1.5)
            highlight.setCosmetic(True)
            painter.setPen(highlight)
            painter.drawRect(self.rect())
        painter.restore()

    # ── Shape / hit-test ─────────────────────────────────────────────────────

    def boundingRect(self) -> QRectF:
        """Rotated-footprint bounds (bake-at-rest — no held item transform).

        The base rect ``boundingRect`` is the axis-aligned local rect; with the
        rotation baked to data we return the rotated footprint's bounds so Qt's
        scene index / culling wraps the real shape (the held transform did this
        for free before).
        """
        base = super().boundingRect()
        if self._angle == 0.0:
            return base
        return self._rotation_transform().mapRect(base)

    def shape(self) -> QPainterPath:
        """Return a stroked outline path so the rectangle border is clickable.

        When filled, also include the interior so clicking anywhere inside
        selects the rectangle.  The path is rotated by the data ``_angle`` about
        the pivot so scene hit-testing tracks the rotated footprint.
        """
        cp = self.get_closed_path()  # addRect path in local coords
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        path = stroker.createStroke(cp)
        if getattr(self, "fill_type", "none") != "none":
            path = path.united(cp)
        if self._angle != 0.0:
            path = self._rotation_transform().map(path)
        return path

    # ── Manipulator capability protocol (selection-manipulator.md) ──────────

    def manip_capabilities(self) -> set:
        """Narrow the duck-typed capability set for the current state.

        Resize is only correct while the rect is axis-aligned: the manipulator
        frame + its ``(fx, fy)`` factors live in the selection's axis-aligned
        scene bounds, but ``manip_scale`` applies them in the rect's rotated
        local frame — which shears (or swaps W/H at 90°/270°) once ``_angle``
        is non-zero. So a rotated rect exposes move + rotate only (no resize
        handles); rotate it back to 0° to resize, or see the ``rotated-rect
        resize`` follow-up. Unrotated rects keep the full set.
        """
        if self._angle != 0.0:
            return {"translate", "rotate"}
        return {"translate", "rotate", "scale"}

    def manip_bounds(self) -> QRectF:
        """The rect's own geometry in scene coords so the manipulator handles
        hug the shape (not the pen-padded ``sceneBoundingRect``).  For a rotated
        rect this is the axis-aligned bounds, which is the correct frame wrap."""
        return self.mapRectToScene(self.rect())

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        """Baked rotate: accumulate ``angle_deg`` onto the current angle about
        ``pivot`` (Y-up CCW+).  One home with ``set_angle`` so the manipulator
        and the placement rotate-step cannot drift."""
        self.set_angle(self._angle + angle_deg, pivot)

    def manip_scale(self, fx: float, fy: float, anchor: "QPointF") -> None:
        """Baked resize about a scene ``anchor`` by factors ``(fx, fy)``.

        Routes through the SAME rect-mutation primitive a corner grip uses
        (:meth:`apply_grip`) so grips and the manipulator share one geometry
        path.  The anchor's nearest local corner is held fixed and the opposite
        corner is scaled about it in the rect's own (rotated) frame, then handed
        to ``apply_grip`` in scene coords.  An anchor at the centre
        (Ctrl / from-centre resize) scales both corners about the centre.
        """
        r = self.rect()
        a_local = self.mapFromScene(anchor)
        c = r.center()
        tl = QPointF(r.left(), r.top())
        br = QPointF(r.right(), r.bottom())
        near_tl = abs(a_local.x() - r.left()) + abs(a_local.y() - r.top())
        near_br = abs(a_local.x() - r.right()) + abs(a_local.y() - r.bottom())
        near_c = abs(a_local.x() - c.x()) + abs(a_local.y() - c.y())
        if near_c < near_tl and near_c < near_br:
            # From-centre: scale both corners about the centre.
            hw = r.width() * abs(fx) / 2.0
            hh = r.height() * abs(fy) / 2.0
            self.prepareGeometryChange()
            self.setRect(QRectF(c.x() - hw, c.y() - hh, 2 * hw, 2 * hh))
            return
        if near_tl <= near_br:
            fixed, moving, grip = tl, br, 4        # TL fixed, drag BR
        else:
            fixed, moving, grip = br, tl, 0        # BR fixed, drag TL
        target_local = QPointF(
            fixed.x() + (moving.x() - fixed.x()) * fx,
            fixed.y() + (moving.y() - fixed.y()) * fy,
        )
        self.apply_grip(grip, self.mapToScene(target_local))


# ─────────────────────────────────────────────────────────────────────────────
# CircleItem  — circle defined by centre + edge point
# ─────────────────────────────────────────────────────────────────────────────

class CircleItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsEllipseItem):
    """
    A circle defined by its centre and one point on the circumference.

    Parameters
    ----------
    center  : QPointF — circle centre in scene coordinates
    radius  : float   — radius in scene units
    color   : str | QColor
    lineweight : float — cosmetic pixel width
    """

    def __init__(self, center: QPointF, radius: float,
                 color: str | QColor = "#ffffff", lineweight: float = 1.0):
        self._center = center
        self._radius = radius
        r = radius
        super().__init__(center.x() - r, center.y() - r, 2 * r, 2 * r)

        self.init_displayable(DEFAULT_LEVEL)
        self.init_geometry2d(DEFAULT_LEVEL)

        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        self.setZValue(Z_CAT_CONSTRUCTION)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)

    # ── Properties ─────────────────────────────────────────────────────────

    def get_properties(self) -> dict:
        props = {
            "Type": {"type": "label", "value": "Circle"},
            "Centre": {"type": "label", "value": f"({self._center.x():.1f}, {self._center.y():.1f})"},
            "Radius": {"type": "label", "value": f"{self._radius:.1f}"},
            "Colour": {"type": "label", "value": self.pen().color().name()},
            "Line Weight": {"type": "label", "value": f"{self.pen().widthF():.1f}"},
        }
        props.update(self._geom2d_properties())
        return props

    def set_property(self, key: str, value):
        if self._geom2d_set(key, value):
            return

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = {
            "type":        "draw_circle",
            "cx":          self._center.x(),
            "cy":          self._center.y(),
            "radius":      self._radius,
            "color":       self.pen().color().name(),
            "lineweight":  self.pen().widthF(),
        }
        return self._geom2d_to_dict(d)

    @classmethod
    def from_dict(cls, data: dict) -> "CircleItem":
        center = QPointF(data["cx"], data["cy"])
        obj = cls(center, data["radius"],
                  data.get("color", "#ffffff"), data.get("lineweight", 1.0))
        obj._geom2d_from_dict(data)
        return obj

    # ── Grip protocol ─────────────────────────────────────────────────────────
    # Grip indices: 0=centre  1=right  2=top  3=left  4=bottom

    def grip_points(self) -> list[QPointF]:
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        return [
            QPointF(cx,     cy),      # 0 centre
            QPointF(cx + r, cy),      # 1 right  (0°)
            QPointF(cx,     cy - r),  # 2 top    (90°)
            QPointF(cx - r, cy),      # 3 left   (180°)
            QPointF(cx,     cy + r),  # 4 bottom (270°)
        ]

    def apply_grip(self, index: int, pos: QPointF):
        """Translate (index 0) or resize (index 1-4)."""
        import math as _math
        if index == 0:
            self._center = pos
        else:
            self._radius = _math.hypot(
                pos.x() - self._center.x(),
                pos.y() - self._center.y(),
            )
            if self._radius < 1:
                self._radius = 1
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        self.setRect(cx - r, cy - r, 2 * r, 2 * r)

    def translate(self, dx: float, dy: float):
        self._center = QPointF(self._center.x() + dx, self._center.y() + dy)
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        self.setRect(cx - r, cy - r, 2 * r, 2 * r)

    # ── Closed-path protocol ─────────────────────────────────────────────────

    def is_closed(self) -> bool:
        """Circles are always closed shapes."""
        return True

    def get_closed_path(self) -> QPainterPath:
        """Return a QPainterPath ellipse for hatching / fill operations."""
        path = QPainterPath()
        path.addEllipse(self.rect())
        return path

    # ── Paint (selection highlight) ──────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        # Apply effective display colour (category or per-instance override).
        dc = getattr(self, "_display_color", None)
        if dc:
            pen = QPen(self.pen())
            pen.setColor(QColor(dc))
            self.setPen(pen)
        # Draw fill FIRST (behind the outline)
        if getattr(self, "fill_type", "none") != "none":
            cp = self.get_closed_path()
            if cp is not None:
                from .displayable_item import draw_fill
                draw_fill(painter, cp, self.scene(), self.fill_type,
                          self.fill_pattern, self._display_fill_color or "#888888",
                          alpha=int(round(self.fill_opacity * 255)))
        super().paint(painter, option, widget)
        if self.isSelected() and not _manip_wraps(self):
            highlight = QPen(self.pen().color().lighter(150), self.pen().widthF() + 1.5)
            highlight.setCosmetic(True)
            painter.setPen(highlight)
            painter.drawEllipse(self.rect())

    # ── Shape / hit-test ─────────────────────────────────────────────────────

    def shape(self) -> QPainterPath:
        """Return a stroked ellipse outline path so the circle border is clickable.

        When filled, also include the interior so clicking anywhere inside
        selects the circle.
        """
        cp = self.get_closed_path()  # addEllipse path in local coords
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        path = stroker.createStroke(cp)
        if getattr(self, "fill_type", "none") != "none":
            path = path.united(cp)
        return path


# ─────────────────────────────────────────────────────────────────────────────
# ArcItem
# ─────────────────────────────────────────────────────────────────────────────

class ArcItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsPathItem):
    """
    A circular arc defined by centre, radius, start angle and span angle.
    Angles are in degrees, measured counter-clockwise from the +X axis
    (Qt convention: positive span = CCW, angles in 1/16ths internally but
    we use QPainterPath.arcTo which takes plain degrees).
    """

    def __init__(self, center: QPointF, radius: float,
                 start_deg: float, span_deg: float,
                 color: str = "#ffffff", lineweight: float = 1.0):
        super().__init__()
        self._center = QPointF(center)
        self._radius = max(radius, 0.01)
        self._start_deg = start_deg
        self._span_deg = span_deg

        self.init_displayable(DEFAULT_LEVEL)
        self.init_geometry2d(DEFAULT_LEVEL)

        pen = QPen(QColor(color), lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setFlags(
            self.GraphicsItemFlag.ItemIsSelectable |
            self.GraphicsItemFlag.ItemIsMovable
        )
        self._rebuild_path()

    def _rebuild_path(self):
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        path = QPainterPath()
        rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
        path.arcMoveTo(rect, self._start_deg)
        path.arcTo(rect, self._start_deg, self._span_deg)
        self.setPath(path)

    # ── Properties ─────────────────────────────────────────────────────────

    def get_properties(self) -> dict:
        props = {
            "Type":        {"type": "label", "value": "Arc"},
            "Centre":      {"type": "label", "value": f"({self._center.x():.1f}, {self._center.y():.1f})"},
            "Radius":      {"type": "label", "value": f"{self._radius:.1f}"},
            "Start Angle": {"type": "label", "value": f"{self._start_deg:.1f}°"},
            "Span":        {"type": "label", "value": f"{self._span_deg:.1f}°"},
            "Colour":      {"type": "label", "value": self.pen().color().name()},
            "Line Weight": {"type": "label", "value": f"{self.pen().widthF():.1f}"},
        }
        props.update(self._geom2d_properties())
        return props

    def set_property(self, key: str, value):
        if self._geom2d_set(key, value):
            return

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = {
            "type":       "arc",
            "cx":         self._center.x(),
            "cy":         self._center.y(),
            "radius":     self._radius,
            "start_deg":  self._start_deg,
            "span_deg":   self._span_deg,
            "color":      self.pen().color().name(),
            "lineweight": self.pen().widthF(),
        }
        return self._geom2d_to_dict(d)

    @classmethod
    def from_dict(cls, data: dict) -> "ArcItem":
        center = QPointF(data["cx"], data["cy"])
        obj = cls(center, data["radius"], data["start_deg"], data["span_deg"],
                  data.get("color", "#ffffff"), data.get("lineweight", 1.0))
        obj._geom2d_from_dict(data)
        return obj

    # ── Grip protocol ─────────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        sa = math.radians(self._start_deg)
        ea = math.radians(self._start_deg + self._span_deg)
        return [
            QPointF(cx, cy),                                    # 0 centre
            QPointF(cx + r * math.cos(sa), cy - r * math.sin(sa)),  # 1 start
            QPointF(cx + r * math.cos(ea), cy - r * math.sin(ea)),  # 2 end
        ]

    def apply_grip(self, index: int, pos: QPointF):
        if index == 0:
            self._center = pos
        elif index == 1:
            # Move start point — change radius and start angle
            dx = pos.x() - self._center.x()
            dy = pos.y() - self._center.y()
            self._radius = max(math.hypot(dx, dy), 0.01)
            self._start_deg = math.degrees(math.atan2(-dy, dx))
        elif index == 2:
            # Move end point — change span angle
            dx = pos.x() - self._center.x()
            dy = pos.y() - self._center.y()
            end_deg = math.degrees(math.atan2(-dy, dx))
            self._span_deg = (end_deg - self._start_deg) % 360
            if self._span_deg == 0:
                self._span_deg = 360
        self._rebuild_path()

    def translate(self, dx: float, dy: float):
        self._center = QPointF(self._center.x() + dx, self._center.y() + dy)
        self._rebuild_path()

    # ── Closed-path protocol ─────────────────────────────────────────────────

    def is_closed(self) -> bool:
        """Return True if the arc spans a full 360 degrees (i.e. a full circle)."""
        return abs(self._span_deg) >= 360

    def get_closed_path(self) -> QPainterPath | None:
        """Return a QPainterPath ellipse if the arc is a full circle, else None."""
        if not self.is_closed():
            return None
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        path = QPainterPath()
        path.addEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        return path

    # ── Paint (selection highlight) ──────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        # Apply effective display colour (category or per-instance override).
        dc = getattr(self, "_display_color", None)
        if dc:
            pen = QPen(self.pen())
            pen.setColor(QColor(dc))
            self.setPen(pen)
        # Draw fill FIRST (behind the outline); only applies when arc is closed
        if getattr(self, "fill_type", "none") != "none":
            cp = self.get_closed_path()
            if cp is not None:
                from .displayable_item import draw_fill
                draw_fill(painter, cp, self.scene(), self.fill_type,
                          self.fill_pattern, self._display_fill_color or "#888888",
                          alpha=int(round(self.fill_opacity * 255)))
        super().paint(painter, option, widget)
        if self.isSelected() and not _manip_wraps(self):
            highlight = QPen(self.pen().color().lighter(150), self.pen().widthF() + 1.5)
            highlight.setCosmetic(True)
            painter.setPen(highlight)
            painter.drawPath(self.path())

    def shape(self) -> QPainterPath:
        """Return a stroked arc path; when the arc is a closed circle and is
        filled, also include the interior for interior hit-testing.
        """
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        path = stroker.createStroke(self.path())
        if getattr(self, "fill_type", "none") != "none":
            cp = self.get_closed_path()
            if cp is not None:
                path = path.united(cp)
        return path


# ─────────────────────────────────────────────────────────────────────────────
# RegularPolygonItem — parametric regular N-gon
# ─────────────────────────────────────────────────────────────────────────────

_POLY_MIN_SIDES = 3
_POLY_MAX_SIDES = 120


class RegularPolygonItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsPathItem):
    """A parametric regular polygon defined by centre/sides/radius/rotation.

    ``_radius_mm`` is the *defining* radius the user picked: the circumradius
    (centre->vertex) when ``_inscribed`` is True, or the apothem (centre->edge
    midpoint) when False.  Vertices are always derived, never stored.
    """

    def __init__(self, center: QPointF, sides: int = 6, radius_mm: float = 0.0,
                 rotation_deg: float = 0.0, inscribed: bool = True,
                 color: str | QColor = "#ffffff", lineweight: float = 1.0):
        super().__init__()
        self._center = QPointF(center)
        self._sides = max(_POLY_MIN_SIDES, min(_POLY_MAX_SIDES, int(sides)))
        self._radius_mm = float(radius_mm)
        self._rotation_deg = float(rotation_deg)
        self._inscribed = bool(inscribed)

        self.init_displayable(DEFAULT_LEVEL)
        self.init_geometry2d(DEFAULT_LEVEL)

        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setZValue(Z_CAT_CONSTRUCTION)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)
        self._regenerate()

    def _circumradius(self) -> float:
        if self._inscribed:
            return self._radius_mm
        return self._radius_mm / math.cos(math.pi / self._sides)

    def vertices(self) -> list[QPointF]:
        rv = self._circumradius()
        step = 360.0 / self._sides
        # For circumscribed polygons the natural orientation places a flat edge
        # facing the user (apothem along +X axis), which means the first vertex
        # is offset by half a step from the rotation origin.
        base = self._rotation_deg + (0.0 if self._inscribed
                                     else 180.0 / self._sides)
        out = []
        for k in range(self._sides):
            a = math.radians(base + k * step)
            # Y-up convention (CCW-positive, app-wide): a positive rotation
            # swings vertices up (−y in Qt scene), so sin is negated.  Matches
            # the placement rotate angle, the dashed reference line, and the
            # shared "rotation" HUD schema.  apply_grip() negates dy to stay the
            # exact inverse of this.
            out.append(QPointF(self._center.x() + rv * math.cos(a),
                               self._center.y() - rv * math.sin(a)))
        return out

    def _regenerate(self):
        verts = self.vertices()
        path = QPainterPath()
        if verts:
            path.addPolygon(QPolygonF(verts))
            path.closeSubpath()
        self.setPath(path)
        self.update()

    def get_closed_path(self) -> QPainterPath | None:
        p = QPainterPath()
        p.addPolygon(QPolygonF(self.vertices()))
        p.closeSubpath()
        return p

    def get_properties(self) -> dict:
        props = {
            "Type":     {"type": "label", "value": "Polygon"},
            "Sides":    {"type": "string", "value": str(self._sides)},
            "Radius":   {"type": "dimension",
                         "value": self._fmt(self._radius_mm),
                         "value_mm": self._radius_mm},
            "Rotation": {"type": "string",
                         "value": f"{self._rotation_deg:.2f}", "suffix": "°"},
            "Shape":    {"type": "enum",
                         "options": ["inscribed", "circumscribed"],
                         "value": "inscribed" if self._inscribed else "circumscribed"},
        }
        props.update(self._geom2d_properties())
        return props

    def set_property(self, key: str, value):
        if key == "Sides":
            try:
                self._sides = max(_POLY_MIN_SIDES, min(_POLY_MAX_SIDES, int(float(value))))
            except (TypeError, ValueError):
                return
            self._regenerate()
            return
        if key == "Radius":
            r = self._parse_dim(value)
            if r is not None and r > 0:
                self._radius_mm = r
                self._regenerate()
            return
        if key == "Rotation":
            try:
                self._rotation_deg = float(str(value).replace("°", "").strip())
            except (TypeError, ValueError):
                return
            self._regenerate()
            return
        if key == "Shape":
            self._inscribed = (str(value) == "inscribed")
            self._regenerate()
            return
        if self._geom2d_set(key, value):
            self._regenerate()
            return

    def grip_points(self) -> list[QPointF]:
        return [QPointF(self._center)] + self.vertices()

    def apply_grip(self, index: int, pos: QPointF):
        if index == 0:
            self._center = QPointF(pos)
            self._regenerate()
            return
        vi = index - 1
        if not (0 <= vi < self._sides):
            return
        dx, dy = pos.x() - self._center.x(), pos.y() - self._center.y()
        rv = math.hypot(dx, dy)
        if rv < 0.5:
            return
        step = 360.0 / self._sides
        # The base angle for vertex 0 is _rotation_deg + circ_offset.
        # Solve: ang = _rotation_deg + circ_offset + vi * step
        # circ_offset mirrors the same half-step applied in vertices(); the two
        # must stay in sync — this line is the inverse of vertices()'s `base`.
        circ_offset = 0.0 if self._inscribed else 180.0 / self._sides
        # Y-up angle of the drag point (−dy): the exact inverse of vertices(),
        # which places vertex vi at angle (rotation + circ_offset + vi*step) in
        # the Y-up frame.  So the dragged vertex lands exactly under the cursor.
        ang = math.degrees(math.atan2(-dy, dx))
        self._rotation_deg = ang - circ_offset - vi * step
        self._radius_mm = rv if self._inscribed else rv * math.cos(math.pi / self._sides)
        self._regenerate()

    def translate(self, dx: float, dy: float):
        self._center = QPointF(self._center.x() + dx, self._center.y() + dy)
        self._regenerate()

    def to_dict(self) -> dict:
        d = {
            "type":        "polygon",
            "center":      [self._center.x(), self._center.y()],
            "sides":       self._sides,
            "radius_mm":   self._radius_mm,
            "rotation":    self._rotation_deg,
            "inscribed":   self._inscribed,
            "color":       self.pen().color().name(),
            "lineweight":  self.pen().widthF(),
        }
        return self._geom2d_to_dict(d)

    @classmethod
    def from_dict(cls, data: dict) -> "RegularPolygonItem":
        c = data["center"]
        obj = cls(QPointF(c[0], c[1]),
                  sides=data.get("sides", 6),
                  radius_mm=data.get("radius_mm", 0.0),
                  rotation_deg=data.get("rotation", 0.0),
                  inscribed=data.get("inscribed", True),
                  color=data.get("color", "#ffffff"),
                  lineweight=data.get("lineweight", 1.0))
        obj._geom2d_from_dict(data)
        obj._regenerate()
        return obj

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        dc = getattr(self, "_display_color", None)
        if dc:
            pen = QPen(self.pen()); pen.setColor(QColor(dc)); self.setPen(pen)
        if getattr(self, "fill_type", "none") != "none":
            cp = self.get_closed_path()
            if cp is not None:
                from .displayable_item import draw_fill
                draw_fill(painter, cp, self.scene(), self.fill_type,
                          self.fill_pattern, self._display_fill_color or "#888888",
                          alpha=int(round(self.fill_opacity * 255)))
        super().paint(painter, option, widget)
        if self.isSelected() and not _manip_wraps(self):
            hl = QPen(self.pen().color().lighter(150), self.pen().widthF() + 1.5)
            hl.setCosmetic(True)
            painter.setPen(hl)
            painter.drawPath(self.path())
            # Draw a dashed circumradius reference circle when selected so the
            # user can see the defining circle.  Subtle: thin dashed cosmetic pen.
            rv = self._circumradius()
            cx, cy = self._center.x(), self._center.y()
            ref_pen = QPen(self.pen().color(), 1, Qt.PenStyle.DashLine)
            ref_pen.setCosmetic(True)
            painter.setPen(ref_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(cx - rv, cy - rv, 2 * rv, 2 * rv))

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        path = stroker.createStroke(self.path())
        if getattr(self, "fill_type", "none") != "none":
            path = path.united(self.get_closed_path())
        return path


# ─────────────────────────────────────────────────────────────────────────────
# GeometryTemplate — pre-placement defaults for geometry tools
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Pure geometry helpers — shared by 2D-geo and wall rectangle placement
# ─────────────────────────────────────────────────────────────────────────────

def rect_sizing_points(anchor, corner, from_center):
    """Return axis-aligned (pt1_topleft, pt2_bottomright) from two placement points.

    Args:
        anchor: First placement click (QPointF).  Corner mode: one corner of
            the rectangle.  Centre mode: the rectangle centre.
        corner: Second placement click (QPointF).  Corner mode: the diagonally
            opposite corner.  Centre mode: any corner — half-extents are taken
            as ``abs(corner - anchor)``.
        from_center: True for centre mode, False for corner mode.

    Returns:
        ``(pt1, pt2)`` where pt1 is the top-left and pt2 the bottom-right of
        the normalised axis-aligned bounding box.
    """
    if from_center:
        hw = abs(corner.x() - anchor.x())
        hh = abs(corner.y() - anchor.y())
        return (QPointF(anchor.x() - hw, anchor.y() - hh),
                QPointF(anchor.x() + hw, anchor.y() + hh))
    r = QRectF(anchor, corner).normalized()
    return (QPointF(r.x(), r.y()),
            QPointF(r.x() + r.width(), r.y() + r.height()))


def rotated_rect_corners(pt1, pt2, angle_deg, pivot):
    """Return the four scene-space corners (TL, TR, BR, BL) of an axis-aligned
    rect after applying a Y-up CCW rotation of ``angle_deg`` about ``pivot``.

    This replicates what ``RectangleItem(pt1, pt2).set_angle(angle_deg, pivot)``
    + ``mapToScene(local_corner)`` produces:

    * ``set_angle`` calls ``setRotation(-angle_deg)`` (Y-up CCW → Qt CW negate).
    * Qt's ``mapToScene`` with rotation ``-angle_deg`` applies the matrix:
      ``x' = cos(a)*dx + sin(a)*dy``, ``y' = -sin(a)*dx + cos(a)*dy``
      where ``dx = p.x() - pivot.x()``, ``dy = p.y() - pivot.y()``.

    Args:
        pt1: Top-left corner of the axis-aligned rect (QPointF).
        pt2: Bottom-right corner of the axis-aligned rect (QPointF).
        angle_deg: Y-up CCW angle in degrees.
        pivot: Scene-space rotation origin (QPointF).

    Returns:
        List of four QPointF in order TL, TR, BR, BL.
    """
    import math as _math
    local = [
        QPointF(pt1.x(), pt1.y()),   # TL
        QPointF(pt2.x(), pt1.y()),   # TR
        QPointF(pt2.x(), pt2.y()),   # BR
        QPointF(pt1.x(), pt2.y()),   # BL
    ]
    rad = _math.radians(angle_deg)
    ca, sa = _math.cos(rad), _math.sin(rad)
    out = []
    for p in local:
        dx = p.x() - pivot.x()
        dy = p.y() - pivot.y()
        # Qt rotation with angle -angle_deg (CW negate of Y-up angle):
        # cos(-a) = ca, sin(-a) = -sa
        # x' = ca*dx + sa*dy   (= cos(-a)*dx - sin(-a)*dy)
        # y' = -sa*dx + ca*dy  (= sin(-a)*dx + cos(-a)*dy)
        rx = ca * dx + sa * dy
        ry = -sa * dx + ca * dy
        out.append(QPointF(pivot.x() + rx, pivot.y() + ry))
    return out


class GeometryTemplate:
    """Pre-placement template for geometry tools (line, rectangle, circle, etc.).

    Provides ``get_properties()`` / ``set_property()`` so the PropertyManager
    can display and edit default values before placement.  Colour and
    line-weight are derived from the selected layer at placement time.
    """

    def __init__(self):
        self.level: str = DEFAULT_LEVEL
        self._level_offset_mm: float = 0.0
        self.name: str = "(Template)"

    def get_properties(self) -> dict:
        return {
            "Type":         {"type": "label",     "value": "Geometry"},
            "Level":        {"type": "level_ref", "value": self.level},
            "Level Offset": {"type": "dimension", "value": self._level_offset_mm},
        }

    def set_property(self, key: str, value):
        if key == "Level":
            self.level = str(value)
        elif key == "Level Offset":
            self._level_offset_mm = float(value)
