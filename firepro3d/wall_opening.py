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
            # Two half-width leaves: each with the full half_w as leaf radius.
            # Each leaf swings from its jamb toward the centre x=0.
            for hinge_x, outward_x_sign in ((-half_w, -1.0), (half_w, 1.0)):
                self._add_leaf_and_arc(path, hinge_x, outward_x_sign, half_w, ht, sy)
        else:
            # Single leaf
            hinge_x = half_w if self.mirror_hinge else -half_w
            # outward_x_sign: +1 = hinge on right → arc extends right;
            #                  -1 = hinge on left → arc extends left
            outward_x_sign = 1.0 if self.mirror_hinge else -1.0
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

        # White fill for the gap rect so the opening cuts the wall visually
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.GlobalColor.white)
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
        props: dict = {}
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
        props["Level"] = {"type": "level_ref", "value": self.level}
        if not self.fits_within_wall():
            props["Fit Warning"] = {
                "type": "warning",
                "value": "Opening extends beyond the host wall's vertical extent.",
            }
        return props

    def set_property(self, key: str, value) -> None:
        """Apply a property mutation, update geometry, and snapshot undo.

        Args:
            key:   Property key as returned by ``get_properties()``.
            value: New value — mm float for dimension keys, str for enum/level_ref,
                   bool for bool keys.  Unknown keys are silently ignored.
        """
        if key == "Width":
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
