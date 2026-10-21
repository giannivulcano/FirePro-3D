"""
section_manager.py
==================
Owns the section markers on the plan and the open section views (tabs).

Cardinals (North/South/East/West) are permanent markers seeded at startup and
keep the ``"elevation"`` identity (spec s7.2); placed sections are
``"section"``. One tab per section; a tab-less scene is built for sheets
(``get_or_build_scene``) and adopted when the tab opens.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QPointF, QRectF, QTimer, pyqtSignal
from PyQt6.QtWidgets import QTabWidget

from .section_scene import SectionScene
from .elevation_view import SectionView
from .section_marker import (SectionMarker, CARDINALS, building_bbox,
                             CROP_MARGIN, FALLBACK_HALF, MIN_CUT_LEN)

if TYPE_CHECKING:
    from .model_space import Model_Space
    from .level_manager import LevelManager
    from .scale_manager import ScaleManager


DEFAULT_DEPTH = 10000.0     # plan-scene units (mm at ppm 1) -- depth when nothing lies on the look side (spec s9)


def _valid_record(d) -> bool:
    """A hand-editable marker record the scene can be built from (spec s13):
    required keys present, a cut of at least ``MIN_CUT_LEN``, depth > 0."""
    try:
        ax, ay = (float(v) for v in d["cut_a"])
        bx, by = (float(v) for v in d["cut_b"])
        depth = float(d.get("depth", DEFAULT_DEPTH))
        str(d["name"])
    except (KeyError, TypeError, ValueError):
        return False
    vals = (ax, ay, bx, by, depth)
    if not all(math.isfinite(v) for v in vals):
        return False
    return math.hypot(bx - ax, by - ay) >= MIN_CUT_LEN and depth > 0.0


class SectionManager(QObject):
    """Markers + views for every section (spec s7.1).

    Args:
        model_space: The plan scene (data source and marker host).
        level_manager: Shared level / elevation lookup.
        scale_manager: Coordinate conversion.
        tab_widget: Central tab widget where section tabs are added.
    """

    sectionsChanged = pyqtSignal()        # place / rename / delete -> browser refresh

    def __init__(self, model_space: "Model_Space", level_manager: "LevelManager",
                 scale_manager: "ScaleManager", tab_widget: QTabWidget, parent=None):
        super().__init__(parent)
        self._ms = model_space
        self._lm = level_manager
        self._sm = scale_manager
        self._tabs = tab_widget
        self.markers: dict[str, SectionMarker] = {}          # key: view_name
        self._views: dict[str, tuple[SectionScene, SectionView | None]] = {}
        self._counter = 0

    # -- keys -------------------------------------------------------------------------
    @staticmethod
    def _key(name: str) -> str:
        return name.lower() if name.lower() in CARDINALS else name

    def marker(self, name: str) -> SectionMarker | None:
        return self.markers.get(self._key(name))

    # -- markers ----------------------------------------------------------------------
    def _adopt(self, marker: SectionMarker) -> SectionMarker:
        from .display_manager import apply_category_defaults
        marker._manager = self
        self.markers[marker.view_name] = marker
        if marker.scene() is not self._ms:
            self._ms.addItem(marker)
        apply_category_defaults(marker)
        return marker

    def seed_cardinals(self) -> None:
        """Create any missing N/S/E/W marker (auto-extent). Idempotent."""
        box = None
        for c in CARDINALS:
            if c in self.markers:
                continue
            box = box or building_bbox(self._ms)
            self._adopt(SectionMarker.for_cardinal(c, box))

    def next_name(self) -> str:
        """The next free ``Section N`` (never collides with an existing name)."""
        while True:
            self._counter += 1
            name = f"Section {self._counter}"
            if name not in self.markers:
                return name

    def _seed_depth(self, a: QPointF, b: QPointF) -> float:
        """Building extent beyond the line on the look side (s9);
        ``DEFAULT_DEPTH`` when the project is empty or nothing lies on that side."""
        bb = building_bbox(self._ms)
        empty = QRectF(-FALLBACK_HALF - CROP_MARGIN, -FALLBACK_HALF - CROP_MARGIN,
                       2 * (FALLBACK_HALF + CROP_MARGIN), 2 * (FALLBACK_HALF + CROP_MARGIN))
        if bb == empty:                                       # building_bbox's empty-project return
            return DEFAULT_DEPTH
        bb = bb.adjusted(CROP_MARGIN, CROP_MARGIN, -CROP_MARGIN, -CROP_MARGIN)   # the building itself, no padding
        nx, ny = SectionMarker("probe", a, b, 1, 1.0).normal_scene()
        best = max((c.x() - a.x()) * nx + (c.y() - a.y()) * ny
                   for c in (bb.topLeft(), bb.topRight(), bb.bottomLeft(), bb.bottomRight()))
        return best if best > 0.0 else DEFAULT_DEPTH

    def place_section(self, a: QPointF, b: QPointF) -> SectionMarker:
        m = SectionMarker(self.next_name(), a, b, 1, self._seed_depth(a, b))
        self._adopt(m)
        self.sectionsChanged.emit()
        return m

    def delete_section(self, name: str) -> None:
        key = self._key(name)
        m = self.markers.get(key)
        if m is None:
            return
        if m.cardinal:
            raise ValueError("cardinal sections are permanent (D5b)")
        self.close_section(key)
        self.markers.pop(key)
        if m.scene() is self._ms:
            self._ms.removeItem(m)
        self.sectionsChanged.emit()

    def rename_section(self, old: str, new: str) -> None:
        key = self._key(old)
        m = self.markers.get(key)
        if m is None or m.cardinal or not new or new == old or self._key(new) in self.markers:
            return
        self.markers.pop(key)
        m.name = new
        self.markers[new] = m
        if key in self._views:
            scene, view = self._views.pop(key)
            self._views[new] = (scene, view)
            if view is not None:
                for i in range(self._tabs.count()):
                    if self._tabs.widget(i) is view:
                        self._tabs.setTabText(i, self._tab_title(m))
        # Sheet viewports bound as section:<old> follow the name.
        for sheet in getattr(self._ms, "_sheets", []) or []:
            for sv in getattr(sheet, "sheet_views", []):
                if sv.source_view_type == "section" and sv.source_view_name == old:
                    sv.source_view_name = new
        self.sectionsChanged.emit()

    @property
    def section_names(self) -> list[str]:
        """Placed (non-cardinal) sections, in creation order."""
        return [m.name for m in self.markers.values() if not m.cardinal]

    # -- views --------------------------------------------------------------------------
    @staticmethod
    def _tab_title(m: SectionMarker) -> str:
        return f"Elevation: {m.cardinal.title()}" if m.cardinal else f"Section: {m.name}"

    def get_or_build_scene(self, name: str) -> SectionScene | None:
        """The section's scene, built tab-less when no tab is open (sheets, s7.2)."""
        key = self._key(name)
        if key in self._views:
            return self._views[key][0]
        m = self.markers.get(key)
        if m is None:
            return None
        scene = SectionScene(m, self._ms, self._lm, self._sm)
        scene.rebuild()
        self._views[key] = (scene, None)
        return scene

    def open_section(self, name: str) -> SectionView | None:
        key = self._key(name)
        if key in self._views and self._views[key][1] is not None:
            scene, view = self._views[key]
            for i in range(self._tabs.count()):
                if self._tabs.widget(i) is view:
                    self._tabs.setCurrentIndex(i)
                    return view
            self._views[key] = (scene, None)              # tab removed externally
        m = self.markers.get(key)
        if m is None:
            return None
        scene = self.get_or_build_scene(key)
        view = SectionView(scene, self._sm)
        idx = self._tabs.addTab(view, self._tab_title(m))
        self._tabs.setCurrentIndex(idx)
        QTimer.singleShot(50, view.fit_to_screen)
        self._views[key] = (scene, view)
        return view

    def close_section(self, name: str) -> None:
        key = self._key(name)
        entry = self._views.pop(key, None)
        if entry is None:
            return
        scene, view = entry
        if view is not None:
            for i in range(self._tabs.count()):
                if self._tabs.widget(i) is view:
                    self._tabs.removeTab(i)
                    break

    def close_all(self) -> None:
        for k in list(self._views):
            self.close_section(k)

    def forget_view(self, widget) -> None:
        """A tab closed by the user: drop the view, keep the scene for sheets."""
        for key, (scene, view) in list(self._views.items()):
            if view is widget:
                self._views[key] = (scene, None)

    def clear(self) -> None:
        """New / load: drop every marker and view (markers are re-seeded by the caller)."""
        blocked = self._tabs.blockSignals(True)       # no tab-change churn mid-reset
        try:
            self.close_all()
        finally:
            self._tabs.blockSignals(blocked)
        for m in list(self.markers.values()):
            if m.scene() is self._ms:
                self._ms.removeItem(m)
        self.markers.clear()
        self._counter = 0

    def get_view(self, name: str) -> SectionView | None:
        e = self._views.get(self._key(name))
        return e[1] if e else None

    def get_scene(self, name: str) -> SectionScene | None:
        e = self._views.get(self._key(name))
        return e[0] if e and e[1] is not None else None

    @property
    def open_names(self) -> list[str]:
        return [k for k, (sc, v) in self._views.items() if v is not None]

    @property
    def open_scenes(self) -> list[SectionScene]:
        """Every live section scene (open tabs and sheet-built) -- 560 / acceptance (c)."""
        return [sc for sc, _v in self._views.values()]

    def rebuild_all(self) -> None:
        for scene, _v in self._views.values():
            scene.rebuild()

    def on_marker_geometry_changed(self, marker: SectionMarker) -> None:
        e = self._views.get(marker.view_name)
        if e is not None:
            e[0]._schedule_rebuild()

    # -- persistence / undo (s8) -------------------------------------------------------
    def to_list(self) -> list[dict]:
        return [m.to_dict() for m in self.markers.values()]

    def from_list(self, data: list[dict]) -> None:
        """Project load: replace every marker; the caller seeds cardinals.

        A record the scene cannot be built from (missing key, cut shorter than
        ``MIN_CUT_LEN``, depth <= 0, duplicate name) is skipped (spec s13); a
        skipped cardinal is re-seeded by ``seed_cardinals``.
        """
        self.clear()
        for d in data or []:
            if not isinstance(d, dict) or not _valid_record(d):
                continue
            m = SectionMarker.from_dict(d)
            if m.cardinal is not None and m.cardinal not in CARDINALS:
                continue
            if m.view_name in self.markers:
                continue
            self._adopt(m)
            parts = m.name.split()
            if not m.cardinal and len(parts) >= 2:
                try:
                    self._counter = max(self._counter, int(parts[-1]))
                except ValueError:
                    pass
        self.sectionsChanged.emit()

    def restore_from_list(self, data: list[dict]) -> None:
        """Undo restore: diff by name -- update survivors in place, remove
        deleted, re-add missing; open tabs are left alone (s8)."""
        want = {(d["cardinal"] or d["name"]): d for d in data if _valid_record(d)}
        for key in list(self.markers):
            if key not in want and not self.markers[key].cardinal:
                self.delete_section(key)
        for key, d in want.items():
            m = self.markers.get(key)
            if m is None:
                self._adopt(SectionMarker.from_dict(d))
                continue
            m.set_geometry(QPointF(*d["cut_a"]), QPointF(*d["cut_b"]), d["depth"], user=False)
            if m.look_sign != d["look_sign"]:
                m.flip()
            m._auto_extent = bool(d.get("auto_extent", False)) if m.cardinal else False
            m.gridline_z_overrides = dict(d.get("gridline_z_overrides", {}))
        self.sectionsChanged.emit()
