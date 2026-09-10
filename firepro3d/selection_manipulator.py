"""Scene-level selection manipulator (frame + rigid transforms).

Governing spec: docs/specs/selection-manipulator.md. One instance per scene
(model + paper); wraps the current selection, previews drags as a held
transform, bakes real coordinates on release via each item's ``manip_*``
capability methods. Parametric grips (grip_points/apply_grip) are untouched
and render via Model_View.drawForeground inside this frame.
"""

from __future__ import annotations

import logging
import math
from typing import Callable, List, Optional, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor, QCursor, QPainter, QPainterPath, QPen, QPixmap, QTransform,
)
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from . import theme
from .constants import (
    MANIP_HANDLE_SIZE_PX, MANIP_HANDLE_BORDER_PX, MANIP_KNOB_RADIUS_PX,
    MANIP_STEM_LEN_PX, MANIP_HANDLE_FILL_DARK, MANIP_HANDLE_FILL_LIGHT,
    SELECTION_GRIP_SIZE_MM, SELECTION_GRIP_OUTLINE_WIDTH_MM,
)
from .dynamic_input import (
    resolve_manip_move, resolve_manip_resize, resolve_manip_rotate,
)
from .manip_math import (
    HandleRole, _ROLE_GEOM, _RESIZE_ROLES, _rect_point, move_delta,
)

log = logging.getLogger(__name__)

MANIP_Z = 1e6          # spec: manipulator sits above all scene content
_SHAPE_PAD_PX = 3.0    # interior hit slack so hairline frames stay grabbable
_BOUND_PAD_PX = 6.0    # boundingRect pad (>= shape pad; generous for culling)

# Handle metrics (device px; ItemIgnoresTransformations keeps them zoom-constant).
# Style A (mockup-approved 2026-08-30): dark-filled square handles with a theme
# ``selection`` outline at rest / ``selection_active`` while dragging/hovered; a
# hollow rotate knob. The fill is theme-derived (see ``_handle_fill``). Metrics
# live in constants.py (one home).
_HANDLE_SIZE_PX = MANIP_HANDLE_SIZE_PX      # square side
_HANDLE_BORDER_PX = MANIP_HANDLE_BORDER_PX
_HANDLE_GRAB_PAD_PX = 3.0    # extra hit slack around the square
_ROTATE_OFFSET_PX = MANIP_STEM_LEN_PX     # stem length from the top-mid to the knob
_ROTATE_RADIUS_PX = MANIP_KNOB_RADIUS_PX
_ROTATE_SNAP_DEG = 15.0      # Shift-snap increment (absolute angle)


def _handle_fill() -> QColor:
    """Handle/knob fill for the active theme (mockup style A).

    A function of the theme: near-black on a dark canvas, white on a light
    canvas, so the square reads against the canvas while the ``selection``
    border does the defining. Decided by the theme's canvas lightness so any
    future variant resolves correctly.
    """
    t = theme.detect()
    light = QColor(t.ground).lightness() >= 128
    return QColor(MANIP_HANDLE_FILL_LIGHT if light else MANIP_HANDLE_FILL_DARK)

#: Manipulator gesture mode -> dynamic-input schema name.  Move drives a
#: gesture in v1; resize/rotate are wired ready for their handles (Task 5).
_SCHEMA_FOR_MODE = {
    "move": "manip_move",
    "resize": "manip_resize",
    "rotate": "manip_rotate",
}


# --------------------------------------------------------------------------- #
#  Capability protocol (duck-typed — spec "Capability protocol" table)
# --------------------------------------------------------------------------- #

def _movable_by_pos(item) -> bool:
    """True for items whose serialized position IS ``pos()`` (Node only).

    Every QGraphicsItem has ``moveBy``, but for items whose geometry is
    serialized from internal coordinates a bare ``moveBy`` desyncs the
    visual position from the saved geometry (reverts on reload — the
    dual-serialization trap). ``move_items`` moves only Node via ``moveBy``;
    mirror that rule here.
    """
    from .node import Node
    return isinstance(item, Node)


def item_capabilities(item) -> set:
    """Return the set of manipulator capabilities an item supports.

    ``"translate"`` if ``manip_translate``/``translate`` exists (or the item
    is a Node, whose ``pos()`` is its serialized position); ``"rotate"`` iff
    ``manip_rotate``; ``"scale"`` iff ``manip_scale``.

    An item may narrow this **dynamically** by implementing
    ``manip_capabilities() -> set``: the returned set intersects the
    duck-typed default, so an item that carries a ``manip_scale`` method but is
    not currently scalable (a detail viewport, whose extent is marker-owned)
    can drop ``"scale"`` for the current state — mirroring the retired
    ``_grip_rects() -> []`` inert-grip behaviour.
    """
    caps: set = set()
    if (hasattr(item, "manip_translate") or hasattr(item, "translate")
            or _movable_by_pos(item)):
        caps.add("translate")
    if hasattr(item, "manip_rotate"):
        caps.add("rotate")
    if hasattr(item, "manip_scale"):
        caps.add("scale")
    narrow = getattr(item, "manip_capabilities", None)
    if narrow is not None:
        caps &= set(narrow())
    return caps


def manip_bounds(item) -> QRectF:
    """Scene-space box the frame wraps: ``item.manip_bounds()`` if provided,
    else ``sceneBoundingRect()`` (spec fallback)."""
    fn = getattr(item, "manip_bounds", None)
    if fn is not None:
        return fn()
    return item.sceneBoundingRect()


def _item_uses_manip_handles(item) -> bool:
    """True when *item* provides its own manipulator handles (U3-migrated), so
    the legacy grip paths (Model_View.drawForeground, scene_tools._find_grip_hit)
    must NOT render/hit-test it — one render path, one hit-test (no double
    handles / no stolen press). Mirrors provides_handles_for; U4 deletes both."""
    fn = getattr(item, "manip_handles", None)
    return fn is not None and bool(fn())


def bake_translate(item, dx: float, dy: float) -> bool:
    """Apply a baked (real-coordinate) move via the item's best translate
    path: ``manip_translate`` > ``translate`` > ``moveBy``.

    Returns:
        True if a translate path existed and was applied, else False.
    """
    fn = getattr(item, "manip_translate", None)
    if fn is not None:
        fn(dx, dy)
        return True
    fn = getattr(item, "translate", None)
    if fn is not None:
        fn(dx, dy)
        return True
    if _movable_by_pos(item):
        item.moveBy(dx, dy)
        return True
    return False


# --------------------------------------------------------------------------- #
#  Rotate cursor + grab handles (ported from the SelectionBox prototype)
# --------------------------------------------------------------------------- #

def _yup_angle_from_delta(d: QTransform) -> float:
    """App-convention (Y-up CCW+) rotation angle of a scene-space delta.

    ``rotate_delta`` builds ``d`` with Qt's ``rotate`` (y-down CW+), so the
    x-axis image gives the Qt angle; negate for the app's Y-up readout/bake
    convention (matching ``RectangleItem.set_angle``)."""
    v = d.map(QPointF(1.0, 0.0)) - d.map(QPointF(0.0, 0.0))
    return -math.degrees(math.atan2(v.y(), v.x()))


def _make_rotate_cursor(size: int = 22) -> QCursor:
    """A small circular-arrow cursor (Qt has no stock rotate cursor)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    rect = QRectF(4, 4, size - 8, size - 8)
    for color, width in ((QColor(0, 0, 0, 200), 3.4), (QColor(255, 255, 255), 1.6)):
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, 30 * 16, 280 * 16)
        cx, cy = size / 2.0, size / 2.0
        r = rect.width() / 2.0
        ax = cx + r * math.cos(math.radians(-30))
        ay = cy - r * math.sin(math.radians(30))
        p.drawLine(QPointF(ax, ay), QPointF(ax - 4.2, ay - 1.2))
        p.drawLine(QPointF(ax, ay), QPointF(ax + 1.4, ay - 4.4))
    p.end()
    return QCursor(pm, size // 2, size // 2)


class _HandleItem(QGraphicsItem):
    """Screen-constant host for a Handle. Renders + receives Qt events; forwards
    all behavior to ``self.handle``. ItemIgnoresTransformations (px, model) or
    paper-mm sizing per the manipulator flag.

    ``ItemIgnoresTransformations`` (model) keeps the handle a constant device-pixel
    size at any zoom; paper-mm hosts scale with the 1-unit==1-mm paper scene so
    they plot true to scale.  Press begins the manipulator's gesture for this
    handle via ``manip._begin_handle``; move/release forward to
    ``_update``/``_finish`` exactly as an interior-move drag does.
    """

    def __init__(self, manip, handle):
        super().__init__(manip)
        self._manip = manip
        self.handle = handle
        self.role = handle.role
        self._hover = False
        # Model scene: screen-constant device-px handles (ItemIgnoresTransformations).
        # Paper scene: paper-mm handles that scale with the 1-unit==1-mm scene, so
        # they plot/print at a true millimetre size (theming.md split).  The flag
        # is owned by the manipulator (per-scene sizing mode).
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                     not manip._handle_mm)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setZValue(2.0 if handle.role is not HandleRole.ROTATE else 1.5)

    # -- geometry (device px OR paper mm; anchored at the handle position) -----

    def _size(self) -> float:
        return self._manip._handle_size

    def _border(self) -> float:
        return self._manip._handle_border

    def _grab_pad(self) -> float:
        return self._manip._handle_grab_pad

    def _half(self) -> float:
        return self._size() / 2.0 + self._grab_pad()

    def boundingRect(self) -> QRectF:
        if self.role is HandleRole.ROTATE:
            r = _ROTATE_OFFSET_PX + _ROTATE_RADIUS_PX + self._grab_pad() + 2.0
            return QRectF(-r, -r, 2 * r, 2 * r)
        h = self._half() * math.sqrt(2.0)   # covers the square at any rotation
        return QRectF(-h, -h, 2 * h, 2 * h)

    def shape(self) -> QPainterPath:
        return self.handle.shape(size=self._size(), grab_pad=self._grab_pad())

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: Optional[QWidget] = None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        border = self._manip._handle_color(self._hover)
        painter.setPen(QPen(border, self._border()))
        self.handle.paint(painter, size=self._size(), border=border,
                          fill=_handle_fill(), hover=self._hover,
                          border_width=self._border())

    # -- interaction ----------------------------------------------------------

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hover = True
        self.setCursor(self.handle.cursor(self._manip))
        self.update()

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hover = False
        self.unsetCursor()
        self.update()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._manip._begin_handle(self.handle, event.scenePos(),
                                      event.screenPos())
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._manip._update(event.scenePos(), event.modifiers(), event.screenPos())

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._manip._finish(event.scenePos(), event.modifiers())


# --------------------------------------------------------------------------- #
#  SelectionManipulator
# --------------------------------------------------------------------------- #

class SelectionManipulator(QGraphicsObject):
    """Attach-once selection frame with interior-drag group move.

    This task (core) draws the frame and implements the move gesture only:
    press inside the frame begins a held-transform preview, release bakes
    real coordinates through :func:`bake_translate` and fires the
    ``commit_hook`` once (one undo per gesture). A plain click falls through
    to normal picking (:meth:`_click_through`). Resize handles / rotate knob
    arrive in later tasks.

    Args:
        scene: The scene to attach to (added + ``selectionChanged`` tracked).
        commit_hook: ``callable(mode: str)`` invoked once after a baked
            gesture (model scene: ``push_undo_state``; paper scene: a
            ``beginMacro``/per-item command/``endMacro`` wrapper — the hook
            reads the manipulator's pre-drag snapshot via
            :meth:`snapshot_items`).
        exclude: Optional ``callable(item) -> bool``; items for which it
            returns True are never wrapped.
        handle_units: ``"px"`` (default, model scene) sizes resize handles in
            device pixels via ``ItemIgnoresTransformations``; ``"mm"`` (paper
            scene) sizes them in paper millimetres so they plot/print true to
            scale (theming.md split; no rotate knob shows on paper because
            paper items don't implement ``manip_rotate``).
    """

    #: Screen-only selection feedback — never plots.  Honoured by
    #: paper_display.apply_paper_overrides during paper-viewport renders.
    PAPER_EXCLUDED = True

    def __init__(self, scene: QGraphicsScene, *,
                 commit_hook: Optional[Callable[[str], None]] = None,
                 exclude: Optional[Callable[[QGraphicsItem], bool]] = None,
                 handle_units: str = "px",
                 press_hook: Optional[Callable[[List[QGraphicsItem]], None]]
                 = None):
        super().__init__()
        self._commit_hook = commit_hook
        self._press_hook = press_hook
        self._exclude = exclude

        # Per-scene handle sizing (px in model, paper-mm in paper).  Read by
        # every _HandleItem; the flag also decides ItemIgnoresTransformations.
        self._handle_mm = (handle_units == "mm")
        if self._handle_mm:
            self._handle_size = SELECTION_GRIP_SIZE_MM
            self._handle_border = SELECTION_GRIP_OUTLINE_WIDTH_MM
            self._handle_grab_pad = SELECTION_GRIP_SIZE_MM * 0.5
        else:
            self._handle_size = _HANDLE_SIZE_PX
            self._handle_border = _HANDLE_BORDER_PX
            self._handle_grab_pad = _HANDLE_GRAB_PAD_PX

        self._rect = QRectF()
        self._sel_ids: frozenset = frozenset()
        self._items: List[QGraphicsItem] = []

        # drag state
        self._mode: Optional[str] = None
        self._role: Optional[HandleRole] = None
        self._B0 = QTransform()
        self._R0 = QRectF()
        self._start_scene = QPointF()
        self._press_screen = QPointF()
        self._moved = False
        self._base_angle = 0.0
        self._last_factors: Tuple[float, float] = (1.0, 1.0)
        self._items0: List[Tuple[QGraphicsItem, QTransform,
                                 QTransform, QTransform]] = []
        self._D = QTransform()
        self._held_snap = None

        # Dynamic-input HUD (live readout + typed-input surface), owned per
        # gesture.  Distinct from the scene's placement HUD (``dynamic_input``)
        # — that one belongs to placement modes; this one reads out and drives
        # a manipulator gesture, so it is built on ``_begin`` and torn down on
        # every gesture exit.  ``None`` between gestures and in headless scenes
        # that carry no view.
        self._hud = None

        self.setZValue(MANIP_Z)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.hide()

        # Absolute-angle Shift-snap increment, exposed to Handles (rotate).
        self._ROTATE_SNAP_DEG = _ROTATE_SNAP_DEG

        # Screen-constant children: 8 resize handles + one rotate knob.  Each is
        # a _HandleItem host wrapping a rigid Handle behavior object; the
        # manipulator orchestrates the held-preview toolkit while the Handle
        # decides geometry/gating/lifecycle.  Visibility is capability-gated in
        # ``_layout`` (frame+move only for multi-select / parametric single-select).
        from .manip_handle import ResizeHandle, RotateHandle
        self._rigid = {role: ResizeHandle(role) for role in _RESIZE_ROLES}
        self._rigid[HandleRole.ROTATE] = RotateHandle()
        for _h in self._rigid.values():     # back-ref for live rotate-preview
            _h._m = self
        self._handles = {role: _HandleItem(self, self._rigid[role])
                         for role in self._rigid}
        self._host_pool = []            # widget-less sourced handles (U3/stub) — Task 3 uses it
        self._active_handle = None
        for h in self._handles.values():
            h.hide()
        self._rotate_cursor = _make_rotate_cursor()

        scene.addItem(self)
        scene.selectionChanged.connect(self._on_selection_changed)
        # Placement modes hide the frame even when the selection survives
        # (e.g. "move"/"stretch" keep their selection on entry).
        mode_sig = getattr(scene, "modeChanged", None)
        if mode_sig is not None:
            mode_sig.connect(self._on_scene_mode_changed)

    # ------------------------------------------------------------------ API --

    def rebake(self) -> None:
        """Recompute the frame as the axis-aligned bounds of the selection.

        Call after changing item geometry/positions outside the manipulator
        (nudge, undo, numeric edits...).
        """
        sc = self.scene()
        if sc is None:
            return
        if not self._mode_allows(sc):
            self._items = []
            self._sel_ids = frozenset()
            self.hide()
            return
        raw = [i for i in sc.selectedItems()
               if self._is_foreign(i)
               and not (self._exclude is not None and self._exclude(i))]
        self._sel_ids = frozenset(id(i) for i in raw)

        # Resolve Sprinkler -> parent Node (same rule as move_items) + dedupe.
        from .sprinkler import Sprinkler
        resolved: List[QGraphicsItem] = []
        seen: set = set()
        for it in raw:
            if isinstance(it, Sprinkler) and it.node is not None:
                it = it.node
            if id(it) not in seen:
                seen.add(id(it))
                resolved.append(it)

        # Spec: items lacking a translate path are excluded and LOGGED,
        # never silently skipped.
        kept: List[QGraphicsItem] = []
        for it in resolved:
            if "translate" in item_capabilities(it):
                kept.append(it)
            else:
                log.warning(
                    "SelectionManipulator: %s excluded from wrap "
                    "(no translate capability)", type(it).__name__)

        self._items = self._top_level_only(kept)
        if not self._items:
            self.hide()
            return
        r = QRectF()
        for it in self._items:
            r = r.united(manip_bounds(it))
        if r.width() < 1e-9:
            r.setWidth(1e-9)
        if r.height() < 1e-9:
            r.setHeight(1e-9)
        self.prepareGeometryChange()
        self.setTransform(QTransform())
        self._rect = r
        self._layout()
        self.show()

    def is_dragging(self) -> bool:
        """True while a press->release gesture is in flight."""
        return self._mode is not None

    def selection_items(self) -> List[QGraphicsItem]:
        """Top-level items the manipulator currently transforms."""
        return list(self._items)

    def wraps(self, item: QGraphicsItem) -> bool:
        """True when *item* is one of the items this manipulator currently
        boxes (drawForeground consults this to skip the legacy per-item
        selection boundary — the manipulator frame is the one boundary)."""
        return item in self._items

    def provides_handles_for(self, item: QGraphicsItem) -> bool:
        """True when the manipulator's OWN resize handles replace *item*'s
        parametric grips — a single, scale-capable selection (a box-native
        item like RectangleItem).  Such an item must be retired from the legacy
        grip pipeline entirely: ``Model_View.drawForeground`` must not draw its
        grips (double handles) and ``_find_grip_hit`` must not hit-test them
        (a manipulator-handle press would otherwise be stolen by the coincident
        rect grip, which also deselects the item).  Parametric items (no
        ``manip_scale``) keep their grips inside the frame.
        """
        return (len(self._items) == 1 and self._items[0] is item
                and "scale" in item_capabilities(item))

    # ----------------------------------------------------- selection tracking --

    def _mode_allows(self, sc) -> bool:
        """Only active in select mode (None == implicit select in Model_Space:
        ``_PRESS_DISPATCH`` maps both to ``_press_select_item``)."""
        return getattr(sc, "mode", None) in (None, "select")

    def _is_foreign(self, item: QGraphicsItem) -> bool:
        if item is self:
            return False
        p = item.parentItem()
        while p is not None:
            if p is self:
                return False
            p = p.parentItem()
        return True

    @staticmethod
    def _top_level_only(items: List[QGraphicsItem]) -> List[QGraphicsItem]:
        sel = set(items)
        out = []
        for it in items:
            p = it.parentItem()
            skip = False
            while p is not None:
                if p in sel:
                    skip = True
                    break
                p = p.parentItem()
            if not skip:
                out.append(it)
        return out

    def _on_selection_changed(self) -> None:
        if self._mode is not None:
            return
        sc = self.scene()
        if sc is None:
            return
        ids = frozenset(id(i) for i in sc.selectedItems() if self._is_foreign(i))
        if ids == self._sel_ids and (self.isVisible() or not ids):
            return  # same set: keep the current frame
        self.rebake()

    def _on_scene_mode_changed(self, mode) -> None:
        if self._mode is not None:
            self.cancel_drag()
        self.rebake()

    # ------------------------------------------------------------- geometry --

    def boundingRect(self) -> QRectF:
        pad = _BOUND_PAD_PX / max(self._view_scale(), 1e-9)
        return self._rect.adjusted(-pad, -pad, pad, pad)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        if self._rect.isNull():
            return path
        # Frame rect = interior drag surface, padded a hair so hairline
        # frames (a single selected line) remain grabbable.
        pad = _SHAPE_PAD_PX / max(self._view_scale(), 1e-9)
        path.addRect(self._rect.adjusted(-pad, -pad, pad, pad))
        return path

    def hit_test(self, scene_pos: QPointF) -> bool:
        """True if *scene_pos* is over the frame interior OR any visible handle.

        The rotate knob (and the outer half of the corner/edge handles) sits
        OUTSIDE the frame ``shape()``, so the model scene's press router must
        test the handles too — otherwise a knob/handle press falls through to
        selection and the gesture (rotation especially) never starts.
        """
        if not self.isVisible():
            return False
        if self.shape().contains(self.mapFromScene(scene_pos)):
            return True
        # Handles are ItemIgnoresTransformations: a plain ``mapFromScene`` uses
        # the item's scene transform and ignores the view zoom, so it only
        # agrees at m11==1.  At any other zoom (e.g. the fit-to-view ~0.02) the
        # mapped point is wrong and the knob/handles read as not-hit — the press
        # then falls through to selection and clears it.  Map through the view's
        # device transform instead (Qt's canonical path for screen-constant
        # items), falling back to mapFromScene only when no view is reachable
        # (headless).
        view = self._view()
        vt = view.viewportTransform() if view is not None else None
        for h in list(self._handles.values()) + list(self._host_pool):
            if not h.isVisible():
                continue
            if vt is not None:
                dt = h.deviceTransform(vt)        # handle-local -> viewport px
                inv, ok = dt.inverted()
                if not ok:
                    continue
                local = inv.map(vt.map(scene_pos))  # scene -> px -> handle-local
            else:
                local = h.mapFromScene(scene_pos)
            if h.shape().contains(local):
                return True
        return False

    def _frame_is_redundant(self) -> bool:
        """A single box-native item (rect/text/viewport) whose own outline IS
        the bounding box — drawing the frame just traces the shape.  Show the
        handles alone (PowerPoint/Figma style); keep the frame for multi-select
        and non-box shapes, where the bounding box adds information."""
        return (len(self._items) == 1
                and self.provides_handles_for(self._items[0]))

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: Optional[QWidget] = None) -> None:
        if self._frame_is_redundant():
            return                              # handles (child items) suffice
        try:
            color = QColor(theme.detect().selection)
        except Exception:                       # headless / no palette yet
            color = QColor("#63BE8B")
        pen = QPen(color, 1.0)
        pen.setCosmetic(True)
        pen.setStyle(Qt.PenStyle.DashLine)      # dashed = selection, distinct
        painter.setPen(pen)                     # from an item's own solid edge
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self._rect)

    def _layout(self) -> None:
        """Position the resize handles + rotate knob and capability-gate them.

        Resize handles show only for a single item that implements
        ``manip_scale``; the rotate knob shows only when every selected item
        implements ``manip_rotate`` (spec handle-gating).  Multi-select or a
        parametric single-select gets frame + interior-move only — the handles
        stay hidden and the item's own grips (drawn by Model_View) drive edits.
        """
        r = self._rect
        for role in _RESIZE_ROLES:
            self._handles[role].setPos(self._rigid[role].scene_position(r))
        # Knob anchored at the top-edge midpoint; the stem/knob draw upward from
        # there in device space (see RotateHandle.shape/paint).
        self._handles[HandleRole.ROTATE].setPos(
            self._rigid[HandleRole.ROTATE].scene_position(r))
        for role in _RESIZE_ROLES:
            self._handles[role].setVisible(self._rigid[role].visible(self))
        self._handles[HandleRole.ROTATE].setVisible(
            self._rigid[HandleRole.ROTATE].visible(self))
        item_handles = [h for h in self._active_handles()
                        if h not in self._rigid.values()]
        self._sync_host_pool(item_handles)

    def _reflow_live(self) -> None:
        """Recompute the frame + reposition existing hosts to the current grip
        points during a live-apply drag (geometry mutates every move, so the
        frame and sibling handles must follow). Reuses the hosts' current
        handle objects — does NOT rebuild the handle list mid-drag."""
        r = QRectF()
        for it in self._items:
            r = r.united(manip_bounds(it))
        if r.width() < 1e-9:
            r.setWidth(1e-9)
        if r.height() < 1e-9:
            r.setHeight(1e-9)
        self.prepareGeometryChange()
        self._rect = r
        for role in _RESIZE_ROLES:
            self._handles[role].setPos(self._rigid[role].scene_position(r))
        self._handles[HandleRole.ROTATE].setPos(
            self._rigid[HandleRole.ROTATE].scene_position(r))
        for host in self._host_pool:
            if host.isVisible():
                host.setPos(host.handle.scene_position(r))
        self.update()

    def _active_handles(self) -> list:
        """Handles for the current selection: item-provided (U3) if any, else
        the rigid set (fallback). Today no item implements manip_handles(), so
        this always returns the rigid handles -> behavior identical."""
        item_handles = []
        for it in self._items:
            fn = getattr(it, "manip_handles", None)
            if fn is not None:
                item_handles.extend(fn())
        return item_handles or list(self._rigid.values())

    def _sync_host_pool(self, handles: list) -> None:
        """Ensure one _HandleItem host per widget-less handle (stub/U3). The
        rigid handles keep their role-keyed hosts; these are the extras."""
        while len(self._host_pool) < len(handles):
            self._host_pool.append(_HandleItem(self, self._rigid[HandleRole.TOP_LEFT]))
        for host in self._host_pool[len(handles):]:
            host.hide()
        r = self._rect
        for host, handle in zip(self._host_pool, handles):
            host.handle = handle
            host.role = handle.role
            # Back-ref so a GripHandle can read the live rotate-preview angle
            # (grip_render_angle + _preview_rotation_deg) when it paints/hit-tests.
            handle._m = self
            host.setPos(handle.scene_position(r))
            host.setVisible(handle.visible(self))

    # ------------------------------------------------------------- styling --

    def _handle_color(self, active: bool) -> QColor:
        """Handle outline colour: ``selection_active`` while dragging or hovered,
        else the resting ``selection`` accent (placeholder until Task-6 mockup)."""
        try:
            th = theme.detect()
            token = th.selection_active if (active or self._mode is not None) \
                else th.selection
            return QColor(token)
        except Exception:                        # headless / no palette yet
            return QColor("#8FE3B4" if active else "#63BE8B")

    def _cursor_for(self, role: HandleRole) -> QCursor:
        """Role cursor: the rotate glyph for the knob, else an axis-aware resize
        cursor.  The frame is unrotated at rest, so the outward direction of each
        resize handle in device space is just its ``_ROLE_GEOM`` direction."""
        if role is HandleRole.ROTATE:
            return self._rotate_cursor
        _, _, dx, dy = _ROLE_GEOM[role]
        ang = math.degrees(math.atan2(float(dy), float(dx))) % 180.0
        if ang < 22.5 or ang >= 157.5:
            shape = Qt.CursorShape.SizeHorCursor
        elif ang < 67.5:
            shape = Qt.CursorShape.SizeFDiagCursor
        elif ang < 112.5:
            shape = Qt.CursorShape.SizeVerCursor
        else:
            shape = Qt.CursorShape.SizeBDiagCursor
        return QCursor(shape)

    # ----------------------------------------------------------- view helpers --

    def _view(self):
        sc = self.scene()
        views = sc.views() if sc else []
        if not views:
            return None
        # Prefer a visible view: Model_Space keeps a hidden vestigial view at
        # index 0 (m11==1) plus one per open plan tab, so views[0] can be the
        # wrong (unshown) transform for hit-testing screen-constant handles.
        for v in views:
            if v.isVisible():
                return v
        return views[0]

    def _view_scale(self) -> float:
        v = self._view()
        if v is None:
            return 1.0
        m = v.viewportTransform()
        return math.hypot(m.m11(), m.m12()) or 1.0

    # --------------------------------------------------------------- snapping --

    def _snap(self, scene_pos: QPointF) -> QPointF:
        """Snap the dragged grab point through the scene's snap engine.

        Snap-then-transform (spec lifecycle step 2): the grab point is
        snapped BEFORE the move delta is computed. The dragged items (and
        their children) are excluded as snap sources so the selection never
        snaps to itself; the winning result is held via ``held=`` for
        hysteresis. Returns ``scene_pos`` unchanged when no engine/view is
        reachable or snapping is off.
        """
        sc = self.scene()
        view = self._view()
        engine = getattr(sc, "_snap_engine", None)
        if (engine is None or view is None
                or not getattr(sc, "_snap_enabled", True)):
            self._held_snap = None
            return scene_pos

        dragged = set(self._items)
        me = self

        def _not_dragged(it):
            p = it
            while p is not None:
                if p in dragged or p is me:
                    return False
                p = p.parentItem()
            return True

        res = engine.find(scene_pos, sc, view.transform(),
                          item_filter=_not_dragged, held=self._held_snap)
        self._held_snap = res
        return QPointF(res.point) if res is not None else scene_pos

    # --------------------------------------------------------------- HUD --

    def _scale_manager(self):
        """The scene's ScaleManager (DIMENSION scene↔mm), or None if absent."""
        return getattr(self.scene(), "scale_manager", None)

    def _open_hud(self, mode: str) -> None:
        """Build the manipulator HUD for *mode* as a passive readout.

        Parented to the visible view's viewport (mirroring
        ``Model_Space._create_dynamic_input``); a no-op in a headless scene
        with no view, so tests and off-screen scenes never crash.  The
        ``committed`` signal is connected only for the life of the gesture so a
        typed value can never reach a stale manipulator.
        """
        self._hud = None
        schema_name = _SCHEMA_FOR_MODE.get(mode)
        if schema_name is None:
            return
        view = self._view()
        if view is None:
            return
        from .dynamic_input import DynamicInputHud, SCHEMAS
        schema = SCHEMAS.get(schema_name)
        if schema is None:
            return
        hud = DynamicInputHud(schema, self._scale_manager(), view.viewport())
        hud.committed.connect(self._on_hud_committed)
        if hasattr(view, "place_dynamic_input"):
            # Passive readout: track the cursor (anchor None), same as the
            # placement path before engage.
            view.place_dynamic_input(hud, None)
        hud.show()
        hud.raise_()
        self._hud = hud

    def _feed_hud(self, values: dict) -> None:
        """Push live schema-unit *values* into the HUD if one is open."""
        hud = self._hud
        if hud is not None and not hud.is_engaged():
            hud.set_values(values)

    def _close_hud(self) -> None:
        """Tear the HUD down so ``is_engaged()`` is False and nothing dangles.

        Disconnects first (a stray ``committed`` in the deleteLater window
        would reach a manipulator whose gesture is already over), then removes
        it from the viewport paint/focus chains.
        """
        hud = self._hud
        self._hud = None
        if hud is None:
            return
        try:
            hud.committed.disconnect(self._on_hud_committed)
        except (TypeError, RuntimeError):
            pass
        hud.hide()
        hud.setParent(None)
        hud.deleteLater()

    def _on_hud_committed(self, values: dict) -> None:
        """Apply a typed transform exactly, bake it, and end the gesture.

        Runs during a live gesture: the user armed the drag, then engaged the
        HUD and typed exact numbers.  The typed values are resolved through the
        active schema into the same bake a released drag produces (shared
        ``_bake_*`` helpers), and committed once.  Handles move / resize /
        rotate — the three transform gestures.
        """
        if self._mode is None:
            return
        mode = self._mode
        handle = self._active_handle
        # Snapshot the resting frame BEFORE dropping the held preview: the
        # handles' commit_typed bake from these (spec baked-at-rest rule).
        self._typed_r0 = QRectF(self._R0)
        self._typed_b0 = QTransform(self._B0)
        self._restore_preview()
        self._typed_items = [rec[0] for rec in self._items0]
        self._end_drag()

        if mode == "move":
            offset = resolve_manip_move(None, values)["offset"]
            dx, dy = offset.x(), offset.y()
            if abs(dx) > 1e-12 or abs(dy) > 1e-12:
                self._bake_move(self._typed_items, dx, dy)
        elif handle is not None:
            handle.commit_typed(self, values)
        self._close_hud()
        self.rebake()

    # ------------------------------------------------------------- dragging --

    def _snapshot_items(self) -> None:
        """Capture per-item pre-drag transforms. Byte copy of the loop from _begin."""
        self._items0 = []
        for it in self._items:
            s0 = it.sceneTransform()
            inv, ok = s0.inverted()
            if ok:
                self._items0.append((it, s0, inv, it.transform()))

    def _restore_preview(self) -> None:
        """Drop the held preview. Byte copy of the restore from _finish."""
        self.setTransform(self._B0)
        for it, _s0, _inv, t0 in self._items0:
            it.setTransform(t0)

    def _preview_rotation_deg(self) -> float:
        """Y-up (CCW+) rotation currently applied by an in-progress ROTATE
        held-preview; 0 when not rotating. Lets a migrated item's square grips
        (``grip_render_angle``) track the rotate knob LIVE — the item's own
        angle is not mutated until the release bake, so without this the grips
        would keep their pre-drag orientation while the item visibly turns.
        Uses the same ``_yup_angle_from_delta`` the bake uses → no jump on
        commit."""
        if self._mode != "rotate":
            return 0.0
        return _yup_angle_from_delta(self._D)

    def _resize_cursor(self, role: HandleRole) -> QCursor:
        return self._cursor_for(role)

    def _show_scale_handles(self) -> bool:
        caps = [item_capabilities(i) for i in self._items]
        return len(self._items) == 1 and bool(caps) and "scale" in caps[0]

    def _show_rotate_knob(self) -> bool:
        caps = [item_capabilities(i) for i in self._items]
        if not self._items or not all("rotate" in c for c in caps):
            return False
        if len(self._items) == 1 and getattr(self._items[0],
                                             "MANIP_NO_SOLO_ROTATE", False):
            return False
        return True

    def _begin(self, mode: str, scene_pos: QPointF, screen_pos: QPointF,
               role: Optional[HandleRole] = None) -> None:
        self._mode = mode
        self._role = role
        self._active_handle = None if mode == "move" else self._rigid.get(role)
        self._B0 = self.transform()
        self._R0 = QRectF(self._rect)
        self._start_scene = QPointF(scene_pos)
        self._press_screen = QPointF(screen_pos)
        self._moved = False
        self._base_angle = 0.0            # frame is unrotated at rest (baked)
        self._last_factors = (1.0, 1.0)
        self._D = QTransform()
        self._held_snap = None
        self._snapshot_items()
        # Paper commit path: let the scene capture per-item pre-drag geometry
        # BEFORE any bake mutates the items, so its commit_hook can build
        # old->new undo commands (model scene passes no press_hook).
        if self._press_hook is not None:
            self._press_hook([rec[0] for rec in self._items0])
        if self._active_handle is not None and mode != "grip":
            self._active_handle.on_press(self)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._open_hud(mode)

    def _begin_handle(self, handle, scene_pos: QPointF,
                      screen_pos: QPointF) -> None:
        self._begin(handle.gesture_mode, scene_pos, screen_pos, handle.role)
        # U3: install the pressed handle itself. _begin installs the rigid
        # handle of the same role (or None for a non-rigid GRIP role); a live
        # item handle must drive its own lifecycle. Parity-safe for rigid
        # handles (handle is self._rigid[role]).
        self._active_handle = handle
        # Rigid handles already got their single on_press via _begin (mode !=
        # "grip"); only grip handles need it fired here (mode == "grip" made
        # _begin skip it). Fires exactly once for every handle kind.
        if handle.gesture_mode == "grip":
            handle.on_press(self)

    def _update(self, scene_pos: QPointF,
                mods: Qt.KeyboardModifier, screen_pos: QPointF) -> None:
        if self._mode is None:
            return
        if not self._moved:
            dist = math.hypot(screen_pos.x() - self._press_screen.x(),
                              screen_pos.y() - self._press_screen.y())
            if dist < QApplication.startDragDistance():
                return
            self._moved = True

        if self._active_handle is not None:
            self._active_handle.on_drag(self, scene_pos, mods)
        else:
            shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
            snapped = self._snap(scene_pos)
            d = move_delta(self._start_scene, snapped, ortho=shift)
            self._apply(d)
            # Live readout: dX/dY in schema (scene) units, Y-up (negate scene
            # dy).  set_values converts DIMENSION scene→mm and is a no-op while
            # the user is typing (is_engaged guard inside _feed_hud).
            self._feed_hud({"dX": d.dx(), "dY": -d.dy()})

    def _apply(self, d: QTransform) -> None:
        """Held-transform preview: prepend the scene-space delta to the frame
        and to each item's own transform (no geometry edits during drag)."""
        self._D = d
        self.setTransform(self._B0 * d)
        for it, s0, s0_inv, t0 in self._items0:
            it.setTransform(s0 * d * s0_inv * t0)
        if self._mode == "rotate":
            # Square grips + the rotate knob read the live preview angle; force
            # their hosts to repaint so they turn with the frame as the knob
            # drags (their own orientation depends on _D, which Qt's transform-
            # change repaint doesn't otherwise track).
            for host in list(self._handles.values()) + self._host_pool:
                if host.isVisible():
                    host.update()

    def _finish(self, scene_pos: QPointF, mods: Qt.KeyboardModifier) -> None:
        if self._mode is None:
            return
        mode = self._mode
        # Snapshot the pre-restore state so a handle's on_release can bake from
        # it AFTER _restore_preview/_end_drag (the original _finish captured all
        # bake inputs from live state BEFORE restoring — same ordering).
        self._items0_at_press = list(self._items0)
        self._R0_at_press = QRectF(self._R0)
        self._B0_at_press = QTransform(self._B0)
        moved = self._moved
        if mode == "move" and not moved:
            self._restore_preview(); self._end_drag()
            self._close_hud()
            self._click_through(scene_pos, mods)
            return
        if self._active_handle is not None:
            self._active_handle.on_release(self, scene_pos, mods)
            if moved:
                self.rebake()
        else:
            # Interior move: capture the held delta, restore, then bake.
            d = QTransform(self._D)
            self._restore_preview(); self._end_drag()
            if moved:
                dx, dy = d.dx(), d.dy()
                if abs(dx) > 1e-12 or abs(dy) > 1e-12:
                    self._bake_move([r[0] for r in self._items0_at_press], dx, dy)
            self.rebake()
        self._close_hud()

    def _refresh_fittings(self, items) -> None:
        """Refresh any node fittings after a bake (shared by move/rotate/scale
        so they cannot drift on fitting freshness)."""
        for it in items:
            fitting = getattr(it, "fitting", None)
            if fitting is not None:
                fitting.update()

    def _bake_move(self, items, dx: float, dy: float) -> None:
        """Bake a move of *items* by (dx, dy) and fire one undo.

        The single home for the move commit, shared by the released-drag path
        (:meth:`_finish`) and the typed-commit path (:meth:`_on_hud_committed`)
        so they can never diverge on constraint solving or the undo push.
        """
        for it in items:
            if not bake_translate(it, dx, dy):
                log.warning(
                    "SelectionManipulator: %s has no translate path — "
                    "move not baked", type(it).__name__)
        self._refresh_fittings(items)
        sc = self.scene()
        tools = getattr(sc, "_tools", None)
        if tools is not None:
            tools._solve_constraints()
        if self._commit_hook is not None:
            self._commit_hook("move")

    def _bake_scale(self, items, role: HandleRole,
                    factors: Tuple[float, float], r0: QRectF,
                    b0: QTransform) -> None:
        """Bake a resize of *items* by ``factors`` about the fixed anchor.

        The anchor is the corner diagonally opposite the dragged handle (or the
        centre when Ctrl/from-centre was used — captured in ``factors`` already
        via the resize math), mapped to scene coords through the resting frame
        ``b0``.  Only single-item ``manip_scale`` items reach here (handle
        gating), but the loop is written generically.  One undo per gesture.
        """
        fx, fy = factors
        u, v, _dx, _dy = _ROLE_GEOM[role]
        # Fixed anchor = opposite corner of the dragged handle, in the frame's
        # local (== scene at rest) coords, then to scene through b0.
        anchor_local = _rect_point(r0, 1.0 - u, 1.0 - v)
        anchor = b0.map(anchor_local)
        for it in items:
            fn = getattr(it, "manip_scale", None)
            if fn is None:
                log.warning("SelectionManipulator: %s has no manip_scale — "
                            "resize not baked", type(it).__name__)
                continue
            fn(fx, fy, anchor)
        self._refresh_fittings(items)
        sc = self.scene()
        tools = getattr(sc, "_tools", None)
        if tools is not None:
            tools._solve_constraints()
        if self._commit_hook is not None:
            self._commit_hook("resize")

    def _bake_rotate(self, items, angle_deg: float, pivot: QPointF) -> None:
        """Bake a rotate of *items* by ``angle_deg`` (Y-up CCW+) about *pivot*.

        One undo per gesture, shared by the released-drag path and the typed
        (HUD) path so they can never diverge.
        """
        for it in items:
            fn = getattr(it, "manip_rotate", None)
            if fn is None:
                log.warning("SelectionManipulator: %s has no manip_rotate — "
                            "rotate not baked", type(it).__name__)
                continue
            fn(angle_deg, pivot)
        self._refresh_fittings(items)
        sc = self.scene()
        tools = getattr(sc, "_tools", None)
        if tools is not None:
            tools._solve_constraints()
        if self._commit_hook is not None:
            self._commit_hook("rotate")

    def cancel_drag(self) -> None:
        """Abort the active drag and restore the pre-drag state (no commit)."""
        if self._mode is None:
            return
        self._restore_preview()
        if self._active_handle is not None:
            self._active_handle.on_cancel(self)
        self._end_drag()
        self._close_hud()

    def _end_drag(self) -> None:
        self._mode = None
        self._moved = False
        self._items0 = []
        self._held_snap = None
        self._active_handle = None

    def _click_through(self, scene_pos: QPointF,
                       mods: Qt.KeyboardModifier) -> None:
        """A plain click inside the frame: behave like normal picking so
        overlapping items stay selectable (Ctrl/Shift toggles membership)."""
        sc = self.scene()
        if sc is None:
            return
        v = self._view()
        dt = v.viewportTransform() if v else QTransform()
        hits = [i for i in sc.items(scene_pos,
                                    Qt.ItemSelectionMode.IntersectsItemShape,
                                    Qt.SortOrder.DescendingOrder, dt)
                if self._is_foreign(i)
                and i.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable]
        toggle = bool(mods & (Qt.KeyboardModifier.ShiftModifier
                              | Qt.KeyboardModifier.ControlModifier))
        if not hits:
            if not toggle:
                sc.clearSelection()
            return
        top = hits[0]
        if toggle:
            top.setSelected(not top.isSelected())
        else:
            sc.clearSelection()
            top.setSelected(True)

    # ------------------------------------------------------------ box events --

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._begin("move", event.scenePos(), event.screenPos())
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._update(event.scenePos(), event.modifiers(), event.screenPos())

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._finish(event.scenePos(), event.modifiers())

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self._mode is not None:
            self.cancel_drag()
            event.accept()
        else:
            super().keyPressEvent(event)
