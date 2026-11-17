"""
wall.py
=======
WallSegment entity for FirePro 3D.

Drawn as a double-line (centerline +/- half thickness) in 2D plan view.
Extruded to a 3D mesh between base_level and top_level (or base + height).
Supports thickness presets, colour, fill mode, and wall openings.
"""

from __future__ import annotations

import math
import uuid
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QGraphicsPathItem, QStyle, QGraphicsItem
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import (
    QPen, QColor, QPainterPath, QBrush, QPainterPathStroker, QPolygonF,
    QPainter, QTransform,
)

if TYPE_CHECKING:
    from .wall_opening import WallOpening

from .colour_tokens import normalize_colour, resolve_colour

_DEFAULT_COLOUR = "#cccccc"
from .constants import (DEFAULT_LEVEL, MATERIAL_NONE_ID,
                       MITER_TOL, MAX_MITER_FACTOR,
                       WALL_JOIN_TOP_TOL_MM, WALL_OUTLINE_ON_EDGE_TOL,
                       CUT_MARGIN_MM)
from .view_scale import scene_hit_width
from .wall_solid import build_solid, clip_depth, subtract_collinear
from PyQt6 import sip
from .wall_outline import (JunctionArm, SeamStroke, WallOutline, _poly_path,
                           boundary_segments, cluster_union, intersect_lines,
                           junction_pie, split_seam, stop_end, stroke_segments,
                           visible_corners)

# ── Constants ────────────────────────────────────────────────────────────────

THICKNESS_PRESETS_IN = [4, 6, 8, 12]           # inches (used by dialog combo)
DEFAULT_THICKNESS_IN = 6                        # inches (used by dialog combo)
DEFAULT_THICKNESS_MM = DEFAULT_THICKNESS_IN * 25.4  # 152.4 mm

# Fill modes
FILL_NONE  = "None"
FILL_SOLID = "Solid"
FILL_HATCH = "Hatch"      # legacy alias
FILL_SECTION = "Section"

# Alignment modes (Revit-style wall placement line)
ALIGN_CENTER   = "Center"
ALIGN_LEFT     = "Left"
ALIGN_RIGHT    = "Right"

_SELECTION_COLOR = QColor("red")


def _scene_hit_width(item) -> float:
    """~14 screen px at the visible view's zoom (see view_scale)."""
    return scene_hit_width(item, 14.0, 8.0)


def compute_wall_quad(
    pt1: QPointF, pt2: QPointF,
    thickness_mm: float,
    alignment: str,
    scale_manager=None,
) -> tuple[QPointF, QPointF, QPointF, QPointF]:
    """Compute the 4 corner points of a wall rectangle without a QGraphicsItem.

    Returns (p1_left, p1_right, p2_right, p2_left) — same order as
    ``WallSegment.quad_points()``.
    """
    dx = pt2.x() - pt1.x()
    dy = pt2.y() - pt1.y()
    angle = math.atan2(dy, dx)
    nx, ny = -math.sin(angle), math.cos(angle)

    # Half-thickness in scene units
    half_mm = thickness_mm / 2.0
    if (scale_manager is not None
            and scale_manager.drawing_scale > 0):
        paper_mm = half_mm / scale_manager.drawing_scale
        ht = scale_manager.paper_to_scene(paper_mm)
    else:
        ht = half_mm  # fallback: 1 px ≈ 1 mm

    if alignment == ALIGN_LEFT:
        # Left: axis is on the left face — wall extends rightward
        off_left = QPointF(nx * ht * 2, ny * ht * 2)
        off_right = QPointF(0, 0)
    elif alignment == ALIGN_RIGHT:
        # Right: axis is on the right face — wall extends leftward
        off_left = QPointF(0, 0)
        off_right = QPointF(-nx * ht * 2, -ny * ht * 2)
    else:  # Center
        off_left = QPointF(nx * ht, ny * ht)
        off_right = QPointF(-nx * ht, -ny * ht)
    return (
        pt1 + off_left,
        pt1 + off_right,
        pt2 + off_right,
        pt2 + off_left,
    )


# ── WallSegment ──────────────────────────────────────────────────────────────

from .displayable_item import DisplayableItemMixin
from . import materials
from . import phase_registry
from .paper_display import shows_selection


class WallSegment(DisplayableItemMixin, QGraphicsPathItem):
    """A straight wall segment defined by two centerline endpoints.

    2D rendering: two parallel lines at +/- thickness/2 from the centerline,
    with optional solid fill or diagonal hatch between them.

    Properties exposed via ``get_properties()`` / ``set_property()``:
        Thickness, Colour, Fill Mode, Base Level, Top Level, Height
    """

    material_category = "Wall"
    paper_category = "Wall"     # paper row (paper-space.md s6.2, R5)
    HALO_AREA = True  # HALO: cursor inside = direct hit

    @property
    def _alignment(self) -> str:
        """Alignment mode (Center / Left / Right).  A property so every
        writer -- placement (wall_placement_controller), ``from_dict``,
        ``set_property``, tests -- rebuilds the outline (design D3)."""
        return self._alignment_value

    @_alignment.setter
    def _alignment(self, value: str) -> None:
        self._alignment_value = value
        if getattr(self, "_outline_ready", False):
            self.invalidate_geometry()

    @property
    def _thickness_mm(self) -> float:
        """Wall thickness in mm.  A property so every writer (grip drag,
        ``set_property``, tests) rebuilds the outline (design D3)."""
        return self._thickness_value

    @_thickness_mm.setter
    def _thickness_mm(self, value: float) -> None:
        self._thickness_value = value
        if getattr(self, "_outline_ready", False):
            self.invalidate_geometry()

    @property
    def _join_mode_pt1(self) -> str:
        """Join mode at pt1 (Auto / Butt / Solid); setter invalidates."""
        return self._join_mode_pt1_value

    @_join_mode_pt1.setter
    def _join_mode_pt1(self, value: str) -> None:
        self._join_mode_pt1_value = value
        if getattr(self, "_outline_ready", False):
            self.invalidate_geometry()

    @property
    def _join_mode_pt2(self) -> str:
        """Join mode at pt2 (Auto / Butt / Solid); setter invalidates."""
        return self._join_mode_pt2_value

    @_join_mode_pt2.setter
    def _join_mode_pt2(self, value: str) -> None:
        self._join_mode_pt2_value = value
        if getattr(self, "_outline_ready", False):
            self.invalidate_geometry()

    def __init__(self, pt1: QPointF, pt2: QPointF,
                 thickness_mm: float = DEFAULT_THICKNESS_MM,
                 color: str | QColor = "#cccccc"):
        super().__init__()
        self._pt1 = QPointF(pt1)
        self._pt2 = QPointF(pt2)
        self._thickness_mm = float(thickness_mm)
        self._colour: str = normalize_colour(color, _DEFAULT_COLOUR)
        self._fill_mode: str = FILL_NONE
        self.material_id: str = MATERIAL_NONE_ID
        self.phase: str = phase_registry.PHASE_NEW     # project-phasing PD1 (status id)

        # Shared display-manager attributes
        self.init_displayable()

        # Level / height (all in mm)
        self._base_level: str = DEFAULT_LEVEL
        self._top_level: str = "Level 2"
        self._height_mm: float = 3048.0            # 10 ft fallback
        self._base_offset_mm: float = 0.0          # offset from base level elevation
        self._top_offset_mm: float = 0.0           # offset from top level elevation

        # Alignment mode (centerline / left / right)
        self._alignment = ALIGN_CENTER

        # Per-endpoint join mode
        # Auto: solid at 2-wall corners, butt at T/cross intersections
        # Solid: continuous fill, no visible miter line
        # Butt: no miter extension
        self._join_mode_pt1 = "Auto"
        self._join_mode_pt2 = "Auto"
        self._solid_pt1: bool = False   # set by mitered_quad()
        self._solid_pt2: bool = False
        # Extra end vertices covering the junction wedge at 3-wall full
        # miters (between p1r→p1l / p2l→p2r in the fill polygon)
        self._end_wedge_pts1: list[QPointF] = []
        self._end_wedge_pts2: list[QPointF] = []

        # Wall openings (doors / windows)
        self.openings: list[WallOpening] = []

        self.name: str = ""
        self._mark: str = ""          # SB2b instance Mark (element-parameters.md Marks)
        # Stable identity for constraint refs (editor-build slice 2, design s2
        # "Wall uid"); a pasted copy re-mints it (Model_Space.paste_items).
        self._uid: str = uuid.uuid4().hex

        self.setZValue(-50)                         # behind pipes, above underlays
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        # One cached outline per wall (wall polish D2/D3)
        self._outline: WallOutline | None = None
        self._outline_key: tuple | None = None
        # (end, its partners, ids of its stop candidates) as last built
        self._join_tops: tuple = ()
        self._tee_tops: tuple = ()
        self._outline_ready = True
        self.invalidate_geometry()

    # ── Geometry helpers ─────────────────────────────────────────────────────

    @property
    def pt1(self) -> QPointF:
        return self._pt1

    @property
    def pt2(self) -> QPointF:
        return self._pt2

    @property
    def thickness_in(self) -> float:
        """Backward compat — returns thickness in inches."""
        return self._thickness_mm / 25.4

    @property
    def thickness_mm(self) -> float:
        return self._thickness_mm

    def centerline_length(self) -> float:
        dx = self._pt2.x() - self._pt1.x()
        dy = self._pt2.y() - self._pt1.y()
        return math.hypot(dx, dy)

    def centerline_angle_rad(self) -> float:
        dx = self._pt2.x() - self._pt1.x()
        dy = self._pt2.y() - self._pt1.y()
        return math.atan2(dy, dx)

    def normal(self) -> tuple[float, float]:
        """Unit normal perpendicular to centerline (rotated +90 deg)."""
        a = self.centerline_angle_rad()
        return (-math.sin(a), math.cos(a))

    def half_thickness_scene(self) -> float:
        """Half-thickness converted from mm to scene units.

        Uses the scene's ScaleManager (which always has valid defaults
        even before calibration: 1 px/mm, 1:100 scale).
        """
        half_mm = self._thickness_mm / 2.0
        sc = self.scene()
        if sc and hasattr(sc, "scale_manager"):
            sm = sc.scale_manager
            if sm.drawing_scale > 0:
                paper_mm = half_mm / sm.drawing_scale
                return sm.paper_to_scene(paper_mm)
        # Fallback when not attached to a scene
        return half_mm

    def quad_points(self) -> tuple[QPointF, QPointF, QPointF, QPointF]:
        """Return the four corner points of the wall rectangle (2D).

        Order: p1_left, p1_right, p2_right, p2_left  (CCW winding).

        Alignment controls how the wall rectangle relates to the click line
        (defined by _pt1 / _pt2):
          Center — click line is the wall centerline (default)
          Left   — click line is the right face; the wall extends toward +normal
          Right  — click line is the left face; the wall extends toward -normal
        """
        nx, ny = self.normal()
        ht = self.half_thickness_scene()
        if self._alignment == ALIGN_LEFT:
            # Left: axis is on the left face — wall extends rightward
            off_left = QPointF(nx * ht * 2, ny * ht * 2)
            off_right = QPointF(0, 0)
        elif self._alignment == ALIGN_RIGHT:
            # Right: axis is on the right face — wall extends leftward
            off_left = QPointF(0, 0)
            off_right = QPointF(-nx * ht * 2, -ny * ht * 2)
        else:  # ALIGN_CENTER
            off_left = QPointF(nx * ht, ny * ht)
            off_right = QPointF(-nx * ht, -ny * ht)
        return (
            self._pt1 + off_left,    # p1 left
            self._pt1 + off_right,   # p1 right
            self._pt2 + off_right,   # p2 right
            self._pt2 + off_left,    # p2 left
        )

    def _centerline_offset(self) -> QPointF:
        """Perpendicular offset from the drawn click line to the TRUE centerline.

        The click line (``_pt1``/``_pt2``) is the wall's alignment reference:
        for Center it IS the centerline; for Left/Right it is a face, and the
        true centerline sits half a thickness toward the wall body.  Derived
        from ``quad_points`` (k=+1 Left, -1 Right, 0 Center).
        """
        k = {ALIGN_CENTER: 0.0, ALIGN_LEFT: 1.0, ALIGN_RIGHT: -1.0}.get(
            self._alignment, 0.0)
        if k == 0.0:
            return QPointF(0.0, 0.0)
        nx, ny = self.normal()
        h = self.half_thickness_scene()
        return QPointF(nx * h * k, ny * h * k)

    @property
    def centerline_pt1(self) -> QPointF:
        """First endpoint of the true geometric centerline (derived)."""
        o = self._centerline_offset()
        return QPointF(self._pt1.x() + o.x(), self._pt1.y() + o.y())

    @property
    def centerline_pt2(self) -> QPointF:
        """Second endpoint of the true geometric centerline (derived)."""
        o = self._centerline_offset()
        return QPointF(self._pt2.x() + o.x(), self._pt2.y() + o.y())

    def centerline_midpoint(self) -> QPointF:
        """Midpoint of the true centerline (derived)."""
        a, b = self.centerline_pt1, self.centerline_pt2
        return QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)

    # ── Path rebuild (2D) ────────────────────────────────────────────────────

    # -- Outline cache (wall polish D2/D3) ------------------------------------

    def _rebuild_path(self):
        """Legacy name kept for duck-typed callers (model_space, manip_handle,
        sketch_adapters, tool_geometry, scene_tools, tests)."""
        self.invalidate_geometry()

    def _geometry_key(self) -> tuple:
        """Own inputs of the outline; a mismatch self-heals in
        ``outline_geometry()`` (neighbour changes arrive through
        ``invalidate_geometry``)."""
        return (self._pt1.x(), self._pt1.y(), self._pt2.x(), self._pt2.y(),
                self._thickness_mm, self._alignment,
                self.half_thickness_scene(), self._join_mode_pt1,
                self._join_mode_pt2, self.isVisible(), id(self.scene()))

    def _tee_guests(self, pool) -> list["WallSegment"]:
        """Walls with a free end inside this wall's band (they tee into it)."""
        band = self.half_thickness_scene() + MITER_TOL
        guests = []
        for other in pool:
            if sip.isdeleted(other):
                continue
            for ep in (other._pt1, other._pt2):
                if self.endpoint_near(ep, MITER_TOL) is not None:
                    continue
                if self.nearest_centerline_point(ep, band,
                                                 true_centerline=True) is not None:
                    guests.append(other)
                    break
        return guests

    def _body_polygons(self, e: dict) -> tuple[QPolygonF, QPolygonF]:
        """``(body, union_body)`` from a ``_join_ends`` result (D2)."""
        p1l, p1r, p2r, p2l = e["quad"]
        w1, w2 = e["wedge"]
        body = QPolygonF([p1l, p2l, *w2, p2r, p1r, *w1])
        u1, u2 = e["tee_union"]
        u1l, u1r = u1 if u1 is not None else (p1l, p1r)
        u2l, u2r = u2 if u2 is not None else (p2l, p2r)
        # A stopping end's union operand overlaps the joined walls with area
        # (run to the junction), as a coped tee's does.
        uw1 = e["union_wedge"][0] if e["union_wedge"][0] is not None else w1
        uw2 = e["union_wedge"][1] if e["union_wedge"][1] is not None else w2
        union_body = QPolygonF([u1l, u2l, *uw2, u2r, u1r, *uw1])
        for i in (0, 1):
            if e["tee_union"][i] is not None:
                union_body = self._clip_tee_extension(
                    union_body, body, e["hosts"][i])
        return body, union_body

    def _rebuild_outline(self, extra=None) -> None:
        """Recompute body, union body, faces, caps, centerline and
        neighbours; set ``path()`` to the body (HALO, hit, bounds -- D9).
        Stroke segments and corners are left for ``outline()`` (lazy)."""
        e = self._join_ends(extra)
        p1l, p1r, p2r, p2l = e["quad"]
        w1, w2 = e["wedge"]
        body, union_body = self._body_polygons(e)
        caps = []
        if not e["partners"][0] and e["hosts"][0] is None:
            caps.append((QPointF(p1l), QPointF(p1r)))
        if not e["partners"][1] and e["hosts"][1] is None:
            caps.append((QPointF(p2l), QPointF(p2r)))
        cands = [o for o, _ep in e["partners"][0]]
        cands += [o for o, _ep in e["partners"][1]]
        cands += [h for h in e["hosts"] if h is not None]
        cands += self._tee_guests(e["pool"])
        neighbours: list = []
        for w in cands:
            if w is not self and not any(w is n for n in neighbours):
                neighbours.append(w)
        self._outline = WallOutline(
            body=body, union_body=union_body, quad=e["quad"],
            solid=e["solid"], wedge=e["wedge"],
            faces=((QPointF(p1l), QPointF(p2l)), (QPointF(p1r), QPointF(p2r))),
            caps=tuple(caps),
            centerline=(self.centerline_pt1, self.centerline_pt2),
            neighbours=tuple(neighbours), seams=e["seams"])
        self._outline_key = self._geometry_key()
        self._join_tops = tuple(
            (i, mine, self._top_candidate_ids(i, mine))
            for i, mine in enumerate(e["partners"]) if mine)
        self._tee_tops = tuple((h, self._tops_differ(h))
                               for h in e["hosts"] if h is not None)
        # legacy paint-coordination readers
        self._solid_pt1, self._solid_pt2 = e["solid"]
        self._end_wedge_pts1, self._end_wedge_pts2 = w1, w2
        path = QPainterPath()
        path.addPolygon(body)
        path.closeSubpath()
        self.setPath(path)          # prepareGeometryChange + update
        for op in self.openings:
            op._reposition()

    def invalidate_geometry(self, extra=None) -> None:
        """Rebuild this wall's outline and every wall it joined before or
        joins after the change (design D3); clear the lazy strokes of those
        walls and of their neighbours (their unions read the new bodies)."""
        if sip.isdeleted(self):
            return
        old = list(self._outline.neighbours) if self._outline else []
        self._rebuild_outline(extra)
        touched = [self]
        for w in old + list(self._outline.neighbours):
            if sip.isdeleted(w) or any(w is t for t in touched):
                continue
            touched.append(w)
            w._rebuild_outline(self)
        for w in list(touched):
            for x in w._outline.neighbours:
                if not sip.isdeleted(x) and not any(x is t for t in touched):
                    touched.append(x)
        for w in touched:
            if w._outline is not None:
                w._outline.stroke_segments = None
                w._outline.corners = None
            w.update()

    def _top_candidate_ids(self, end_idx: int, mine: list) -> set[int]:
        """Identity of this end's stop candidates, for ``_stops_are_stale``."""
        return {id(w) for w in self._stop_candidates(
            [(self, end_idx), *mine])[0]}

    def _stops_are_stale(self) -> bool:
        """True when wall tops now give different stop candidates."""
        for end_idx, mine, seen in self._join_tops:
            if any(sip.isdeleted(w) for w, _ep in mine):
                return True
            if self._top_candidate_ids(end_idx, mine) != seen:
                return True
        return any(sip.isdeleted(h) or self._tops_differ(h) != seen
                   for h, seen in self._tee_tops)

    @staticmethod
    def refresh_stale_stops(walls: list["WallSegment"]) -> None:
        """Rebuild only the walls whose stop changed after a level move.

        Plan geometry reads a wall's height only through the stop decision,
        so a level edit that changes no decision costs no rebuild.  Every
        member of a changed junction is itself stale, and a tee's host keeps
        its body, so one rebuild per wall is enough; there is no fan-out as
        in ``invalidate_geometry``.
        Only those bodies move and a level edit changes no wall's neighbours,
        so this clears the same stale walls and neighbours of neighbours as
        ``invalidate_geometry``.
        """
        stale = [w for w in walls
                 if not sip.isdeleted(w) and w._stops_are_stale()]
        for w in stale:
            w._rebuild_outline()
        touched = {id(w): w for w in stale}
        for w in stale:
            for n in w._outline.neighbours:
                if not sip.isdeleted(n):
                    touched[id(n)] = n
        for w in touched.values():
            if w._outline is not None:
                w._outline.stroke_segments = None
                w._outline.corners = None
            w.update()

    def outline_geometry(self) -> WallOutline:
        """The cached outline without strokes (bodies, faces, caps)."""
        if self._outline is None or self._outline_key != self._geometry_key():
            self._rebuild_outline()
        return self._outline

    def outline(self) -> WallOutline:
        """The cached outline with stroke segments and visible corners
        (cluster union of this wall's and its neighbours' union bodies)."""
        o = self.outline_geometry()
        if o.stroke_segments is None:
            polys = [o.union_body]
            for w in o.neighbours:
                if not sip.isdeleted(w):
                    polys.append(w.outline_geometry().union_body)
            boundary = boundary_segments(cluster_union(polys))
            o.edge_strokes = stroke_segments(o.body, boundary)
            o.seam_strokes = self._seam_strokes(o)
            o.corners = visible_corners(o.body, boundary)
            o.stroke_segments = o.edge_strokes + list(o.seams)
        return o

    def _seam_pieces(self, o: WallOutline) -> list[SeamStroke]:
        """This stopper's seams, split once: the walls involved all read
        this same split, so no span of a seam can be drawn twice.  A wall
        that does not list this one back holds no record, so it owns no span:
        the span would go undrawn whenever that wall paints later."""
        live = [n for n in o.neighbours if not sip.isdeleted(n)
                and any(x is self for x in n.outline_geometry().neighbours)]
        out = []
        for seam in o.seams:
            touchers = [(n, stroke_segments(n.outline_geometry().body, [seam]))
                        for n in live]
            out += [SeamStroke(line, self, toucher)
                    for line, toucher in split_seam(seam, touchers)]
        return out

    def _seam_strokes(self, o: WallOutline) -> list[SeamStroke]:
        """Seam pieces that may fall to this wall to paint.

        A seam runs between two bodies, so whichever paints later fills over
        the half of the line on its side.  Each piece therefore belongs to
        the stopper and the joined wall under it, and only the later of the
        two draws it (``_paints_seam``): one stroke, over both fills.
        """
        out = self._seam_pieces(o)
        for n in o.neighbours:
            if not sip.isdeleted(n):
                g = n.outline_geometry()
                if g.seams:
                    out += [s for s in n._seam_pieces(g) if s.toucher is self]
        return out

    def _paints_seam(self, s: SeamStroke) -> bool:
        """True when this wall paints after the other wall under *s*.

        Same-z walls stack by insertion order, which only an add or remove
        changes, and that rebuilds these strokes; so the answer is found
        once per pair of z values (the model scene is NoIndex, and a lookup
        walks every item).
        """
        if (s.toucher is None or sip.isdeleted(s.stopper)
                or sip.isdeleted(s.toucher)):
            return True
        key = (s.stopper.zValue(), s.toucher.zValue())
        if key != s.painter_key:
            s.painter_key = key
            a, b = s.line
            mid = QRectF((a.x() + b.x()) / 2.0 - 1.0,
                         (a.y() + b.y()) / 2.0 - 1.0, 2.0, 2.0)
            s.painter = next(
                (it for it in self.scene().items(
                    mid, Qt.ItemSelectionMode.IntersectsItemBoundingRect,
                    Qt.SortOrder.DescendingOrder, QTransform())
                 if it is s.stopper or it is s.toucher),
                s.stopper)
        return s.painter is self

    def snap_geometry(self) -> dict:
        """Snap targets from the cached outline (design D10; named targets
        per snapping-engine.md s8.3).

        Returns:
            ``named``: ``(snap_type, point, name)`` -- true centerline ends
            and midpoint; the mitered quad corners that are visible outline
            corners (``face-<side>-corner-<A|B>``); any other visible
            outline corner on this wall (unnamed endpoint, e.g. a T-break);
            both face midpoints.
            ``faces``: the two full face lines (always foot-snappable).
            ``edges``: true centerline + caps on free ends (foot snaps
            gated by the Nearest toggle).
        """
        o = self.outline()
        c1, c2 = o.centerline
        named = [("endpoint", QPointF(c1), "centerline-end-A"),
                 ("endpoint", QPointF(c2), "centerline-end-B"),
                 ("midpoint", QPointF((c1.x() + c2.x()) / 2.0,
                                      (c1.y() + c2.y()) / 2.0),
                  "centerline-mid")]
        p1l, p1r, p2r, p2l = o.quad
        tol = WALL_OUTLINE_ON_EDGE_TOL

        def visible(pt):
            return any(abs(pt.x() - c.x()) <= tol and abs(pt.y() - c.y()) <= tol
                       for c in o.corners)

        quad_names = ((p1l, "face-left-corner-A"), (p1r, "face-right-corner-A"),
                      (p2l, "face-left-corner-B"), (p2r, "face-right-corner-B"))
        for pt, name in quad_names:
            if visible(pt):
                named.append(("endpoint", QPointF(pt), name))
        for c in o.corners:
            if not any(abs(c.x() - q.x()) <= tol and abs(c.y() - q.y()) <= tol
                       for q, _n in quad_names):
                named.append(("endpoint", QPointF(c), None))
        (fl1, fl2), (fr1, fr2) = o.faces
        named.append(("midpoint", QPointF((fl1.x() + fl2.x()) / 2.0,
                                          (fl1.y() + fl2.y()) / 2.0),
                      "face-left-mid"))
        named.append(("midpoint", QPointF((fr1.x() + fr2.x()) / 2.0,
                                          (fr1.y() + fr2.y()) / 2.0),
                      "face-right-mid"))
        return {"named": named, "faces": list(o.faces),
                "edges": [o.centerline, *o.caps]}

    def itemChange(self, change, value):
        """Scene add/remove and visibility (level switch, sheet viewport
        isolation) change who joins whom (design D3/D4)."""
        if (change == QGraphicsItem.GraphicsItemChange.ItemVisibleChange
                and not sip.isdeleted(self)):
            # Not yet applied: isVisible() is still the old state.
            self._visible_before = self.isVisible()
        result = super().itemChange(change, value)
        if sip.isdeleted(self):
            return result
        if change == QGraphicsItem.GraphicsItemChange.ItemVisibleHasChanged:
            # After an add Qt's queued polish pass sends the visibility pair
            # to every item that is not explicitly hidden, with nothing
            # changed; rebuilding on it made opening a project O(N^2).
            was = getattr(self, "_visible_before", None)
            self._visible_before = None
            if was is not None and was == self.isVisible():
                return result
        if (change in (QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged,
                       QGraphicsItem.GraphicsItemChange.ItemVisibleHasChanged)
                and getattr(self, "_outline_ready", False)):
            try:
                self.invalidate_geometry()
            except RuntimeError as e:
                # Hazard: a GC pass mid-rebuild on scene teardown can free this
                # wrapper; PyQt aborts the process on an exception escaping a
                # virtual. A dying wall has no geometry to maintain.
                if not (sip.isdeleted(self) or "has been deleted" in str(e)):
                    raise
        return result

    # ── Colour ───────────────────────────────────────────────────────────────

    @property
    def _color(self) -> QColor:
        """Canvas-resolved colour of the stored wall colour (legacy readers);
        paint and the 3D mesh resolve ``self._colour`` themselves."""
        return resolve_colour(self._colour)

    @_color.setter
    def _color(self, value) -> None:
        self._colour = normalize_colour(value, _DEFAULT_COLOUR)

    # ── Paint ────────────────────────────────────────────────────────────────

    def _line_colour(self) -> QColor:
        """Resolved outline colour."""
        dc = self._display_color            # None = unset; "" = No stroke
        return resolve_colour(self._colour if dc is None else dc, item=self)

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected

        o = self.outline()
        line_col = self._line_colour()
        pen = self._outline_pen(line_col)

        # Fill (own body only -- D7: differing fills meet at the miter)
        fill_brush = Qt.BrushStyle.NoBrush
        dfc = self._display_fill_color
        fill_src = self._colour if dfc is None else dfc     # "" = no colour
        if self._fill_mode == FILL_SOLID and fill_src != "":
            fill_color = resolve_colour(fill_src, item=self)
            if not getattr(self, "_paper_fill_opaque", False):
                fill_color.setAlpha(80)
            fill_brush = QBrush(fill_color)
        fill_poly = o.body

        # Fill, then the section hatch, then the outline on top: the hatch
        # body fills the whole polygon, so an outline stroked before it loses
        # its inner half on paper (AC1, wall-room-floor-system s6.2).
        if fill_brush != Qt.BrushStyle.NoBrush:
            # Antialiasing off for the body fill: two translucent bodies that
            # share a miter edge would each blend at ~50% coverage along it
            # and show a lighter seam (S1-F4).  Strokes keep the caller's hint.
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill_brush)
            painter.drawPolygon(fill_poly)
            painter.restore()

        # Section hatching — shown when fill mode is Section/Hatch, OR when
        # the view-range cut plane intersects this wall.
        _show_section = (self._fill_mode in (FILL_HATCH, FILL_SECTION)
                         or getattr(self, "_is_section_cut", False))
        if _show_section:
            from .displayable_item import draw_section_type
            clip = QPainterPath()
            clip.addPolygon(fill_poly)
            clip.closeSubpath()
            # The cut draws through its Fill Type (HF5): the type background
            # replaces the element fill; a By element pattern uses the
            # element's normal line colour and weight.
            draw_section_type(painter, clip, self.scene(), self,
                              materials.fill_type_of(self),
                              line_col,
                              # canvas cosmetic px width (paper uses hatch_line_mm)
                              line_width=pen.widthF() if pen.isCosmetic() else 1.0,
                              to_scene=self.sceneTransform())

        # Outline: only the cluster-union boundary on this wall's own edges
        # (D6) -- no seam line inside a joined junction.
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for a, b in o.edge_strokes:
            painter.drawLine(a, b)
        # A stop's seam: always the stopper's pen, whichever wall paints it.
        for s in o.seam_strokes:
            if self._paints_seam(s):
                stopper = s.stopper
                painter.setPen(stopper._outline_pen(stopper._line_colour()))
                painter.drawLine(*s.line)

        # Selection highlight -- same pieces (Task 6 gates it off paper)
        if shows_selection(self):
            sel_pen = QPen(_SELECTION_COLOR, 2)
            sel_pen.setCosmetic(True)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for a, b in o.stroke_segments:
                painter.drawLine(a, b)

    # ── Shape / hit-test ─────────────────────────────────────────────────────

    def shape(self) -> QPainterPath:
        path = self.path()
        stroker = QPainterPathStroker()
        stroker.setWidth(max(_scene_hit_width(self), self.half_thickness_scene() * 2))
        return stroker.createStroke(path)

    # ── Grip points for interactive editing ───────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        mid = QPointF(
            (self._pt1.x() + self._pt2.x()) / 2,
            (self._pt1.y() + self._pt2.y()) / 2,
        )
        # Width grip on the far face midpoint
        p1l, p1r, p2r, p2l = self.quad_points()
        if self._alignment == ALIGN_RIGHT:
            # Right-aligned: far face is the right (negative-normal) side
            width_grip = QPointF((p2r.x() + p1r.x()) / 2,
                                 (p2r.y() + p1r.y()) / 2)
        else:
            # Center/Left: far face is the left (positive-normal) side
            width_grip = QPointF((p1l.x() + p2l.x()) / 2,
                                 (p1l.y() + p2l.y()) / 2)
        return [QPointF(self._pt1), QPointF(self._pt2), mid, width_grip]

    def apply_grip(self, index: int, new_pos: QPointF):
        if index == 0:
            self._pt1 = QPointF(new_pos)
        elif index == 1:
            self._pt2 = QPointF(new_pos)
        elif index == 2:
            # Move whole wall
            old_mid = QPointF(
                (self._pt1.x() + self._pt2.x()) / 2,
                (self._pt1.y() + self._pt2.y()) / 2,
            )
            dx = new_pos.x() - old_mid.x()
            dy = new_pos.y() - old_mid.y()
            self._pt1 = QPointF(self._pt1.x() + dx, self._pt1.y() + dy)
            self._pt2 = QPointF(self._pt2.x() + dx, self._pt2.y() + dy)
        elif index == 3:
            # Width grip — drag perpendicular to wall to adjust thickness
            nx, ny = self.normal()
            mid_x = (self._pt1.x() + self._pt2.x()) / 2
            mid_y = (self._pt1.y() + self._pt2.y()) / 2
            d = abs((new_pos.x() - mid_x) * nx + (new_pos.y() - mid_y) * ny)
            ht_scene = self.half_thickness_scene()
            if ht_scene > 0 and d > 0:
                if self._alignment == ALIGN_CENTER:
                    new_thickness = self._thickness_mm * (d / ht_scene)
                else:
                    new_thickness = self._thickness_mm * (d / (2 * ht_scene))
                self._thickness_mm = max(new_thickness, 25.4)  # min ~1 inch
        self.invalidate_geometry()

    def manip_handles(self):
        """U3: [pt1, pt2, mid(move), width] as live-apply manipulator grips.

        Endpoints (0, 1) render round + Ctrl-angle-constrain against the opposite
        endpoint AND propagate to joined walls (``WallEndpointGripHandle``); the
        mid grip (2) is a round move grip (translates the whole wall); the width
        grip (3) is a square thickness grip. The manipulator renders/hit-tests/
        commits them; the legacy grip paths skip this item (coexistence gate).
        """
        from .manip_handle import (GripHandle, TranslateGripHandle,
                                   WallEndpointGripHandle)
        return [
            WallEndpointGripHandle(self, 0, opposite_index=1),
            WallEndpointGripHandle(self, 1, opposite_index=0),
            TranslateGripHandle(self, 2, circular=True),   # S2 handle snap
            GripHandle(self, 3, circular=False),
        ]

    def grip_render_angle(self, index: int) -> float:
        """U3 grip-shape hook: rotate the SQUARE width grip (index 3) to the
        wall's centerline orientation so its edges align with the wall (like
        RectangleItem's edge-midpoint grips / EllipseItem's axis grips).

        Returns the Y-up angle of the centerline; the round endpoint/centre grips
        (0, 1, 2) ignore it (a disc is rotation-invariant, so ``GripHandle``
        short-circuits before calling this). A square is 90 deg-symmetric, so the
        centerline angle aligns it regardless of the face-perpendicular offset.
        """
        return -math.degrees(self.centerline_angle_rad())

    def translate(self, dx: float, dy: float):
        self._pt1 = QPointF(self._pt1.x() + dx, self._pt1.y() + dy)
        self._pt2 = QPointF(self._pt2.x() + dx, self._pt2.y() + dy)
        self.invalidate_geometry()

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        """Baked rigid rotate of the wall centerline about ``pivot`` (Y-up CCW+).

        Mirrors :meth:`translate`: rotate both endpoints, then rebuild (miters +
        hosted openings follow).  No lock check — ``translate`` has none either.
        """
        from .cad_math import CAD_Math
        self._pt1 = CAD_Math.rotate_point(self._pt1, pivot, -angle_deg)
        self._pt2 = CAD_Math.rotate_point(self._pt2, pivot, -angle_deg)
        self.invalidate_geometry()

    # ── Properties API ───────────────────────────────────────────────────────

    def vertical_extent(self, level_manager) -> tuple[float, float]:
        """``(bot, top)`` world-mm vertical extent (wall-room-floor-system, Vertical extent).

        Pure: resolves through *level_manager* (None = no levels). Base = base
        level elevation (0 when missing) + base offset; top = top level
        elevation + top offset, or base + own height when the top level is
        missing.
        """
        def elev(name):
            lvl = level_manager.get(name) if level_manager is not None else None
            return None if lvl is None else lvl.elevation
        base_e = elev(self._base_level)
        base_z = (0.0 if base_e is None else base_e) + self._base_offset_mm
        top_e = elev(self._top_level)
        top_z = (base_z + self._height_mm if top_e is None
                 else top_e + self._top_offset_mm)
        return (base_z, top_z)

    def z_range_mm(self) -> tuple[float, float]:
        """Vertical extent through the scene's level manager."""
        sc = self.scene()
        return self.vertical_extent(getattr(sc, "_level_manager", None) if sc else None)

    def _computed_height_mm(self) -> float:
        """Wall height from its vertical extent."""
        bot, top = self.z_range_mm()
        return top - bot

    def get_properties(self) -> dict:
        height_mm = self._computed_height_mm()
        return {
            "Type":         {"type": "label",     "value": "Wall"},
            "Name":         {"type": "string",    "value": self.name},
            "Mark":         {"type": "string",    "value": self._mark},
            phase_registry.ROW_KEY: phase_registry.property_row(self),
            "Colour":       {"type": "color",     "value": self._colour},
            "Thickness":    {"type": "dimension", "value": self._fmt(self._thickness_mm),
                             "value_mm": self._thickness_mm},
            "Fill Mode":    {"type": "enum",      "value": self._fill_mode,
                             "options": ["None", "Solid", "Section"]},
            materials.ROW_KEY: materials.property_row(self),
            "Alignment":    {"type": "enum",      "value": self._alignment,
                             "options": ["Center", "Left", "Right"]},
            "Base Level":   {"type": "level_ref", "value": self._base_level},
            "Base Offset":  {"type": "dimension", "value": self._fmt(self._base_offset_mm),
                             "value_mm": self._base_offset_mm},
            "Top Level":    {"type": "level_ref", "value": self._top_level},
            "Top Offset":   {"type": "dimension", "value": self._fmt(self._top_offset_mm),
                             "value_mm": self._top_offset_mm},
            "Height":       {"type": "label",     "value": self._fmt(height_mm)},
            "Join Start":   {"type": "enum",      "value": self._join_mode_pt1,
                             "options": ["Auto", "Butt", "Solid"]},
            "Join End":     {"type": "enum",      "value": self._join_mode_pt2,
                             "options": ["Auto", "Butt", "Solid"]},
        }

    def _parse_dim(self, value) -> float | None:
        """Parse a dimension value (display-formatted or raw) to mm.

        If *value* is already a numeric type (float/int), it is treated as
        mm and returned directly.  String values are parsed through the
        ScaleManager (supports feet-inches, mm, m, etc.).
        """
        if isinstance(value, (int, float)):
            return float(value)
        from .scale_manager import ScaleManager
        sc = self.scene()
        sm = sc.scale_manager if sc and hasattr(sc, "scale_manager") else self._scale_manager_ref
        if sm:
            parsed = ScaleManager.parse_dimension(str(value), sm.bare_number_unit())
            if parsed is not None:
                return parsed
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def set_property(self, key: str, value):
        if key == "Name":
            self.name = str(value)
        elif key == "Mark":
            self._mark = str(value)
        elif key == "Colour":
            from .stroke_style import is_block_only_colour_label
            if is_block_only_colour_label(value):
                return                     # WM3 D4: a placed block's row label
            self._colour = normalize_colour(value, _DEFAULT_COLOUR)
            self.update()
        elif key == "Thickness":
            parsed = self._parse_dim(value)
            if parsed is not None:
                self._thickness_mm = max(parsed, 1.0)
                self.invalidate_geometry()
                self.update()
        elif key == "Fill Mode":
            self._fill_mode = str(value)
            self.update()
        elif key == materials.ROW_KEY:
            materials.set_from_row(self, value)
        elif key == phase_registry.ROW_KEY:
            phase_registry.set_from_row(self, value)
        elif key == "Alignment":
            self._alignment = str(value)
            self.invalidate_geometry()
            self.update()
        elif key == "Base Level":
            self._base_level = str(value)
            self.level = str(value)
            self._height_mm = self._computed_height_mm()
            self.invalidate_geometry()
            self.update()
        elif key == "Base Offset":
            parsed = self._parse_dim(value)
            if parsed is not None:
                self._base_offset_mm = parsed
                self._height_mm = self._computed_height_mm()
                self.invalidate_geometry()
                self.update()
        elif key == "Top Level":
            self._top_level = str(value)
            self._height_mm = self._computed_height_mm()
            self.invalidate_geometry()
            self.update()
        elif key == "Top Offset":
            parsed = self._parse_dim(value)
            if parsed is not None:
                self._top_offset_mm = parsed
                self._height_mm = self._computed_height_mm()
                self.invalidate_geometry()
                self.update()
        elif key in ("Join Start", "Join End"):
            if str(value) in ("Auto", "Butt", "Solid"):
                if key == "Join Start":
                    self._join_mode_pt1 = str(value)
                else:
                    self._join_mode_pt2 = str(value)
                self.invalidate_geometry()
                self.update()

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        openings_data = []
        for op in self.openings:
            openings_data.append(op.to_dict())
        d = {
            "type":          "wall",
            "pt1":           [self._pt1.x(), self._pt1.y()],
            "pt2":           [self._pt2.x(), self._pt2.y()],
            "thickness_mm":  self._thickness_mm,
            "color":         self._colour,
            "fill_mode":     self._fill_mode,
            "alignment":     self._alignment,
            "base_level":    self._base_level,
            "top_level":     self._top_level,
            "height_mm":     self._height_mm,
            "base_offset_mm": self._base_offset_mm,
            "top_offset_mm":  self._top_offset_mm,
            "level":         self.level,
            "name":          self.name,
            "mark":          self._mark,
            "uid":           self._uid,
            "join_mode_pt1": self._join_mode_pt1,
            "join_mode_pt2": self._join_mode_pt2,
            "openings":      openings_data,
        }
        materials.write_element(self, d)
        phase_registry.write_element(self, d)
        return self.display_overrides_to_dict(d)       # L283: Hide / colours

    @classmethod
    def from_dict(cls, data: dict) -> "WallSegment":
        FT = 304.8
        pt1 = QPointF(data["pt1"][0], data["pt1"][1])
        pt2 = QPointF(data["pt2"][0], data["pt2"][1])
        # Accept new mm key; fall back to old in key with conversion
        if "thickness_mm" in data:
            thick_mm = data["thickness_mm"]
        elif "thickness_in" in data:
            thick_mm = data["thickness_in"] * 25.4
        else:
            thick_mm = DEFAULT_THICKNESS_MM
        thick_mm = max(thick_mm, 1.0)
        wall = cls(pt1, pt2, thickness_mm=thick_mm,
                   color=data.get("color", "#cccccc"))
        wall._fill_mode = data.get("fill_mode", FILL_NONE)
        wall._alignment = data.get("alignment", ALIGN_CENTER)
        # Migration: rename Interior/Exterior → Left/Right
        if wall._alignment == "Interior":
            wall._alignment = "Left"
        elif wall._alignment == "Exterior":
            wall._alignment = "Right"
        wall._base_level = data.get("base_level", DEFAULT_LEVEL)
        wall._top_level = data.get("top_level", "Level 2")
        if "height_mm" in data:
            wall._height_mm = data["height_mm"]
        elif "height_ft" in data:
            wall._height_mm = data["height_ft"] * FT
        else:
            wall._height_mm = 3048.0
        if "base_offset_mm" in data:
            wall._base_offset_mm = data["base_offset_mm"]
        elif "base_offset_ft" in data:
            wall._base_offset_mm = data["base_offset_ft"] * FT
        else:
            wall._base_offset_mm = 0.0
        if "top_offset_mm" in data:
            wall._top_offset_mm = data["top_offset_mm"]
        elif "top_offset_ft" in data:
            wall._top_offset_mm = data["top_offset_ft"] * FT
        else:
            wall._top_offset_mm = 0.0
        wall.level = data.get("level", DEFAULT_LEVEL)
        wall.name = data.get("name", "")
        wall._mark = data.get("mark", "")
        if data.get("uid"):                     # legacy dicts keep the minted uid
            wall._uid = str(data["uid"])
        # Per-endpoint join modes (backward compat: old "join_mode" applies to both)
        legacy = data.get("join_mode", "Auto")
        wall._join_mode_pt1 = data.get("join_mode_pt1", legacy)
        wall._join_mode_pt2 = data.get("join_mode_pt2", legacy)
        # Migration: Miter removed — map to Solid (preserves corner geometry)
        if wall._join_mode_pt1 == "Miter":
            wall._join_mode_pt1 = "Solid"
        if wall._join_mode_pt2 == "Miter":
            wall._join_mode_pt2 = "Solid"
        wall.display_overrides_from_dict(data)         # L283 (canonical_id on section_type)
        materials.read_element(wall, data)             # M7: after the canonical_id re-point
        phase_registry.read_element(wall, data)
        # Openings restored by caller after wall_opening module is available
        return wall

    # ── 3D mesh generation ───────────────────────────────────────────────────

    def z_span_mm(self, level_manager=None) -> tuple[float, float]:
        """``(base_z, top_z)`` for the 3D mesh: the vertical extent (6.5)."""
        return self.vertical_extent(level_manager)

    def pool_3d(self) -> list["WallSegment"]:
        """Walls the 3D view shows (D2): the ``_display_overrides`` visible
        flag only -- the plan's level visibility does not apply."""
        sc = self.scene()
        if sc is None or not hasattr(sc, "_walls"):
            return []
        return [w for w in sc._walls
                if w is not self and not sip.isdeleted(w) and w.scene() is sc
                and (getattr(w, "_display_overrides", None) or {}).get(
                    "visible") is not False]

    def _band_neighbours(self, e: dict, members) -> list["WallSegment"]:
        """Walls joined, hosting or teeing into this wall in a band (*e* is
        its ``_join_ends`` over *members*)."""
        nbrs = [o for o, _ep in e["partners"][0] + e["partners"][1]]
        nbrs += [h for h in e["hosts"] if h is not None]
        nbrs += self._tee_guests(members)
        return nbrs

    def _solid_bands(self, pool, level_manager) -> list[tuple]:
        """``[(body, z0, z1, e)]`` per height band (D4), identical bands merged.

        Breakpoints: own span plus the spans of every endpoint partner, tee
        host and tee guest reached through *pool*; each band joins only the
        pool walls whose span covers the band's mid height.
        """
        pool = [w for w in pool if w is not self]
        z0, z1 = self.z_span_mm(level_manager)
        if z1 - z0 < 1.0:
            return []
        full = self._join_ends(pool=pool)
        near = [o for o, _ep in full["partners"][0] + full["partners"][1]]
        near += [h for h in full["hosts"] if h is not None]
        near += self._tee_guests(pool)
        cuts = {z0, z1}
        spans = {id(w): w.z_span_mm(level_manager) for w in pool}
        for w in near:
            for z in spans[id(w)]:
                if z0 < z < z1:
                    cuts.add(z)
        zs = sorted(cuts)
        out: list[tuple] = []
        for za, zb in zip(zs, zs[1:]):
            zm = (za + zb) / 2.0
            members = [w for w in pool
                       if spans[id(w)][0] <= zm <= spans[id(w)][1]]
            e = self._join_ends(pool=members)
            body, _u = self._body_polygons(e)
            # Merge only when the body AND the walls joined/unioned for the
            # edges are equal: a neighbour that ends mid-wall must keep its
            # own band so the outline above it is drawn without its union.
            key = ([(round(p.x(), 6), round(p.y(), 6)) for p in body],
                   frozenset(id(n) for n in self._band_neighbours(e, members)))
            if out and out[-1][4] == key:
                out[-1] = (out[-1][0], out[-1][1], zb, out[-1][3], key)
            else:
                out.append((body, za, zb, e, key))
        return [(b, za, zb, e) for b, za, zb, e, _k in out]

    def _to_mm(self):
        """Scene point -> (x_mm, -y_mm) for 3D (Y negated, 6.5)."""
        sc = self.scene()
        sm = sc.scale_manager if sc and hasattr(sc, "scale_manager") else None
        cal = sm is not None and sm.is_calibrated and sm.drawing_scale > 0

        def f(pt: QPointF) -> tuple[float, float]:
            if cal:
                return (sm.scene_to_real(pt.x()), -sm.scene_to_real(pt.y()))
            return (pt.x(), -pt.y())
        return f

    def _opening_cuts(self, level_manager) -> list[tuple]:
        """Per opening: the plan gap rect (width x full thickness, as
        ``WallOpening._gap_rect`` draws it, measured along from
        ``centerline_pt1``) centred on the wall axis, in scene coords,
        the opening's vertical extent clamped to the wall's (D5):
        ``[(QPointF x4, z0, z1)]``."""
        base_z, top_z = self.z_span_mm(level_manager)
        a, b = self.centerline_pt1, self.centerline_pt2
        length = math.hypot(b.x() - a.x(), b.y() - a.y())
        if length < 1e-9:
            return []
        ux, uy = (b.x() - a.x()) / length, (b.y() - a.y()) / length
        nx, ny = -uy, ux
        sc = self.scene()
        sm = sc.scale_manager if sc and hasattr(sc, "scale_manager") else None
        cal = sm is not None and sm.is_calibrated and sm.drawing_scale > 0
        mm_per_scene = sm.scene_to_real(1.0) if cal else 1.0
        half_t = self.half_thickness_scene() + CUT_MARGIN_MM / mm_per_scene
        out = []
        for op in self.openings:
            half_w = (op._width_mm / mm_per_scene) / 2.0
            # On the wall axis: the cut is full thickness, so the opening's
            # cross offset / alignment shift (D5, Q4) does not move it.
            cx = a.x() + ux * op._offset_along
            cy = a.y() + uy * op._offset_along
            o0, o1 = op.vertical_extent(level_manager)
            z0, z1 = max(base_z, o0), min(top_z, o1)
            if z1 <= z0:
                continue
            rect = [QPointF(cx + ux * su * half_w + nx * sv * half_t,
                            cy + uy * su * half_w + ny * sv * half_t)
                    for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            out.append((rect, z0, z1))
        return out

    def get_3d_mesh(self, level_manager=None, pool=None) -> dict | None:
        """Exact solid of this wall for the 3D view (3D wall solids design).

        Bands of the plan body joined against *pool* (default ``pool_3d()``),
        minus the opening cuts; ``edges`` follow the plan outline rule (D7).

        Args:
            level_manager: Resolves the base / top levels to z.
            pool: The 3D join pool. It must hold this wall's
                ``join_neighbourhoods`` ring (the view passes exactly that):
                a narrower pool can change joins and edges (a wrong mesh);
                walls beyond the ring only cost time. None: this wall's
                ring within ``pool_3d()`` (``join_ring``).

        Returns:
            ``{"vertices", "faces", "color", "edges"}`` or None (degenerate).
        """
        if pool is None:
            pool = join_ring(self, self.pool_3d())
        else:
            pool = [w for w in pool if w is not self]
        bands = self._solid_bands(pool, level_manager)
        if not bands:
            return None
        to_mm = self._to_mm()
        cuts = self._opening_cuts(level_manager)
        solid = build_solid(
            [([to_mm(p) for p in body], z0, z1) for body, z0, z1, _e in bands],
            [([to_mm(p) for p in rect], z0, z1) for rect, z0, z1 in cuts])
        if solid is None:
            return None
        # The 3D view has no paper: a token resolves with canvas semantics;
        # "" (no colour) is alpha 0 and View3D draws no surface for it.
        c = resolve_colour(self._colour)
        solid["color"] = (c.redF(), c.greenF(), c.blueF(),
                          0.0 if self._colour == "" else 0.9)
        solid["edges"] = self._solid_edges(bands, cuts, pool, level_manager)
        return solid

    def _solid_edges(self, bands, cuts, pool, level_manager) -> list:
        """3D edge segments in mm following the plan outline rule (D7)."""
        pool = [w for w in pool if w is not self]
        to_mm = self._to_mm()
        tol = WALL_OUTLINE_ON_EDGE_TOL

        def seg2(line):
            return (to_mm(line[0]), to_mm(line[1]))

        spans = {id(w): w.z_span_mm(level_manager) for w in pool}
        per_band = []                 # (z0, z1, pieces 2D, corners 2D)
        for body, z0, z1, e in bands:
            zm = (z0 + z1) / 2.0
            members = [w for w in pool
                       if spans[id(w)][0] <= zm <= spans[id(w)][1]]
            _b, union = self._body_polygons(e)
            nbrs = self._band_neighbours(e, members)
            polys = [union]
            for n in nbrs:
                ne = n._join_ends(pool=[m for m in members if m is not n] + [self])
                polys.append(n._body_polygons(ne)[1])
            boundary = boundary_segments(cluster_union(polys))
            pieces = [seg2(l) for l in stroke_segments(body, boundary)]
            pieces += [seg2(l) for l in e["seams"]]
            corners = [to_mm(p) for p in visible_corners(body, boundary)]
            for l in e["seams"]:
                corners += [to_mm(l[0]), to_mm(l[1])]
            per_band.append((z0, z1, pieces, corners))

        cut_faces = []                # per cut: its two face lines (2D mm)
        for rect, cz0, cz1 in cuts:
            r = [to_mm(p) for p in rect]
            cut_faces.append(([(r[0], r[1]), (r[3], r[2])], cz0, cz1, r))

        def minus_cuts(pieces, z):
            for faces, cz0, cz1, _r in cut_faces:
                if cz0 - 1e-6 <= z <= cz1 + 1e-6:
                    pieces = subtract_collinear(pieces, faces, CUT_MARGIN_MM + tol)
            return pieces

        out = []
        levels = sorted({z for z0, z1, _p, _c in per_band for z in (z0, z1)})
        for z in levels:
            below = next((p for z0, z1, p, _c in per_band if z1 == z), [])
            above = next((p for z0, z1, p, _c in per_band if z0 == z), [])
            horiz = (subtract_collinear(below, above, tol)
                     + subtract_collinear(above, below, tol))
            for (ax, ay), (bx, by) in minus_cuts(horiz, z):
                out.append(((ax, ay, z), (bx, by, z)))
        verts: dict = {}
        for z0, z1, _p, corners in per_band:
            uniq = {(round(x, 3), round(y, 3)) for x, y in corners}
            for k in sorted(uniq):
                if k in verts and abs(verts[k][1] - z0) < 1e-6:
                    verts[k] = (verts[k][0], z1)
                else:
                    if k in verts:
                        out.append(((k[0], k[1], verts[k][0]),
                                    (k[0], k[1], verts[k][1])))
                    verts[k] = (z0, z1)
        for (x, y), (z0, z1) in verts.items():
            out.append(((x, y, z0), (x, y, z1)))
        out += self._reveal_edges(bands, cut_faces)
        return out

    def _reveal_edges(self, bands, cut_faces) -> list:
        """Per cut, the edges of its own surfaces inside the host body (D7.4)."""
        out = []
        to_mm = self._to_mm()
        zlo, zhi = bands[0][1], bands[-1][2]
        for _faces, cz0, cz1, r in cut_faces:
            band = next((b for b, z0, z1, _e in bands
                         if z0 <= (cz0 + cz1) / 2 <= z1), None)
            if band is None:
                continue
            poly = [to_mm(p) for p in band]
            # r: [u0 face-, u1 face-, u1 face+, u0 face+] overshooting by
            # CUT_MARGIN_MM; pull each corner back onto the body face
            inner = clip_depth(r, poly)
            for (x, y) in inner:
                out.append(((x, y, cz0), (x, y, cz1)))                 # jambs
            for z in (cz0, cz1):
                # A sill/head on the wall's own bottom/top leaves the face
                # open there: no face-line edge (i = 0, 2) -- the plan
                # outline is broken across the opening.
                open_face = z <= zlo + 1e-6 or z >= zhi - 1e-6
                for i in range(4):
                    if open_face and i in (0, 2):
                        continue
                    a, b = inner[i], inner[(i + 1) % 4]
                    out.append(((a[0], a[1], z), (b[0], b[1], z)))      # sill/head
        return out

    # ── Miter join ────────────────────────────────────────────────────────────

    @staticmethod
    def _intersect_lines(p1: QPointF, p2: QPointF,
                         p3: QPointF, p4: QPointF) -> QPointF | None:
        """Intersect infinite lines (p1→p2) and (p3→p4). None if parallel."""
        dx1 = p2.x() - p1.x()
        dy1 = p2.y() - p1.y()
        dx2 = p4.x() - p3.x()
        dy2 = p4.y() - p3.y()
        denom = dx1 * dy2 - dy1 * dx2
        if abs(denom) < 1e-10:
            return None  # parallel
        t = ((p3.x() - p1.x()) * dy2 - (p3.y() - p1.y()) * dx2) / denom
        return QPointF(p1.x() + t * dx1, p1.y() + t * dy1)

    def _resolve_join_mode(self, endpoint_idx: int, num_walls_at_point: int) -> str:
        """Resolve the effective join mode for an endpoint.

        Auto defaults:
          - 2 walls at corner → Solid (continuous fill, no miter line)
          - 3+ walls (T or cross) → Butt (clean termination)
          - 1 wall (free end) → Butt
        """
        mode = self._join_mode_pt1 if endpoint_idx == 0 else self._join_mode_pt2
        if mode != "Auto":
            return mode
        # Auto logic
        if num_walls_at_point == 2:
            return "Solid"
        return "Butt"

    def mitered_quad(self) -> tuple[QPointF, QPointF, QPointF, QPointF]:
        """The cached mitered corners (p1l, p1r, p2r, p2l) of ``outline()``.
        ``_solid_pt1`` / ``_solid_pt2`` are kept current by the rebuild."""
        return self.outline_geometry().quad

    def snap_quad_points(self) -> tuple[QPointF, QPointF, QPointF, QPointF]:
        """Same corners as ``mitered_quad()`` (readers: section_scene,
        tool_geometry, tests)."""
        return self.outline_geometry().quad

    def _join_pool(self, extra=None) -> list["WallSegment"]:
        """Walls this wall may join (design D4): same scene and visible on
        the active view (``LevelManager.apply_to_scene`` and sheet viewport
        isolation express level visibility as ``isVisible()``).

        *extra* adds a wall that is already in the scene but not yet in
        ``scene._walls`` -- load and placement call ``addItem`` before the
        append, and ``itemChange`` refreshes neighbours in between.
        """
        sc = self.scene()
        if sc is None or not hasattr(sc, "_walls"):
            return []
        cands = list(sc._walls)
        if extra is not None and not any(w is extra for w in cands):
            cands.append(extra)
        return [w for w in cands
                if w is not self and not sip.isdeleted(w)
                and w.scene() is sc and w.isVisible()]

    def _junction_arm(self, end_idx: int) -> JunctionArm | None:
        """This wall's end *end_idx* as a pie arm (wall_outline.junction_pie).

        At pt1 the outward vector is pt1->pt2 and the +90 deg face is the
        left face; at pt2 the vector flips and so do the faces.
        """
        p1l, p1r, p2r, p2l = self.quad_points()
        dx = self._pt2.x() - self._pt1.x()
        dy = self._pt2.y() - self._pt1.y()
        length = math.hypot(dx, dy)
        if length < 1e-9:
            return None
        if end_idx == 0:
            return JunctionArm(self, dx / length, dy / length,
                               (p1l, p2l), (p1r, p2r))
        return JunctionArm(self, -dx / length, -dy / length,
                           (p1r, p2r), (p1l, p2l))

    def _pie_corners(self, my_idx: int, my_pt: QPointF, partners,
                     max_miter: float):
        """N-way pie corners for one end (design D5).

        Returns ``(int_left, int_right, hub)`` -- left/right as this wall's
        ``quad_points`` faces -- or None (degenerate: caller keeps Butt).
        """
        arms = [self._junction_arm(my_idx)]
        arms += [other._junction_arm(other_ep) for other, other_ep in partners]
        if any(a is None for a in arms):
            return None
        res = junction_pie(arms, my_pt, max_miter)
        if res is None:
            return None
        corners, hub = res
        if self not in corners:      # this end's pair fell back (Edge Cases)
            return None
        ccw, cw = corners[self]
        if my_idx == 0:
            return ccw, cw, hub          # (p1l, p1r)
        return cw, ccw, hub              # (p2l, p2r)

    def _tops_differ(self, other: "WallSegment") -> bool:
        """True when the tops differ (R8)."""
        mine, theirs = self.z_range_mm(), other.z_range_mm()
        return abs(mine[1] - theirs[1]) > WALL_JOIN_TOP_TOL_MM

    def _tee_host(self, my_pt: QPointF, walls) -> "WallSegment | None":
        """Nearest wall whose centerline passes within its half thickness
        (+ ``MITER_TOL``) of *my_pt*, away from that wall's own ends."""
        host = None
        host_dist = float("inf")
        for other in walls:
            if other is self:
                continue
            band = other.half_thickness_scene() + MITER_TOL
            proj = other.nearest_centerline_point(my_pt, band,
                                                  true_centerline=True)
            if proj is None:
                continue
            if self._mutual_tee(my_pt, other, walls):
                continue
            d = math.hypot(my_pt.x() - proj.x(), my_pt.y() - proj.y())
            if d < host_dist:
                host_dist = d
                host = other
        return host

    def _mutual_tee(self, my_pt: QPointF, other: "WallSegment",
                    pool) -> bool:
        """True when a FREE end of *other* (no endpoint partner in *pool*)
        would tee into this wall at the same junction as *my_pt* (two ends
        lying on each other's faces at an L).  Neither tees then: they
        cannot cope to each other without leaving a notch (S1-F2)."""
        band_self = self.half_thickness_scene() + MITER_TOL
        reach = band_self + other.half_thickness_scene() + MITER_TOL
        for ep in (other._pt1, other._pt2):
            if math.hypot(ep.x() - my_pt.x(), ep.y() - my_pt.y()) > reach:
                continue
            if any(w is not other and w.endpoint_near(ep, MITER_TOL)
                   is not None for w in pool):
                continue            # that end is joined: it never tees
            if self.nearest_centerline_point(ep, band_self,
                                             true_centerline=True) is not None:
                return True
        return False

    def _junction_stops(self, my_idx: int, mine: list) -> list["WallSegment"]:
        """Walls that stop at this junction; [] for a plain join.

        Every member computes the same answer: the rule reads only the
        member set, never which member is asking.

        Args:
            my_idx: This wall's end at the junction.
            mine: Endpoint partners as ``(wall, endpoint_idx)``.

        Returns:
            Butt walls plus lower Auto walls, or [] when too few walls
            would stay joined.
        """
        members = [(self, my_idx), *mine]

        def valid(stops):
            left = len(members) - len(stops)
            return bool(stops) and left >= (1 if len(members) == 2 else 2)

        for candidate in self._stop_candidates(members):
            if valid(candidate) and self._stops_fit(members, candidate):
                return candidate
        return []

    def _stop_candidates(self, members: list) -> tuple[list, list]:
        """``(butts + lower Auto walls, butts)``, before any geometry check.

        Only the first list can move with wall tops; a level edit cannot
        change whether a stop fits, so this is all it needs to compare.
        """
        def raw(wall, ep):
            return wall._join_mode_pt1 if ep == 0 else wall._join_mode_pt2

        butts = [w for w, ep in members if raw(w, ep) == "Butt"]
        lower = self._lower_auto_walls(members, raw)
        return (butts + [w for w in lower if not any(w is b for b in butts)],
                butts)

    @staticmethod
    def _stops_fit(members: list, stops: list) -> bool:
        """True when every wall can take its part of the stop.

        Decided once for the whole junction, so a stop never lands on one
        wall only: a stop that does not fit leaves today's join.
        """
        joined = [m for m in members if not any(m[0] is w for w in stops)]
        clamp = MAX_MITER_FACTOR * max(
            w.half_thickness_scene() for w, _ep in members)

        def end_pt(wall, ep):
            return wall._pt1 if ep == 0 else wall._pt2

        for wall, ep in members:
            if (any(wall is w for w in stops)
                    and wall._stop_corners(ep, end_pt(wall, ep), joined,
                                           wall.quad_points(), clamp) is None):
                return False
        if len(members) == 2:
            wall, ep = joined[0]
            return wall._tee_cope_corners(
                ep, end_pt(wall, ep), stops[0], wall.quad_points(), clamp,
                far=True) is not None
        if len(joined) == 2:
            (a, a_ep), (b, b_ep) = joined
            for wall, ep, other, other_ep in ((a, a_ep, b, b_ep),
                                              (b, b_ep, a, a_ep)):
                corners = wall._mitre_corners(ep, other, other_ep,
                                              wall.quad_points())
                if corners is None:
                    continue    # a straight run needs no mitre
                pt = end_pt(wall, ep)
                limit = MAX_MITER_FACTOR * wall.half_thickness_scene()
                if any(math.hypot(c.x() - pt.x(), c.y() - pt.y()) >= limit
                       for c in corners):
                    return False
        if len(joined) >= 3:
            for wall, ep in joined:
                others = [m for m in joined if m[0] is not wall]
                limit = MAX_MITER_FACTOR * wall.half_thickness_scene()
                if wall._pie_corners(ep, end_pt(wall, ep), others,
                                     limit) is None:
                    return False
        return True

    @staticmethod
    def _lower_auto_walls(members: list, raw) -> list["WallSegment"]:
        """Auto walls below the highest top; [] when the height rule is off.

        Three or more walls need two at the highest top.  Tops come from
        the vertical extent (no level manager: levels at elevation 0).
        """
        ranges = [w.z_range_mm() for w, _ep in members]
        top = max(r[1] for r in ranges)
        tall = sum(1 for r in ranges if r[1] >= top - WALL_JOIN_TOP_TOL_MM)
        if tall == len(members) or (len(members) >= 3 and tall < 2):
            return []
        return [w for (w, ep), r in zip(members, ranges)
                if r[1] < top - WALL_JOIN_TOP_TOL_MM and raw(w, ep) == "Auto"]

    def _stop_corners(self, my_idx: int, my_pt: QPointF, joined: list, quad,
                      clamp: float):
        """Stop this end on *joined*: ``(left, right, wedge)`` or None."""
        if len(joined) == 1:
            tee = self._tee_cope_corners(my_idx, my_pt, joined[0][0], quad,
                                         clamp)
            return None if tee is None else (tee[0], tee[1], [])
        arm = self._junction_arm(my_idx)
        arms = [w._junction_arm(ep) for w, ep in joined]
        if arm is None or any(a is None for a in arms):
            return None
        res = stop_end(arm, arms, my_pt, clamp)
        if res is None:
            return None
        ccw, cw, ends = res
        return (ccw, cw, ends) if my_idx == 0 else (cw, ccw, ends)

    def _tee_union_end(self, host: "WallSegment", quad):
        """Union-only end for a coped tee (G0): this wall's face lines run
        to the host's TRUE centerline, so the stub's union polygon overlaps
        the host with area and ``united()`` merges them.  Returns
        ``(left, right)`` or None when a face runs parallel to the host."""
        p1l, p1r, p2r, p2l = quad
        a, b = host.centerline_pt1, host.centerline_pt2
        ul = intersect_lines(p1l, p2l, a, b)
        ur = intersect_lines(p1r, p2r, a, b)
        if ul is None or ur is None:
            return None
        return ul, ur

    @staticmethod
    def _clip_tee_extension(union_body: QPolygonF, body: QPolygonF, host):
        """Clip a coped tee's union-only extension to the host body (S1-F3).

        The extension runs to the host centerline across the stub's full
        width; where the stub is wider than what is left of the host span
        the part past the host's end is cut off, so the stub's overhanging
        end edge stays a union boundary (stroked, its corner visible).  The
        host's raw quad is used (not its cached outline) so that mutually
        teeing chains cannot recurse.  Falls back to *union_body* unless the
        result is a single closed region.  When every extension point (those
        on the host's true centerline) already lies inside the host quad there
        is no overhang to cut, and the boolean is skipped: Qt's clipper drops
        a body when the operands share collinear edges.
        """
        host_quad = list(host.quad_points())
        a, b = host.centerline_pt1, host.centerline_pt2
        span = math.hypot(b.x() - a.x(), b.y() - a.y())
        body_pts = {(round(body.at(i).x(), 6), round(body.at(i).y(), 6))
                    for i in range(body.count())}
        ext = [union_body.at(i) for i in range(union_body.count())
               if (round(union_body.at(i).x(), 6),
                   round(union_body.at(i).y(), 6)) not in body_pts
               and span > 0.0
               and abs((b.x() - a.x()) * (union_body.at(i).y() - a.y())
                       - (b.y() - a.y()) * (union_body.at(i).x() - a.x())
                       ) / span <= WALL_OUTLINE_ON_EDGE_TOL]

        def _inside(pt: QPointF) -> bool:
            side = None
            for i in range(4):
                p, q = host_quad[i], host_quad[(i + 1) % 4]
                edge = math.hypot(q.x() - p.x(), q.y() - p.y())
                if edge == 0.0:
                    continue
                d = ((q.x() - p.x()) * (pt.y() - p.y())
                     - (q.y() - p.y()) * (pt.x() - p.x())) / edge
                if abs(d) <= WALL_OUTLINE_ON_EDGE_TOL:
                    continue
                if side is None:
                    side = d > 0
                elif side != (d > 0):
                    return False
            return True

        if ext and all(_inside(pt) for pt in ext):
            return union_body

        host_poly = QPolygonF(host_quad)
        allowed = _poly_path(body).united(_poly_path(host_poly))
        clipped = _poly_path(union_body).intersected(allowed).simplified()
        polys = clipped.toSubpathPolygons()
        if len(polys) != 1 or polys[0].count() < 4:
            return union_body
        return polys[0]

    def _compute_mitered_quad(
        self, extra=None,
    ) -> tuple[tuple[QPointF, QPointF, QPointF, QPointF], bool, bool,
               list[QPointF], list[QPointF]]:
        """Pure computation behind ``outline()`` / ``mitered_quad()``.

        Returns ((p1l, p1r, p2r, p2l), solid_pt1, solid_pt2, wedge_pts1,
        wedge_pts2); a pie end's wedge list is ``[hub]`` (design D7).
        Does NOT read or write the cached outline.
        """
        e = self._join_ends(extra)
        return (e["quad"], e["solid"][0], e["solid"][1],
                e["wedge"][0], e["wedge"][1])

    def _join_ends(self, extra=None, pool=None) -> dict:
        """Resolve both ends against the visible join pool.

        Args:
            extra: A wall in the scene but not yet in ``scene._walls``.
            pool: Explicit join pool (the 3D view passes its own); default
                is ``_join_pool(extra)``, the plan pool.

        Returns a dict: ``quad`` (p1l, p1r, p2r, p2l), ``solid`` (2 bools),
        ``wedge`` (2 vertex lists), ``partners`` (2 lists of
        ``(wall, endpoint_idx)``), ``hosts`` (tee host per end or None, found
        whenever an end has no endpoint partner), ``tee_union`` (union-only
        end corners per coped tee end or None), ``pool``, ``union_wedge``
        and ``seams``.
        """
        p1l, p1r, p2r, p2l = self.quad_points()
        solid = [False, False]
        wedge: list[list[QPointF]] = [[], []]
        partners: list[list] = [[], []]
        hosts: list = [None, None]
        tee_union: list = [None, None]
        union_wedge: list = [None, None]
        seams: list = []
        pool = self._join_pool(extra) if pool is None else list(pool)

        if pool:
            MAX_MITER = self.half_thickness_scene() * MAX_MITER_FACTOR
            for my_idx in (0, 1):
                my_pt = self._pt1 if my_idx == 0 else self._pt2
                mine = partners[my_idx]
                for other in pool:
                    other_ep = other.endpoint_near(my_pt, MITER_TOL)
                    if other_ep is not None:
                        mine.append((other, other_ep))
                if not mine:
                    hosts[my_idx] = self._tee_host(my_pt, pool)

                raw_mode = (self._join_mode_pt1 if my_idx == 0
                            else self._join_mode_pt2)
                active = mine
                stops = self._junction_stops(my_idx, mine) if mine else []
                if stops:
                    members = [(self, my_idx), *mine]
                    joined = [m for m in members
                              if not any(m[0] is w for w in stops)]
                    clamp = MAX_MITER_FACTOR * max(
                        w.half_thickness_scene() for w, _ep in members)
                    quad = (p1l, p1r, p2r, p2l)
                    if any(self is w for w in stops):
                        res = self._stop_corners(my_idx, my_pt, joined, quad,
                                                 clamp)
                        if res is not None:
                            int_l, int_r, ends = res
                            if my_idx == 0:
                                p1l, p1r = int_l, int_r
                            else:
                                p2l, p2r = int_l, int_r
                            solid[my_idx] = True
                            wedge[my_idx] = ends
                            union_wedge[my_idx] = [QPointF(my_pt)]
                            chain = [int_l, *ends, int_r]
                            seams.extend(zip(chain, chain[1:]))
                        continue
                    active = [m for m in joined if m[0] is not self]
                    if len(members) == 2:
                        # Lone joined wall runs to the stopper's far face
                        far = self._tee_cope_corners(
                            my_idx, my_pt, stops[0], quad, clamp, far=True)
                        if far is not None:
                            int_l, int_r = far
                            if my_idx == 0:
                                p1l, p1r = int_l, int_r
                            else:
                                p2l, p2r = int_l, int_r
                            solid[my_idx] = True
                        continue

                if raw_mode in ("Auto", "Solid") and len(active) >= 2:
                    # 3+ walls: full pie (D5); degenerate -> Butt
                    pie = self._pie_corners(my_idx, my_pt, active, MAX_MITER)
                    if pie is not None:
                        int_l, int_r, hub = pie
                        if my_idx == 0:
                            p1l, p1r = int_l, int_r
                        else:
                            p2l, p2r = int_l, int_r
                        solid[my_idx] = True
                        wedge[my_idx] = [hub]
                    continue

                if raw_mode in ("Auto", "Butt") and not mine:
                    # Tee join: cope to the host's near face (any angle);
                    # a seam on Butt or where the tops differ (R8, R9)
                    host = hosts[my_idx]
                    quad = (p1l, p1r, p2r, p2l)
                    tee = (self._tee_cope_corners(my_idx, my_pt, host, quad,
                                                  MAX_MITER)
                           if host is not None else None)
                    if tee is not None:
                        int_l, int_r = tee
                        if my_idx == 0:
                            p1l, p1r = int_l, int_r
                        else:
                            p2l, p2r = int_l, int_r
                        solid[my_idx] = True
                        tee_union[my_idx] = self._tee_union_end(host, quad)
                        if raw_mode == "Butt" or self._tops_differ(host):
                            seams.append((int_l, int_r))
                    continue

                mode = self._resolve_join_mode(my_idx, 1 + len(active))
                if mode == "Butt" or not active:
                    continue

                other, other_ep = active[0]
                corners = self._mitre_corners(my_idx, other, other_ep,
                                              (p1l, p1r, p2r, p2l))
                if corners is not None:
                    int_l, int_r = corners
                    dist_l = math.hypot(int_l.x() - my_pt.x(),
                                        int_l.y() - my_pt.y())
                    dist_r = math.hypot(int_r.x() - my_pt.x(),
                                        int_r.y() - my_pt.y())
                    if dist_l < MAX_MITER and dist_r < MAX_MITER:
                        if my_idx == 0:
                            p1l, p1r = int_l, int_r
                        else:
                            p2l, p2r = int_l, int_r
                        if mode == "Solid":
                            solid[my_idx] = True

        return {"quad": (p1l, p1r, p2r, p2l), "solid": tuple(solid),
                "wedge": (wedge[0], wedge[1]),
                "partners": (partners[0], partners[1]),
                "hosts": (hosts[0], hosts[1]),
                "tee_union": (tee_union[0], tee_union[1]), "pool": pool,
                "union_wedge": (union_wedge[0], union_wedge[1]),
                "seams": tuple(seams)}

    def _mitre_corners(self, my_idx: int, other, other_ep: int, quad):
        """Two-wall mitre corners ``(left, right)``, unclamped.

        None when a pair of faces is parallel (a straight run).
        """
        p1l, p1r, p2r, p2l = quad
        o_p1l, o_p1r, o_p2r, o_p2l = other.quad_points()
        if my_idx == other_ep:
            left_target, right_target = (o_p1r, o_p2r), (o_p1l, o_p2l)
        else:
            left_target, right_target = (o_p1l, o_p2l), (o_p1r, o_p2r)
        int_l = self._intersect_lines(p1l, p2l, *left_target)
        int_r = self._intersect_lines(p1r, p2r, *right_target)
        if int_l is None or int_r is None:
            return None
        return int_l, int_r

    def _tee_cope_corners(self, my_idx: int, my_pt: QPointF, host,
                          quad, max_miter: float, far: bool = False):
        """Cope an endpoint that tees into *host* mid-span.

        Both of this wall's face lines are intersected with the host's
        *near* face (the face on this wall's body side), so the end hugs
        the host face at any angle.  Works for endpoints on the host
        centerline (tee snap) and for legacy endpoints snapped to the face.
        With *far* the host's other face is used instead, so a wall that
        another wall stops on runs across that wall's end.

        Returns ``(int_left, int_right)`` or ``None`` (ref on the host
        centerline, parallel faces, or miter beyond the clamp).
        """
        p1l, p1r, p2r, p2l = quad
        # Near face = host face on my body's side of the host centerline
        ref = self._pt2 if my_idx == 0 else self._pt1
        hax, hay = host._pt1.x(), host._pt1.y()
        hdx = host._pt2.x() - hax
        hdy = host._pt2.y() - hay
        s_ref = hdx * (ref.y() - hay) - hdy * (ref.x() - hax)
        if abs(s_ref) < 1e-9:
            return None    # running along the host — no usable cope
        sign = 1.0 if s_ref > 0 else -1.0
        if far:
            sign = -sign
        o_p1l, o_p1r, o_p2r, o_p2l = host.quad_points()
        s_l = hdx * (o_p1l.y() - hay) - hdy * (o_p1l.x() - hax)
        s_r = hdx * (o_p1r.y() - hay) - hdy * (o_p1r.x() - hax)
        if s_l * sign >= s_r * sign:
            face = (o_p1l, o_p2l)
        else:
            face = (o_p1r, o_p2r)

        int_l = self._intersect_lines(p1l, p2l, face[0], face[1])
        int_r = self._intersect_lines(p1r, p2r, face[0], face[1])
        if int_l is None or int_r is None:
            return None
        if (math.hypot(int_l.x() - my_pt.x(), int_l.y() - my_pt.y())
                >= max_miter
                or math.hypot(int_r.x() - my_pt.x(), int_r.y() - my_pt.y())
                >= max_miter):
            return None
        return int_l, int_r

    # ── Wall joining helper ──────────────────────────────────────────────────

    def endpoint_near(self, pos: QPointF, tolerance: float) -> int | None:
        """Return 0 if pos is near pt1, 1 if near pt2, else None."""
        if math.hypot(pos.x() - self._pt1.x(), pos.y() - self._pt1.y()) <= tolerance:
            return 0
        if math.hypot(pos.x() - self._pt2.x(), pos.y() - self._pt2.y()) <= tolerance:
            return 1
        return None

    def snap_endpoint_to(self, idx: int, target: QPointF):
        """Snap endpoint idx (0 or 1) exactly to target and rebuild."""
        if idx == 0:
            self._pt1 = QPointF(target)
        else:
            self._pt2 = QPointF(target)
        self.invalidate_geometry()

    def nearest_centerline_point(self, pos: QPointF, tolerance: float,
                                 true_centerline: bool = False
                                 ) -> QPointF | None:
        """Return the projection of *pos* onto this wall's centerline if
        *pos* projects within the wall's span (tee-join target).

        Returns ``None`` if *pos* projects outside the span, is coincident
        with an endpoint (``MITER_TOL`` -- a corner, not a tee) or lies
        farther than *tolerance* from the centerline.

        By default the line is the wall's click line (``_pt1``/``_pt2``,
        the placement snap target).  With *true_centerline* it is the
        geometric centerline (``centerline_pt1/2``), which the tee band of
        a Left/Right-aligned host is measured from (wall polish F9).
        """
        if true_centerline:
            c1, c2 = self.centerline_pt1, self.centerline_pt2
        else:
            c1, c2 = self._pt1, self._pt2
        ax, ay = c1.x(), c1.y()
        bx, by = c2.x(), c2.y()
        dx, dy = bx - ax, by - ay
        len_sq = dx * dx + dy * dy
        if len_sq < 1e-12:
            return None
        t = ((pos.x() - ax) * dx + (pos.y() - ay) * dy) / len_sq
        eps = 1e-9
        if t < -eps or t > 1.0 + eps:
            return None
        # A point coincident with a host end is a corner (endpoint partner),
        # not a tee.  There is no relative end margin: a stub a few mm from
        # the host's end still tees (wall polish S1-F2).
        if (math.hypot(pos.x() - ax, pos.y() - ay) <= MITER_TOL
                or math.hypot(pos.x() - bx, pos.y() - by) <= MITER_TOL):
            return None
        t = min(1.0, max(0.0, t))
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        if math.hypot(pos.x() - proj_x, pos.y() - proj_y) > tolerance:
            return None
        return QPointF(proj_x, proj_y)

    def nearest_face_point(self, pos: QPointF, tolerance: float,
                           scale_manager=None,
                           reference_point: QPointF | None = None) -> QPointF | None:
        """Return the point on the wall face nearest to *reference_point*
        if *pos* is near the mid-section of this wall's centerline.

        Used for tee-intersection snapping: the joining wall's endpoint
        is trimmed to the face of the existing wall that is closest to the
        new wall's *other* endpoint (``reference_point``).  If no
        ``reference_point`` is given, the face closest to *pos* is returned
        (legacy behaviour).

        Returns ``None`` if *pos* is near an endpoint or too far from the
        centerline.
        """
        # Project pos onto the centerline parametrically
        ax, ay = self._pt1.x(), self._pt1.y()
        bx, by = self._pt2.x(), self._pt2.y()
        dx, dy = bx - ax, by - ay
        len_sq = dx * dx + dy * dy
        if len_sq < 1e-12:
            return None
        t = ((pos.x() - ax) * dx + (pos.y() - ay) * dy) / len_sq

        # Must be in the mid-section (not near endpoints)
        margin = 0.05
        if t < margin or t > 1.0 - margin:
            return None

        # Perpendicular distance to centerline
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        perp_dist = math.hypot(pos.x() - proj_x, pos.y() - proj_y)
        if perp_dist > tolerance:
            return None

        # Get the wall quad to determine face positions
        p1l, p1r, p2r, p2l = compute_wall_quad(
            self._pt1, self._pt2, self._thickness_mm,
            self._alignment, scale_manager)

        # Interpolate left and right face at parameter t
        face_l = QPointF(p1l.x() + t * (p2l.x() - p1l.x()),
                         p1l.y() + t * (p2l.y() - p1l.y()))
        face_r = QPointF(p1r.x() + t * (p2r.x() - p1r.x()),
                         p1r.y() + t * (p2r.y() - p1r.y()))

        # Choose the face nearest to reference_point (the new wall's
        # other endpoint) so the new wall terminates on the correct side.
        ref = reference_point if reference_point is not None else pos
        d_l = math.hypot(ref.x() - face_l.x(), ref.y() - face_l.y())
        d_r = math.hypot(ref.x() - face_r.x(), ref.y() - face_r.y())
        return face_l if d_l <= d_r else face_r


def _reach_box(wall: WallSegment) -> tuple[float, float, float, float]:
    """Scene box bounding every join reach of *wall* (3D join neighbourhood).

    The end points grown by twice the half thickness plus ``MITER_TOL``:
    an aligned centerline sits at most one half thickness off the
    ``_pt1``-``_pt2`` line, so the box holds both faces, the centerline,
    and every endpoint-partner, tee-host and tee-guest reach.
    """
    r = 2.0 * wall.half_thickness_scene() + MITER_TOL
    a, b = wall._pt1, wall._pt2
    return (min(a.x(), b.x()) - r, min(a.y(), b.y()) - r,
            max(a.x(), b.x()) + r, max(a.y(), b.y()) + r)


def join_neighbourhoods(walls) -> dict[int, list[WallSegment]]:
    """Per wall (keyed by ``id``): the 3D join pool it needs.

    The walls whose reach box overlaps its own (first ring) or a first-ring
    wall's (second ring): ``get_3d_mesh`` joins against the first ring and
    its edge pass re-joins each neighbour, which reads that neighbour's
    first ring. Passing this ring instead of every wall gives the same mesh
    without the per-wall scan of the whole pool (G9). Sort-and-sweep on x;
    each list keeps the order of *walls*.
    """
    walls = list(walls)
    order = {id(w): i for i, w in enumerate(walls)}
    boxes = [(_reach_box(w), w) for w in walls]
    boxes.sort(key=lambda bw: bw[0][0])
    ring1: dict[int, set[int]] = {id(w): set() for w in walls}
    active: list = []
    for box, w in boxes:
        active = [(b, o) for b, o in active if b[2] >= box[0]]
        for b, o in active:
            if b[1] <= box[3] and box[1] <= b[3]:
                ring1[id(w)].add(id(o))
                ring1[id(o)].add(id(w))
        active.append((box, w))
    by_id = {id(w): w for w in walls}
    out: dict[int, list[WallSegment]] = {}
    for w in walls:
        keep = set(ring1[id(w)])
        for o in ring1[id(w)]:
            keep |= ring1[o]
        keep.discard(id(w))
        out[id(w)] = [by_id[i] for i in sorted(keep, key=order.__getitem__)]
    return out


def _boxes_overlap(a, b) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def join_ring(wall: WallSegment, pool) -> list[WallSegment]:
    """*wall*'s ``join_neighbourhoods`` ring within *pool*, built for that
    wall alone: one box per pool wall instead of every wall's ring, for
    callers meshing one wall (selection highlight, thermal extract)."""
    mine = _reach_box(wall)
    boxes = [(w, _reach_box(w)) for w in pool if w is not wall]
    first = [b for _w, b in boxes if _boxes_overlap(mine, b)]
    return [w for w, b in boxes
            if any(_boxes_overlap(f, b) for f in first)]
