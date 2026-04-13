"""
level_manager.py
================
Floor-level system for multi-story building support.

Each drawing item carries a ``level`` string attribute naming the floor
level it belongs to.  Switching the active level hides entities on other
levels, with optional faded display for context.

Classes
-------
Level           — dataclass for one level's properties
LevelManager    — ordered list of levels + visibility application

The UI widget (LevelWidget) is in level_widget.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtCore import Qt


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

FADE_OPACITY = 0.25  # opacity for faded levels
CROSS_LEVEL_OPACITY = 0.50  # opacity for items from other levels shown via Z-range


def _apply_z_filter(item, view_height, view_depth):
    """Hide *item* if its Z-range is entirely outside the view range,
    and flag it as section-cut if it straddles *view_height*.
    """
    fn = getattr(item, "z_range_mm", None)
    if fn is None:
        return  # no Z data — keep current visibility
    zr = fn()
    if zr is None:
        return
    z_bot, z_top = zr
    if z_top < view_depth or z_bot > view_height:
        item.setVisible(False)
        return
    # Mark section-cut if element straddles the cut plane
    if hasattr(item, "_is_section_cut"):
        item._is_section_cut = (z_bot < view_height < z_top)


def _z_intersects(item, view_height, view_depth) -> bool:
    """Return True if *item* has a Z-range that overlaps [view_depth, view_height]."""
    fn = getattr(item, "z_range_mm", None)
    if fn is None:
        return False
    zr = fn()
    if zr is None:
        return False
    z_bot, z_top = zr
    return z_top >= view_depth and z_bot <= view_height

from .constants import DEFAULT_LEVEL, DEFAULT_CEILING_OFFSET_MM
# Display mode options (stored in Level.display_mode)
DISPLAY_MODES = ["Auto", "Hidden", "Faded", "Visible"]


@dataclass
class Level:
    name:         str
    elevation:    float = 0.0       # mm, relative to project datum
    view_top:     float = 2000.0    # mm above elevation (default offset for new plan views)
    view_bottom:  float = -1000.0   # mm below elevation (default offset for new plan views)
    display_mode: str   = "Auto"    # Auto | Hidden | Faded | Visible

    def to_dict(self) -> dict:
        return {
            "name":         self.name,
            "elevation_mm": self.elevation,
            "view_top":     self.view_top,
            "view_bottom":  self.view_bottom,
            "display_mode": self.display_mode,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Level":
        # Prefer new mm key; fall back to legacy ft key converted to mm
        if "elevation_mm" in d:
            elev = d["elevation_mm"]
        else:
            elev = d.get("elevation", 0.0) * 304.8
        return cls(
            name         = d["name"],
            elevation    = elev,
            view_top     = d.get("view_top",     2000.0),
            view_bottom  = d.get("view_bottom",  -1000.0),
            display_mode = d.get("display_mode", "Auto"),
        )


@dataclass
class PlanView:
    """Per-view cut-plane range for a plan tab.

    *view_height* is the absolute elevation (mm) of the cut plane (camera
    height).  Elements that straddle this plane are "section-cut" and get
    hatching.  *view_depth* is the lowest elevation visible in the view.
    """
    name:        str            # unique view name, e.g. "Plan: Level 1"
    level_name:  str            # which level this plan view shows
    view_height: float = 0.0   # mm, absolute elevation of the cut plane
    view_depth:  float = 0.0   # mm, absolute elevation of the bottom limit

    def to_dict(self) -> dict:
        return {
            "name":        self.name,
            "level_name":  self.level_name,
            "view_height": self.view_height,
            "view_depth":  self.view_depth,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PlanView":
        return cls(
            name        = d["name"],
            level_name  = d["level_name"],
            view_height = d.get("view_height", 0.0),
            view_depth  = d.get("view_depth",  0.0),
        )


class PlanViewInfo:
    """Lightweight wrapper that exposes PlanView data to the property panel.

    Passed to ``PropertyManager.show_properties()`` when nothing is selected
    and the active tab is a plan view.
    """

    def __init__(self, plan_view: "PlanView", level_manager: "LevelManager",
                 scale_manager=None, on_view_range=None):
        self._pv = plan_view
        self._lm = level_manager
        self._sm = scale_manager
        self._on_view_range = on_view_range  # callback to open ViewRangeDialog

    def get_properties(self) -> dict:
        pv = self._pv
        sm = self._sm
        props = {}
        props["── Plan View ──"] = {"value": "", "type": "label"}
        props["Name"] = {"value": pv.name, "type": "string", "readonly": True}
        props["Level"] = {"value": pv.level_name, "type": "string", "readonly": True}
        lvl = self._lm.get(pv.level_name)
        elev_str = sm.format_length(lvl.elevation) if (lvl and sm) else "?"
        props["Level Elevation"] = {"value": elev_str, "type": "string", "readonly": True}
        props["── View Range ──"] = {"value": "", "type": "label"}
        vh_str = sm.format_length(pv.view_height) if sm else f"{pv.view_height:.1f}"
        vd_str = sm.format_length(pv.view_depth) if sm else f"{pv.view_depth:.1f}"
        props["Cut Plane Height"] = {"value": vh_str, "type": "string", "readonly": True}
        props["View Depth"] = {"value": vd_str, "type": "string", "readonly": True}
        if self._on_view_range is not None:
            props["Edit View Range"] = {
                "type": "button", "value": "View Range\u2026",
                "callback": self._on_view_range}
        return props

    def set_property(self, key, value):
        pass  # read-only


_DEFAULT_SLAB_THICKNESS_MM = 152.4  # 6 inches — used to compute default view_height


class PlanViewManager:
    """Manages per-view cut-plane settings for plan tabs."""

    def __init__(self):
        self._views: dict[str, PlanView] = {}

    def get(self, name: str) -> PlanView | None:
        return self._views.get(name)

    def create(self, level_name: str, level_manager: "LevelManager") -> PlanView:
        """Create (or return existing) PlanView with smart defaults."""
        name = f"Plan: {level_name}"
        existing = self._views.get(name)
        if existing is not None:
            return existing

        lvl = level_manager.get(level_name)
        elev = lvl.elevation if lvl else 0.0

        # view_depth: this level's elevation (show floor-level items)
        view_depth = elev + (lvl.view_bottom if lvl else -1000.0)

        # view_height: next level's elevation minus slab thickness,
        # or this level + view_top if no level above exists
        levels_sorted = sorted(level_manager.levels, key=lambda l: l.elevation)
        next_lvl = None
        for l in levels_sorted:
            if l.elevation > elev:
                next_lvl = l
                break
        if next_lvl is not None:
            view_height = next_lvl.elevation - _DEFAULT_SLAB_THICKNESS_MM
        else:
            view_height = elev + (lvl.view_top if lvl else 2000.0)

        pv = PlanView(name=name, level_name=level_name,
                      view_height=view_height, view_depth=view_depth)
        self._views[name] = pv
        return pv

    def remove(self, name: str):
        self._views.pop(name, None)

    def to_list(self) -> list[dict]:
        return [pv.to_dict() for pv in self._views.values()]

    def from_list(self, data: list[dict]):
        self._views = {}
        for d in data:
            pv = PlanView.from_dict(d)
            self._views[pv.name] = pv

    def rename_level(self, old_name: str, new_name: str):
        """Update plan views when a level is renamed."""
        old_key = f"Plan: {old_name}"
        pv = self._views.pop(old_key, None)
        if pv is not None:
            pv.name = f"Plan: {new_name}"
            pv.level_name = new_name
            self._views[pv.name] = pv

    def remove_level(self, level_name: str):
        """Remove any plan views referencing a deleted level."""
        key = f"Plan: {level_name}"
        self._views.pop(key, None)


# Defaults shipped with every new document
DEFAULT_LEVELS: list[Level] = [
    Level(DEFAULT_LEVEL, elevation=0.0),
    Level("Level 2", elevation=3048.0),
    Level("Level 3", elevation=6096.0),
]


# ─────────────────────────────────────────────────────────────────────────────
# Manager (pure data, no Qt)
# ─────────────────────────────────────────────────────────────────────────────

class LevelManager:
    """Manages the ordered list of floor levels.

    The "active level" concept is now purely view-driven: whichever
    Plan tab is currently displayed defines the active level.  The
    manager no longer stores active-level state; callers pass the
    level name explicitly to ``apply_for_level()``.
    """

    def __init__(self):
        self._levels: list[Level] = [
            Level(**vars(l)) for l in DEFAULT_LEVELS
        ]

    # ── Level list API ────────────────────────────────────────────────────────

    @property
    def levels(self) -> list[Level]:
        return list(self._levels)

    def get(self, name: str) -> Level | None:
        for lvl in self._levels:
            if lvl.name == name:
                return lvl
        return None

    def add_level(self, name: str | None = None,
                  elevation: float = 0.0) -> Level:
        if name is None or self.get(name) is not None:
            i = 1
            while self.get(f"Level {i}") is not None:
                i += 1
            name = f"Level {i}"
        lvl = Level(name, elevation=elevation)
        self._levels.append(lvl)
        return lvl

    def remove_level(self, name: str):
        """Delete a level.  The last remaining level cannot be deleted."""
        if len(self._levels) <= 1:
            return
        self._levels = [l for l in self._levels if l.name != name]

    def rename_level(self, old_name: str, new_name: str, items) -> bool:
        """Rename a level and update all items that referenced the old name."""
        if not new_name or (self.get(new_name) is not None
                           and new_name != old_name):
            return False
        lvl = self.get(old_name)
        if lvl is None:
            return False
        lvl.name = new_name
        for item in items:
            if getattr(item, "level", None) == old_name:
                item.level = new_name
        return True

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_list(self) -> list[dict]:
        return [l.to_dict() for l in self._levels]

    def from_list(self, data: list[dict]):
        self._levels = [Level.from_dict(d) for d in data]
        # Ensure at least one level exists
        if not self._levels:
            self._levels = [Level(**vars(l)) for l in DEFAULT_LEVELS]

    def reset(self):
        """Reset to default levels (used on new file)."""
        self._levels = [Level(**vars(l)) for l in DEFAULT_LEVELS]

    # ── Elevation helpers ───────────────────────────────────────────────────

    def update_elevations(self, scene):
        """Recompute z_pos for all nodes using ceiling_level + ceiling_offset."""
        from .node import Node
        lvl_map = {l.name: l for l in self._levels}
        for node in scene.sprinkler_system.nodes:
            # 3D elevation = ceiling level elevation (mm) + ceiling offset (mm)
            ceil_lvl = lvl_map.get(getattr(node, "ceiling_level", DEFAULT_LEVEL))
            ceil_elev = ceil_lvl.elevation if ceil_lvl else 0.0
            node.z_pos = ceil_elev + getattr(node, "ceiling_offset", DEFAULT_CEILING_OFFSET_MM)

    # ── Z-range helpers (module-level to avoid repeated closure overhead) ────

    @staticmethod
    def _get_z_range(item):
        """Return (z_bot, z_top) or None if the item has no Z data."""
        fn = getattr(item, "z_range_mm", None)
        return fn() if fn is not None else None

    # ── Apply to scene ────────────────────────────────────────────────────────

    def apply_to_scene(self, scene, active_level: str | None = None,
                       view_height: float | None = None,
                       view_depth: float | None = None):
        """Show/hide/fade entities based on *active_level* and display_mode,
        then re-apply layer visibility so both level AND layer filtering
        are respected.

        *active_level* is the level of the current plan view.  If ``None``,
        falls back to ``scene.active_level``.

        When *view_height* and *view_depth* are provided, elements with a
        ``z_range_mm()`` method are additionally filtered by elevation:
        only elements whose vertical extent intersects [view_depth, view_height]
        are visible.  Elements on non-active levels that intersect the range
        are shown (faded).  Elements cut by *view_height* get ``_is_section_cut = True``.
        """
        active = active_level or getattr(scene, "active_level", DEFAULT_LEVEL)
        lvl_map = {l.name: l for l in self._levels}
        has_view_range = (view_height is not None and view_depth is not None)

        # Flag floor slabs that act as occluding masks within the view range.
        for slab in getattr(scene, "_floor_slabs", []):
            slab._is_occluding = False
        if has_view_range:
            for slab in getattr(scene, "_floor_slabs", []):
                zr = slab.z_range_mm() if hasattr(slab, "z_range_mm") else None
                if zr is None:
                    continue
                slab_top = zr[1]
                if view_depth < slab_top <= view_height:
                    slab._is_occluding = True

        def _set_level_vis(item):
            # Guard against deleted C++ objects (e.g. after undo)
            try:
                item.isVisible()
            except RuntimeError:
                return

            # Reset section-cut flag
            if hasattr(item, "_is_section_cut"):
                item._is_section_cut = False

            lvl_name = getattr(item, "level", DEFAULT_LEVEL)
            lvl_def = lvl_map.get(lvl_name)
            mode = lvl_def.display_mode if lvl_def else "Auto"

            # "Hidden" always hides, even if active
            if mode == "Hidden":
                item.setVisible(False)
                item.setOpacity(1.0)
                return

            if lvl_name == active:
                # Active level — fully visible and selectable
                item.setVisible(True)
                item.setOpacity(1.0)
                item.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True,
                )
                # Apply view-range Z filter
                if has_view_range:
                    _apply_z_filter(item, view_height, view_depth)
                return

            # Non-active level — check display_mode first, then Z-range
            if mode == "Faded":
                item.setVisible(True)
                item.setOpacity(FADE_OPACITY)
                item.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False,
                )
                if has_view_range:
                    _apply_z_filter(item, view_height, view_depth)
            elif mode == "Visible":
                item.setVisible(True)
                item.setOpacity(1.0)
                item.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False,
                )
                if has_view_range:
                    _apply_z_filter(item, view_height, view_depth)
            else:
                # "Auto" when not active — check if Z-range brings it in
                if has_view_range and _z_intersects(item, view_height, view_depth):
                    # Multi-level element visible on this plan — full opacity
                    item.setVisible(True)
                    item.setOpacity(1.0)
                    item.setFlag(
                        QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True,
                    )
                    _apply_z_filter(item, view_height, view_depth)
                else:
                    item.setVisible(False)
                    item.setOpacity(1.0)

        # ── Sprinkler system ──────────────────────────────────────────────
        for node in scene.sprinkler_system.nodes:
            _set_level_vis(node)

        for pipe in scene.sprinkler_system.pipes:
            _set_level_vis(pipe)

        # ── Construction / draw geometry ──────────────────────────────────
        for item in getattr(scene, "_construction_lines", []):
            _set_level_vis(item)

        for item in getattr(scene, "_polylines", []):
            _set_level_vis(item)

        for item in getattr(scene, "_draw_lines", []):
            _set_level_vis(item)

        for item in getattr(scene, "_draw_rects", []):
            _set_level_vis(item)

        for item in getattr(scene, "_draw_circles", []):
            _set_level_vis(item)

        for item in getattr(scene, "_draw_arcs", []):
            _set_level_vis(item)

        # ── Gridlines (always visible on all levels) ─────────────────────
        for item in getattr(scene, "_gridlines", []):
            item.setVisible(True)
            item.setOpacity(1.0)
            item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        # ── Annotations ───────────────────────────────────────────────────
        annotations = getattr(scene, "annotations", None)
        if annotations is not None:
            for dim in getattr(annotations, "dimensions", []):
                _set_level_vis(dim)
            for note in getattr(annotations, "notes", []):
                _set_level_vis(note)

        # ── Walls ─────────────────────────────────────────────────────────
        for item in getattr(scene, "_walls", []):
            _set_level_vis(item)
            # Also handle openings belonging to this wall
            for op in getattr(item, "openings", []):
                _set_level_vis(op)

        # ── Floor slabs ──────────────────────────────────────────────────
        for item in getattr(scene, "_floor_slabs", []):
            _set_level_vis(item)

        # ── Roofs ────────────────────────────────────────────────────────
        for item in getattr(scene, "_roofs", []):
            _set_level_vis(item)

        # ── Rooms ───────────────────────────────────────────────────────
        for item in getattr(scene, "_rooms", []):
            _set_level_vis(item)

        # ── Hatches ───────────────────────────────────────────────────────
        for item in getattr(scene, "_hatch_items", []):
            _set_level_vis(item)

        # ── Water supply ──────────────────────────────────────────────────
        ws = getattr(scene, "water_supply_node", None)
        if ws is not None:
            _set_level_vis(ws)

        # ── Underlays ────────────────────────────────────────────────────
        for data, item in getattr(scene, "underlays", []):
            if item is None:
                continue
            try:
                item.isVisible()
            except RuntimeError:
                continue
            if not data.visible:
                item.setVisible(False)
                continue
            if data.level == "*":
                item.setVisible(True)
                continue
            lvl = lvl_map.get(data.level)
            if lvl is None:
                item.setVisible(False)
                continue
            if has_view_range:
                z = lvl.elevation
                item.setVisible(view_depth <= z <= view_height)
            else:
                item.setVisible(data.level == active)

        # ── Elevation-based Z-ordering ────────────────────────────────────
        # Assign Qt Z-values based on actual elevation so that higher items
        # render on top of lower items.  Small category offsets preserve
        # draw order within the same elevation (slab < room < wall < pipe < node).
        _Z_CATEGORY = {
            "FloorSlab": 0.0,
            "RoofItem":  0.1,
            "Room":      0.2,
            "WallSegment": 0.3,
            "DoorOpening": 0.35,
            "WindowOpening": 0.35,
            "Pipe":      0.4,
            "Node":      0.5,
        }
        # Items that always overlay on top regardless of elevation
        _Z_OVERLAY = {"DetailMarker": 500, "GridlineItem": 500}
        _Z_SCALE = 1.0 / 100.0  # mm → Z units (keeps values manageable)

        def _apply_elev_z(item):
            overlay_z = _Z_OVERLAY.get(type(item).__name__)
            if overlay_z is not None:
                item.setZValue(overlay_z)
                return
            cat_offset = _Z_CATEGORY.get(type(item).__name__)
            if cat_offset is None:
                return  # not a model item — keep its current Z
            z_mm = 0.0
            zr = item.z_range_mm() if hasattr(item, "z_range_mm") else None
            if zr is not None:
                # Rooms use floor elevation (min) so they render below
                # their ceiling slab.  All other items use the highest
                # point (max) — handles slabs with negative thickness
                # where the tuple isn't normalized.
                if type(item).__name__ == "Room":
                    z_mm = min(zr)
                else:
                    z_mm = max(zr)
            elif hasattr(item, "z_pos"):
                z_mm = item.z_pos
            else:
                # Fall back to level elevation
                lvl_name = getattr(item, "level", None)
                lvl_obj = lvl_map.get(lvl_name) if lvl_name else None
                if lvl_obj is not None:
                    z_mm = lvl_obj.elevation
            item.setZValue(z_mm * _Z_SCALE + cat_offset)

        for node in scene.sprinkler_system.nodes:
            _apply_elev_z(node)
        for pipe in scene.sprinkler_system.pipes:
            _apply_elev_z(pipe)
        for item in getattr(scene, "_walls", []):
            _apply_elev_z(item)
            for op in getattr(item, "openings", []):
                _apply_elev_z(op)
        for item in getattr(scene, "_floor_slabs", []):
            _apply_elev_z(item)
        for item in getattr(scene, "_roofs", []):
            _apply_elev_z(item)
        for item in getattr(scene, "_rooms", []):
            _apply_elev_z(item)

        for item in getattr(scene, "_gridlines", []):
            _apply_elev_z(item)

        # ── Detail markers ────────────────────────────────────────────────
        dm = getattr(scene, "_detail_manager", None)
        if dm is not None:
            for marker in dm._markers.values():
                _set_level_vis(marker)

        dm = getattr(scene, "_detail_manager", None)
        if dm is not None:
            for marker in dm._markers.values():
                _apply_elev_z(marker)

        # ── Re-apply user-layer visibility on top ─────────────────────────
        ulm = getattr(scene, "_user_layer_manager", None)
        if ulm is not None:
            ulm.apply_to_scene(scene)

        # ── Fixup: restore faded opacity for items that survived layer
        #    filtering (ulm.apply_to_scene may have reset opacity) ─────────
        faded_levels = {l.name for l in self._levels
                        if l.display_mode == "Faded" and l.name != active}
        if faded_levels:
            self._reapply_fade(scene, faded_levels)

    def _reapply_fade(self, scene, faded_levels: set[str]):
        """Re-apply FADE_OPACITY to items on faded levels that are still
        visible after user-layer filtering."""
        def _fix(item):
            if not item.isVisible():
                return
            if getattr(item, "level", DEFAULT_LEVEL) in faded_levels:
                item.setOpacity(FADE_OPACITY)

        for node in scene.sprinkler_system.nodes:
            _fix(node)
        for pipe in scene.sprinkler_system.pipes:
            _fix(pipe)
        for item in getattr(scene, "_construction_lines", []):
            _fix(item)
        for item in getattr(scene, "_polylines", []):
            _fix(item)
        for item in getattr(scene, "_draw_lines", []):
            _fix(item)
        for item in getattr(scene, "_draw_rects", []):
            _fix(item)
        for item in getattr(scene, "_draw_circles", []):
            _fix(item)
        for item in getattr(scene, "_draw_arcs", []):
            _fix(item)
        for item in getattr(scene, "_gridlines", []):
            _fix(item)
        annotations = getattr(scene, "annotations", None)
        if annotations is not None:
            for dim in getattr(annotations, "dimensions", []):
                _fix(dim)
            for note in getattr(annotations, "notes", []):
                _fix(note)
        for item in getattr(scene, "_hatch_items", []):
            _fix(item)
        ws = getattr(scene, "water_supply_node", None)
        if ws is not None:
            _fix(ws)

