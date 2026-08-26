# firepro3d/align_engine.py
"""Generic inferred-placement engine (first slice: H/V alignment guides).

Entity-agnostic. Consumers supply candidate reference features; the engine
returns a snapped position + the active guides + the winning priority band.
See docs/specs/align-placement.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReferenceFeature:
    """A point/edge/face an active placement point can align to."""
    kind: str            # "point" (now); "edge"/"face" reserved
    x: float
    y: float
    source_id: int       # id() of the source item — for excluding the active item
    label: str = ""      # "endpoint"/"bubble" — glyph/debug


@dataclass
class Guide:
    orientation: str     # "h" or "v"
    coord: float         # y for "h", x for "v"
    ref: ReferenceFeature


@dataclass
class AlignResult:
    snapped: tuple[float, float]
    guides: list[Guide] = field(default_factory=list)
    priority: str = "free"   # "guide-intersection" | "single-guide" | "free"


class AlignEngine:
    """Pure geometry. No Qt, no scene knowledge. Model_Space owns one."""

    def resolve(self, cursor: tuple[float, float],
                refs: list[ReferenceFeature], tol: float) -> AlignResult:
        cx, cy = cursor
        # Nearest vertical (shared X) and horizontal (shared Y) candidate within tol.
        best_v = self._nearest(refs, key=lambda r: abs(r.x - cx), tol=tol)
        best_h = self._nearest(refs, key=lambda r: abs(r.y - cy), tol=tol)
        guides: list[Guide] = []
        sx, sy = cx, cy
        if best_v is not None:
            guides.append(Guide("v", best_v.x, best_v))
            sx = best_v.x
        if best_h is not None:
            guides.append(Guide("h", best_h.y, best_h))
            sy = best_h.y
        if best_v is not None and best_h is not None:
            priority = "guide-intersection"
        elif guides:
            priority = "single-guide"
        else:
            priority = "free"
        return AlignResult(snapped=(sx, sy), guides=guides, priority=priority)

    @staticmethod
    def _nearest(refs, key, tol):
        best, best_d = None, tol
        for r in refs:
            d = key(r)
            if d < best_d:            # strict: ties keep the earlier candidate
                best_d = d
                best = r
        return best
