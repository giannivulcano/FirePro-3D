"""
geometry_2d.py
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
from .displayable_item import DisplayableItemMixin
from .hatch_patterns import PATTERN_NAMES
from .view_scale import scene_hit_width

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

    def init_geometry2d(self):
        """Initialise fill state.  Call after ``init_displayable(level=None)``.

        2D primitives are **definition-local and level-less** (containment C3):
        they carry no level / elevation offset — that scope lives on the placed
        BlockInstance. Only the reference-graphic ``layer`` tag + fill state live
        here.
        """
        # Source-layer tag for imported reference geometry (reference-graphic
        # unification, R1). Empty for authored primitives — a reference
        # definition batch-compiles per this tag. See
        # docs/specs/reference-graphic-model.md.
        self.layer: str = ""
        self.fill_type: str = "none"          # "none" | "solid" | "hatch"
        self.fill_pattern: str = _DEFAULT_FILL_PATTERN
        self.fill_opacity: float = 0.45       # solid-fill opacity (0.0–1.0)
        # fill colour lives in DisplayableItemMixin._display_fill_color

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

    def dimension_specs(self) -> list:
        """Selection dimension readouts this primitive reports (2d-geometry §8).

        Default: none (Text, Spline). Pure — never owns or paints anything.
        """
        return []

    def _push_undo(self) -> None:
        """One scene undo step after a typed dimension edit (mutate-then-push)."""
        sc = self.scene()
        if sc is not None and hasattr(sc, "push_undo_state"):
            sc.push_undo_state()

    def _geom2d_properties(self) -> dict:
        # Level-less (containment C3): no Level / Level Offset / Elevation rows.
        props: dict = {}
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
        """Stamp mixin fields onto *d* and return it (level-less — C3)."""
        if getattr(self, "layer", ""):
            d["layer"] = self.layer
        if self.fill_type != "none":
            d["fill"] = {
                "type":    self.fill_type,
                "pattern": self.fill_pattern,
                "color":   self._display_fill_color or "#888888",
                "opacity": self.fill_opacity,
            }
        return d

    def _geom2d_from_dict(self, data: dict):
        """Restore mixin fields from *data* (level-less — C3).

        Pre-C3 dicts may carry ``level``/``level_offset_mm``; they are ignored.
        """
        self.layer = data.get("layer", "")
        f = data.get("fill")
        if f:
            self.fill_type = f.get("type", "none")
            self.fill_pattern = f.get("pattern", _DEFAULT_FILL_PATTERN)
            self._display_fill_color = f.get("color")
            self.fill_opacity = f.get("opacity", 0.45)


def _scene_hit_width(item) -> float:
    """~10 screen px at the visible view's zoom (see view_scale)."""
    return scene_hit_width(item, 10.0, 6.0)


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

        self.init_displayable(level=None)   # level-less primitive (C3)
        self.init_geometry2d()

        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._lineweight = lineweight   # restored (solid) by finalize() after a dashed ghost
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
        """Snap the path to the committed points and stop accepting input.

        Restores the committed SOLID pen at the item's lineweight — during
        placement the polyline is ghosted in the width-1 dashed reference style
        (set by ``_press_polyline``); a finalized polyline renders solid.
        """
        p = QPen(self.pen())
        p.setStyle(Qt.PenStyle.SolidLine)
        p.setWidthF(getattr(self, "_lineweight", 1.0))
        self.setPen(p)
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

    # ── Typed dimensions (2d-geometry.md §8) ─────────────────────────────

    _EPS_LEN = 1e-9

    @staticmethod
    def _yup_deg(frm: QPointF, to: QPointF) -> float:
        return math.degrees(math.atan2(-(to.y() - frm.y()), to.x() - frm.x()))

    def _seg_indices(self) -> list[int]:
        n = len(self._points)
        return list(range(n)) if self.is_closed() else list(range(max(n - 1, 0)))

    def _seg_len(self, i: int) -> float:
        a, b = self._points[i], self._points[(i + 1) % len(self._points)]
        return math.hypot(b.x() - a.x(), b.y() - a.y())

    def _vertex_sweep(self, i: int):
        """(start_deg, span_deg, ccw) of the <=180° angle at vertex *i*;
        ccw=True when the next leg is CCW of the previous one."""
        n = len(self._points)
        v = self._points[i]
        a_prev = self._yup_deg(v, self._points[(i - 1) % n])
        a_next = self._yup_deg(v, self._points[(i + 1) % n])
        inc = (a_next - a_prev) % 360.0
        if inc <= 180.0:
            return a_prev, inc, True
        return a_next, 360.0 - inc, False

    def set_segment_length(self, i: int, length_mm: float) -> None:
        """Set segment *i*'s length, moving only its end vertex (wraps)."""
        n = len(self._points)
        j = (i + 1) % n
        a, b = self._points[i], self._points[j]
        cur = math.hypot(b.x() - a.x(), b.y() - a.y())
        if length_mm <= 0 or cur < self._EPS_LEN:
            return
        k = length_mm / cur
        self._points[j] = QPointF(a.x() + (b.x() - a.x()) * k,
                                  a.y() + (b.y() - a.y()) * k)
        self._rebuild_path()

    def set_vertex_angle(self, i: int, theta_deg: float) -> None:
        """Set the <=180° angle at vertex *i* by rotating vertex (i+1)%n about
        it (same side kept). Clamped to (0, 180]."""
        n = len(self._points)
        theta = min(max(float(theta_deg), 1e-6), 180.0)
        v = self._points[i]
        j = (i + 1) % n
        a_prev = self._yup_deg(v, self._points[(i - 1) % n])
        a_next = self._yup_deg(v, self._points[j])
        _, _, ccw = self._vertex_sweep(i)
        target = a_prev + theta if ccw else a_prev - theta
        d = math.radians(target - a_next)
        dx, dy = self._points[j].x() - v.x(), self._points[j].y() - v.y()
        c, s = math.cos(d), math.sin(d)
        self._points[j] = QPointF(v.x() + dx * c + dy * s,
                                  v.y() - dx * s + dy * c)
        self._rebuild_path()

    def dimension_specs(self) -> list:
        from .selection_readouts import DimSpec
        n = len(self._points)
        if n < 2:
            return []
        specs = []
        zero = set()
        for i in self._seg_indices():
            if self._seg_len(i) < self._EPS_LEN:
                zero.update({i, (i + 1) % n})
                continue
            j = (i + 1) % n
            specs.append(DimSpec(
                kind="linear", key=f"seg:{i}", field=f"Seg {i + 1}", prefix="",
                value=self._seg_len(i), field_kind="dimension",
                apply=lambda v, i=i: self.set_segment_length(i, v),
                a=QPointF(self._points[i]), b=QPointF(self._points[j])))
        verts = range(n) if self.is_closed() else range(1, n - 1)
        for i in verts:
            if i in zero:
                continue
            start, span, _ = self._vertex_sweep(i)
            leg = min(self._seg_len((i - 1) % n), self._seg_len(i))
            specs.append(DimSpec(
                kind="angular", key=f"ang:{i}", field=f"Angle {i + 1}", prefix="",
                value=span, field_kind="span",
                apply=lambda v, i=i: self.set_vertex_angle(i, v),
                maximum=180.0, center=QPointF(self._points[i]),
                ref_radius=leg, start_deg=start, span_deg=span))
        return specs

    def manip_handles(self):
        """U3: expose each vertex as a live-apply GripHandle. All grips are
        vertices (no midpoint/convenience grips), so all render round per the
        house rule (vertex/endpoint grips = round disc; midpoints = square).
        Move is the manipulator's interior-drag (no centre grip). The
        manipulator renders/hit-tests/commits them; the legacy grip paths skip
        this item (coexistence gate)."""
        from .manip_handle import default_grip_handles
        return default_grip_handles(self, circular=set(range(len(self._points))))

    def translate(self, dx: float, dy: float):
        """Move all vertices by (dx, dy)."""
        self._points = [QPointF(p.x() + dx, p.y() + dy) for p in self._points]
        self._rebuild_path()

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        """Baked rigid rotate of all vertices about ``pivot`` (Y-up CCW+)."""
        from .cad_math import CAD_Math
        self._points = [CAD_Math.rotate_point(p, pivot, -angle_deg)
                        for p in self._points]
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

        self.init_displayable(level=None)   # level-less primitive (C3)
        self.init_geometry2d()

        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)
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

    # ── Typed dimensions (2d-geometry.md §8) ─────────────────────────────

    def set_length(self, length_mm: float) -> None:
        """Set the length, keeping ``pt1`` and the direction. No-op if <= 0
        or the line is degenerate."""
        dx = self._pt2.x() - self._pt1.x()
        dy = self._pt2.y() - self._pt1.y()
        cur = math.hypot(dx, dy)
        if length_mm <= 0 or cur < 1e-9:
            return
        k = length_mm / cur
        self._pt2 = QPointF(self._pt1.x() + dx * k, self._pt1.y() + dy * k)
        self.setLine(self._pt1.x(), self._pt1.y(), self._pt2.x(), self._pt2.y())

    def dimension_specs(self) -> list:
        from .selection_readouts import DimSpec
        length = math.hypot(self._pt2.x() - self._pt1.x(),
                            self._pt2.y() - self._pt1.y())
        if length < 1e-9:
            return []
        return [DimSpec(kind="linear", key="length", field="Length", prefix="",
                        value=length, field_kind="dimension",
                        apply=self.set_length, minimum=0.0,
                        a=QPointF(self._pt1), b=QPointF(self._pt2))]

    def manip_handles(self):
        """U3: [pt1, midpoint, pt2] as live-apply grips. Endpoints (0, 2) render
        round and Ctrl-angle-constrain against the opposite endpoint
        (EndpointGripHandle); the midpoint (1) also renders round — it translates
        the whole line, so it is a move grip (round per the house rule), not a
        geometric midpoint — with a plain GripHandle (no constrain, matching the
        legacy path, which only constrained endpoint grips). The manipulator
        renders/hit-tests/commits them; the legacy grip paths skip this item
        (coexistence gate)."""
        from .manip_handle import GripHandle, EndpointGripHandle
        return [
            EndpointGripHandle(self, 0, opposite_index=2, circular=True),
            GripHandle(self, 1, circular=True),
            EndpointGripHandle(self, 2, opposite_index=0, circular=True),
        ]

    def translate(self, dx: float, dy: float):
        """Move the entire line by (dx, dy)."""
        self._pt1 = QPointF(self._pt1.x() + dx, self._pt1.y() + dy)
        self._pt2 = QPointF(self._pt2.x() + dx, self._pt2.y() + dy)
        self.setLine(self._pt1.x(), self._pt1.y(), self._pt2.x(), self._pt2.y())

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        """Baked rigid rotate of both endpoints about ``pivot`` (Y-up CCW+)."""
        from .cad_math import CAD_Math
        self._pt1 = CAD_Math.rotate_point(self._pt1, pivot, -angle_deg)
        self._pt2 = CAD_Math.rotate_point(self._pt2, pivot, -angle_deg)
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
# ReferenceLineItem — non-printing finite reference/construction line
# ─────────────────────────────────────────────────────────────────────────────

class ReferenceLineItem(LineItem):
    """A finite 2-point *reference* line: a non-printing drafting aid.

    Subclasses :class:`LineItem`, inheriting all grip/manipulator/translate/
    rotate behaviour AND snap participation for free (the snap engine matches
    ``isinstance(item, LineItem)``). Differences:

    * Always rendered in the canonical width-1 dashed reference style.
    * Carries a per-item ``printed`` flag (default False). ``printed=False``
      excludes it from paper-space plots/exports AND from a saved block
      definition (pure scaffolding); ``printed=True`` graduates it to real
      output geometry (still dashed).
    * Its own "Reference Lines" Display-Manager category.
    """

    def __init__(self, pt1: QPointF, pt2: QPointF,
                 color: str | QColor = "#ffffff", lineweight: float = 1.0,
                 printed: bool = False):
        super().__init__(pt1, pt2, color, lineweight)
        self.printed = bool(printed)
        # Canonical reference-line style: width-1 dashed cosmetic, geom colour.
        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(1.0)
        pen.setCosmetic(True)
        pen.setStyle(Qt.PenStyle.DashLine)
        self.setPen(pen)

    # ── Properties ────────────────────────────────────────────────────────────

    def get_properties(self) -> dict:
        props = {
            "Type": {"type": "label", "value": "Reference Line"},
            "Colour": {"type": "label", "value": self.pen().color().name()},
            "Length": {"type": "label", "value": f"{self.line().length():.1f}"},
            "Printed": {"type": "toggle", "value": bool(self.printed)},
        }
        props.update(self._geom2d_properties())
        return props

    def set_property(self, key: str, value):
        if key == "Printed":
            self.printed = bool(value)
            self.update()
            return
        if self._geom2d_set(key, value):
            return

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = {
            "type":        "reference_line",
            "pt1":         [self._pt1.x(), self._pt1.y()],
            "pt2":         [self._pt2.x(), self._pt2.y()],
            "color":       self.pen().color().name(),
            "lineweight":  self.pen().widthF(),
            "printed":     bool(self.printed),
        }
        return self._geom2d_to_dict(d)

    @classmethod
    def from_dict(cls, data: dict) -> "ReferenceLineItem":
        pt1 = QPointF(data["pt1"][0], data["pt1"][1])
        pt2 = QPointF(data["pt2"][0], data["pt2"][1])
        obj = cls(pt1, pt2, data.get("color", "#ffffff"),
                  data.get("lineweight", 1.0), data.get("printed", False))
        obj._geom2d_from_dict(data)
        return obj


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

        self.init_displayable(level=None)   # level-less primitive (C3)
        self.init_geometry2d()

        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
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

    def mapToParent(self, *args):
        """Local→parent through the data rotation, then Qt's own pos/transform.

        Overridden like :meth:`mapToScene` so ``mapToParent`` consumers (e.g.
        ``BlockDefinition._compile``) see the rotated footprint instead of the
        axis-aligned local ``rect()``.  Same overloads: ``QPointF``, ``(x, y)``
        or ``QPainterPath``.
        """
        t = self._rotation_transform()
        if len(args) == 2:                       # (x, y)
            return super().mapToParent(t.map(QPointF(args[0], args[1])))
        obj = args[0]
        if isinstance(obj, QPainterPath):
            return super().mapToParent(t.map(obj))
        return super().mapToParent(t.map(QPointF(obj)))

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
        resize runs in the rectangle's own (rotated) frame (one home:
        :func:`rect_grip_resize`, plain mode — no Ctrl/Shift). Interactive
        drags go through ``RectGripHandle``, which resizes from the PRESS-time
        rect with the modifiers; this is the programmatic single-shot path.
        """
        if not 0 <= index <= 8:
            return
        self.prepareGeometryChange()
        self.setRect(rect_grip_resize(self.rect(), index, self.mapFromScene(pos),
                                      False, False))
        # A centre-following pivot (``_pivot is None``) re-derives from the new
        # rect centre automatically (see ``_rotation_origin``).

    # ── Typed dimensions (2d-geometry.md §8) ─────────────────────────────

    def _resize_keeping(self, new_rect: QRectF, anchor_local: QPointF,
                        anchor_local_new: QPointF) -> None:
        """Apply *new_rect*, then translate so the anchor corner stays put in
        scene (a centre-following pivot would otherwise slide it)."""
        before = self.mapToScene(anchor_local)
        self.prepareGeometryChange()
        self.setRect(new_rect)
        after = self.mapToScene(anchor_local_new)
        self.translate(before.x() - after.x(), before.y() - after.y())

    def set_width(self, width_mm: float) -> None:
        """Set the local-x extent, keeping the left edge. No-op if <= 0."""
        if width_mm <= 0:
            return
        r = self.rect()
        bl = QPointF(r.left(), r.bottom())
        self._resize_keeping(QRectF(r.left(), r.top(), width_mm, r.height()),
                             bl, bl)

    def set_height(self, height_mm: float) -> None:
        """Set the local-y extent, keeping the bottom edge. No-op if <= 0."""
        if height_mm <= 0:
            return
        r = self.rect()
        bl = QPointF(r.left(), r.bottom())
        self._resize_keeping(
            QRectF(r.left(), r.bottom() - height_mm, r.width(), height_mm),
            bl, bl)

    def dimension_specs(self) -> list:
        from .selection_readouts import DimSpec
        r = self.rect()
        bl = self.mapToScene(QPointF(r.left(), r.bottom()))
        br = self.mapToScene(QPointF(r.right(), r.bottom()))
        tr = self.mapToScene(QPointF(r.right(), r.top()))
        c = self.mapToScene(r.center())
        return [
            DimSpec(kind="linear", key="width", field="Width", prefix="",
                    value=r.width(), field_kind="dimension",
                    apply=self.set_width, a=bl, b=br, away=c),
            DimSpec(kind="linear", key="height", field="Height", prefix="",
                    value=r.height(), field_kind="dimension",
                    apply=self.set_height, a=br, b=tr, away=c),
        ]

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
        if self.isSelected():
            if not _manip_wraps(self):
                highlight = QPen(self.pen().color().lighter(150), self.pen().widthF() + 1.5)
                highlight.setCosmetic(True)
                painter.setPen(highlight)
                painter.drawRect(self.rect())
            # Corner-diagonal reference guides — shown whenever selected (a content
            # aid, NOT the selection highlight). Canonical width-1 dashed style,
            # matching EllipseItem's axis guides.
            ref = QPen(self.pen().color(), 1, Qt.PenStyle.DashLine)
            ref.setCosmetic(True)
            painter.setPen(ref)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for a, b in self._selection_ref_segments():
                painter.drawLine(a, b)
        painter.restore()

    def _selection_ref_segments(self):
        """Corner-diagonal reference guides, in the rect's LOCAL (axis-aligned)
        frame — the paint rotation transform orients them for a rotated rect."""
        r = self.rect()
        return [(r.topLeft(), r.bottomRight()), (r.topRight(), r.bottomLeft())]

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

    def manip_handles(self):
        """U3: the rect's own 9 live-apply grips at EVERY angle.

        Corners (0,2,4,6) + centre (8) render round; edge midpoints (1,3,5,7)
        square and align to the rect's angle via ``grip_render_angle``. Each is
        a ``RectGripHandle``: local-frame resize from the press-time rect,
        Ctrl = symmetric about the centre, Shift (corners) = keep aspect,
        centre grip = move. The rect exposes no ``scale`` capability, so the
        manipulator's rigid resize handles never surface for it."""
        from .manip_handle import RectGripHandle
        return [RectGripHandle(self, i, circular=i in (0, 2, 4, 6, 8))
                for i in range(9)]

    def manip_frame_redundant(self) -> bool:
        """True while unrotated: the rect's own outline coincides with the
        manipulator's axis-aligned frame, so the dashed frame is suppressed.
        A rotated rect keeps the frame (its bounds add information)."""
        return self._angle == 0.0

    def grip_render_angle(self, index: int) -> float:
        """Rotate the square edge-midpoint grips to the rect's baked Y-up
        orientation so their edges align with the (rotated) rect edges; the round
        corner/centre grips ignore it (rotation-invariant)."""
        return self._angle

    def manip_bounds(self) -> QRectF:
        """The rect's own geometry in scene coords so the manipulator frame
        hugs the shape (not the pen-padded ``sceneBoundingRect``).  For a rotated
        rect this is the axis-aligned bounds of the rotated footprint."""
        return self.mapRectToScene(self.rect())

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        """Baked rotate: accumulate ``angle_deg`` onto the current angle about
        ``pivot`` (Y-up CCW+).  One home with ``set_angle`` so the manipulator
        and the placement rotate-step cannot drift."""
        self.set_angle(self._angle + angle_deg, pivot)


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

        self.init_displayable(level=None)   # level-less primitive (C3)
        self.init_geometry2d()

        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
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

    # ── Typed dimensions (2d-geometry.md §8) ─────────────────────────────

    def set_radius(self, radius_mm: float) -> None:
        """Set the radius, keeping the centre (floor 1 mm, as apply_grip)."""
        self._radius = max(1.0, float(radius_mm))
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        self.setRect(cx - r, cy - r, 2 * r, 2 * r)

    def dimension_specs(self) -> list:
        from .selection_readouts import DimSpec
        c, r = QPointF(self._center), self._radius
        return [DimSpec(kind="linear", key="radius", field="Radius", prefix="R",
                        value=r, field_kind="dimension", apply=self.set_radius,
                        a=c, b=QPointF(c.x() + r, c.y()),
                        away=QPointF(c.x(), c.y() + r))]   # label above the radial

    def translate(self, dx: float, dy: float):
        self._center = QPointF(self._center.x() + dx, self._center.y() + dy)
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        self.setRect(cx - r, cy - r, 2 * r, 2 * r)

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        """Baked rigid rotate about ``pivot`` (Y-up CCW+): the centre moves; the
        circle shape is rotation-invariant so the radius is unchanged."""
        from .cad_math import CAD_Math
        self._center = CAD_Math.rotate_point(self._center, pivot, -angle_deg)
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        self.setRect(cx - r, cy - r, 2 * r, 2 * r)

    def manip_handles(self):
        """U3: expose parametric grips as live-apply GripHandles (center +
        4 radius). The manipulator renders/hit-tests/commits them; the legacy
        grip paths skip this item (coexistence gate). Grip 0 is the centre/move
        grip (circular); the 4 radius grips are square parametric points."""
        from .manip_handle import default_grip_handles
        return default_grip_handles(self, circular={0})

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
        if self.isSelected():
            if not _manip_wraps(self):
                highlight = QPen(self.pen().color().lighter(150), self.pen().widthF() + 1.5)
                highlight.setCosmetic(True)
                painter.setPen(highlight)
                painter.drawEllipse(self.rect())
            # Radius guide + bounding box — shown whenever selected (a content aid,
            # NOT the selection highlight). Canonical width-1 dashed style.
            ref = QPen(self.pen().color(), 1, Qt.PenStyle.DashLine)
            ref.setCosmetic(True)
            painter.setPen(ref)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect())               # bounding box
            for a, b in self._selection_ref_segments():
                painter.drawLine(a, b)                  # radius guide

    def _selection_ref_segments(self):
        """A single radius guide from the centre to the right edge (local coords)."""
        r = self.rect()
        return [(r.center(), QPointF(r.right(), r.center().y()))]

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
        # Store every arc in CCW form (span > 0): a negative (CW) span — the
        # mirror tool, legacy saves — is the same geometric arc starting at
        # start + span. The grip refits assume CCW start→end.
        from .arc_math import _norm360
        if span_deg < 0:
            start_deg, span_deg = start_deg + span_deg, -span_deg
        self._start_deg = _norm360(start_deg)
        self._span_deg = span_deg

        self.init_displayable(level=None)   # level-less primitive (C3)
        self.init_geometry2d()

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

    def arc_midpoint(self) -> QPointF:
        """The point halfway along the arc (Y-up start + span/2)."""
        from .arc_math import point_at
        return point_at(self._center, self._radius,
                        self._start_deg + self._span_deg / 2.0)

    def begin_endpoint_refit(self) -> None:
        """Snapshot the endpoint-drag reference (called by the grip on press)."""
        pts = self.grip_points()
        self._arc_refit_ref = {"start": pts[1], "end": pts[2],
                               "mid": self.arc_midpoint(),
                               "center": QPointF(self._center),
                               "radius": self._radius}

    def end_endpoint_refit(self) -> None:
        self._arc_refit_ref = None

    def apply_grip(self, index: int, pos: QPointF):
        """Re-shape the arc from a grip drag (user 2026-09-23).

        * 0 centre — both endpoints stay fixed; the centre is projected onto
          their perpendicular bisector (radius/bulge follow; CCW start→end is
          kept, so crossing the chord grows the arc through a semicircle into a
          major arc). A full-circle arc (no chord) translates instead.
        * 1 start / 2 end — the centre, radius and the other endpoint stay
          fixed (user 2026-09-24); *pos* is projected radially onto the circle
          and only the dragged endpoint's angle changes. A span within 0.5° of
          0° / 360° (or *pos* on the centre) holds the last valid shape.
        """
        from .arc_math import project_to_bisector, yup_angle, _norm360
        if index == 0:
            pts = self.grip_points()
            s, e = pts[1], pts[2]
            proj = project_to_bisector(s, e, pos)
            if proj is None or abs(self._span_deg) >= 360.0 - 1e-6:
                self._center = QPointF(pos)
            else:
                c, _t = proj
                r = math.hypot(s.x() - c.x(), s.y() - c.y())
                ts = yup_angle(c, s)
                span = (yup_angle(c, e) - ts) % 360.0   # CCW start→end kept
                if r < 0.01 or span < 1e-6:
                    return                       # hold last valid shape
                self._center = c
                self._radius = r
                self._start_deg = _norm360(ts)
                self._span_deg = span
        elif index in (1, 2):
            c = self._center
            if math.hypot(pos.x() - c.x(), pos.y() - c.y()) < 1e-9:
                return                           # no radial direction
            theta = yup_angle(c, pos)
            if index == 1:
                start = theta
                span = (self._start_deg + self._span_deg - theta) % 360.0
            else:
                start = self._start_deg
                span = (theta - self._start_deg) % 360.0
            if span < 0.5 or span > 359.5:
                return                           # hold last valid shape
            self._start_deg = _norm360(start)
            self._span_deg = span
        else:
            return
        self._rebuild_path()

    # ── Typed dimensions (2d-geometry.md §8) ─────────────────────────────

    def _point_at(self, deg: float) -> QPointF:
        a = math.radians(deg)
        return QPointF(self._center.x() + self._radius * math.cos(a),
                       self._center.y() - self._radius * math.sin(a))

    def set_span(self, span_deg: float) -> None:
        """Set the included angle, keeping centre / radius / start (end moves
        CCW). Clamped to (0, 360)."""
        self._span_deg = min(max(float(span_deg), 1e-6), 360.0 - 1e-6)
        self._rebuild_path()

    def set_radius(self, radius_mm: float) -> None:
        """Set the radius, keeping centre and both angles (floor 0.01 mm)."""
        self._radius = max(float(radius_mm), 0.01)
        self._rebuild_path()

    def dimension_specs(self) -> list:
        from .selection_readouts import DimSpec
        c = QPointF(self._center)
        return [
            DimSpec(kind="angular", key="angle", field="Angle", prefix="",
                    value=self._span_deg, field_kind="span",
                    apply=self.set_span, maximum=360.0 - 1e-6,
                    center=c, ref_radius=self._radius,
                    start_deg=self._start_deg, span_deg=self._span_deg),
            DimSpec(kind="linear", key="radius", field="Radius", prefix="R",
                    value=self._radius, field_kind="dimension",
                    apply=self.set_radius, minimum=0.0,
                    a=c, b=self._point_at(self._start_deg),
                    away=self._point_at(self._start_deg + self._span_deg)),
        ]

    def manip_handles(self):
        """U3: centre grip (bisector slide) + start/end ``ArcEndpointGripHandle``s
        (slide along the circle). All round (house rule)."""
        from .manip_handle import GripHandle, ArcEndpointGripHandle
        return [GripHandle(self, 0, circular=True),
                ArcEndpointGripHandle(self, 1),
                ArcEndpointGripHandle(self, 2)]

    def translate(self, dx: float, dy: float):
        self._center = QPointF(self._center.x() + dx, self._center.y() + dy)
        self._rebuild_path()

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        """Baked rigid rotate about ``pivot`` (Y-up CCW+): rotate the centre and
        advance the start angle by ``angle_deg`` (Y-up); span unchanged."""
        from .cad_math import CAD_Math
        self._center = CAD_Math.rotate_point(self._center, pivot, -angle_deg)
        self._start_deg = (self._start_deg + angle_deg) % 360.0
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
        if self.isSelected():
            if not _manip_wraps(self):
                highlight = QPen(self.pen().color().lighter(150), self.pen().widthF() + 1.5)
                highlight.setCosmetic(True)
                painter.setPen(highlight)
                painter.drawPath(self.path())
            # Centre→start / centre→end reference radials — shown whenever
            # selected (a content aid, NOT the selection highlight). Canonical
            # width-1 dashed style, matching EllipseItem's axis guides.
            ref = QPen(self.pen().color(), 1, Qt.PenStyle.DashLine)
            ref.setCosmetic(True)
            painter.setPen(ref)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for a, b in self._selection_ref_segments():
                painter.drawLine(a, b)

    def _selection_ref_segments(self):
        """Reference radials centre→start and centre→end (scene coords)."""
        c, s, e = self.grip_points()
        return [(c, s), (c, e)]

    def itemChange(self, change, value):
        # The selected bounds grow to cover the radials (the centre can lie
        # outside the arc's path bounds) — tell the scene before they change.
        if change == self.GraphicsItemChange.ItemSelectedChange:
            self.prepareGeometryChange()
        return super().itemChange(change, value)

    def boundingRect(self) -> QRectF:
        """Path bounds; when selected, also the centre so the reference
        radials repaint/cull correctly. Hit-testing uses :meth:`shape`, which
        stays the stroked arc."""
        base = super().boundingRect()
        if not self.isSelected():
            return base
        c = self._center
        return base.united(QRectF(c.x() - 1.0, c.y() - 1.0, 2.0, 2.0))

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

        self.init_displayable(level=None)   # level-less primitive (C3)
        self.init_geometry2d()

        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
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
                self.set_radius(r)
                self._push_undo()
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

    # ── Typed dimensions (2d-geometry.md §8) ─────────────────────────────

    def set_radius(self, mm: float) -> None:
        """Set the stored defining radius (circumradius if inscribed, apothem if
        circumscribed); keeps centre / sides / rotation. No-op if <= 0."""
        if mm <= 0:
            return
        self._radius_mm = float(mm)
        self._regenerate()

    def dimension_specs(self) -> list:
        from .selection_readouts import DimSpec
        a = math.radians(self._rotation_deg)
        c = QPointF(self._center)
        b = QPointF(c.x() + self._radius_mm * math.cos(a),
                    c.y() - self._radius_mm * math.sin(a))
        away = QPointF(c.x() - self._radius_mm * math.sin(a),
                       c.y() - self._radius_mm * math.cos(a))   # +90° side
        return [DimSpec(kind="linear", key="radius", field="Radius", prefix="R",
                        value=self._radius_mm, field_kind="dimension",
                        apply=self.set_radius, a=c, b=b, away=away)]

    def manip_handles(self):
        """U3: expose the centre + each vertex as a live-apply GripHandle.

        All grips render round per the house rule: the centre is a move grip
        and the vertices are the polygon's defining points (dragging a vertex
        resizes + rotates — the edit math lives in apply_grip). Zero special
        drag semantics: the legacy grip path explicitly excludes polygon from
        Ctrl-constrain, so no EndpointGripHandle/_transform_point. Same shape
        as ArcItem/Spline. The manipulator renders/hit-tests/commits them; the
        legacy grip paths skip this item (coexistence gate)."""
        from .manip_handle import default_grip_handles
        return default_grip_handles(
            self, circular=set(range(len(self.grip_points()))))

    def translate(self, dx: float, dy: float):
        self._center = QPointF(self._center.x() + dx, self._center.y() + dy)
        self._regenerate()

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        """Baked rigid rotate about ``pivot`` (Y-up CCW+): rotate the centre and
        advance the parametric orientation ``_rotation_deg`` by ``angle_deg``."""
        from .cad_math import CAD_Math
        self._center = CAD_Math.rotate_point(self._center, pivot, -angle_deg)
        self._rotation_deg = (self._rotation_deg + angle_deg) % 360.0
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
        if self.isSelected():
            if not _manip_wraps(self):
                hl = QPen(self.pen().color().lighter(150), self.pen().widthF() + 1.5)
                hl.setCosmetic(True)
                painter.setPen(hl)
                painter.drawPath(self.path())
            # Dashed circumradius reference circle — shown whenever selected
            # (manipulator-wrapped or not): a content aid, NOT the highlight.
            # Canonical reference-line style (width-1 dashed).
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
# EllipseItem — centre + two half-axes + Y-up rotation
# ─────────────────────────────────────────────────────────────────────────────

_AXIS_MIN = 0.5   # anti-degeneracy floor (mm), matches circle/polygon


class EllipseItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsPathItem):
    """An ellipse defined by centre, semi-major (rx), semi-minor (ry) and a
    Y-up rotation of the major axis.

    Path-based (not a native QGraphicsEllipseItem) because the rotation is
    data-parametric and paint-applied — never Qt setRotation — matching the
    app-wide Y-up / CCW-positive convention used by RegularPolygonItem.
    """

    def __init__(self, center: QPointF, rx: float, ry: float,
                 rotation_deg: float = 0.0,
                 color: str | QColor = "#ffffff", lineweight: float = 1.0):
        super().__init__()
        self._center = QPointF(center)
        self._rx = max(float(rx), _AXIS_MIN)
        self._ry = max(float(ry), _AXIS_MIN)
        self._rotation_deg = float(rotation_deg)

        self.init_displayable(level=None)   # level-less primitive (C3)
        self.init_geometry2d()

        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)
        self._regenerate()

    def _ellipse_path_local(self) -> QPainterPath:
        p = QPainterPath()
        p.addEllipse(QPointF(0.0, 0.0), self._rx, self._ry)
        return p

    def get_closed_path(self) -> QPainterPath:
        t = QTransform()
        t.translate(self._center.x(), self._center.y())
        t.rotate(-self._rotation_deg)
        return t.map(self._ellipse_path_local())

    def is_closed(self) -> bool:
        return True

    def _regenerate(self):
        self.setPath(self.get_closed_path())
        self.update()

    def _axis_endpoint(self, semi: float, angle_off_deg: float) -> QPointF:
        a = math.radians(self._rotation_deg + angle_off_deg)
        return QPointF(self._center.x() + semi * math.cos(a),
                       self._center.y() - semi * math.sin(a))

    def grip_points(self) -> list[QPointF]:
        return [
            QPointF(self._center),
            self._axis_endpoint(self._rx, 0.0),
            self._axis_endpoint(self._rx, 180.0),
            self._axis_endpoint(self._ry, 90.0),
            self._axis_endpoint(self._ry, 270.0),
        ]

    def apply_grip(self, index: int, pos: QPointF):
        if index == 0:
            self._center = QPointF(pos)
            self._regenerate()
            return
        dx = pos.x() - self._center.x()
        dy = pos.y() - self._center.y()
        dist = math.hypot(dx, dy)
        if dist < _AXIS_MIN:
            return
        if index in (1, 2):
            self._rx = dist
            ang = math.degrees(math.atan2(-dy, dx))
            self._rotation_deg = (ang - (180.0 if index == 2 else 0.0)) % 360.0
        elif index in (3, 4):
            self._ry = dist
        self._regenerate()

    # ── Typed dimensions (2d-geometry.md §8) ─────────────────────────────

    def set_rx(self, mm: float) -> None:
        """R1 (rx semi-axis); keeps centre + rotation. Floor _AXIS_MIN."""
        self._rx = max(float(mm), _AXIS_MIN)
        self._regenerate()

    def set_ry(self, mm: float) -> None:
        """R2 (ry semi-axis); keeps centre + rotation. Floor _AXIS_MIN."""
        self._ry = max(float(mm), _AXIS_MIN)
        self._regenerate()

    def dimension_specs(self) -> list:
        from .selection_readouts import DimSpec
        c = QPointF(self._center)
        return [
            DimSpec(kind="linear", key="r1", field="R1", prefix="R1",
                    value=self._rx, field_kind="dimension", apply=self.set_rx,
                    a=c, b=self._axis_endpoint(self._rx, 0.0),
                    away=self._axis_endpoint(self._ry, 90.0)),
            DimSpec(kind="linear", key="r2", field="R2", prefix="R2",
                    value=self._ry, field_kind="dimension", apply=self.set_ry,
                    a=c, b=self._axis_endpoint(self._ry, 90.0),
                    away=self._axis_endpoint(self._rx, 0.0)),
        ]

    def manip_handles(self):
        """U3: expose parametric grips as live-apply GripHandles (centre + 4
        axis endpoints). Mirrors CircleItem (an ellipse is a generalized
        circle): grip 0 is the centre/move grip (round); the 4 axis-endpoint
        grips (major rx = 1,2; minor ry = 3,4) are square sizing points — the
        major pair also rotates. Zero special drag semantics (the legacy grip
        path only Ctrl-constrains Wall/Gridline/Line); apply_grip carries the
        edit math. The manipulator renders/hit-tests/commits them; the legacy
        grip paths skip this item (coexistence gate)."""
        from .manip_handle import default_grip_handles
        return default_grip_handles(self, circular={0})

    def grip_render_angle(self, index: int) -> float:
        """U3 grip-shape hook: rotate the square axis grips to the ellipse's
        orientation so their edges align radially with the major/minor axes (and
        stay aligned after a rotate). Returns the Y-up ``_rotation_deg``; the
        round centre grip ignores it (rotation-invariant). Each axis radial is
        ``_rotation_deg`` mod 90, so one box angle aligns all four squares."""
        return self._rotation_deg

    def translate(self, dx: float, dy: float):
        self._center = QPointF(self._center.x() + dx, self._center.y() + dy)
        self._regenerate()

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        from .cad_math import CAD_Math
        self._center = CAD_Math.rotate_point(self._center, pivot, -angle_deg)
        self._rotation_deg = (self._rotation_deg + angle_deg) % 360.0
        self._regenerate()

    def get_properties(self) -> dict:
        props = {
            "Type":     {"type": "label", "value": "Ellipse"},
            "Centre":   {"type": "label",
                         "value": f"({self._center.x():.1f}, {self._center.y():.1f})"},
            "R1": {"type": "dimension",
                   "value": self._fmt(self._rx), "value_mm": self._rx},
            "R2": {"type": "dimension",
                   "value": self._fmt(self._ry), "value_mm": self._ry},
            "Rotation": {"type": "string",
                         "value": f"{self._rotation_deg:.2f}", "suffix": "°"},
            "Colour":   {"type": "label", "value": self.pen().color().name()},
            "Line Weight": {"type": "label", "value": f"{self.pen().widthF():.1f}"},
        }
        props.update(self._geom2d_properties())
        return props

    def set_property(self, key: str, value):
        if key == "R1":
            r = self._parse_dim(value)
            if r is not None and r >= _AXIS_MIN:
                self.set_rx(r)
                self._push_undo()
            return
        if key == "R2":
            r = self._parse_dim(value)
            if r is not None and r >= _AXIS_MIN:
                self.set_ry(r)
                self._push_undo()
            return
        if key == "Rotation":
            try:
                self._rotation_deg = float(str(value).replace("°", "").strip())
            except (TypeError, ValueError):
                return
            self._regenerate()
            return
        if self._geom2d_set(key, value):
            self._regenerate()
            return

    def to_dict(self) -> dict:
        d = {
            "type":        "draw_ellipse",
            "cx":          self._center.x(),
            "cy":          self._center.y(),
            "rx":          self._rx,
            "ry":          self._ry,
            "rotation":    self._rotation_deg,
            "color":       self.pen().color().name(),
            "lineweight":  self.pen().widthF(),
        }
        return self._geom2d_to_dict(d)

    @classmethod
    def from_dict(cls, data: dict) -> "EllipseItem":
        obj = cls(QPointF(data["cx"], data["cy"]),
                  data["rx"], data["ry"], data.get("rotation", 0.0),
                  data.get("color", "#ffffff"), data.get("lineweight", 1.0))
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
        if self.isSelected():
            if not _manip_wraps(self):
                hl = QPen(self.pen().color().lighter(150), self.pen().widthF() + 1.5)
                hl.setCosmetic(True)
                painter.setPen(hl)
                painter.drawPath(self.path())
            # Dashed major + minor axis reference guides — shown whenever the
            # ellipse is selected (manipulator-wrapped or not): a content aid,
            # NOT the selection highlight. Canonical reference-line style
            # (width-1 dashed) matching the placement-time radial guide.
            ref = QPen(self.pen().color(), 1, Qt.PenStyle.DashLine)
            ref.setCosmetic(True)
            painter.setPen(ref)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            gp = self.grip_points()
            painter.drawLine(gp[1], gp[2])   # major axis (major+ ↔ major-)
            painter.drawLine(gp[3], gp[4])   # minor axis (minor+ ↔ minor-)

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        path = stroker.createStroke(self.path())
        if getattr(self, "fill_type", "none") != "none":
            path = path.united(self.get_closed_path())
        return path


# ─────────────────────────────────────────────────────────────────────────────
# SplineItem — editable NURBS / B-spline
# ─────────────────────────────────────────────────────────────────────────────


def _is_bezier_chain(n: int, degree: int, knots, weights) -> bool:
    """True for a non-rational clamped cubic whose every interior knot has
    multiplicity 3 — i.e. a chain of cubic Bézier spans (``n == 3k + 1``)."""
    if degree != 3 or n < 4 or (n - 1) % 3 or not knots:
        return False
    if weights and any(abs(w - 1.0) > 1e-12 for w in weights):
        return False
    if len(knots) != n + 4:
        return False
    k = knots
    if not (k[0] == k[1] == k[2] == k[3] and k[-1] == k[-2] == k[-3] == k[-4]):
        return False
    interior = k[4:-4]
    return all(interior[i] == interior[i + 1] == interior[i + 2]
               and (i == 0 or interior[i] > interior[i - 1])
               for i in range(0, len(interior), 3))


def _bspline_path(control_points: list[QPointF], degree: int,
                  knots: list[float] | None,
                  weights: list[float] | None) -> QPainterPath:
    """Build a QPainterPath tessellating a NURBS/B-spline via ezdxf.math.BSpline.

    ezdxf is a pure evaluator here (no DXF I/O) — respects the read-only-DXF
    rule.  ``order = degree + 1``; a curve with fewer control points than
    ``degree+1`` auto-lowers by clamping the order to the control-point count.
    """
    path = QPainterPath()
    n = len(control_points)
    if n == 0:
        return path
    if n == 1:
        path.moveTo(control_points[0])
        return path
    if _is_bezier_chain(n, degree, knots, weights):
        # Piecewise-Bézier form (e.g. PDF-imported curves): each span IS a
        # cubic Bézier, so Qt draws it exactly and natively — ~100x faster
        # than the pure-Python NURBS flattening below.
        path.moveTo(control_points[0])
        for i in range(1, n, 3):
            path.cubicTo(control_points[i], control_points[i + 1],
                         control_points[i + 2])
        return path
    from ezdxf.math import BSpline
    order = min(degree + 1, n)
    cps = [(p.x(), p.y()) for p in control_points]
    spline = BSpline(cps, order=order,
                     knots=knots if knots else None,
                     weights=weights if weights else None)
    pts = list(spline.flattening(0.5))
    if not pts:
        return path
    path.moveTo(pts[0][0], pts[0][1])
    for p in pts[1:]:
        path.lineTo(p[0], p[1])
    return path


def _auto_knots(n_points: int, degree: int) -> list[float]:
    """Return the clamped-uniform knot vector ezdxf would generate for *n_points*
    control points at *degree* (already clamped to n_points-1)."""
    from ezdxf.math import BSpline
    order = min(degree + 1, n_points)
    cps = [(0.0, 0.0)] * n_points
    return list(BSpline(cps, order=order).knots())


class SplineItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsPathItem):
    """An editable NURBS/B-spline.

    Data model is the full DXF SPLINE payload (control points + degree + knot
    vector + optional weights) so an imported spline round-trips exactly.
    Authored splines are the constrained subset: cubic (degree lowers under 4
    control points), auto clamped-uniform knots, non-rational.
    """

    def __init__(self, control_points: list[QPointF], degree: int = 3,
                 knots: list[float] | None = None,
                 weights: list[float] | None = None,
                 color: str | QColor = "#ffffff", lineweight: float = 1.0):
        super().__init__()
        self._control_points = [QPointF(p) for p in control_points]
        n = len(self._control_points)
        self._degree = max(1, min(int(degree), max(n - 1, 1)))
        # ezdxf's BSpline rejects order 1 (a single control point), so a
        # degenerate 0/1-point spline gets no auto knot vector — _bspline_path
        # handles n < 2 via its own early return (moveTo / empty path).
        self._knots = (list(knots) if knots
                       else (_auto_knots(n, self._degree) if n >= 2 else None))
        self._weights = list(weights) if weights else None

        self.init_displayable(level=None)   # level-less primitive (C3)
        self.init_geometry2d()

        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)
        self._regenerate()

    def _regenerate(self):
        self.setPath(_bspline_path(self._control_points, self._degree,
                                   self._knots, self._weights))
        self.update()

    def is_closed(self) -> bool:
        cps = self._control_points
        return len(cps) >= 3 and cps[0] == cps[-1]

    def get_closed_path(self) -> QPainterPath | None:
        if not self.is_closed():
            return None
        p = QPainterPath(self.path())
        p.closeSubpath()
        return p

    def grip_points(self) -> list[QPointF]:
        return [QPointF(p) for p in self._control_points]

    def apply_grip(self, index: int, pos: QPointF):
        if 0 <= index < len(self._control_points):
            self._control_points[index] = QPointF(pos)
            self._regenerate()

    def manip_handles(self):
        """U3: expose each control point as a live-apply GripHandle. Control
        points are the spline's defining ("vertex") points — all render round
        per the house rule (vertex grips = round disc; midpoints = square); a
        spline has no midpoint/convenience grips. No move-centre grip (move is
        the manipulator's interior-drag). The manipulator renders/hit-tests/
        commits them; the legacy grip paths skip this item (coexistence gate)."""
        from .manip_handle import default_grip_handles
        return default_grip_handles(
            self, circular=set(range(len(self._control_points))))

    def translate(self, dx: float, dy: float):
        self._control_points = [QPointF(p.x() + dx, p.y() + dy)
                                for p in self._control_points]
        self._regenerate()

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        from .cad_math import CAD_Math
        self._control_points = [CAD_Math.rotate_point(p, pivot, -angle_deg)
                                for p in self._control_points]
        self._regenerate()

    def get_properties(self) -> dict:
        props = {
            "Type":     {"type": "label", "value": "Spline"},
            "Points":   {"type": "label", "value": str(len(self._control_points))},
            "Degree":   {"type": "label", "value": str(self._degree)},
            "Rational": {"type": "label", "value": "yes" if self._weights else "no"},
            "Colour":   {"type": "label", "value": self.pen().color().name()},
            "Line Weight": {"type": "label", "value": f"{self.pen().widthF():.1f}"},
        }
        props.update(self._geom2d_properties())
        return props

    def set_property(self, key: str, value):
        if self._geom2d_set(key, value):
            self._regenerate()
            return

    def to_dict(self) -> dict:
        d = {
            "type":           "draw_spline",
            "control_points": [[p.x(), p.y()] for p in self._control_points],
            "degree":         self._degree,
            "knots":          list(self._knots) if self._knots else None,
            "weights":        list(self._weights) if self._weights else None,
            "color":          self.pen().color().name(),
            "lineweight":     self.pen().widthF(),
        }
        return self._geom2d_to_dict(d)

    @classmethod
    def from_dict(cls, data: dict) -> "SplineItem":
        cps = [QPointF(x, y) for x, y in data["control_points"]]
        obj = cls(cps, data.get("degree", 3),
                  data.get("knots"), data.get("weights"),
                  data.get("color", "#ffffff"), data.get("lineweight", 1.0))
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
        if self.isSelected():
            if not _manip_wraps(self):
                hl = QPen(self.pen().color().lighter(150), self.pen().widthF() + 1.5)
                hl.setCosmetic(True)
                painter.setPen(hl)
                painter.drawPath(self.path())
            # Dashed control-polygon reference guide (straight lines between the
            # control points) — shown whenever selected (manipulator or not):
            # a content aid, NOT the selection highlight. Canonical reference-
            # line style, matching the placement-time control-polygon guide.
            if len(self._control_points) >= 2:
                ref = QPen(self.pen().color(), 1, Qt.PenStyle.DashLine)
                ref.setCosmetic(True)
                painter.setPen(ref)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                for a, b in zip(self._control_points, self._control_points[1:]):
                    painter.drawLine(a, b)

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        path = stroker.createStroke(self.path())
        if getattr(self, "fill_type", "none") != "none":
            cp = self.get_closed_path()
            if cp is not None:
                path = path.united(cp)
        return path


# ─────────────────────────────────────────────────────────────────────────────
# GeometryTemplate — pre-placement defaults for geometry tools
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Pure geometry helpers — shared by 2D-geo / wall / floor rectangle placement
# ─────────────────────────────────────────────────────────────────────────────

# Grip indices (clockwise from top-left): 0 TL 1 TM 2 TR 3 RM 4 BR 5 BM 6 BL 7 LM 8 C
_RECT_CORNER_OPPOSITE = {0: 4, 2: 6, 4: 0, 6: 2}


def rect_grip_resize(r0: QRectF, index: int, p: QPointF,
                     from_center: bool, keep_aspect: bool) -> QRectF:
    """New LOCAL rect after dragging grip *index* of the press-time rect *r0*.

    Args:
        r0: The press-time rect, in the item's LOCAL (axis-aligned) frame.
        index: Grip index (0 TL, 1 TM, 2 TR, 3 RM, 4 BR, 5 BM, 6 BL, 7 LM,
            8 centre).
        p: The drag point in the same LOCAL frame.
        from_center: Ctrl — resize symmetrically about the ``r0`` centre.
        keep_aspect: Shift — keep ``r0``'s aspect ratio (corners only; no
            effect on edge grips).

    Returns:
        The new normalised local rect. The centre grip (8) translates.
    """
    cx, cy = r0.center().x(), r0.center().y()
    l, t, ri, b = r0.left(), r0.top(), r0.right(), r0.bottom()
    if index == 8:
        return r0.translated(p.x() - cx, p.y() - cy)
    if index in _RECT_CORNER_OPPOSITE:
        pts = {0: (l, t), 2: (ri, t), 4: (ri, b), 6: (l, b)}
        ox, oy = pts[index]
        ax, ay = (cx, cy) if from_center else pts[_RECT_CORNER_OPPOSITE[index]]
        dx, dy = p.x() - ax, p.y() - ay
        if keep_aspect:
            bx, by = ox - ax, oy - ay
            fx = dx / bx if bx else 0.0
            fy = dy / by if by else 0.0
            s = fx if abs(fx) >= abs(fy) else fy
            dx, dy = s * bx, s * by
        corner = QPointF(ax + dx, ay + dy)
        other = QPointF(ax - dx, ay - dy) if from_center else QPointF(ax, ay)
        return QRectF(corner, other).normalized()
    # Edges: one axis only (Shift has no effect).
    if index in (1, 5):
        y = p.y()
        if from_center:
            return QRectF(QPointF(l, y), QPointF(ri, 2 * cy - y)).normalized()
        return QRectF(QPointF(l, y), QPointF(ri, b if index == 1 else t)).normalized()
    if index in (3, 7):
        x = p.x()
        if from_center:
            return QRectF(QPointF(x, t), QPointF(2 * cx - x, b)).normalized()
        return QRectF(QPointF(x, t), QPointF(l if index == 3 else ri, b)).normalized()
    return QRectF(r0)


def rect_side_frame(base, side_pt):
    """Return the frame of the first rect side ``base → side_pt``.

    Args:
        base: The first placement click (QPointF).
        side_pt: The second placement click (QPointF).

    Returns:
        ``(length, angle_deg, (nx, ny))`` — ``angle_deg`` is Y-up degrees CCW
        from +x and ``(nx, ny)`` the unit left normal (Qt coords), the
        direction a POSITIVE depth extends.  None when the side is degenerate.
    """
    dx, dy = side_pt.x() - base.x(), side_pt.y() - base.y()
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return None
    ux, uy = dx / length, dy / length
    return length, math.degrees(math.atan2(-dy, dx)), (uy, -ux)


def rect_signed_depth(base, side_pt, cursor) -> float:
    """Signed perpendicular distance of *cursor* from the side line (+ = left).

    Returns 0.0 for a degenerate side.
    """
    f = rect_side_frame(base, side_pt)
    if f is None:
        return 0.0
    nx, ny = f[2]
    return (cursor.x() - base.x()) * nx + (cursor.y() - base.y()) * ny


def rect_side_ghost(base, cursor, from_center):
    """Return the segment drawn while picking the first side.

    ``base → cursor`` in the corner variant; the full side centred on *base*
    (mirrored through it) in the centre variant.
    """
    if from_center:
        return (QPointF(2 * base.x() - cursor.x(), 2 * base.y() - cursor.y()),
                QPointF(cursor))
    return QPointF(base), QPointF(cursor)


def rect_from_side_and_depth(base, side_pt, depth, from_center):
    """Solve the 3-click rectangle (base → side → depth; 2d-geometry.md §4).

    Corner variant: *base* is a corner, ``base → side_pt`` is the first side
    (W, angle) and *depth* the signed second side (H, + = left of the side).
    Centre variant: *base* is the centre, ``|base → side_pt|`` is HALF of W
    along the angle and ``|depth|`` is half of H.

    Args:
        base: First click (corner or centre), QPointF.
        side_pt: Second click (side end or side midpoint), QPointF.
        depth: Signed perpendicular depth (see ``rect_signed_depth``).
        from_center: True for the centre variant.

    Returns:
        ``(pt1, pt2, angle_deg, pivot)`` such that
        ``RectangleItem(pt1, pt2).set_angle(angle_deg, pivot)`` and
        ``rotated_rect_corners(pt1, pt2, angle_deg, pivot)`` give the
        rectangle — the unrotated local rect about ``pivot = base``.  None
        when a FULL extent is under 0.5 mm.
    """
    return _rect_solve(base, side_pt, depth, from_center, 0.5)


def _rect_solve(base, side_pt, depth, from_center, min_extent):
    """``rect_from_side_and_depth`` with the minimum FULL extent as a parameter.

    ``min_extent=0.0`` admits a zero-depth (line-along-the-side) rect — the
    ghost shape — while commits use the 0.5 mm floor.  None for a
    degenerate (zero-length) side whatever the floor.
    """
    f = rect_side_frame(base, side_pt)
    if f is None:
        return None
    length, angle, _n = f
    bx, by = base.x(), base.y()
    if from_center:
        h = abs(depth)
        if 2 * length < min_extent or 2 * h < min_extent:
            return None
        return (QPointF(bx - length, by - h), QPointF(bx + length, by + h),
                angle, QPointF(base))
    if length < min_extent or abs(depth) < min_extent:
        return None
    # Unrotated local frame: the side runs +x from base, positive depth is
    # Y-up (screen -y); set_angle then turns it about base onto the real side.
    r = QRectF(QPointF(bx, by), QPointF(bx + length, by - depth)).normalized()
    return r.topLeft(), r.bottomRight(), angle, QPointF(base)


def apply_rect_ghost(preview, base, side_pt, cursor, from_center):
    """Fit a ``QGraphicsRectItem`` ghost to the 3-click rect at *cursor*.

    One home for the 2D / wall / floor depth-step ghost.  Uses the same Qt
    transform ``RectangleItem.set_angle`` does, so the ghost matches the
    committed item.  The ghost is drawn WITHOUT the 0.5 mm floor, so a
    near-zero depth shows as a line along the first side (not a stale shape).

    Returns:
        The ``rect_from_side_and_depth`` solution — None when a full extent is
        under 0.5 mm (the commit would refuse it) even though the ghost was
        still drawn.
    """
    depth = rect_signed_depth(base, side_pt, cursor)
    ghost = _rect_solve(base, side_pt, depth, from_center, 0.0)
    if preview is not None and ghost is not None:
        pt1, pt2, ang, piv = ghost
        preview.setRotation(0.0)
        preview.setRect(QRectF(pt1, pt2).normalized())
        preview.setTransformOriginPoint(piv)
        preview.setRotation(-ang)        # Y-up CCW → Qt CW negate
    return rect_from_side_and_depth(base, side_pt, depth, from_center)


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
    from .cad_math import CAD_Math
    local = [
        QPointF(pt1.x(), pt1.y()),   # TL
        QPointF(pt2.x(), pt1.y()),   # TR
        QPointF(pt2.x(), pt2.y()),   # BR
        QPointF(pt1.x(), pt2.y()),   # BL
    ]
    # Y-up CCW angle → CAD_Math's screen-space rotate takes the negation
    # (the same CW negate ``set_angle`` applies via ``setRotation``).
    return [CAD_Math.rotate_point(p, pivot, -angle_deg) for p in local]


class GeometryTemplate:
    """Pre-placement template for geometry tools (line, rectangle, circle, etc.).

    Provides ``get_properties()`` / ``set_property()`` so the PropertyManager
    can display and edit default values before placement.  Colour and
    line-weight are derived from the selected layer at placement time.
    """

    def __init__(self):
        # Level-less (containment C3): geometry templates carry no level.
        self.name: str = "(Template)"

    def get_properties(self) -> dict:
        return {
            "Type": {"type": "label", "value": "Geometry"},
        }

    def set_property(self, key: str, value):
        return
