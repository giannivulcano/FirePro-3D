"""
wall_opening.py
===============
First-class, wall-hosted Opening entity (door / window / blank) for FirePro 3D.

An opening is parameterised by a FeatureDef (from ``feature.py``) and placed
on a host WallSegment via a local reference frame:

* ``_offset_along``  — distance from host pt1 to opening centre, scene units;
                       clamped to [0, wall_length] on reposition.
* ``cross_offset_mm``— signed cross-wall displacement (mm); stored as the
                       user's typed value; NOT clamped (user can go off-wall).
* ``alignment``      — preset cross-wall alignment (Centered / Flush-front /
                       Flush-back); shifts the effective cross position without
                       overwriting the typed ``cross_offset_mm``.
* ``mirror_hinge``   — flip the door leaf / hinge side (along-wall axis).
* ``mirror_facing``  — flip which wall face is "front" — negates the effective
                       cross displacement (proud-stays-proud invariant: a
                       positive cross_offset_mm always means "toward the current
                       front face").

See docs/specs/wall-room-floor-system.md §7.4 / §7.5 / §7.7 / §7.9.

Backward-compat aliases ``DoorOpening`` and ``WindowOpening`` are provided at
the bottom so existing import sites in model_space.py / model_browser.py /
scene_io.py continue to resolve without change.  They will be reworked in later
tasks once all call sites are updated.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QGraphicsPathItem, QStyle, QGraphicsItem
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPen, QColor, QPainterPath, QPainterPathStroker

from .displayable_item import DisplayableItemMixin
from .constants import (
    DEFAULT_LEVEL, Z_CAT_OPENING,
    OPENING_ALIGN_CENTER, OPENING_ALIGN_FRONT, OPENING_ALIGN_BACK,
    OPENING_ALIGNMENTS,
)
from .feature import FEATURE_REGISTRY, get_feature, nearest_feature_for

if TYPE_CHECKING:
    from .wall import WallSegment

_SELECTION_COLOR = QColor("red")
_DOOR_COLOR = QColor("#aa6633")
_WINDOW_COLOR = QColor("#3399cc")

# A door/window FRAME is a fixed real-world object — its depth does NOT stretch
# with the host wall (only the opening CUT through the wall matches wall depth).
# Frame jamb depth is a fixed value, clamped to the wall when the wall is thinner.
_FRAME_DEPTH_MM = 114.3   # ~4.5" standard jamb depth


# ── Preset libraries (legacy — kept for backward compat with from_dict) ───────

DOOR_PRESETS = {
    "820×2040":  (820,  2040),
    "920×2040":  (920,  2040),
    "1200×2040": (1200, 2040),
    "1800×2040": (1800, 2040),
}
DOOR_DEFAULT = "920×2040"

WINDOW_PRESETS = {
    "600×600":   (600,  600),
    "900×1200":  (900,  1200),
    "1200×1500": (1200, 1500),
    "1800×1200": (1800, 1200),
}
WINDOW_DEFAULT = "900×1200"


def _scene_hit_width(item) -> float:
    sc = item.scene()
    if sc:
        views = sc.views()
        if views:
            scale = views[0].transform().m11()
            return max(4.0, 12.0 / max(scale, 1e-6))
    return 6.0


# ── WallOpening ───────────────────────────────────────────────────────────────

class WallOpening(DisplayableItemMixin, QGraphicsPathItem):
    """First-class, wall-hosted Opening parameterised by a FeatureDef.

    A single class handles all opening types ("door" | "window" | "blank");
    the FeatureDef supplies type-specific defaults.  Rendering (``_rebuild_path``
    / ``_paint_symbol``) is stubbed — later tasks implement the 2D symbols.

    Args:
        wall:       Host WallSegment, or ``None`` for a detached opening.
        feature_id: Key into ``FEATURE_REGISTRY`` (default "door_914").
        offset_along: Distance (scene units) from host ``pt1`` to opening centre.
        width_mm:   Override feature default width (mm), or ``None`` to use default.
        height_mm:  Override feature default height (mm), or ``None`` to use default.
        sill_mm:    Override feature default sill height (mm), or ``None`` to use
                    default.
    """

    KIND = "opening"   # matches legacy test checks; used by to_dict

    def __init__(self, wall=None, *, feature_id: str = "door_914",
                 offset_along: float = 0.0,
                 width_mm=None, height_mm=None, sill_mm=None,
                 # Legacy kwargs accepted but ignored — kept so old call sites
                 # like DoorOpening(wall=w, offset_along=x) still work through
                 # the alias without TypeError.
                 preset=None,
                 **_legacy):
        QGraphicsPathItem.__init__(self)
        self.init_displayable(level=DEFAULT_LEVEL)

        # ── Feature resolution ────────────────────────────────────────────────
        fdef = FEATURE_REGISTRY.get(feature_id) or get_feature("door_914")
        self.feature_id: str = fdef.id
        self._type: str = fdef.type
        self._leaves: int = fdef.leaves

        # ── Dimensional overrides ─────────────────────────────────────────────
        self._width_mm: float = float(width_mm if width_mm is not None
                                      else fdef.default_width_mm)
        self._height_mm: float = float(height_mm if height_mm is not None
                                       else fdef.default_height_mm)
        self._sill_mm: float = float(sill_mm if sill_mm is not None
                                     else fdef.default_sill_mm)

        # ── Placement frame ───────────────────────────────────────────────────
        self._wall = wall
        self._offset_along: float = float(offset_along)

        # Cross-wall offset (mm) — the user's typed value; never clamped.
        self.cross_offset_mm: float = 0.0
        # Alignment preset: shifts effective cross position without mutating
        # cross_offset_mm.
        self.alignment: str = OPENING_ALIGN_CENTER
        # Mirror flags
        self.mirror_hinge: bool = False    # flip leaf/hinge side (along-wall)
        self.mirror_facing: bool = False   # flip front/back face (cross-wall)

        # ── Qt item setup ─────────────────────────────────────────────────────
        self.setZValue(Z_CAT_OPENING)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        if wall is not None:
            self._reposition()

    # ── Host wall ─────────────────────────────────────────────────────────────

    @property
    def wall(self):
        return self._wall

    @wall.setter
    def wall(self, w):
        self._wall = w
        if w is not None:
            self._reposition()

    # ── Dimensional properties (with public setters for tests) ────────────────

    @property
    def width_mm(self) -> float:
        return self._width_mm

    @width_mm.setter
    def width_mm(self, v: float):
        self._width_mm = float(v)

    @property
    def height_mm(self) -> float:
        return self._height_mm

    @height_mm.setter
    def height_mm(self, v: float):
        self._height_mm = float(v)

    @property
    def sill_mm(self) -> float:
        return self._sill_mm

    @sill_mm.setter
    def sill_mm(self, v: float):
        self._sill_mm = float(v)

    @property
    def openings_type(self) -> str:
        """Opening type string: "door" | "window" | "blank"."""
        return self._type

    # ── Feature switching (template + placement) ─────────────────────────────

    def apply_feature(self, feature_id: str) -> None:
        """Switch this opening to *feature_id*, resetting dims to its defaults.

        Sets ``feature_id`` / ``_type`` / ``_leaves`` from ``FEATURE_REGISTRY``
        and resets ``_width_mm`` / ``_height_mm`` / ``_sill_mm`` to that
        feature's defaults.  Used when the ribbon button, Feature Browser, or the
        panel's "Feature" enum selects a different feature on the placement
        template.  Unknown ids fall back to ``door_914``.

        Args:
            feature_id: Key into ``FEATURE_REGISTRY``.
        """
        fdef = FEATURE_REGISTRY.get(feature_id) or get_feature("door_914")
        self.feature_id = fdef.id
        self._type = fdef.type
        self._leaves = fdef.leaves
        self._width_mm = float(fdef.default_width_mm)
        self._height_mm = float(fdef.default_height_mm)
        self._sill_mm = float(fdef.default_sill_mm)
        if self._wall is not None:
            self._reposition()

    def _features_for_category(self) -> list["FeatureDef"]:
        """FeatureDefs sharing this opening's category, for the panel enum."""
        cur = FEATURE_REGISTRY.get(self.feature_id)
        category = cur.category if cur is not None else "Openings"
        return [f for f in FEATURE_REGISTRY.values() if f.category == category]

    # ── Scene/unit helpers ────────────────────────────────────────────────────

    def _mm_to_scene(self, mm: float) -> float:
        """Convert mm to scene units using the attached scene's ScaleManager."""
        sc = self._wall.scene() if self._wall is not None else self.scene()
        if sc and hasattr(sc, "scale_manager"):
            sm = sc.scale_manager
            if sm.drawing_scale > 0:
                return sm.paper_to_scene(mm / sm.drawing_scale)
        return mm * 0.15  # fallback: 1 scene-unit ≈ 0.15 mm

    def width_scene(self) -> float:
        """Opening width in scene units."""
        return self._mm_to_scene(self._width_mm)

    def _half_thickness_mm(self) -> float:
        """Half the host wall thickness (mm)."""
        if self._wall is not None:
            return self._wall._thickness_mm / 2.0
        return 0.0

    # ── Cross-wall displacement (the "proud-stays-proud" math) ───────────────

    def _cross_offset_effective_mm(self) -> float:
        """Compute the signed cross-wall displacement (mm) for the current
        alignment preset, then apply the facing mirror.

        The user's typed ``cross_offset_mm`` is the base value.  The alignment
        preset adds or subtracts half the wall thickness so the opening sits:
        * Centered  — on the wall centreline (no shift).
        * Flush-front — shifted toward the +normal face by half thickness.
        * Flush-back  — shifted toward the -normal face by half thickness.

        ``mirror_facing`` negates the result so the opening flips sides while
        the typed offset magnitude is preserved (proud-stays-proud).
        """
        base = self.cross_offset_mm
        if self.alignment == OPENING_ALIGN_FRONT:
            base += self._half_thickness_mm()
        elif self.alignment == OPENING_ALIGN_BACK:
            base -= self._half_thickness_mm()
        # Centered: no extra shift
        return -base if self.mirror_facing else base

    # ── Geometry ──────────────────────────────────────────────────────────────

    def center_on_wall(self) -> QPointF:
        """World position of the opening centre (along + cross of host wall)."""
        if self._wall is None:
            return QPointF(0, 0)
        a = self._wall.centerline_angle_rad()
        nx, ny = self._wall.normal()   # unit normal (tuple[float, float])
        # Along-wall component (scene units)
        along = QPointF(
            self._wall.pt1.x() + self._offset_along * math.cos(a),
            self._wall.pt1.y() + self._offset_along * math.sin(a),
        )
        # Cross-wall component (convert mm → scene units)
        cross_scene = self._mm_to_scene(self._cross_offset_effective_mm())
        return QPointF(along.x() + nx * cross_scene,
                       along.y() + ny * cross_scene)

    def _reposition(self):
        """Clamp along-wall offset and sync the Qt item position."""
        if self._wall is None:
            return
        length = self._wall.centerline_length()
        self._offset_along = max(0.0, min(self._offset_along, length))
        self.setPos(self.center_on_wall())
        self._rebuild_path()

    def _rebuild_path(self):
        """Build the plan-view schematic path for this opening type.

        Local coordinates have the wall running along +X.  The wall gap rect
        spans (-half_w … +half_w) along X and (-ht … +ht) along Y.

        Door:
            Hinge pivot is at x = -half_w (mirror_hinge=False) or +half_w
            (mirror_hinge=True).  The swing arc extends to side sy=-1 (toward
            +Y, i.e. top of screen) when mirror_facing=False, or sy=+1 (toward
            -Y) when mirror_facing=True.  The opened leaf goes perpendicular to
            the wall by full opening width.  For double-leaf (self._leaves==2),
            two symmetric half-width leaf+arc pairs are drawn.

        Window:
            Gap rect + three parallel horizontal lines spanning the gap at
            y = -ht*0.5, 0, +ht*0.5.

        Blank:
            Gap rect only — no swing or extra lines.
        """
        if self._wall is None:
            self.setPath(QPainterPath())
            return

        # Set rotation so local X aligns with the wall direction.
        a = self._wall.centerline_angle_rad()
        self.setRotation(math.degrees(a))

        half_w = self.width_scene() / 2.0
        ht = self._wall.half_thickness_scene()

        if self._type == "door":
            path = self._door_path(half_w, ht)
        elif self._type == "window":
            path = self._window_path(half_w, ht)
        else:
            path = self._blank_path(half_w, ht)

        self.setPath(path)

    # ── Path builders ─────────────────────────────────────────────────────────

    @staticmethod
    def _gap_rect(half_w: float, ht: float) -> QPainterPath:
        """Return a QPainterPath containing only the wall gap rectangle."""
        path = QPainterPath()
        path.addRect(-half_w, -ht, half_w * 2.0, ht * 2.0)
        return path

    def _door_path(self, half_w: float, ht: float) -> QPainterPath:
        """Build door path: gap rect + leaf line(s) + swing arc(s).

        The hinge pivot jamb X is determined by mirror_hinge:
            mirror_hinge=False → hinge at x = -half_w (left jamb)
            mirror_hinge=True  → hinge at x = +half_w (right jamb)

        The swing side (which face the door swings toward) is determined by
        mirror_facing:
            mirror_facing=False → sy = -1 (arc extends toward -Y face in local
                                  coords, i.e. the wall's front face)
            mirror_facing=True  → sy = +1 (arc extends toward +Y face)

        For double-leaf (self._leaves == 2), two symmetric half-width
        leaf+arc pairs are drawn (one from each jamb, meeting at x=0).
        """
        path = self._gap_rect(half_w, ht)

        # Swing direction: -1 = toward -Y face, +1 = toward +Y face
        sy = 1.0 if self.mirror_facing else -1.0

        if self._leaves == 2:
            # Two half-width leaves: each closes from its jamb toward the centre
            # x=0, so each arc sweeps INWARD across its half of the opening.
            for hinge_x, outward_x_sign in ((-half_w, 1.0), (half_w, -1.0)):
                self._add_leaf_and_arc(path, hinge_x, outward_x_sign, half_w, ht, sy)
        else:
            # Single leaf: the closed leaf lies along the wall from the hinge jamb
            # ACROSS the opening to the opposite jamb, so the arc sweeps toward
            # that opposite jamb (spanning the gap), not away from it.
            hinge_x = half_w if self.mirror_hinge else -half_w
            # outward_x_sign points from the hinge toward the opposite jamb:
            #   hinge on left (-half_w)  → sweep right (+1)
            #   hinge on right (+half_w) → sweep left  (-1)
            outward_x_sign = -1.0 if self.mirror_hinge else 1.0
            self._add_leaf_and_arc(path, hinge_x, outward_x_sign, 2.0 * half_w, ht, sy)

        return path

    @staticmethod
    def _add_leaf_and_arc(
        path: QPainterPath,
        hinge_x: float,
        outward_x_sign: float,
        leaf_len: float,
        ht: float,
        sy: float,
    ) -> None:
        """Add one door-leaf line + 90° swing arc to *path*.

        The hinge corner is at (hinge_x, sy*ht).  The open leaf goes
        perpendicular into the room (sy direction, length leaf_len).  The
        swing arc has radius = leaf_len, centred on the hinge corner, and
        sweeps 90° outward from the open-leaf position toward the wall
        (outward_x_sign direction), so it visually shows how far the door
        needs to clear.  The arc's outer end lies at distance leaf_len
        from the hinge in the wall-plane direction, which is OUTSIDE the
        gap rect when outward_x_sign != 0, making the two hinge positions
        produce different bounding rects.

        Args:
            hinge_x:        Local X of the hinge jamb (±half_w for the gap edges).
            outward_x_sign: +1 if the hinge is on the right (arc extends right),
                            -1 if hinge is on the left (arc extends left).
            leaf_len:       Leaf length in scene units (= full door width for single
                            leaf, half width per leaf for double).
            ht:             Half-thickness of the wall.
            sy:             Swing side: -1 = -Y face, +1 = +Y face.
        """
        from PyQt6.QtCore import QRectF as _QRectF

        # Hinge corner on the swing face of the wall
        hinge_y = sy * ht

        # Open leaf: perpendicular to wall from hinge into room (sy direction)
        open_tip_x = hinge_x
        open_tip_y = hinge_y + sy * leaf_len

        # Draw open-position leaf line
        path.moveTo(hinge_x, hinge_y)
        path.lineTo(open_tip_x, open_tip_y)

        # Arc: centred on hinge_x, hinge_y; radius = leaf_len.
        # The arc sweeps from the open leaf position (90° into room from wall)
        # to the along-wall outward direction, showing the clearance envelope.
        # The outward end of the arc lies at:
        #   (hinge_x + outward_x_sign * leaf_len, hinge_y)
        # which is OUTSIDE the gap rect by leaf_len in the outward direction,
        # producing an asymmetric bounding rect for the two hinge positions.
        rect = _QRectF(hinge_x - leaf_len, hinge_y - leaf_len,
                       leaf_len * 2.0, leaf_len * 2.0)

        # In Qt, arcTo angles are measured from +X axis, CCW positive.
        # Open tip is at angle: sy=-1 → 90° (up in Qt coords = -Y), sy=+1 → 270°
        open_angle_deg = 90.0 if sy < 0.0 else 270.0

        # Outward tip is at angle: outward_x_sign=+1 → 0°, outward_x_sign=-1 → 180°
        out_angle_deg = 0.0 if outward_x_sign > 0.0 else 180.0

        # Sweep from open position toward outward along-wall position.
        # Determine shortest signed sweep (CCW positive, CW negative).
        raw_sweep = out_angle_deg - open_angle_deg
        # Normalise to (-180, 180] — we always want a 90° or -90° sweep.
        if raw_sweep > 180.0:
            raw_sweep -= 360.0
        elif raw_sweep < -180.0:
            raw_sweep += 360.0

        path.arcMoveTo(rect, open_angle_deg)
        path.arcTo(rect, open_angle_deg, raw_sweep)

    def _window_path(self, half_w: float, ht: float) -> QPainterPath:
        """Gap rect + three horizontal glass lines spanning the opening."""
        path = self._gap_rect(half_w, ht)
        for frac in (-0.5, 0.0, 0.5):
            y = ht * frac
            path.moveTo(-half_w, y)
            path.lineTo(half_w, y)
        return path

    def _blank_path(self, half_w: float, ht: float) -> QPainterPath:
        """Gap rect only."""
        return self._gap_rect(half_w, ht)

    # ── Z range ───────────────────────────────────────────────────────────────

    def z_range_mm(self) -> tuple[float, float] | None:
        """Return (z_bottom, z_top) in absolute mm from the assigned level.

        Returns ``None`` when no LevelManager is reachable or the level name
        is not registered.
        """
        # Prefer the wall's scene (opening may not be in the scene itself yet)
        sc = (self._wall.scene() if self._wall is not None else None) or self.scene()
        lm = getattr(sc, "_level_manager", None) if sc else None
        if lm is None:
            return None
        lvl = lm.get(self.level)
        if lvl is None:
            return None
        z_bot = lvl.elevation + self._sill_mm
        z_top = lvl.elevation + self._sill_mm + self._height_mm
        return (z_bot, z_top)

    def fits_within_wall(self) -> bool:
        """True when the opening's Z range lies within the host wall's Z range."""
        zr = self.z_range_mm()
        wr = self._wall.z_range_mm() if self._wall is not None else None
        if zr is None or wr is None:
            return True
        return wr[0] - 1e-6 <= zr[0] and zr[1] <= wr[1] + 1e-6

    # ── Move support (for grip/drag) ──────────────────────────────────────────

    def translate(self, dx: float, dy: float):
        """Shift the along-wall offset by the wall-projected component of (dx, dy)."""
        if self._wall is None:
            return
        a = self._wall.centerline_angle_rad()
        self._offset_along += dx * math.cos(a) + dy * math.sin(a)
        self._reposition()

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        self._paint_symbol(painter)
        if self.isSelected():
            pen = QPen(_SELECTION_COLOR, 2)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.path())

    def _paint_symbol(self, painter):
        """Draw the plan-view symbol for this opening type.

        Uses a cosmetic pen in the type's default colour (or ``_display_color``
        if one has been assigned).  The gap rect receives a white fill so the
        opening visually cuts through the wall.  The swing/glass lines are
        stroked on top.
        """
        path = self.path()
        if path.isEmpty():
            return

        # Resolve pen colour
        if self._display_color is not None:
            pen_color = QColor(self._display_color)
        elif self._type == "door":
            pen_color = _DOOR_COLOR
        elif self._type == "window":
            pen_color = _WINDOW_COLOR
        else:
            pen_color = QColor("#888888")

        # Fill the gap with the correct background colour:
        #   Paper/plot: _paper_gap_color is set by apply_paper_overrides → white,
        #               so the opening reads as a clean hole on white paper.
        #   Screen:     use the scene background (dark theme) so the gap blends
        #               with the canvas and the wall appears cut through.
        paper_gap = getattr(self, "_paper_gap_color", None)
        if paper_gap is not None:
            gap_bg = QColor(paper_gap)
        else:
            gap_bg = QColor("#2b2b2b")
            sc = self.scene()
            if sc is not None:
                brush = sc.backgroundBrush()
                if brush.style() != Qt.BrushStyle.NoBrush:
                    gap_bg = brush.color()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gap_bg)
        half_w = self.width_scene() / 2.0
        ht = self._wall.half_thickness_scene() if self._wall else 1.0
        from PyQt6.QtCore import QRectF as _QRectF
        painter.drawRect(_QRectF(-half_w, -ht, half_w * 2.0, ht * 2.0))

        # Stroke the full path (gap outline + swing / glass lines)
        pen = QPen(pen_color, 1.5)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    # ── Shape / hit-test ─────────────────────────────────────────────────────

    def shape(self) -> QPainterPath:
        path = self.path()
        if path.isEmpty():
            return path
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        return stroker.createStroke(path) | path

    # ── Serialisation (§7.11) ────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "feature_id":      self.feature_id,
            "type":            self._type,
            "width_mm":        self._width_mm,
            "height_mm":       self._height_mm,
            "sill_mm":         self._sill_mm,
            "offset_along":    self._offset_along,
            "cross_offset_mm": self.cross_offset_mm,
            "alignment":       self.alignment,
            "mirror_hinge":    self.mirror_hinge,
            "mirror_facing":   self.mirror_facing,
            "level":           self.level,
        }

    @classmethod
    def from_dict(cls, data: dict, wall=None) -> "WallOpening":
        """Reconstruct from a saved dict.

        Supports two dict shapes:

        * **New format** (§7.11) — has ``"feature_id"`` key; all placement
          fields present.
        * **Legacy format** — has ``"kind"`` key (``"door"`` / ``"window"`` /
          ``"blank"``); ``cross_offset_mm``, ``alignment``, and ``mirror_*``
          absent; migrated by resolving the nearest Feature for the given width.
        """
        # ── Feature resolution ────────────────────────────────────────────────
        if "feature_id" in data:
            feature_id = data["feature_id"]
        else:
            legacy_type = data.get("kind", "door")
            if legacy_type not in ("door", "window", "blank"):
                legacy_type = "door"
            feature_id = nearest_feature_for(
                legacy_type, float(data.get("width_mm", 914))
            )

        obj = cls(
            wall=wall,
            feature_id=feature_id,
            offset_along=float(data.get("offset_along", 0.0)),
            width_mm=float(data["width_mm"]) if "width_mm" in data else None,
            height_mm=float(data["height_mm"]) if "height_mm" in data else None,
            sill_mm=float(data["sill_mm"]) if "sill_mm" in data else None,
        )

        # ── Placement-frame fields (absent in legacy dicts → defaults) ────────
        obj.cross_offset_mm = float(data.get("cross_offset_mm", 0.0))
        obj.alignment = data.get("alignment", OPENING_ALIGN_CENTER)
        obj.mirror_hinge = bool(data.get("mirror_hinge", False))
        obj.mirror_facing = bool(data.get("mirror_facing", False))
        obj.level = data.get("level", DEFAULT_LEVEL)

        if wall is not None:
            obj._reposition()
        return obj

    # ── Property panel integration (§7.6 / §7.9 / §7.13) ────────────────────

    def get_properties(self) -> dict:
        """Return an ordered dict of property descriptors for the property panel.

        Keys and types match the property-panel protocol:
            - ``"label"``     — read-only text row.
            - ``"dimension"`` — DimensionEdit; ``set_property`` receives a mm float.
            - ``"enum"``      — QComboBox; ``set_property`` receives a str.
            - ``"bool"``      — QCheckBox; ``set_property`` receives a bool.
            - ``"level_ref"`` — level combo; ``set_property`` receives a level name str.
            - ``"warning"``   — warning box; only included when a warning exists.

        Returns:
            dict: Ordered mapping of property-key → descriptor dict.
        """
        is_template = self._wall is None
        props: dict = {}
        # As a pre-placement template (no host wall) the first row is an editable
        # "Feature" enum so the user can switch door/window/blank + size class
        # before placing.  On a placed opening the type is fixed, shown as a
        # read-only label.
        if is_template:
            cur = FEATURE_REGISTRY.get(self.feature_id)
            props["Feature"] = {
                "type": "enum",
                "value": cur.display_name if cur is not None else self.feature_id,
                "options": [f.display_name for f in self._features_for_category()],
            }
        else:
            props["Type"] = {"type": "label", "value": self._type.title()}
        props["Width"] = {"type": "dimension", "value_mm": self._width_mm}
        props["Height"] = {"type": "dimension", "value_mm": self._height_mm}
        props["Sill Height"] = {"type": "dimension", "value_mm": self._sill_mm}
        props["Alignment"] = {
            "type": "enum",
            "value": self.alignment,
            "options": list(OPENING_ALIGNMENTS),
        }
        props["Cross Offset"] = {"type": "dimension", "value_mm": self.cross_offset_mm}
        props["Hinge Flip"] = {"type": "bool", "value": self.mirror_hinge}
        props["Facing Flip"] = {"type": "bool", "value": self.mirror_facing}
        # Level + fit warning need a wall context; drop them on the template.
        if not is_template:
            props["Level"] = {"type": "level_ref", "value": self.level}
            if not self.fits_within_wall():
                props["Fit Warning"] = {
                    "type": "warning",
                    "value": "Opening extends beyond the host wall's vertical extent.",
                }
        return props

    # ── 3D geometry (§7.8.3) ─────────────────────────────────────────────────

    def get_3d_meshes(self, level_manager=None) -> list[dict]:
        """Return a list of mesh dicts for the 3D view (frame + leaf/pane).

        Each dict has:
            ``{"vertices": [[x,y,z],...], "faces": [[i,j,k],...], "color": (r,g,b,a)}``

        Returns an empty list for blank openings (no 3D geometry) or when the
        host wall or scene is unavailable.

        The coordinate convention matches ``WallSegment.get_3d_mesh``:
        * Scene X → world X via ``scale_manager.scene_to_real``
        * Scene Y → world Y via ``-scale_manager.scene_to_real`` (Y negated)
        * Z = ``level.elevation + sill_mm`` (bottom) / ``+ height_mm`` (top)

        Args:
            level_manager: Optional LevelManager for elevation lookup.

        Returns:
            List of mesh dicts; empty for blank type.
        """
        if self._type == "blank":
            return []
        if self._wall is None:
            return []

        # ── Scale helper (mirrors wall.get_3d_mesh to_mm) ────────────────────
        sc = self._wall.scene() if self._wall is not None else self.scene()
        sm = sc.scale_manager if sc and hasattr(sc, "scale_manager") else None

        def scene_to_real(v: float) -> float:
            if sm and sm.is_calibrated and sm.drawing_scale > 0:
                return sm.scene_to_real(v)
            return v

        # ── Elevations ────────────────────────────────────────────────────────
        base_z = 0.0
        if level_manager is not None:
            lvl = level_manager.get(self.level)
            if lvl is not None:
                base_z = lvl.elevation
        z_bot = base_z + self._sill_mm
        z_top = z_bot + self._height_mm
        if z_top <= z_bot:
            return []

        # ── Opening centre in 3D world coords ────────────────────────────────
        cpt = self.center_on_wall()
        cx = scene_to_real(cpt.x())
        cy = -scene_to_real(cpt.y())   # Y-negate for 3D convention

        # ── Wall orientation vectors in 3D ────────────────────────────────────
        # Wall angle θ in scene coords.  Along-wall 3D = (cos θ, −sin θ).
        # Scene normal = (−sin θ, cos θ); 3D normal = (−sin θ, −cos θ).
        theta = self._wall.centerline_angle_rad()
        import math as _m
        ax = _m.cos(theta)          # along-wall, world-X component
        ay = -_m.sin(theta)         # along-wall, world-Y component (Y-negated)
        nx = -_m.sin(theta)         # normal, world-X component
        ny = -_m.cos(theta)         # normal, world-Y component (Y-negated)

        # ── Dimensions in mm ─────────────────────────────────────────────────
        half_w = self._width_mm / 2.0
        half_d = self._wall._thickness_mm / 2.0   # half wall-depth (the CUT depth)
        # Frame is a fixed-depth object (not parametric to the wall) — clamp only
        # so it never protrudes from a wall thinner than the standard frame.
        frame_half_d = min(half_d, _FRAME_DEPTH_MM / 2.0)
        frame_t = max(20.0, min(50.0, frame_half_d * 0.15))  # frame bar thickness
        leaf_t  = 40.0   # door leaf / window pane thickness in mm

        # ── Box helper ────────────────────────────────────────────────────────
        def _box(cx3, cy3, cz3, dw, dd, dh, color):
            """Axis-aligned box centred on (cx3,cy3,cz3) with half-extents dw×dd×dh."""
            verts = [
                [cx3 - dw, cy3 - dd, cz3 - dh],
                [cx3 + dw, cy3 - dd, cz3 - dh],
                [cx3 + dw, cy3 + dd, cz3 - dh],
                [cx3 - dw, cy3 + dd, cz3 - dh],
                [cx3 - dw, cy3 - dd, cz3 + dh],
                [cx3 + dw, cy3 - dd, cz3 + dh],
                [cx3 + dw, cy3 + dd, cz3 + dh],
                [cx3 - dw, cy3 + dd, cz3 + dh],
            ]
            faces = [
                [0, 1, 2], [0, 2, 3],   # bottom
                [4, 6, 5], [4, 7, 6],   # top
                [0, 1, 5], [0, 5, 4],   # front
                [1, 2, 6], [1, 6, 5],   # right
                [2, 3, 7], [2, 7, 6],   # back
                [3, 0, 4], [3, 4, 7],   # left
            ]
            return {"vertices": verts, "faces": faces, "color": color}

        # _oriented_box: places a box whose local-X is the wall along-axis,
        # local-Y is the wall normal, local-Z is world-Z.
        def _oriented_box(along_offset, normal_offset, z_center, dw, dd, dh, color):
            """Box whose X-axis = wall along, Y-axis = wall normal.

            Args:
                along_offset:  centre displacement along wall (mm), relative to
                               the opening centre projected onto the wall axis.
                normal_offset: centre displacement along wall normal (mm).
                z_center:      world-Z of the box centre.
                dw:            half-extent along wall axis.
                dd:            half-extent along normal axis.
                dh:            half-extent along Z.
                color:         (r, g, b, a) tuple.
            """
            # Centre in world
            bx = cx + along_offset * ax + normal_offset * nx
            by = cy + along_offset * ay + normal_offset * ny
            bz = z_center

            # 8 corners (±dw along wall, ±dd along normal, ±dh along Z)
            verts = []
            for sa in (-1, 1):
                for sn in (-1, 1):
                    for sz in (-1, 1):
                        verts.append([
                            bx + sa * dw * ax + sn * dd * nx,
                            by + sa * dw * ay + sn * dd * ny,
                            bz + sz * dh,
                        ])
            # Corner indices: [along_sign, normal_sign, z_sign] cycling
            # Order: (--−), (--+), (-+−), (-++), (+-−), (+-+), (++−), (+++)
            # which maps to indices 0..7 per the loop above.
            faces = [
                [0, 2, 4], [2, 6, 4],   # bottom (sz=−1 plane: 0,2,4,6)
                [1, 5, 3], [3, 5, 7],   # top    (sz=+1 plane: 1,3,5,7)
                [0, 1, 2], [1, 3, 2],   # left   (sa=−1 plane: 0,1,2,3)
                [4, 6, 5], [5, 6, 7],   # right  (sa=+1 plane: 4,5,6,7)
                [0, 4, 1], [1, 4, 5],   # front  (sn=−1 plane: 0,4,1,5)
                [2, 3, 6], [3, 7, 6],   # back   (sn=+1 plane: 2,3,6,7)
            ]
            return {"vertices": verts, "faces": faces, "color": color}

        meshes: list[dict] = []
        z_center = (z_bot + z_top) / 2.0
        half_h = (z_top - z_bot) / 2.0

        if self._type == "door":
            # Frame: four thin bars — left jamb, right jamb, head, sill-threshold
            frame_color = (0.55, 0.33, 0.14, 1.0)   # brown

            # Left jamb: at along = −half_w + frame_t/2
            meshes.append(_oriented_box(
                -half_w + frame_t / 2.0, 0.0, z_center,
                frame_t / 2.0, frame_half_d, half_h, frame_color,
            ))
            # Right jamb
            meshes.append(_oriented_box(
                half_w - frame_t / 2.0, 0.0, z_center,
                frame_t / 2.0, frame_half_d, half_h, frame_color,
            ))
            # Head (top bar)
            meshes.append(_oriented_box(
                0.0, 0.0, z_top - frame_t / 2.0,
                half_w, frame_half_d, frame_t / 2.0, frame_color,
            ))
            # Threshold (bottom bar)
            meshes.append(_oriented_box(
                0.0, 0.0, z_bot + frame_t / 2.0,
                half_w, frame_half_d, frame_t / 2.0, frame_color,
            ))

            # Closed leaf: thin slab filling inner aperture, slightly toward facing side
            leaf_normal_offset = (frame_half_d - leaf_t / 2.0) * (
                -1.0 if self.mirror_facing else 1.0
            )
            leaf_color = (0.67, 0.40, 0.18, 1.0)   # warm wood
            inner_half_w = half_w - frame_t
            inner_half_h = half_h - frame_t
            if inner_half_w > 0 and inner_half_h > 0:
                meshes.append(_oriented_box(
                    0.0, leaf_normal_offset, z_center,
                    inner_half_w, leaf_t / 2.0, inner_half_h, leaf_color,
                ))

        elif self._type == "window":
            # Frame: same four-bar approach
            frame_color = (0.75, 0.75, 0.75, 1.0)   # light grey

            meshes.append(_oriented_box(
                -half_w + frame_t / 2.0, 0.0, z_center,
                frame_t / 2.0, frame_half_d, half_h, frame_color,
            ))
            meshes.append(_oriented_box(
                half_w - frame_t / 2.0, 0.0, z_center,
                frame_t / 2.0, frame_half_d, half_h, frame_color,
            ))
            meshes.append(_oriented_box(
                0.0, 0.0, z_top - frame_t / 2.0,
                half_w, frame_half_d, frame_t / 2.0, frame_color,
            ))
            meshes.append(_oriented_box(
                0.0, 0.0, z_bot + frame_t / 2.0,
                half_w, frame_half_d, frame_t / 2.0, frame_color,
            ))

            # Glass pane: thin semi-transparent slab at wall centreline
            pane_color = (0.5, 0.75, 0.9, 0.35)   # translucent blue
            inner_half_w = half_w - frame_t
            inner_half_h = half_h - frame_t
            if inner_half_w > 0 and inner_half_h > 0:
                meshes.append(_oriented_box(
                    0.0, 0.0, z_center,
                    inner_half_w, leaf_t / 2.0, inner_half_h, pane_color,
                ))

        return meshes

    def set_property(self, key: str, value) -> None:
        """Apply a property mutation, update geometry, and snapshot undo.

        Args:
            key:   Property key as returned by ``get_properties()``.
            value: New value — mm float for dimension keys, str for enum/level_ref,
                   bool for bool keys.  Unknown keys are silently ignored.
        """
        if key == "Feature":
            # value is a display_name (or an id) from the panel enum → resolve
            # to a feature id and switch (resets dims to that feature's defaults).
            fid = str(value)
            if fid not in FEATURE_REGISTRY:
                match = next(
                    (f.id for f in FEATURE_REGISTRY.values()
                     if f.display_name == fid),
                    None,
                )
                fid = match or self.feature_id
            self.apply_feature(fid)
        elif key == "Width":
            self._width_mm = float(value)
        elif key == "Height":
            self._height_mm = float(value)
        elif key == "Sill Height":
            self._sill_mm = float(value)
        elif key == "Alignment":
            self.alignment = str(value)
        elif key == "Cross Offset":
            self.cross_offset_mm = float(value)
        elif key == "Hinge Flip":
            self.mirror_hinge = bool(value)
        elif key == "Facing Flip":
            self.mirror_facing = bool(value)
        elif key == "Level":
            self.level = str(value)
        else:
            return  # unknown key — no-op, no undo push

        self._reposition()
        sc = self.scene()
        if sc is not None and hasattr(sc, "push_undo_state"):
            sc.push_undo_state()


# ── Backward-compat aliases ───────────────────────────────────────────────────
# model_space.py, model_browser.py, scene_io.py and __init__.py import these by
# name.  They point to WallOpening so isinstance checks continue to work.
# Later tasks rework all call sites and remove these aliases.

Opening = WallOpening
DoorOpening = WallOpening
WindowOpening = WallOpening
