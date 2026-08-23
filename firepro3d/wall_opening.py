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
        """Stub — rendering is implemented in a later task."""
        self.setPath(QPainterPath())

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
        """Stub — rendering is implemented in a later task."""
        pass

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

    # ── Legacy property accessors ─────────────────────────────────────────────

    def get_properties(self) -> dict:
        return {
            "Type":   {"type": "label",  "value": self._type.title()},
            "Width":  {"type": "string", "value": self._fmt(self._width_mm)},
            "Height": {"type": "string", "value": self._fmt(self._height_mm)},
        }

    def set_property(self, key: str, value):
        if key in ("Width", "Width (mm)"):
            try:
                self._width_mm = float(value)
            except (ValueError, TypeError):
                return
            self._reposition()
        elif key in ("Height", "Height (mm)"):
            try:
                self._height_mm = float(value)
            except (ValueError, TypeError):
                return


# ── Backward-compat aliases ───────────────────────────────────────────────────
# model_space.py, model_browser.py, scene_io.py and __init__.py import these by
# name.  They point to WallOpening so isinstance checks continue to work.
# Later tasks rework all call sites and remove these aliases.

Opening = WallOpening
DoorOpening = WallOpening
WindowOpening = WallOpening
