""" UPDATES
- On selection highlight handles
- add handle to centerline
- Sprint Q: tick marks, label above line, draggable offset, text overhaul

"""

# annotations.py
import math
from .cad_math import CAD_Math
from PyQt6.QtWidgets import (
    QGraphicsTextItem, QGraphicsLineItem,
    QGraphicsPolygonItem, QGraphicsPathItem,
    QStyle,
)
from PyQt6.QtGui import QPen, QColor, QPolygonF, QFont, QPainter, QTextOption, QPainterPath, QPainterPathStroker, QBrush
from PyQt6.QtCore import Qt, QPointF, QLineF, QRectF
from .constants import DEFAULT_LEVEL, DEFAULT_ANNOTATION_GROUP

class Annotation:
    """Base class for CAD annotations."""

    def __init__(self):
        self._properties = {
            "Layer": {"type": "enum", "options": [DEFAULT_ANNOTATION_GROUP, "Notes", "Dimensions"], "value": DEFAULT_ANNOTATION_GROUP},
            "Color": {"type": "enum", "options": ["Black", "Red", "Blue"], "value": "Black"},
        }
        self.dimensions = [] #list of dimensions
        self.notes = [] #list of notes
        self.base_point_A = None
        self.base_point_B = None


    def get_properties(self):
        return self._properties

    def set_property(self, key, value):
        if key in self._properties:
            self._properties[key]["value"] = value

    def add_dimension(self, dim):
        self.dimensions.append(dim)

    def add_note(self, note):
        self.notes.append(note)


# ═════════════════════════════════════════════════════════════════════════════
# NoteAnnotation — MText-like text annotation
# ═════════════════════════════════════════════════════════════════════════════

class NoteAnnotation(QGraphicsTextItem, Annotation):
    """A text note placed on the drawing.  Supports multiline word-wrap,
    bold/italic, and alignment when a text_width is set."""

    def __init__(self, text="Note", x=0, y=0, text_width=0):
        QGraphicsTextItem.__init__(self, text)
        Annotation.__init__(self)
        self.setDefaultTextColor(Qt.GlobalColor.white)
        self.setPos(x, y)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, True)
        self.level: str = DEFAULT_LEVEL

        # Enable word wrap if width was specified
        if text_width > 0:
            self.setTextWidth(text_width)

        self._properties.update({
            "Text":      {"type": "string", "value": text},
            "Color":     {"type": "enum",
                          "options": ["White", "Black", "Red", "Blue"],
                          "value": "White"},
            "FontSize":  {"type": "string", "value": "12"},
            "Bold":      {"type": "enum", "options": ["Off", "On"], "value": "Off"},
            "Italic":    {"type": "enum", "options": ["Off", "On"], "value": "Off"},
            "Alignment": {"type": "enum",
                          "options": ["Left", "Center", "Right"],
                          "value": "Left"},
        })

    # ── property dispatch ─────────────────────────────────────────────────

    def set_property(self, key, value):
        super().set_property(key, value)
        if key == "Text":
            self.setPlainText(value)
        elif key == "Color":
            _color_map = {"Black": "#000000", "Red": "#ff0000",
                          "Blue": "#0000ff", "White": "#ffffff"}
            self.setDefaultTextColor(QColor(_color_map.get(value, value)))
        elif key == "FontSize":
            try:
                f = self.font()
                f.setPointSize(int(value))
                self.setFont(f)
            except (ValueError, TypeError):
                pass
        elif key == "Bold":
            f = self.font()
            f.setBold(value == "On")
            self.setFont(f)
        elif key == "Italic":
            f = self.font()
            f.setItalic(value == "On")
            self.setFont(f)
        elif key == "Alignment":
            opt = self.document().defaultTextOption()
            _map = {
                "Left":   Qt.AlignmentFlag.AlignLeft,
                "Center": Qt.AlignmentFlag.AlignCenter,
                "Right":  Qt.AlignmentFlag.AlignRight,
            }
            opt.setAlignment(_map.get(value, Qt.AlignmentFlag.AlignLeft))
            self.document().setDefaultTextOption(opt)

    # ── grip protocol ────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        """Single grip at the note's position."""
        return [self.pos()]

    def apply_grip(self, index: int, pos: QPointF):
        if index == 0:
            self.setPos(pos)

    # ── Selection-manipulator adapter (translate-only) ────────────────────
    # Governing spec: docs/specs/selection-manipulator.md.  A note's serialized
    # position IS its pos() (network_codec.serialize_note uses scenePos), so a
    # baked move is a plain moveBy.  No scale/rotate in v1.

    def manip_capabilities(self) -> set:
        # Translate-only (U1 deferred rotate): a mixed selection that includes
        # a note hides the group rotate knob (the manipulator requires every
        # member to implement manip_rotate).  Adding "rotate" here + a
        # manip_rotate method lights up group rotate for notes.
        return {"translate"}

    def manip_translate(self, dx: float, dy: float):
        self.moveBy(dx, dy)

    # ── visual editing frame ──────────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self.hasFocus():
            pen = QPen(QColor("#88aaff"), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())


# ═════════════════════════════════════════════════════════════════════════════
# DimensionAnnotation — AutoCAD-style linear dimension
# ═════════════════════════════════════════════════════════════════════════════

class DimensionAnnotation(QGraphicsLineItem, Annotation):
    def __init__(self, p1: QPointF, p2: QPointF):
        super().__init__(p1.x(), p1.y(), p2.x(), p2.y())

        self.level: str = DEFAULT_LEVEL

        # Properties
        self._properties = {
            "Text Size": {"type": "string", "value": "10"},
            "Colour": {"type": "enum", "options": ["Black", "Red", "Blue", "White"], "value": "White"},
            "Line Weight": {"type": "enum", "options": ["2", "4", "6"], "value": "2"},
            "Witness Length": {"type": "string", "value": "20"},
            "Offset": {"type": "string", "value": "10"},
        }

        # Measurement endpoints (plain QPointF — no child Handle objects)
        self._p1 = QPointF(p1)
        self._p2 = QPointF(p2)

        # Draggable perpendicular offset distance (scene units)
        self._offset_dist = float(self._properties["Offset"]["value"])
        self._perp_angle = 0.0     # stored by update_arrows_and_witness
        self._updating = False     # recursion guard
        self.is_radius: bool = False  # True → label shows "R" prefix
        # Per-dimension witness extension override (None = use default)
        self._witness_ext_override: float | None = None

        # Styling — cosmetic pen so dimension lines stay visible at any zoom
        self._dim_pen = QPen(QColor(self._properties["Colour"]["value"]),
                        float(self._properties["Line Weight"]["value"]),
                        Qt.PenStyle.SolidLine)
        self._dim_pen.setCosmetic(True)
        self.setPen(self._dim_pen)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(0)

        # Label — model-space sized (12" text height, scales with zoom like pipe labels)
        self.label = QGraphicsTextItem(parent=self)
        self.label.setZValue(100)
        # No ItemIgnoresTransformations — label is in model-space units

        # Tick marks (45-degree slashes at each end of dimension line)
        self.tick1 = QGraphicsLineItem(self)
        self.tick1.setPen(self._dim_pen)
        self.tick1.setZValue(0)
        self.tick2 = QGraphicsLineItem(self)
        self.tick2.setPen(self._dim_pen)
        self.tick2.setZValue(0)

        # Witness lines
        self.witness1 = QGraphicsLineItem(self)
        self.witness1.setPen(self._dim_pen)
        self.witness1.setZValue(0)
        self.witness2 = QGraphicsLineItem(self)
        self.witness2.setPen(self._dim_pen)
        self.witness2.setZValue(0)

        self.update_geometry()

    # ── Paint override — suppress Qt's dashed selection rectangle ─────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)

    # ── Hit-area overrides — make dimensions easy to click ───────────────

    def shape(self) -> QPainterPath:
        """Return a wide stroke around the dimension line + label area."""
        path = QPainterPath()
        line = self.line()
        path.moveTo(line.p1())
        path.lineTo(line.p2())
        stroker = QPainterPathStroker()
        stroker.setWidth(16.0)          # generous 16-px click corridor
        wide_path = stroker.createStroke(path)
        # Include the label bounding rect so clicking the text selects too
        if self.label:
            label_path = QPainterPath()
            label_path.addRect(self.label.boundingRect())
            mapped = self.label.mapToParent(label_path)
            wide_path = wide_path.united(mapped)
        return wide_path

    def boundingRect(self) -> QRectF:
        """Encompass the main line, witness lines, ticks, and label."""
        base = super().boundingRect()
        for child in (self.witness1, self.witness2, self.tick1, self.tick2):
            if child:
                base = base.united(child.mapRectToParent(child.boundingRect()))
        if self.label:
            base = base.united(self.label.mapRectToParent(self.label.boundingRect()))
        return base.adjusted(-8, -8, 8, 8)

    # ── Grip protocol (integrates with Model_View grip squares) ──────────

    def grip_points(self) -> list[QPointF]:
        """Return single grip at dimension line midpoint for offset dragging."""
        line = QLineF(self._p1, self._p2)
        angle = math.atan2(line.dy(), line.dx())
        perp = angle + math.pi / 2
        mid = QPointF((self._p1.x() + self._p2.x()) / 2,
                      (self._p1.y() + self._p2.y()) / 2)
        # Grip is at the midpoint of the offset dimension line
        return [QPointF(mid.x() + self._offset_dist * math.cos(perp),
                        mid.y() + self._offset_dist * math.sin(perp))]

    def apply_grip(self, index: int, pos: QPointF):
        """Single grip (index 0): drag to change perpendicular offset distance."""
        if index == 0:
            mid = QPointF((self._p1.x() + self._p2.x()) / 2,
                          (self._p1.y() + self._p2.y()) / 2)
            line = QLineF(self._p1, self._p2)
            angle = math.atan2(line.dy(), line.dx())
            perp = angle + math.pi / 2
            dx = pos.x() - mid.x()
            dy = pos.y() - mid.y()
            self._offset_dist = dx * math.cos(perp) + dy * math.sin(perp)
        self.update_geometry()

    # ── Selection-manipulator adapter (translate-only) ────────────────────
    # Governing spec: docs/specs/selection-manipulator.md.  A dimension is
    # serialized from its internal measurement endpoints (_p1/_p2), not pos()
    # (network_codec.serialize_dimension), so a bare moveBy would desync the
    # drawn line from the saved geometry.  Translate the endpoints and rebuild.
    # No scale/rotate in v1.

    def manip_capabilities(self) -> set:
        # Translate-only (U1 deferred rotate): a mixed selection that includes
        # a dimension hides the group rotate knob.  Adding "rotate" here + a
        # manip_rotate method lights up group rotate for dimensions.
        return {"translate"}

    def manip_translate(self, dx: float, dy: float):
        self._p1 = QPointF(self._p1.x() + dx, self._p1.y() + dy)
        self._p2 = QPointF(self._p2.x() + dx, self._p2.y() + dy)
        self.update_geometry()

    # ---------------------------------|
    # Helpers -------------------------|

    def get_properties(self):
        return self._properties

    def set_property(self, key, value):
        if key in self._properties:
            self._properties[key]["value"] = value
        if key == "Text Size":
            # Text size is now fixed in model-space (12"); rebuild label HTML
            self.update_label()
        elif key == "Colour":
            _color_map = {"Black": "#000000", "Red": "#ff0000", "Blue": "#0000ff", "White": "#ffffff"}
            c = _color_map.get(value, value.lower())
            self._dim_pen = QPen(QColor(c), float(self._properties["Line Weight"]["value"]))
            self._dim_pen.setCosmetic(True)
            self.setPen(self._dim_pen)
            self.tick1.setPen(self._dim_pen)
            self.tick2.setPen(self._dim_pen)
            self.witness1.setPen(self._dim_pen)
            self.witness2.setPen(self._dim_pen)
            # Rebuild label HTML with new colour
            self.update_label()
        elif key in ("Witness Length", "Offset"):
            if key == "Offset":
                self._offset_dist = float(value)
            self.update_geometry()

    def update_geometry(self):
        """Recalculate line, ticks, label, and witness lines based on _p1/_p2."""
        if self._updating:
            return
        self._updating = True
        try:
            self.setLine(self._p1.x(), self._p1.y(), self._p2.x(), self._p2.y())
            self.update_arrows_and_witness()
            self.update_label()
        finally:
            self._updating = False

    def rescale(self, sm=None) -> None:
        """Re-draw with updated scale-aware sizes (called after calibration)."""
        self.update_geometry()

    def update_label(self):
        # Compute display length from _p1 → _p2 (the measurement, not the offset line)
        p1 = self._p1
        p2 = self._p2
        length = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
        scene = self.scene()
        prefix = "R " if self.is_radius else ""
        if scene and hasattr(scene, "scale_manager"):
            text = prefix + scene.scale_manager.scene_to_display(length)
        else:
            text = f"{prefix}{length:.1f} px"

        # Model-space label: 12" text height (304.8 mm), matches pipe labels
        text_h = 12.0 * 25.4  # 304.8 mm
        _color_map = {"Black": "#000000", "Red": "#ff0000",
                      "Blue": "#0000ff", "White": "#ffffff"}
        color = _color_map.get(self._properties["Colour"]["value"], "#ffffff")
        html = (f"<div style='text-align:center; font-size:{text_h:.0f}px; "
                f"font-family:Consolas; color:{color};'>{text}</div>")
        self.label.setHtml(html)
        # Lock width so text-align:center works
        self.label.setTextWidth(-1)
        ideal = self.label.document().idealWidth()
        self.label.setTextWidth(ideal)
        self.set_label_position()

    def set_label_position(self):
        line = self.line()  # QLineF — the offset dimension line

        v1 = CAD_Math.get_unit_vector(line.p1(), line.p2())
        # If pointing left, flip direction
        if v1.x() < 0:
            v1 = QPointF(-v1.x(), -v1.y())
        v2 = QPointF(1, 0)
        angle = -CAD_Math.get_angle_between_vectors(v1, v2, signed=True)
        if angle == 90:
            angle = -90

        mid_point = QPointF((line.x1() + line.x2()) / 2, (line.y1() + line.y2()) / 2)
        bounds = self.label.boundingRect()
        center = bounds.center()

        # set transform origin so future rotations work around the center
        self.label.setTransformOriginPoint(center)

        # Label is now in model-space — boundingRect() is in scene units directly
        label_gap = 25.4  # 1 inch gap above the line

        # Use the same perpendicular direction as the witness lines
        perp_dx = math.cos(self._perp_angle)
        perp_dy = math.sin(self._perp_angle)
        # Offset the label so its bottom edge sits above the line
        offset = QPointF(perp_dx * label_gap, perp_dy * label_gap)
        label_pos = mid_point + offset - QPointF(center.x(), bounds.height())
        self.label.setPos(label_pos)
        self.label.setRotation(angle)

    def update_arrows_and_witness(self):
        # Scale-aware sizes
        sm = getattr(self.scene(), "scale_manager", None) if self.scene() else None
        if sm and sm.is_calibrated:
            tick_size = sm.paper_to_scene(6.0)    # 6mm tick on paper (4× original)
            offset_gap = sm.paper_to_scene(1.0)   # 1mm gap at measurement point
            default_ext = sm.paper_to_scene(4.0)  # 4mm extension past dimension line
        else:
            tick_size = 24                         # 4× fallback (was 6)
            offset_gap = 3
            default_ext = 12                       # 2× fallback (was 6)
        # Use per-dimension override if set, otherwise use default
        witness_ext = self._witness_ext_override if self._witness_ext_override is not None else default_ext

        # Measurement endpoints
        start = QPointF(self._p1)
        end = QPointF(self._p2)

        # Line angle and perpendicular
        line = QLineF(start, end)
        angle = math.atan2(line.dy(), line.dx())
        perp_angle = angle + math.pi / 2
        self._perp_angle = perp_angle  # store for label positioning

        dx_perp = math.cos(perp_angle)
        dy_perp = math.sin(perp_angle)

        # Dimension line offset from measurement baseline
        offset = self._offset_dist

        # Witness lines: from near measurement point to past the dimension line
        w1_start = start + QPointF(dx_perp * offset_gap, dy_perp * offset_gap)
        w1_end   = start + QPointF(dx_perp * (offset + offset_gap + witness_ext),
                                    dy_perp * (offset + offset_gap + witness_ext))
        self.witness1.setLine(w1_start.x(), w1_start.y(), w1_end.x(), w1_end.y())

        w2_start = end + QPointF(dx_perp * offset_gap, dy_perp * offset_gap)
        w2_end   = end + QPointF(dx_perp * (offset + offset_gap + witness_ext),
                                  dy_perp * (offset + offset_gap + witness_ext))
        self.witness2.setLine(w2_start.x(), w2_start.y(), w2_end.x(), w2_end.y())

        # Dimension line endpoints (at offset distance from measurement points)
        p1 = start + QPointF(dx_perp * offset, dy_perp * offset)
        p2 = end   + QPointF(dx_perp * offset, dy_perp * offset)
        self.setLine(QLineF(p1, p2))

        # Tick marks — 45-degree slashes at each end of the dimension line
        tick_angle = angle + math.pi / 4
        dx_tick = math.cos(tick_angle) * tick_size
        dy_tick = math.sin(tick_angle) * tick_size
        self.tick1.setLine(p1.x() - dx_tick, p1.y() - dy_tick,
                           p1.x() + dx_tick, p1.y() + dy_tick)
        self.tick1.setPen(self._dim_pen)
        self.tick2.setLine(p2.x() - dx_tick, p2.y() - dy_tick,
                           p2.x() + dx_tick, p2.y() + dy_tick)
        self.tick2.setPen(self._dim_pen)

        # (No child handles to reposition — grip squares drawn by the view)


# ═════════════════════════════════════════════════════════════════════════════
# Legacy migration helper — kept as a module-level function so scene_io.py
# can import it when loading old .fpd files that contain "hatches" entries.
# HatchItem itself has been retired; fills are now properties of the geometry.
# ═════════════════════════════════════════════════════════════════════════════

def _rebuild_path_from_elements(elements: list) -> "QPainterPath":
    """Rebuild a QPainterPath from a serialised element list.

    Each element is ``[el_type, x, y]`` where el_type follows
    QPainterPath.ElementType integer values (0=MoveTo, 1=LineTo, 2=CurveTo).
    Cubic curves consume three consecutive elements (control1, control2, end).
    This is the exact format that the retired HatchItem.to_dict() produced.
    """
    path = QPainterPath()
    i = 0
    while i < len(elements):
        el_type, x, y = elements[i]
        if el_type == 0:        # MoveToElement
            path.moveTo(x, y)
            i += 1
        elif el_type == 1:      # LineToElement
            path.lineTo(x, y)
            i += 1
        elif el_type == 2:      # CurveToElement — next 2 entries are data
            if i + 2 < len(elements):
                _, cx2, cy2 = elements[i + 1]
                _, ex, ey = elements[i + 2]
                path.cubicTo(x, y, cx2, cy2, ex, ey)
                i += 3
            else:
                i += 1  # malformed — skip
        else:
            i += 1
    return path


# ---------------------------------------------------------------------------
# NOTE: HatchItem has been RETIRED (2026-08-22).
# Fills are now a property of 2-D geometry items (PolylineItem, RectangleItem,
# CircleItem) via Geometry2DMixin (fill_type / fill_pattern / fill_opacity).
# Legacy "hatches" entries in old .fpd files are migrated on load in scene_io.
# ---------------------------------------------------------------------------
