"""
elevation_scene.py
==================
QGraphicsScene that projects 3D model entities onto a vertical elevation plane.

Each elevation direction (North/South/East/West) projects onto a different axis:
  North (looking from +Y → -Y): H = world X, V = world Z
  South (looking from -Y → +Y): H = -world X, V = world Z
  East  (looking from +X → -X): H = -world Y, V = world Z
  West  (looking from -X → +X): H = world Y, V = world Z

Scene coordinates: H increases rightward, V (= -Z) increases downward (Qt convention).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QGraphicsScene, QGraphicsRectItem, QGraphicsLineItem,
    QGraphicsEllipseItem, QGraphicsSimpleTextItem, QGraphicsPathItem,
    QGraphicsItem, QGraphicsTextItem, QStyle,
)
from PyQt6.QtCore import pyqtSignal, Qt, QRectF, QPointF, QLineF, QTimer
from PyQt6.QtGui import QPen, QColor, QBrush, QFont, QPainterPath, QPainter

from PyQt6.QtCore import QSettings

from .constants import DEFAULT_LEVEL
from . import theme as th

if TYPE_CHECKING:
    from .model_space import Model_Space
    from .level_manager import LevelManager
    from .scale_manager import ScaleManager

# Data role for storing source entity reference on projected items
_ROLE_SOURCE = Qt.ItemDataRole.UserRole

# Marker role so elevation views can filter these from Ctrl+A
_ROLE_ELEV_ANNOTATION = Qt.ItemDataRole.UserRole + 1


# ─────────────────────────────────────────────────────────────────────────────
# ElevGridlineItem — selectable gridline in elevation view
# ─────────────────────────────────────────────────────────────────────────────

class _ElevBubble(QGraphicsEllipseItem):
    """Bubble at a gridline/datum endpoint in elevation view.

    Clicking selects the parent composite item.  Visual appearance mirrors
    the plan-view GridBubble.
    """

    def __init__(self, radius: float, label: str, color: QColor,
                 fill: QColor, parent: QGraphicsItem | None = None):
        super().__init__(-radius, -radius, 2 * radius, 2 * radius, parent)
        self._radius = radius
        pen = QPen(color, max(1, radius * 0.04))
        self.setPen(pen)
        self.setBrush(QBrush(fill))
        self.setZValue(500)

        self._label = QGraphicsTextItem(label, self)
        self._label.setDefaultTextColor(color.lighter(150))
        font = QFont("Consolas")
        font.setPixelSize(max(1, int(radius * 0.9)))
        font.setBold(True)
        self._label.setFont(font)
        self._center_label()

    def set_label(self, text: str):
        self._label.setPlainText(text)
        self._center_label()

    def _center_label(self):
        br = self._label.boundingRect()
        self._label.setPos(-br.width() / 2, -br.height() / 2)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        parent = self.parentItem()
        if parent is not None and parent.isSelected():
            r = self._radius
            base_color = self.pen().color()
            highlight = QPen(base_color.lighter(150), max(1, r * 0.08))
            painter.setPen(highlight)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(-r, -r, 2 * r, 2 * r))

    def mousePressEvent(self, event):
        parent = self.parentItem()
        if parent is not None:
            scene = parent.scene()
            if scene is not None:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    parent.setSelected(not parent.isSelected())
                else:
                    scene.clearSelection()
                    parent.setSelected(True)
        event.accept()


class ElevGridlineItem(QGraphicsLineItem):
    """Interactive gridline in an elevation view — selectable with grip handles."""

    def __init__(self, h_pos: float, v_top: float, v_bot: float,
                 label: str, bubble_r: float,
                 color: QColor, fill: QColor, pen_w: float,
                 opacity: float = 1.0):
        super().__init__(h_pos, v_top, h_pos, v_bot)
        self._h = h_pos
        self._bubble_r = bubble_r

        # Line pen — suppress default; drawn manually in paint()
        self.setPen(QPen(Qt.PenStyle.NoPen))

        self._grid_color = color
        self._pen_w = pen_w

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(50)   # in front of walls/floors/roofs
        self.setOpacity(opacity)
        self.setData(_ROLE_ELEV_ANNOTATION, True)

        # Bubbles at top and bottom
        self.bubble1 = _ElevBubble(bubble_r, label, color, fill, self)
        self.bubble2 = _ElevBubble(bubble_r, label, color, fill, self)
        self._update_bubble_positions()

    def _update_bubble_positions(self):
        line = self.line()
        self.bubble1.setPos(line.p1())
        self.bubble2.setPos(line.p2())

    # ── Drawing ──────────────────────────────────────────────────────────

    def boundingRect(self):
        br = super().boundingRect()
        m = self._bubble_r
        return br.adjusted(-m, -m, m, m)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        r = self._bubble_r
        path.addEllipse(self.bubble1.pos(), r, r)
        path.addEllipse(self.bubble2.pos(), r, r)
        return path

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        line = self.line()
        p1, p2 = line.p1(), line.p2()

        # Shorten to meet bubbles at edge
        dy = p2.y() - p1.y()
        length = abs(dy)
        if length > 1e-9:
            uy = dy / length
            r1 = self._bubble_r * self.bubble1.scale()
            r2 = self._bubble_r * self.bubble2.scale()
            draw_p1 = QPointF(p1.x(), p1.y() + uy * r1) if self.bubble1.isVisible() else p1
            draw_p2 = QPointF(p2.x(), p2.y() - uy * r2) if self.bubble2.isVisible() else p2
        else:
            draw_p1, draw_p2 = p1, p2

        pen = QPen(self._grid_color, self._pen_w, Qt.PenStyle.DashDotLine)
        painter.setPen(pen)
        painter.drawLine(draw_p1, draw_p2)

        if self.isSelected():
            sel_pen = QPen(self._grid_color.lighter(150),
                           self._pen_w * 2, Qt.PenStyle.DashDotLine)
            painter.setPen(sel_pen)
            painter.drawLine(draw_p1, draw_p2)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.bubble1.update()
            self.bubble2.update()
        return super().itemChange(change, value)

    # ── Grip handles ─────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        line = self.line()
        return [line.p1(), line.p2()]

    def apply_grip(self, index: int, new_pos: QPointF):
        """Move grip along the vertical line (constrained to H position)."""
        line = self.line()
        p1, p2 = line.p1(), line.p2()
        if index == 0:
            self.setLine(self._h, new_pos.y(), self._h, p2.y())
        elif index == 1:
            self.setLine(self._h, p1.y(), self._h, new_pos.y())
        self._update_bubble_positions()
        self.update()


class ElevDatumItem(QGraphicsLineItem):
    """Interactive level datum in an elevation view — selectable with grip handles."""

    def __init__(self, v_pos: float, h_min: float, h_max: float,
                 level_name: str, elev_str: str,
                 bubble_r: float, datum_color: QColor, fill_color: QColor,
                 pen_w: float, name_font: QFont, elev_font: QFont,
                 scale: float = 1.0, opacity: float = 1.0):
        super().__init__(h_min, v_pos, h_max, v_pos)
        self._v = v_pos
        self._h_min = h_min
        self._h_max = h_max
        self._bubble_r = bubble_r
        self._datum_color = datum_color
        self._fill_color = fill_color
        self._pen_w = pen_w
        self._scale = scale
        self._level_name = level_name.upper() if level_name else "LEVEL"
        self._elev_str = elev_str

        # Preserve the original fonts so grip moves don't lose sizing
        self._name_font = QFont(name_font)
        self._elev_font = QFont(elev_font)

        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(50)   # in front of walls/floors/roofs
        self.setOpacity(opacity)
        self.setData(_ROLE_ELEV_ANNOTATION, True)

        # ── Bubble (4-quadrant) at left end ──────────────────────────────
        bx = h_min - bubble_r * 0.5
        self._bx = bx
        self._build_bubble(bx, v_pos, bubble_r, datum_color, fill_color, pen_w)

        # ── Labels ───────────────────────────────────────────────────────
        self._build_labels()

    def _build_bubble(self, bx, by, r, datum_color, fill_color, pen_w):
        """Build the 4-quadrant datum bubble as child items."""
        circle_pen = QPen(datum_color, pen_w)
        circle_pen.setCosmetic(False)

        circle = QGraphicsEllipseItem(bx - r, by - r, r * 2, r * 2, self)
        circle.setPen(circle_pen)
        circle.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        circle.setZValue(51)

        QGraphicsLineItem(bx - r, by, bx + r, by, self).setPen(circle_pen)
        QGraphicsLineItem(bx, by - r, bx, by + r, self).setPen(circle_pen)

        arc_rect = QRectF(bx - r, by - r, r * 2, r * 2)

        lq = QPainterPath()
        lq.moveTo(bx, by); lq.arcTo(arc_rect, 0, 90); lq.closeSubpath()
        lq.moveTo(bx, by); lq.arcTo(arc_rect, 180, 90); lq.closeSubpath()
        lq_item = QGraphicsPathItem(lq, self)
        lq_item.setPen(QPen(Qt.PenStyle.NoPen))
        lq_item.setBrush(QBrush(datum_color))
        lq_item.setZValue(52)

        fq = QPainterPath()
        fq.moveTo(bx, by); fq.arcTo(arc_rect, 90, 90); fq.closeSubpath()
        fq.moveTo(bx, by); fq.arcTo(arc_rect, 270, 90); fq.closeSubpath()
        fq_item = QGraphicsPathItem(fq, self)
        fq_item.setPen(QPen(Qt.PenStyle.NoPen))
        fq_item.setBrush(QBrush(fill_color))
        fq_item.setZValue(52)

    def _build_labels(self):
        """Create or recreate label items using the stored fonts."""
        tag_gap = 50 * self._scale
        tag_x = self._bx + self._bubble_r + tag_gap

        self._name_text = QGraphicsSimpleTextItem(self._level_name, self)
        self._name_text.setFont(self._name_font)
        self._name_text.setBrush(QBrush(self._datum_color))
        name_br = self._name_text.boundingRect()
        self._name_text.setPos(tag_x, self._v - name_br.height() - 20)
        self._name_text.setZValue(53)

        self._elev_text = QGraphicsSimpleTextItem(self._elev_str, self)
        self._elev_text.setFont(self._elev_font)
        self._elev_text.setBrush(QBrush(self._datum_color.lighter(130)))
        self._elev_text.setPos(tag_x, self._v + 20)
        self._elev_text.setZValue(53)

    # ── Drawing ──────────────────────────────────────────────────────────

    def boundingRect(self):
        br = super().boundingRect()
        m = self._bubble_r * 2
        return br.adjusted(-m, -m, m, m)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        r = self._bubble_r
        path.addEllipse(QPointF(self._bx, self._v), r, r)
        return path

    def paint(self, painter, option, widget=None):
        # The datum line is drawn by the scene's drawForeground() so it
        # remains visible even when the bubble has scrolled off-screen.
        # Do NOT call super().paint() — the base QGraphicsLineItem must
        # not draw its own line.
        pass

    def mousePressEvent(self, event):
        """Clicking the bubble area selects this item."""
        r = self._bubble_r
        bp = QPointF(self._bx, self._v)
        if (event.scenePos() - bp).manhattanLength() < r * 1.5:
            scene = self.scene()
            if scene is not None:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    self.setSelected(not self.isSelected())
                else:
                    scene.clearSelection()
                    self.setSelected(True)
            event.accept()
            return
        super().mousePressEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update()
        return super().itemChange(change, value)

    # ── Grip handles ─────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        line = self.line()
        return [line.p1(), line.p2()]

    def apply_grip(self, index: int, new_pos: QPointF):
        """Move grip along the horizontal line (constrained to V position)."""
        line = self.line()
        p1, p2 = line.p1(), line.p2()
        if index == 0:
            new_x = new_pos.x()
            self.setLine(new_x, self._v, p2.x(), self._v)
            r = self._bubble_r
            self._bx = new_x - r * 0.5
            self._reposition_children()
        elif index == 1:
            self.setLine(p1.x(), self._v, new_pos.x(), self._v)
        self.prepareGeometryChange()
        self.update()

    def _reposition_children(self):
        """Rebuild child items after left-grip move, preserving fonts."""
        for child in list(self.childItems()):
            if self.scene():
                self.scene().removeItem(child)

        self._build_bubble(self._bx, self._v, self._bubble_r,
                           self._datum_color, self._fill_color, self._pen_w)
        self._build_labels()


class ElevationScene(QGraphicsScene):
    """Projects model entities onto a vertical plane for elevation display."""

    entitySelected = pyqtSignal(object)   # picked legacy entity
    cursorMoved = pyqtSignal(str)         # formatted "H: … Z: …"

    def __init__(self, direction: str, model_space: "Model_Space",
                 level_manager: "LevelManager", scale_manager: "ScaleManager",
                 parent=None):
        super().__init__(parent)
        self._direction = direction.lower()
        self._ms = model_space
        self._lm = level_manager
        self._sm = scale_manager
        self._show_datums = True

        # Grip-drag state (mirrors Model_Space pattern)
        self._grip_item = None
        self._grip_index: int = -1
        self._grip_dragging = False

        # Theme
        _t = th.detect()
        bg = QColor(_t.canvas_bg)
        self.setBackgroundBrush(QBrush(bg))

        # Edge/line color based on background brightness
        br = bg.redF() * 0.299 + bg.greenF() * 0.587 + bg.blueF() * 0.114
        self._edge_color = QColor("#d0d0d0") if br < 0.5 else QColor("#000000")
        self._datum_color = QColor("#4488cc")

        # Large scene rect (in mm)
        self.setSceneRect(-500000, -500000, 1000000, 1000000)

        # Debounce rebuild
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(100)
        self._rebuild_timer.timeout.connect(self.rebuild)
        self._ms.sceneModified.connect(self._schedule_rebuild)
        self.selectionChanged.connect(self._on_selection_changed)

    # ── Selection sync ───────────────────────────────────────────────────

    def _on_selection_changed(self):
        """When items are selected (click or rubber-band), emit source entity."""
        selected = self.selectedItems()
        if selected:
            # Emit the last selected item's source entity
            for item in reversed(selected):
                source = item.data(_ROLE_SOURCE)
                if source is not None:
                    self.entitySelected.emit(source)
                    return
        self.entitySelected.emit(None)

    # ── Grip-drag handling ────────────────────────────────────────────────

    def _find_grip_hit(self, pos: QPointF):
        """Return (item, grip_index) if pos is near a grip handle, else None."""
        views = self.views()
        if not views:
            return None
        scale = views[0].transform().m11()
        tol = 16.0 / max(abs(scale), 1e-6)

        for item in self.selectedItems():
            if not hasattr(item, "grip_points"):
                continue
            for idx, gpt in enumerate(item.grip_points()):
                if (pos - gpt).manhattanLength() <= tol * 1.5:
                    return (item, idx)
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            # Don't pass right-click to base — it deselects items.
            # contextMenuEvent handles right-click menus separately.
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._find_grip_hit(event.scenePos())
            if hit is not None:
                self._grip_item, self._grip_index = hit
                self._grip_dragging = True
                # Snapshot grip positions of co-selected items for delta propagation
                self._grip_start_pos = event.scenePos()
                self._grip_co_items = []
                primary_type = type(self._grip_item)
                for sel in self.selectedItems():
                    if sel is self._grip_item:
                        continue
                    if isinstance(sel, primary_type) and hasattr(sel, "grip_points"):
                        grips = sel.grip_points()
                        if len(grips) > self._grip_index:
                            self._grip_co_items.append(
                                (sel, grips[self._grip_index]))
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._grip_dragging and self._grip_item is not None:
            pos = event.scenePos()
            # Move primary item
            old_grips = self._grip_item.grip_points()
            self._grip_item.apply_grip(self._grip_index, pos)
            new_grips = self._grip_item.grip_points()

            # Compute delta and propagate to co-selected items
            if len(old_grips) > self._grip_index and len(new_grips) > self._grip_index:
                delta = new_grips[self._grip_index] - old_grips[self._grip_index]
                for sel, start_pt in self._grip_co_items:
                    sg = sel.grip_points()
                    if len(sg) > self._grip_index:
                        target = QPointF(
                            sg[self._grip_index].x() + delta.x(),
                            sg[self._grip_index].y() + delta.y())
                        sel.apply_grip(self._grip_index, target)

            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._grip_dragging:
            self._grip_item = None
            self._grip_index = -1
            self._grip_dragging = False
            self._grip_co_items = []
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        """Show right-click context menu for elevation view entities."""
        from .entity_context_menu import build_entity_context_menu

        # Find entity under cursor
        target = None
        for item in self.items(event.scenePos()):
            source = item.data(_ROLE_SOURCE)
            if source is not None:
                target = item
                break
            if isinstance(item, (ElevDatumItem, ElevGridlineItem)):
                target = item
                break

        if target is not None and not target.isSelected():
            self.clearSelection()
            target.setSelected(True)

        selected = self.selectedItems()
        source_entity = target.data(_ROLE_SOURCE) if target else None

        menu = build_entity_context_menu(
            selected,
            target,
            scene=self._ms,
            on_hide=lambda: self._hide_elev_items(
                [target] + [i for i in selected if i is not target]
            ),
            on_show_all=lambda: self._show_all_elev_hidden(),
            on_delete=lambda: self._delete_elev_selected(),
            on_properties=lambda: (
                self.entitySelected.emit(source_entity) if source_entity else None
            ),
            on_refresh=lambda: self.rebuild(),
        )
        menu.exec(event.screenPos())

    def _hide_elev_items(self, items):
        """Hide elevation items and their source entities."""
        for item in items:
            source = item.data(_ROLE_SOURCE) if item else None
            if source is not None and hasattr(source, "_display_overrides"):
                source._display_overrides["visible"] = False
            item.setVisible(False)

    def _show_all_elev_hidden(self):
        """Restore all hidden source entities and rebuild."""
        self._ms._show_all_hidden()
        self.rebuild()

    def _delete_elev_selected(self):
        """Delete source entities for selected elevation items."""
        for item in list(self.selectedItems()):
            source = item.data(_ROLE_SOURCE) if item else None
            if source is not None and hasattr(source, "setSelected"):
                source.setSelected(True)
        self._ms.delete_selected_items()
        self.rebuild()

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def direction(self) -> str:
        return self._direction

    @property
    def show_datums(self) -> bool:
        return self._show_datums

    @show_datums.setter
    def show_datums(self, val: bool):
        self._show_datums = val
        self.rebuild()

    # ── Coordinate projection ────────────────────────────────────────────

    def _ppm(self) -> float:
        """Pixels-per-mm (calibration factor), default 1.0."""
        return self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0

    def _scene_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        """Convert legacy scene coords (pixels) to world mm with Y flip."""
        ppm = self._ppm()
        return sx / ppm, -sy / ppm

    def _world_to_elev(self, wx: float, wy: float, wz: float) -> tuple[float, float]:
        """Project world (mm) coords onto elevation 2D plane.

        Returns (h, v) where h is horizontal scene coord and v = -wz
        (Qt Y increases downward, Z increases upward).
        """
        d = self._direction
        if d == "north":
            h = -wx       # looking south: East (+X) on left, West (-X) on right
        elif d == "south":
            h = wx        # looking north: West (-X) on left, East (+X) on right
        elif d == "east":
            h = wy        # looking west: South (-Y) on left, North (+Y) on right
        elif d == "west":
            h = -wy       # looking east: North (+Y) on left, South (-Y) on right
        else:
            h = -wx
        return h, -wz

    def _level_z(self, level_name: str) -> float:
        lvl = self._lm.get(level_name)
        return lvl.elevation if lvl else 0.0

    # ── Rebuild ──────────────────────────────────────────────────────────

    def _schedule_rebuild(self):
        if not self._rebuild_timer.isActive():
            self._rebuild_timer.start()

    def rebuild(self):
        """Clear and re-project all entities from the model."""
        self.clear()
        self._depth_items: list[tuple[float, list]] = []  # (depth, [items])
        self._project_level_datums()
        self._project_walls()
        self._project_pipes()
        self._project_sprinklers()
        self._project_floor_slabs()
        self._project_roofs()
        self._project_gridlines()
        self._project_construction_geometry()
        self._assign_depth_z_values()

    def _register_depth_item(self, depth: float, *items):
        """Register scene items at a given depth for unified Z assignment."""
        self._depth_items.append((depth, list(items)))

    def _assign_depth_z_values(self):
        """Sort all depth-registered items farthest-first and assign Z-values.

        Items at the same depth are drawn in registration order.
        Farther items get lower Z (drawn first / behind).
        """
        self._depth_items.sort(key=lambda x: x[0])
        z = -50.0
        for depth, items in self._depth_items:
            for item in items:
                item.setZValue(z)
                z += 0.01
        self._depth_items = []

    # ── Foreground (datum lines) ─────────────────────────────────────────

    def drawForeground(self, painter, rect):
        """Draw datum lines from the bubble to h_max (gridline extent).

        Drawn in foreground so lines remain visible even when the bubble
        has scrolled out of the viewport.
        """
        super().drawForeground(painter, rect)
        for item in self.items():
            if not isinstance(item, ElevDatumItem):
                continue
            if not item.isVisible():
                continue
            v = item._v
            h_start = item._bx + item._bubble_r
            h_end = item._h_max
            if h_end <= h_start:
                continue

            pen = QPen(item._datum_color, item._pen_w, Qt.PenStyle.DashDotLine)
            painter.setPen(pen)
            painter.drawLine(QPointF(h_start, v), QPointF(h_end, v))

            if item.isSelected():
                sel_pen = QPen(item._datum_color.lighter(150),
                               item._pen_w * 2, Qt.PenStyle.DashDotLine)
                painter.setPen(sel_pen)
                painter.drawLine(QPointF(h_start, v), QPointF(h_end, v))

    # ── Walls ────────────────────────────────────────────────────────────

    def _project_walls(self):
        props = self._wall_display_props()
        if not props["visible"]:
            return
        dm_color = QColor(props["color"])
        dm_fill = QColor(props["fill"])
        dm_opacity = props["opacity"] / 100.0
        has_explicit_fill = props.get("has_explicit_fill", False)

        ppm = self._ppm()
        d = self._direction

        # Collect all wall rects with their depth for sorting
        wall_rects: list[tuple[float, QGraphicsRectItem]] = []

        for wall in getattr(self._ms, "_walls", []):
            # Get Z extents
            base_z = 0.0
            top_z = wall._height_mm
            base_lvl = self._lm.get(wall._base_level)
            if base_lvl:
                base_z = base_lvl.elevation + wall._base_offset_mm
            top_lvl = self._lm.get(wall._top_level)
            if top_lvl:
                top_z = top_lvl.elevation + wall._top_offset_mm
            else:
                top_z = base_z + wall._height_mm
            if abs(top_z - base_z) < 1.0:
                continue

            # Get mitered 2D quad corners, convert to world mm
            try:
                p1l, p1r, p2r, p2l = wall.mitered_quad()
            except Exception:
                p1l, p1r, p2r, p2l = wall.quad_points()

            corners_world = []
            for pt in (p1l, p1r, p2r, p2l):
                wx, wy = self._scene_to_world(pt.x(), pt.y())
                corners_world.append((wx, wy))

            # Project to elevation H axis
            h_values = [self._world_to_elev(wx, wy, 0)[0]
                        for wx, wy in corners_world]
            h_min = min(h_values)
            h_max = max(h_values)
            width = h_max - h_min
            if width < 0.5:
                continue

            # Compute depth (distance from camera along view direction)
            # for sorting: closer walls should be drawn on top (higher Z)
            all_wx = [c[0] for c in corners_world]
            all_wy = [c[1] for c in corners_world]
            centroid_x = sum(all_wx) / len(all_wx)
            centroid_y = sum(all_wy) / len(all_wy)
            if d == "north":
                depth = centroid_y   # camera at +Y, closer = larger Y
            elif d == "south":
                depth = -centroid_y  # camera at -Y, closer = smaller Y
            elif d == "east":
                depth = centroid_x   # camera at +X, closer = larger X
            elif d == "west":
                depth = -centroid_x
            else:
                depth = centroid_y

            # Elevation scene rect: (h_min, -top_z) to (h_max, -base_z)
            v_top = -top_z      # Qt Y for top of wall
            v_bottom = -base_z  # Qt Y for bottom of wall
            height = v_bottom - v_top

            rect = QGraphicsRectItem(h_min, v_top, width, height)

            # Use display manager colour; fall back to wall's own colour
            pen = QPen(dm_color, 1)
            pen.setCosmetic(True)
            rect.setPen(pen)
            if has_explicit_fill:
                fill_col = dm_fill
            else:
                fill_col = QColor(wall._color) if hasattr(wall, "_color") else dm_fill
                fill_col.setAlpha(255)
            rect.setBrush(QBrush(fill_col))
            rect.setOpacity(dm_opacity)

            rect.setData(_ROLE_SOURCE, wall)
            rect.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
            wall_rects.append((depth, rect))

        for depth, rect in wall_rects:
            self.addItem(rect)
            self._register_depth_item(depth, rect)

    # ── Pipes ────────────────────────────────────────────────────────────

    def _project_pipes(self):
        from .constants import PIPE_COLORS as _PIPE_COLORS
        d = self._direction
        pipe_items: list[tuple[float, QGraphicsLineItem]] = []

        for pipe in self._ms.sprinkler_system.pipes:
            n1, n2 = pipe.node1, pipe.node2
            if n1 is None or n2 is None:
                continue
            # Get world positions
            wx1, wy1 = self._scene_to_world(n1.scenePos().x(), n1.scenePos().y())
            wx2, wy2 = self._scene_to_world(n2.scenePos().x(), n2.scenePos().y())
            z1 = getattr(n1, "z_pos", 0.0)
            z2 = getattr(n2, "z_pos", 0.0)

            h1, v1 = self._world_to_elev(wx1, wy1, z1)
            h2, v2 = self._world_to_elev(wx2, wy2, z2)

            col_name = pipe._properties.get("Colour", {}).get("value", "Red")
            color = QColor(_PIPE_COLORS.get(col_name, "#e62828"))

            line = QGraphicsLineItem(h1, v1, h2, v2)
            pen = QPen(color, 2)
            pen.setCosmetic(True)
            line.setPen(pen)
            line.setData(_ROLE_SOURCE, pipe)
            line.setFlag(QGraphicsLineItem.GraphicsItemFlag.ItemIsSelectable, True)

            # Depth for sorting
            cx = (wx1 + wx2) / 2
            cy = (wy1 + wy2) / 2
            if d == "north":
                depth = cy
            elif d == "south":
                depth = -cy
            elif d == "east":
                depth = cx
            elif d == "west":
                depth = -cx
            else:
                depth = cy
            pipe_items.append((depth, line))

        for depth, line in pipe_items:
            self.addItem(line)
            self._register_depth_item(depth, line)

    # ── Sprinklers ───────────────────────────────────────────────────────

    def _project_sprinklers(self):
        d = self._direction
        spr_items: list[tuple[float, QGraphicsEllipseItem]] = []

        for node in self._ms.sprinkler_system.nodes:
            if not node.has_sprinkler():
                continue
            wx, wy = self._scene_to_world(node.scenePos().x(), node.scenePos().y())
            z = getattr(node, "z_pos", 0.0)
            h, v = self._world_to_elev(wx, wy, z)

            orient = node.sprinkler._properties.get(
                "Orientation", {}).get("value", "Upright")
            if orient == "Pendent":
                color = QColor("#ff3232")
            elif orient == "Sidewall":
                color = QColor("#32c832")
            else:
                color = QColor("#3264ff")

            r = 30.0  # mm radius
            ellipse = QGraphicsEllipseItem(h - r, v - r, r * 2, r * 2)
            pen = QPen(color, 1.5)
            pen.setCosmetic(True)
            ellipse.setPen(pen)
            ellipse.setBrush(QBrush())
            ellipse.setData(_ROLE_SOURCE, node)
            ellipse.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable, True)

            if d == "north":
                depth = wy
            elif d == "south":
                depth = -wy
            elif d == "east":
                depth = wx
            elif d == "west":
                depth = -wx
            else:
                depth = wy
            spr_items.append((depth, ellipse))

        for depth, ellipse in spr_items:
            self.addItem(ellipse)
            self._register_depth_item(depth, ellipse)

    # ── Floor slabs ──────────────────────────────────────────────────────

    def _project_floor_slabs(self):
        props = self._floor_display_props()
        if not props["visible"]:
            return
        dm_color = QColor(props["color"])
        dm_fill = QColor(props["fill"])
        dm_opacity = props["opacity"] / 100.0

        d = self._direction
        # Each entry: (depth, mask_rect, visible_rect)
        slab_rects: list[tuple[float, QGraphicsRectItem, QGraphicsRectItem]] = []

        # Background color for opaque mask
        _t = th.detect()
        bg = QColor(_t.canvas_bg)

        for slab in getattr(self._ms, "_floor_slabs", []):
            z = self._level_z(getattr(slab, "level", DEFAULT_LEVEL)) + getattr(slab, "_level_offset_mm", 0.0)
            thickness = getattr(slab, "_thickness_mm", 150.0)

            pts = getattr(slab, "_points", [])
            if not pts:
                continue
            h_vals = []
            world_pts = []
            for pt in pts:
                wx, wy = self._scene_to_world(pt.x(), pt.y())
                world_pts.append((wx, wy))
                h, _ = self._world_to_elev(wx, wy, 0)
                h_vals.append(h)
            h_min, h_max = min(h_vals), max(h_vals)

            # Compute depth (same convention as walls)
            cx = sum(w[0] for w in world_pts) / len(world_pts)
            cy = sum(w[1] for w in world_pts) / len(world_pts)
            if d == "north":
                depth = cy
            elif d == "south":
                depth = -cy
            elif d == "east":
                depth = cx
            elif d == "west":
                depth = -cx
            else:
                depth = cy

            v_top = -(z)
            v_bottom = -(z - thickness)
            width = h_max - h_min
            height = v_bottom - v_top

            # Opaque mask rect — hides items behind the slab
            mask = QGraphicsRectItem(h_min, v_top, width, height)
            mask.setPen(QPen(Qt.PenStyle.NoPen))
            mask.setBrush(QBrush(bg))
            mask.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, False)

            # Visible slab rect with styled fill
            rect = QGraphicsRectItem(h_min, v_top, width, height)
            pen = QPen(dm_color, 1)
            pen.setCosmetic(True)
            rect.setPen(pen)
            rect.setBrush(QBrush(dm_fill))
            rect.setOpacity(dm_opacity)
            rect.setData(_ROLE_SOURCE, slab)
            rect.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
            slab_rects.append((depth, mask, rect))

        for depth, mask, rect in slab_rects:
            self.addItem(mask)
            self.addItem(rect)
            # Register mask + visible rect at the same depth as walls;
            # the unified sorter places them at the correct Z relative
            # to walls at the same depth (mask first, then visible rect).
            self._register_depth_item(depth, mask, rect)

    # ── Roofs ────────────────────────────────────────────────────────────

    def _project_roofs(self):
        props = self._roof_display_props()
        if not props["visible"]:
            return
        dm_color = QColor(props["color"])
        dm_fill = QColor(props["fill"])
        dm_opacity = props["opacity"] / 100.0

        for roof in getattr(self._ms, "_roofs", []):
            mesh_data = None
            try:
                mesh_data = roof.get_3d_mesh(level_manager=self._lm)
            except Exception:
                pass
            if mesh_data is None:
                continue

            verts = mesh_data.get("vertices", [])
            if not verts:
                continue
            col = mesh_data.get("color", (0.8, 0.7, 0.5, 0.5))

            # Project all vertices and draw outline polygon
            elev_pts = []
            for vx, vy, vz in verts:
                h, v = self._world_to_elev(vx, vy, vz)
                elev_pts.append(QPointF(h, v))

            if not elev_pts:
                continue

            # Draw convex hull outline (simplified)
            h_vals = [p.x() for p in elev_pts]
            v_vals = [p.y() for p in elev_pts]
            rect = QGraphicsRectItem(
                min(h_vals), min(v_vals),
                max(h_vals) - min(h_vals), max(v_vals) - min(v_vals),
            )
            pen = QPen(dm_color, 1)
            pen.setCosmetic(True)
            rect.setPen(pen)
            rect.setBrush(QBrush(dm_fill))
            rect.setOpacity(dm_opacity)
            rect.setData(_ROLE_SOURCE, roof)
            rect.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
            rect.setZValue(-70)
            self.addItem(rect)

    # ── Display manager helpers ──────────────────────────────────────────

    def _wall_display_props(self) -> dict:
        """Read Wall display properties from QSettings (display manager)."""
        s = QSettings("GV", "FirePro3D")
        return {
            "color":   s.value("display/Wall/color",   "#666666"),
            "fill":    s.value("display/Wall/fill",    "#999999"),
            "opacity": int(float(s.value("display/Wall/opacity", 100))),
            "visible": str(s.value("display/Wall/visible", "true")).lower() not in ("false", "0"),
            "has_explicit_fill": s.contains("display/Wall/fill"),
        }

    def _roof_display_props(self) -> dict:
        """Read Roof display properties from QSettings (display manager)."""
        s = QSettings("GV", "FirePro3D")
        return {
            "color":   s.value("display/Roof/color",   "#8B4513"),
            "fill":    s.value("display/Roof/fill",    "#D2B48C"),
            "opacity": int(float(s.value("display/Roof/opacity", 100))),
            "visible": str(s.value("display/Roof/visible", "true")).lower() not in ("false", "0"),
        }

    def _floor_display_props(self) -> dict:
        """Read Floor display properties from QSettings (display manager)."""
        s = QSettings("GV", "FirePro3D")
        return {
            "color":   s.value("display/Floor/color",   "#8888cc"),
            "fill":    s.value("display/Floor/fill",    "#8888cc"),
            "opacity": int(float(s.value("display/Floor/opacity", 100))),
            "visible": str(s.value("display/Floor/visible", "true")).lower() not in ("false", "0"),
        }

    def _gridline_display_props(self) -> dict:
        """Read Grid Line display properties from QSettings (display manager)."""
        s = QSettings("GV", "FirePro3D")
        return {
            "color":   s.value("display/Grid Line/color",   "#4488cc"),
            "fill":    s.value("display/Grid Line/fill",    "#1a1a2e"),
            "opacity": int(float(s.value("display/Grid Line/opacity", 100))),
            "visible": str(s.value("display/Grid Line/visible", "true")).lower() not in ("false", "0"),
            "scale":   float(s.value("display/Grid Line/scale", 1.0)),
        }

    def _datum_display_props(self) -> dict:
        """Read Level Datum display properties from QSettings (display manager)."""
        s = QSettings("GV", "FirePro3D")
        return {
            "color":   s.value("display/Level Datum/color",   "#4488cc"),
            "fill":    s.value("display/Level Datum/fill",    "#1a1a2e"),
            "opacity": int(float(s.value("display/Level Datum/opacity", 100))),
            "visible": str(s.value("display/Level Datum/visible", "true")).lower() not in ("false", "0"),
            "scale":   float(s.value("display/Level Datum/scale", 1.0)),
            "font":    int(float(s.value("display/Level Datum/font", 10))),
        }

    # ── Gridlines ────────────────────────────────────────────────────────

    @staticmethod
    def _gridline_is_vertical(line_geom) -> bool:
        """True if the gridline is more vertical than horizontal in scene."""
        dx = abs(line_geom.x2() - line_geom.x1())
        dy = abs(line_geom.y2() - line_geom.y1())
        return dy >= dx

    def _should_show_gridline(self, line_geom) -> bool:
        """Filter gridlines by elevation direction.

        North/South elevations look along Y — show only vertical gridlines
        (which run along Y and project to distinct H positions on the X axis).
        East/West elevations look along X — show only horizontal gridlines
        (which run along X and project to distinct H positions on the Y axis).
        """
        is_vert = self._gridline_is_vertical(line_geom)
        if self._direction in ("north", "south"):
            return is_vert       # vertical gridlines → visible as vertical lines in N/S
        else:  # east, west
            return not is_vert   # horizontal gridlines → visible as vertical lines in E/W

    def _project_gridlines(self):
        props = self._gridline_display_props()
        if not props["visible"]:
            return

        grid_color = QColor(props["color"])
        fill_color = QColor(props["fill"])
        opacity = props["opacity"] / 100.0
        bubble_scale = props["scale"]
        BUBBLE_R = 203.2 * bubble_scale  # 8" in mm, scaled
        gl_pen_w = max(1.0, BUBBLE_R * 0.04)

        for gl in getattr(self._ms, "_gridlines", []):
            line_geom = gl.line()

            # Filter: only show gridlines perpendicular to the view direction
            if not self._should_show_gridline(line_geom):
                continue

            wx1, wy1 = self._scene_to_world(line_geom.x1(), line_geom.y1())
            wx2, wy2 = self._scene_to_world(line_geom.x2(), line_geom.y2())
            h1, _ = self._world_to_elev(wx1, wy1, 0)
            h2, _ = self._world_to_elev(wx2, wy2, 0)
            h_avg = (h1 + h2) / 2.0

            levels = self._lm.levels
            if not levels:
                continue
            z_min = min(l.elevation for l in levels) - 1000
            z_max = max(l.elevation for l in levels) + 4000

            label_text = getattr(gl, "_label_text", "")
            v_top = -z_max - BUBBLE_R - 50
            v_bot = -z_min + BUBBLE_R + 50

            item = ElevGridlineItem(
                h_avg, v_top, v_bot, label_text, BUBBLE_R,
                grid_color, fill_color, gl_pen_w, opacity)
            self.addItem(item)

    # ── Construction geometry ────────────────────────────────────────────

    def _project_construction_geometry(self):
        ppm = self._ppm()
        constr_color = QColor("#666666")
        pen = QPen(constr_color, 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)

        for item in getattr(self._ms, "_draw_lines", []):
            z = self._level_z(getattr(item, "level", DEFAULT_LEVEL))
            wx1, wy1 = self._scene_to_world(item._pt1.x(), item._pt1.y())
            wx2, wy2 = self._scene_to_world(item._pt2.x(), item._pt2.y())
            h1, v1 = self._world_to_elev(wx1, wy1, z)
            h2, v2 = self._world_to_elev(wx2, wy2, z)
            line = QGraphicsLineItem(h1, v1, h2, v2)
            line.setPen(pen)
            line.setZValue(-90)
            self.addItem(line)

        for item in getattr(self._ms, "_construction_lines", []):
            z = self._level_z(getattr(item, "level", DEFAULT_LEVEL))
            wx1, wy1 = self._scene_to_world(item._pt1.x(), item._pt1.y())
            wx2, wy2 = self._scene_to_world(item._pt2.x(), item._pt2.y())
            h1, v1 = self._world_to_elev(wx1, wy1, z)
            h2, v2 = self._world_to_elev(wx2, wy2, z)
            line = QGraphicsLineItem(h1, v1, h2, v2)
            line.setPen(pen)
            line.setZValue(-90)
            self.addItem(line)

    # ── Level datums ─────────────────────────────────────────────────────

    def _datum_extent(self) -> tuple[float, float]:
        """Compute H range for datum lines to match gridline extents.

        Returns (h_min, h_max) in world mm based on the actual gridline
        positions.  Falls back to DEFAULT_GRIDLINE_LENGTH_IN if no gridlines.
        """
        from .constants import DEFAULT_GRIDLINE_LENGTH_IN
        ppm = self._ppm()

        gridlines = getattr(self._ms, "_gridlines", [])
        if not gridlines:
            # Fallback: 1000" offset, 864" length (default gridline dims)
            half = DEFAULT_GRIDLINE_LENGTH_IN / ppm / 2.0
            return -half, half

        # Gather H positions only from gridlines visible in this elevation
        # (perpendicular to the view direction).  Parallel gridlines project
        # to extreme H values and would make the datum lines way too long.
        h_vals = []
        for gl in gridlines:
            lg = gl.line()
            if not self._should_show_gridline(lg):
                continue
            wx1, wy1 = self._scene_to_world(lg.x1(), lg.y1())
            wx2, wy2 = self._scene_to_world(lg.x2(), lg.y2())
            h1, _ = self._world_to_elev(wx1, wy1, 0)
            h2, _ = self._world_to_elev(wx2, wy2, 0)
            h_vals.extend([h1, h2])

        if not h_vals:
            half = DEFAULT_GRIDLINE_LENGTH_IN / ppm / 2.0
            return -half, half

        margin = abs(max(h_vals) - min(h_vals)) * 0.2 + 500
        return min(h_vals) - margin, max(h_vals) + margin

    def _project_level_datums(self):
        if not self._show_datums:
            return

        # Use Level Datum display properties from display manager
        props = self._datum_display_props()
        if not props.get("visible", True):
            return
        datum_color = QColor(props["color"])
        fill_color = QColor(props.get("fill", "#1a1a2e"))
        opacity = props["opacity"] / 100.0
        scale = props.get("scale", 1.0)

        h_min, h_max = self._datum_extent()

        # Datum line pen — dash-dot-dash, weight matched to gridline
        from .gridline import BUBBLE_RADIUS_MM
        grid_props = self._gridline_display_props()
        grid_scale = grid_props.get("scale", 1.0)
        pen_w = max(1.0, BUBBLE_RADIUS_MM * 0.04 * grid_scale)

        # Text size: base 175mm, scaled by display manager font size (pt)
        font_pt = props.get("font", 10)
        text_height = 175.0 * scale * (font_pt / 10.0)
        name_font = QFont("Consolas")
        name_font.setPixelSize(max(1, int(text_height)))
        name_font.setBold(True)

        elev_font = QFont("Consolas")
        elev_font.setPixelSize(max(1, int(text_height * 0.8)))

        # Bubble radius matches gridline bubbles
        bubble_r = BUBBLE_RADIUS_MM * scale

        for lvl in self._lm.levels:
            z = lvl.elevation
            v = -z  # Qt Y

            elev_str = self._sm.format_length(z) if self._sm else f"{z:.0f} mm"

            item = ElevDatumItem(
                v, h_min, h_max,
                lvl.name, elev_str,
                bubble_r, datum_color, fill_color,
                pen_w, name_font, elev_font,
                scale, opacity)
            self.addItem(item)

    # ── Selection ────────────────────────────────────────────────────────
    # Selection is handled by Qt's built-in rubber-band + ItemIsSelectable
    # flags, routed through _on_selection_changed() which emits entitySelected.
