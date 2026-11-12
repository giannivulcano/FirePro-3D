"""
room.py
=======
Room / Space element for FirePro 3D.

A Room is a closed polygonal region derived from wall boundaries.
It tracks sprinklers inside its boundary and computes NFPA 13
coverage metrics.

Created by clicking inside a closed wall loop — the boundary is
auto-detected from connected walls on the active level.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QGraphicsPolygonItem, QGraphicsItem, QStyle
from PyQt6.QtGui import QPen, QColor, QBrush, QPolygonF, QPainterPath
from PyQt6.QtCore import Qt, QPointF

from . import phase_registry
from .bound_label import BoundLabelItem, TagBlockHost
from .colour_tokens import resolve_colour
from .constants import DEFAULT_LEVEL, Z_ANNOT_TAG
from .floor_cut import signed_area

if TYPE_CHECKING:
    from .scale_manager import ScaleManager

# ── NFPA 13 coverage limits — imported from constants.py ─────────────────
from .constants import HAZARD_CLASSES, NFPA_MAX_COVERAGE_SQFT as _NFPA_MAX_COVERAGE_SQFT
from .nfpa_curves import min_design_point, STORAGE_HAZARDS


# NFPA 13 ceiling construction types — determines max spacing and
# protection area per Table 10.2.4.2.1(a)/(b).
CEILING_TYPES = [
    "Noncombustible unobstructed",
    "Noncombustible obstructed",
    "Combustible unobstructed - no exposed members",
    "Combustible unobstructed - exposed members >= 3ft (910 mm) O/C",
    "Combustible unobstructed - exposed members < 3ft (910 mm) O/C",
    "Combustible obstructed - exposed members >= 3ft (910 mm) O/C",
    "Combustible obstructed - exposed members < 3ft (910 mm) O/C",
    "Combustible concealed space per 10.2.6.1.4",
]

COMPARTMENT_TYPES = [
    "Room", "Corridor", "Stairwell", "Shaft",
    "Attic", "Concealed Space",
]


def _ring_length(pts) -> float:
    """Closed-ring edge-length sum (scene units)."""
    n = len(pts)
    return sum(math.hypot(pts[(i + 1) % n].x() - pts[i].x(),
                          pts[(i + 1) % n].y() - pts[i].y()) for i in range(n))

# ── Room class ──────────────────────────────────────────────────────────


from .displayable_item import DisplayableItemMixin
from .paper_display import shows_selection


class Room(TagBlockHost, DisplayableItemMixin, QGraphicsPolygonItem):
    """A closed polygonal room/space region derived from wall boundaries."""

    HALO_AREA = True  # HALO: cursor inside = direct hit
    _TAG_CATEGORY = "Room"

    def __init__(self, boundary: list[QPointF] | None = None,
                 color: str | QColor = "#4488cc", *,
                 holes: list[list[QPointF]] | None = None):
        super().__init__()
        self._boundary: list[QPointF] = list(boundary) if boundary else []
        # Hole rings (room-detection rework §2.1): islands this room surrounds.
        # polygon() stays the outer ring; holes are a snapshot like it (§8.5).
        self._holes: list[list[QPointF]] = [list(h) for h in (holes or []) if len(h) >= 3]
        self._color = QColor(color) if isinstance(color, str) else QColor(color)

        # Shared display-manager attributes
        self.init_displayable()
        self.phase: str = phase_registry.PHASE_NEW

        # Identity
        self.name: str = ""
        self._mark: str = ""
        self._show_label: bool = True
        self._ceiling_level: str = "Level 2"
        self._ceiling_offset: float = 0.0   # mm offset from ceiling level

        # NFPA / fire protection
        self._hazard_class: str = "Light Hazard"
        self._occupancy: str = ""
        self._system_type: str = "Wet"           # "Wet" | "Dry"
        # Selected NFPA design point (area_sqft, density gpm/ft²).
        # None → default to the hazard curve's minimum-area point.
        self._design_point: tuple[float, float] | None = None
        self._compartment_type: str = "Room"
        self._ceiling_type: str = "Noncombustible unobstructed"

        # Room-specific display extras (beyond mixin)
        self._display_scale: float = 1.0
        self._display_opacity: float = 100
        self._display_visible: bool = True

        # Room tag (SB3; concept F5): a BoundLabelItem (top-level, synced by
        # the room) draws the block mapped for "Room" at centroid +
        # label_offset. The room owns show_label / label_offset; the item is
        # never serialised.
        self._label_offset: QPointF = QPointF(0, 0)  # user drag offset from centroid
        # SB4d D5: TOP-LEVEL (Qt child z is local to the room) -- synced by
        # itemChange below: joins / leaves the room's scene, hides with it,
        # takes its opacity; the anchor is in scene coords (rooms carry no
        # transform). z = the annotation band's tag sub-band.
        self._tag = BoundLabelItem(self, child=False)
        self._tag.setZValue(Z_ANNOT_TAG)
        # SB3b: this room's own tag block id; None = the project default
        # (annotation_defaults["Room"]). Resolved first by BoundLabelItem._resolve.
        self._init_tag_block()

        # Rendering
        self.setZValue(-60)  # below walls (-50), above floors (-80)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        if self._boundary:
            self._rebuild()

    # ── Z-range for view-depth filtering ────────────────────────────────

    def z_range_mm(self) -> tuple[float, float] | None:
        """Room spans from floor level to underside of ceiling slab."""
        sc = self.scene()
        lm = getattr(sc, "_level_manager", None) if sc else None
        if lm is None:
            return None
        floor_lvl = lm.get(getattr(self, "level", None))
        if floor_lvl is None:
            return None
        bot_z = floor_lvl.elevation
        ceil_lvl = lm.get(getattr(self, "_ceiling_level", None))
        if ceil_lvl is None:
            top_z = bot_z + 3048.0  # 10ft default
        else:
            # Subtract ceiling slab thickness
            slab_thickness = 0.0
            for slab in getattr(sc, "_floor_slabs", []):
                if getattr(slab, "level", None) == self._ceiling_level:
                    slab_thickness = max(slab_thickness, slab._thickness_mm)
            top_z = ceil_lvl.elevation - slab_thickness + self._ceiling_offset
        return (bot_z, top_z)

    # ── Grip protocol (drawn by Model_View like all other geometry) ────

    def _centroid(self) -> QPointF | None:
        """Tag anchor base (D-R3): the boundary's vertex mean; for a room with
        holes, a point inside the net area when the mean is not (Gap 2: hole-less
        rooms are unchanged). None without a boundary."""
        if not self._boundary:
            return None
        n = len(self._boundary)
        mean = QPointF(sum(p.x() for p in self._boundary) / n,
                       sum(p.y() for p in self._boundary) / n)
        if not self._holes or self.contains_point(mean):
            return mean
        return self._inside_point(mean)

    def grip_points(self) -> list[QPointF]:
        """One grip at the tag anchor (centroid + label_offset).

        Label-only: shown while the label is visible and the room has a
        name (the shipped tag binds the Name, SB3 Q1); never a polygon grip.
        """
        if not self._show_label or not (self.name or "") or not self._boundary:
            return []
        return [QPointF(self._tag.pos())]

    def apply_grip(self, index: int, pos: QPointF):
        """Move the tag anchor to *pos*: writes ``label_offset`` (SB3 Q3)."""
        c = self._centroid()
        if index != 0 or c is None:
            return
        self._label_offset = QPointF(pos.x() - c.x(), pos.y() - c.y())
        self._update_label()

    def manip_handles(self):
        """U3: the single label-centre grip as a live-apply manipulator grip.

        ``default_grip_handles`` loops ``grip_points()``, which is empty when the
        label is hidden — so a label-less room returns ``[]`` and the coexistence
        gate stays off (nothing renders either way). When the label shows, the
        one grip renders round (a move affordance — it repositions the label) and
        the manipulator owns render/hit-test/commit; the legacy grip paths skip
        this item. Zero special drag semantics (`apply_grip` moves the label).
        """
        from .manip_handle import default_grip_handles
        return default_grip_handles(self, circular={0})

    # ── Geometry ─────────────────────────────────────────────────────────

    def _rebuild(self):
        """Rebuild polygon and label from boundary points."""
        if len(self._boundary) < 3:
            self.setPolygon(QPolygonF())
            return
        poly = QPolygonF(self._boundary)
        self.setPolygon(poly)
        self.update()        # setPolygon skips an equal polygon: a punched hole must repaint
        self._update_label()

    def _update_label(self):
        """Anchor the tag at centroid + label_offset; show it with show_label.

        The tag pulls its text at paint (SB3: ``BoundLabelItem``); a geometry
        rebuild or Renumber lands here, so the cached bounds rect is dropped
        too (a tag bound to ``@[Area]`` / ``@[Mark]`` would otherwise go stale).
        """
        c = self._centroid()
        self._tag.setVisible(self._show_label and c is not None and self.isVisible())
        if c is None:
            return          # degenerate room: tag hidden (design Edge Cases)
        self._tag.set_anchor(QPointF(c.x() + self._label_offset.x(),
                                     c.y() + self._label_offset.y()))
        self._tag.refresh()       # drop the cached rect (rebuild / Renumber reach here)

    def itemChange(self, change, value):
        """Keep the top-level tag with the room (SB4d D5): it leaves the old
        scene before the room does, joins the new one after it, and follows
        the room's visibility and opacity (a child got all three from Qt).
        QGraphicsScene.clear() / the scene destructor send no ItemSceneChange
        (probed 2026-11-03) and delete both items together."""
        gc = QGraphicsItem.GraphicsItemChange
        tag = getattr(self, "_tag", None)
        if tag is not None:
            if change == gc.ItemSceneChange:
                old = self.scene()
                if old is not None and tag.scene() is old:
                    old.removeItem(tag)
            elif change == gc.ItemSceneHasChanged:
                if value is not None and tag.scene() is None:
                    value.addItem(tag)
                    self._update_label()
            elif change == gc.ItemVisibleHasChanged:
                self._update_label()
            elif change == gc.ItemOpacityHasChanged:
                tag.setOpacity(self.opacity())
        return super().itemChange(change, value)

    @property
    def boundary(self) -> list[QPointF]:
        return list(self._boundary)

    @property
    def holes(self) -> list[list[QPointF]]:
        """Copies of the hole rings (room-detection rework §2.1)."""
        return [[QPointF(p) for p in h] for h in self._holes]

    def room_path(self) -> QPainterPath:
        """Odd-even path of the outer ring plus every hole (§2.2): the one
        geometry source for paint, shape, the HALO trace, sprinkler detection
        and :meth:`contains_point`."""
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        if len(self._boundary) < 3:
            return path
        for ring in [self._boundary] + self._holes:
            path.addPolygon(QPolygonF(ring))
            path.closeSubpath()
        return path

    def contains_point(self, pt: QPointF) -> bool:
        """True when *pt* is inside the outer ring and in no hole (§2.2)."""
        if len(self._boundary) < 3:
            return False
        if not QPolygonF(self._boundary).containsPoint(pt, Qt.FillRule.OddEvenFill):
            return False
        return not any(QPolygonF(h).containsPoint(pt, Qt.FillRule.OddEvenFill)
                       for h in self._holes)

    def sample_point(self) -> QPointF | None:
        """Interior sample point (Gap 3): the first outer-edge midpoint pushed
        ``ROOM_SAMPLE_INSET_MM`` into the net area; None for a degenerate room."""
        from .room_detection import edge_sample
        return edge_sample(self._boundary, self.contains_point)

    def _inside_point(self, mean: QPointF) -> QPointF:
        """D-R3 fallback anchor: the midpoint of the widest inside interval of
        the horizontal line through *mean* (crossings with the outer ring and
        every hole, sorted and paired; the first interval wins a tie); with no
        interval, :meth:`sample_point`; else *mean*."""
        y = mean.y()
        xs: list[float] = []
        for ring in [self._boundary] + self._holes:
            n = len(ring)
            for i in range(n):
                a, b = ring[i], ring[(i + 1) % n]
                if (a.y() > y) != (b.y() > y):
                    xs.append(a.x() + (y - a.y()) * (b.x() - a.x()) / (b.y() - a.y()))
        xs.sort()
        best = None
        for i in range(0, len(xs) - 1, 2):
            width = xs[i + 1] - xs[i]
            if width > 0.0 and (best is None or width > best[0]):
                best = (width, (xs[i] + xs[i + 1]) / 2.0)
        if best is not None:
            return QPointF(best[1], y)
        s = self.sample_point()
        return s if s is not None else mean

    # ── Area / perimeter calculations ────────────────────────────────────

    def _compute_area_mm2(self) -> float:
        """Net area (§2.3): |outer| minus every hole (shoelace; scene units squared)."""
        pts = self._boundary
        if len(pts) < 3:
            return 0.0
        return max(0.0, abs(signed_area(pts)) - sum(abs(signed_area(h)) for h in self._holes))

    def _compute_perimeter_mm(self) -> float:
        """Outer ring plus every hole ring (D-R2; scene units)."""
        pts = self._boundary
        if len(pts) < 2:
            return 0.0
        total = _ring_length(pts)
        return total + sum(_ring_length(h) for h in self._holes)

    def _ceiling_height_mm(self) -> float:
        """Compute ceiling height from level elevations, accounting for
        the floor slab thickness at the ceiling level."""
        sc = self.scene()
        lm = getattr(sc, "_level_manager", None) if sc else None
        if lm is None:
            return 0.0
        floor_lvl = lm.get(self.level)
        ceil_lvl = lm.get(self._ceiling_level)
        if floor_lvl is None or ceil_lvl is None:
            return 0.0
        # Find the thickest floor slab on the ceiling level
        slab_thickness = 0.0
        for slab in getattr(sc, "_floor_slabs", []):
            if getattr(slab, "level", None) == self._ceiling_level:
                slab_thickness = max(slab_thickness, slab._thickness_mm)
        return ceil_lvl.elevation - floor_lvl.elevation - slab_thickness + self._ceiling_offset

    # ── Sprinkler detection ──────────────────────────────────────────────

    def _detect_sprinklers(self) -> list:
        """Return sprinklers assigned to this room.

        First checks for nodes explicitly tagged with this room's name
        (set by auto-populate).  Falls back to XY + Z-range detection
        for manually placed sprinklers.
        """
        sc = self.scene()
        if sc is None or not hasattr(sc, "sprinkler_system"):
            return []

        my_name = self.name
        tagged = []
        untagged_nodes = []

        for node in sc.sprinkler_system.nodes:
            if not node.has_sprinkler():
                continue
            room_tag = getattr(node, "_room_name", "")
            if room_tag and room_tag == my_name:
                tagged.append(node.sprinkler)
            elif not room_tag:
                untagged_nodes.append(node)

        # For untagged nodes, fall back to XY polygon + Z range check
        if untagged_nodes and len(self._boundary) >= 3:
            path = self.room_path()                    # holes excluded (§2.2)

            zr =self.z_range_mm()
            if zr is not None:
                z_bot, z_top = min(zr), max(zr)
            else:
                z_bot, z_top = None, None

            for node in untagged_nodes:
                if not path.contains(node.scenePos()):
                    continue
                if z_bot is not None:
                    z = getattr(node, "z_pos", None)
                    if z is not None and (z < z_bot or z > z_top):
                        continue
                tagged.append(node.sprinkler)

        return tagged

    def _nfpa_max_coverage_sqft(self) -> float:
        """Max coverage per sprinkler (sq ft) for the current hazard class."""
        return _NFPA_MAX_COVERAGE_SQFT.get(self._hazard_class, 130.0)

    def design_point(self) -> tuple[float, float] | None:
        """Selected design point (area_sqft, density); defaults to the
        hazard curve's minimum-area point. None for storage hazards
        (no density/area curve — criteria are a planned follow-up)."""
        if self._design_point is not None:
            return self._design_point
        return min_design_point(self._hazard_class)

    # ── Formatting helpers ───────────────────────────────────────────────

    def _fmt_area(self, mm2: float) -> str:
        """Format area for display (ScaleManager.format_area_mm2)."""
        sm = self._get_scale_manager()
        if sm is None:
            return f"{mm2:.0f} mm²"
        return sm.format_area_mm2(mm2)

    def _fmt_volume(self, mm3: float) -> str:
        """Format a volume for display (ScaleManager.format_volume_mm3)."""
        sm = self._get_scale_manager()
        if sm is None:
            return f"{mm3:.0f} mm³"
        return sm.format_volume_mm3(mm3)

    # ── Geometry ──────────────────────────────────────────────────────────

    def boundingRect(self):
        """Include the polygon AND all child items (label, background).

        Without this override, the inherited QGraphicsPolygonItem bounding
        rect only covers the polygon.  When the label child extends beyond
        the polygon, Qt's BSP can incorrectly cull the polygon fill once
        the label scrolls off screen.
        """
        br = super().boundingRect()
        return br.united(self.childrenBoundingRect())

    # NOTE: hole-less rooms keep the inherited QGraphicsPolygonItem.shape()
    # (the full polygon) -- a shape restricted to the label once made the fill
    # vanish when the label scrolled off-screen. A room with holes returns
    # room_path() (D-R4): the hole is not the room for picking, so a click in
    # it falls through to whatever sits there (the inner room).
    def shape(self) -> QPainterPath:
        """Inherited polygon shape, or the odd-even room path when holed (D-R4)."""
        if not self._holes:  # D-R4: hole-less rooms keep the inherited shape
            return super().shape()
        return self.room_path()

    # ── Paint ────────────────────────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected

        dc = self._display_color            # None = unset; "" = No stroke
        line_col = resolve_colour(self._color.name() if dc is None else dc,
                                  item=self)

        painter.setPen(self._outline_pen(line_col, style=Qt.PenStyle.DashLine))
        # In paper viewports rooms render as boundary + tag only — no fill
        # (_paper_no_fill set by paper_display.apply_paper_overrides). On the
        # model canvas the fill stays (opaque under _paper_fill_opaque, else
        # the model alpha-50 wash).
        dfc = self._display_fill_color
        if getattr(self, "_paper_no_fill", False) or dfc == "":
            painter.setBrush(Qt.BrushStyle.NoBrush)     # "" = No Fill
        else:
            fill_col = resolve_colour(self._color.name() if dfc is None else dfc,
                                      item=self)
            if not getattr(self, "_paper_fill_opaque", False):
                fill_col.setAlpha(50)
            painter.setBrush(QBrush(fill_col))
        path = self.room_path()
        painter.drawPath(path)                        # fill + dashed outline

        # Selection highlight
        if shows_selection(self):
            sel_pen = QPen(QColor("red"), 2)
            sel_pen.setCosmetic(True)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)                    # selection outline: outer + hole rings

    # ── Properties API ───────────────────────────────────────────────────

    def get_properties(self) -> dict:
        area_mm2 = self._compute_area_mm2()
        perim_mm = self._compute_perimeter_mm()
        ceil_h = self._ceiling_height_mm()
        vol_mm3 = area_mm2 * ceil_h if ceil_h > 0 else 0.0

        sprinklers = self._detect_sprinklers()
        spr_count = len(sprinklers)

        # Coverage per sprinkler in sq ft
        area_sqft = area_mm2 / (304.8 ** 2)
        cov_per_spr = area_sqft / spr_count if spr_count > 0 else 0.0
        max_cov = self._nfpa_max_coverage_sqft()
        status = "Pass" if (spr_count > 0 and cov_per_spr <= max_cov) else "Fail"

        dp = self.design_point()
        if dp:
            # Shared unit convention (imperial "sq ft" / metric m² + mm/min)
            from .scale_manager import format_area_sqft, format_density
            sm = self._get_scale_manager()
            dp_face = (f"{format_area_sqft(dp[0], sm)} @ "
                       f"{format_density(dp[1], sm)}")
        else:
            dp_face = "N/A — storage criteria (follow-up)"

        return {
            "Room Info":         {"type": "header"},
            "Type":              {"type": "label",     "value": "Room"},
            "Room Name":         {"type": "string",    "value": self.name},
            "Mark":              {"type": "string",    "value": self._mark},
            phase_registry.ROW_KEY: phase_registry.property_row(self),
            "Show Label":       {"type": "enum",      "value": "True" if self._show_label else "False",
                                  "options": ["True", "False"]},
            "Tag":               self._tag_row(),      # SB3b: per-room tag block (None = project default)
            # No "Fill Color" row — the Display Manager owns room
            # appearance.  set_property("Fill Color") stays for back-compat.
            "Geometry":          {"type": "header"},
            "Area":              {"type": "label",     "value": self._fmt_area(area_mm2)},
            "Perimeter":         {"type": "label",     "value": self._fmt(perim_mm)},
            "Floor Level":       {"type": "level_ref", "value": self.level},
            "Ceiling Level":     {"type": "level_ref", "value": self._ceiling_level},
            "Ceiling Offset":    {"type": "dimension", "value_mm": self._ceiling_offset},
            "Ceiling Height":    {"type": "label",     "value": self._fmt(ceil_h)},
            "Volume":            {"type": "label",     "value": self._fmt_volume(vol_mm3)},
            "Protection Criteria": {"type": "header"},
            "Hazard Class":      {"type": "enum",      "value": self._hazard_class,
                                  "options": HAZARD_CLASSES},
            "Occupancy":         {"type": "string",    "value": self._occupancy},
            "System Type":       {"type": "enum",      "value": self._system_type,
                                  "options": ["Wet", "Dry"]},
            "Design Point":      {"type": "button",    "value": dp_face,
                                  "callback": self._pick_design_point},
            "Compartment Type":  {"type": "enum",      "value": self._compartment_type,
                                  "options": COMPARTMENT_TYPES},
            "Ceiling Type":      {"type": "enum",      "value": self._ceiling_type,
                                  "options": CEILING_TYPES},
            "Sprinkler Count":   {"type": "label",     "value": str(spr_count)},
            "Coverage/Sprinkler": {"type": "label",    "value": f"{cov_per_spr:.1f} sq ft"},
            "Max Coverage":      {"type": "label",     "value": f"{max_cov:.0f} sq ft"},
            "Coverage Status":   {"type": "label",     "value": status},
        }

    def _pick_design_point(self):
        """Open the curve picker (Design Point button in the panel)."""
        if self._hazard_class in STORAGE_HAZARDS:
            return  # no density/area curve — button face already reads N/A
        from .design_point_dialog import DesignPointDialog
        dlg = DesignPointDialog(self._hazard_class, self.design_point())
        if dlg.exec():
            pt = dlg.selected_point()
            if pt:
                self._design_point = pt
                sc = self.scene()
                if sc is not None and hasattr(sc, "sceneModified"):
                    sc.sceneModified.emit()

    def _tag_changed(self) -> None:
        """Re-shape the room tag after its mapping changed."""
        self._tag.refresh()

    def set_property(self, key: str, value):
        if key == "Room Name":
            self.name = str(value)
            self._tag.refresh()       # pull-on-paint; the ops cache keys on the resolved strings
        elif key == "Mark":
            self._mark = str(value)
            self._tag.refresh()
        elif key == phase_registry.ROW_KEY:
            phase_registry.set_from_row(self, value)
        elif key == "Show Label":
            self._show_label = (str(value) == "True")
            self._update_label()
        elif key == "Tag":
            self._set_tag(str(value))
        elif key == "Floor Level":
            self.level = str(value)
        elif key == "Ceiling Level":
            self._ceiling_level = str(value)
        elif key == "Ceiling Offset":
            try:
                self._ceiling_offset = float(value)
            except (ValueError, TypeError):
                pass
        elif key == "Hazard Class":
            if str(value) in HAZARD_CLASSES and str(value) != self._hazard_class:
                self._hazard_class = str(value)
                # The design point lives on a hazard's density/area curve —
                # switching curves invalidates it.
                self._design_point = None
        elif key == "Occupancy":
            self._occupancy = str(value)
        elif key == "System Type":
            if str(value) in ("Wet", "Dry"):
                self._system_type = str(value)
        elif key == "Compartment Type":
            if str(value) in COMPARTMENT_TYPES:
                self._compartment_type = str(value)
        elif key == "Ceiling Type":
            if str(value) in CEILING_TYPES:
                self._ceiling_type = str(value)
        elif key == "Fill Color":
            self._color = QColor(value)
            self.update()

    # ── Grip points (label-only) ─────────────────────────────────────────
    # NOTE: grip_points / apply_grip defined earlier handle label dragging.
    # Room boundary vertices are NOT exposed as grips.

    def translate(self, dx: float, dy: float):
        self._boundary = [QPointF(p.x() + dx, p.y() + dy) for p in self._boundary]
        self._holes = [[QPointF(p.x() + dx, p.y() + dy) for p in h] for h in self._holes]
        self._rebuild()

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        """Baked rigid rotate of the room boundary about ``pivot`` (Y-up CCW+).

        Mirrors :meth:`translate`; rotates every boundary vertex then rebuilds."""
        from .cad_math import CAD_Math
        self._boundary = [CAD_Math.rotate_point(p, pivot, -angle_deg)
                          for p in self._boundary]
        self._holes = [[CAD_Math.rotate_point(p, pivot, -angle_deg) for p in h] for h in self._holes]
        self._rebuild()

    # ── Serialization ────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = {
            "type":             "room",
            "boundary":         [[p.x(), p.y()] for p in self._boundary],
            "color":            self._color.name(),
            "name":             self.name,
            "mark":             self._mark,
            "show_label":       self._show_label,
            "level":            self.level,
            "ceiling_level":    self._ceiling_level,
            "ceiling_offset":   self._ceiling_offset,
            "hazard_class":     self._hazard_class,
            "occupancy":        self._occupancy,
            "system_type":      self._system_type,
            "design_point":     list(self._design_point) if self._design_point else None,
            "compartment_type": self._compartment_type,
            "ceiling_type":     self._ceiling_type,
            "label_offset":     [self._label_offset.x(), self._label_offset.y()],
        }
        if self._holes:                                   # sparse key (§2.6)
            d["holes"] = [[[p.x(), p.y()] for p in h] for h in self._holes]
        if self._tag_block is not None:
            d["tag_block"] = self._tag_block          # SB3b: absent = project default
        phase_registry.write_element(self, d)
        return self.display_overrides_to_dict(d)       # L283

    @classmethod
    def from_dict(cls, data: dict) -> "Room":
        pts = [QPointF(p[0], p[1]) for p in data.get("boundary", [])]
        holes = [[QPointF(p[0], p[1]) for p in h] for h in data.get("holes", [])]
        room = cls(boundary=pts, color=data.get("color", "#4488cc"), holes=holes)
        room.name = data.get("name", "")
        room._mark = data.get("mark", data.get("tag", ""))
        room._show_label = data.get("show_label", True)
        room.level = data.get("level", DEFAULT_LEVEL)
        room._ceiling_level = data.get("ceiling_level", "Level 2")
        room._ceiling_offset = float(data.get("ceiling_offset", 0.0))
        room._hazard_class = data.get("hazard_class", "Light Hazard")
        room._compartment_type = data.get("compartment_type", "Room")
        room._ceiling_type = data.get("ceiling_type", "Noncombustible unobstructed")
        lo = data.get("label_offset", [0, 0])
        room._label_offset = QPointF(lo[0], lo[1])
        room._occupancy = data.get("occupancy", "")
        room._system_type = data.get("system_type", "Wet")
        dp = data.get("design_point")
        room._design_point = (float(dp[0]), float(dp[1])) if dp else None
        tb = data.get("tag_block")                     # SB3b: missing / non-str / "" -> None
        room._tag_block = tb if isinstance(tb, str) and tb else None
        phase_registry.read_element(room, data)
        room._rebuild()  # rebuild polygon + label now that name/tag are set
        room.display_overrides_from_dict(data)         # L283: after the rebuild
        return room
