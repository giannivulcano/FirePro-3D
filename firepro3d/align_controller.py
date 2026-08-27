# firepro3d/align_controller.py
"""ALIGN acquire state machine — the stateful half of the ALIGN subsystem.

Pure-ish and Qt-free at the logic level: dwell is decided from elapsed-ms told
in by the seam (deterministic tests), not a live timer. Owns the acquired set,
the two acquire flavors, cap-evict, re-hover-release, active-anchor auto-acquire,
and per-frame ray generation. Model_Space holds one and delegates.
See docs/specs/align-placement.md.
"""
from __future__ import annotations

from .align_engine import AcquiredRef, Ray, rays_for_acquired

# Snap types that acquire as a discrete POINT (H/V + optional extension).
_POINT_SNAPS = {"endpoint", "midpoint", "center", "quadrant", "intersection", "node"}
# Snap types whose hit acquires the object's DIRECTION (parallel).
_DIRECTION_SNAPS = {"nearest", "perpendicular"}


class AlignController:
    """Owns ALIGN acquire-state; builds transient tracking rays each frame."""

    def __init__(self, dwell_ms: int = 400, max_points: int = 5,
                 dir_hv_enabled: bool = True,
                 dir_extension_enabled: bool = True,
                 dir_parallel_enabled: bool = True,
                 dir_perpendicular_enabled: bool = True):
        self.dwell_ms = dwell_ms
        self.max_points = max_points
        # Per-direction ray-kind gating (SnappingPane knobs, live-applied). A
        # disabled kind is omitted from build_rays so no candidate of that kind
        # ever reaches the picker.  All default on (constants ALIGN_DIR_*).
        self.dir_hv_enabled = dir_hv_enabled
        self.dir_extension_enabled = dir_extension_enabled
        self.dir_parallel_enabled = dir_parallel_enabled
        self.dir_perpendicular_enabled = dir_perpendicular_enabled
        self.acquired: list[AcquiredRef] = []
        self._anchor: AcquiredRef | None = None
        # Dwell tracking: the source we have been resting on and for how long.
        self._dwell_source: int | None = None
        self._dwell_ms: float = 0.0

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def clear(self) -> None:
        """Drop all acquisitions and the auto-anchor (command end / Esc / commit)."""
        self.acquired.clear()
        self._anchor = None
        self._dwell_source = None
        self._dwell_ms = 0.0

    def set_active_anchor(self, point: tuple[float, float] | None,
                          direction: tuple[float, float] | None) -> None:
        """Auto-acquire the active placement anchor (H/V + its own extension)."""
        if point is None:
            self._anchor = None
            return
        self._anchor = AcquiredRef(point=point, direction=direction,
                                   flavor="point", snap_type="anchor", source_id=-1)

    # ── Per-move ──────────────────────────────────────────────────────────

    def on_move(self, cursor, snap, elapsed_ms: float) -> None:
        """Advance the dwell machine for one mouse-move.

        Args:
            cursor: (x, y) scene position (unused for logic; kept for symmetry).
            snap: dict {"point", "snap_type", "source_id", "direction"} of the
                current SNAP result, or None if the cursor is over nothing.
            elapsed_ms: milliseconds since the previous move on the SAME source
                (the seam resets this by feeding a small value when the source
                changes). When the running dwell on one source crosses
                ``dwell_ms``, that source is acquired (or, if already acquired,
                released).
        """
        if snap is None:
            self._dwell_source = None
            self._dwell_ms = 0.0
            return
        sid = snap["source_id"]
        if sid != self._dwell_source:
            # Started resting on a new source: restart the dwell clock.
            self._dwell_source = sid
            self._dwell_ms = elapsed_ms
            crossed = elapsed_ms >= self.dwell_ms
        else:
            self._dwell_ms += elapsed_ms
            crossed = self._dwell_ms >= self.dwell_ms
        if not crossed:
            return
        # Latch: acquiring/releasing consumes the dwell so it does not re-fire
        # every subsequent frame while the cursor keeps resting.
        self._dwell_source = None
        self._dwell_ms = 0.0
        self._toggle_acquire(snap)

    def _toggle_acquire(self, snap) -> None:
        sid = snap["source_id"]
        existing = next((a for a in self.acquired if a.source_id == sid), None)
        if existing is not None:
            self.acquired.remove(existing)   # re-hover → release
            return
        flavor = "direction" if snap["snap_type"] in _DIRECTION_SNAPS else "point"
        ref = AcquiredRef(
            point=(None if flavor == "direction" else snap["point"]),
            direction=snap.get("direction"),
            flavor=flavor, snap_type=snap["snap_type"], source_id=sid,
        )
        self.acquired.append(ref)
        while len(self.acquired) > self.max_points:
            self.acquired.pop(0)             # evict oldest

    # ── Ray generation ────────────────────────────────────────────────────

    def set_direction_flags(self, *, hv: bool | None = None,
                            extension: bool | None = None,
                            parallel: bool | None = None,
                            perpendicular: bool | None = None) -> None:
        """Live-update the per-direction ray gating (SnappingPane apply()).

        Only the kwargs supplied are changed; ``None`` leaves a flag as-is.
        """
        if hv is not None:
            self.dir_hv_enabled = bool(hv)
        if extension is not None:
            self.dir_extension_enabled = bool(extension)
        if parallel is not None:
            self.dir_parallel_enabled = bool(parallel)
        if perpendicular is not None:
            self.dir_perpendicular_enabled = bool(perpendicular)

    def build_rays(self, active_point: tuple[float, float]) -> list[Ray]:
        """Return the enabled transient tracking rays (anchor + acquired set).

        Per-direction gating (``dir_hv_enabled`` / ``dir_extension_enabled`` /
        ``dir_parallel_enabled`` / ``dir_perpendicular_enabled``) drops whole ray
        KINDS: ``hv`` rays come from point-acquires, ``extension`` and
        ``perpendicular`` rays from directional points, ``parallel`` rays from
        direction-acquires. A disabled kind never reaches the picker.
        """
        refs = list(self.acquired)
        if self._anchor is not None:
            refs = [self._anchor] + refs
        rays = rays_for_acquired(refs, active_point)
        if (self.dir_hv_enabled and self.dir_extension_enabled
                and self.dir_parallel_enabled and self.dir_perpendicular_enabled):
            return rays
        return [r for r in rays if (
            (r.kind != "hv" or self.dir_hv_enabled)
            and (r.kind != "extension" or self.dir_extension_enabled)
            and (r.kind != "parallel" or self.dir_parallel_enabled)
            and (r.kind != "perpendicular" or self.dir_perpendicular_enabled)
        )]

    def acquired_points(self) -> list[tuple[float, float]]:
        """Scene points to draw ``+`` markers at (for drawForeground)."""
        pts = [a.point for a in self.acquired if a.point is not None]
        if self._anchor is not None and self._anchor.point is not None:
            pts.append(self._anchor.point)
        return pts
