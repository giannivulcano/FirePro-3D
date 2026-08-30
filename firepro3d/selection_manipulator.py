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
    QBrush, QColor, QCursor, QPainter, QPainterPath, QPen, QPixmap, QTransform,
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
    HandleRole, _ROLE_GEOM, _RESIZE_ROLES, _rect_point,
    move_delta, resize_delta, rotate_delta,
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


class _Handle(QGraphicsItem):
    """Screen-constant grab handle — a child of the SelectionManipulator.

    ``ItemIgnoresTransformations`` keeps the handle a constant device-pixel size
    at any zoom.  Press begins the manipulator's ``resize``/``rotate`` gesture
    for this handle's role via ``manip._begin``; move/release forward to
    ``_update``/``_finish`` exactly as an interior-move drag does.
    """

    def __init__(self, manip: "SelectionManipulator", role: HandleRole):
        super().__init__(manip)
        self._manip = manip
        self.role = role
        self._hover = False
        # Model scene: screen-constant device-px handles (ItemIgnoresTransformations).
        # Paper scene: paper-mm handles that scale with the 1-unit==1-mm scene, so
        # they plot/print at a true millimetre size (theming.md split).  The flag
        # is owned by the manipulator (per-scene sizing mode).
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                     not manip._handle_mm)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setZValue(2.0 if role is not HandleRole.ROTATE else 1.5)

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

    def _knob_center(self) -> QPointF:
        """Rotate-knob centre in this item's (device) frame — above the top-mid.

        The frame carries no rotation at rest (bake-at-rest), so the knob sits
        straight up (device -y) by the stem offset.
        """
        return QPointF(0.0, -_ROTATE_OFFSET_PX)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        if self.role is HandleRole.ROTATE:
            c = self._knob_center()
            r = _ROTATE_RADIUS_PX + self._grab_pad()
            path.addEllipse(c, r, r)
        else:
            h = self._half()
            path.addRect(QRectF(-h, -h, 2 * h, 2 * h))
        return path

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: Optional[QWidget] = None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        border = self._manip._handle_color(self._hover)
        fill = _handle_fill()
        bw = self._border()
        if self.role is HandleRole.ROTATE:
            c = self._knob_center()
            stem = QPen(QColor(border.red(), border.green(), border.blue(), 140), 1.0)
            painter.setPen(stem)
            painter.drawLine(QPointF(0, 0), c)
            painter.setPen(QPen(border, bw))
            painter.setBrush(QBrush(border if self._hover else fill))
            painter.drawEllipse(c, _ROTATE_RADIUS_PX, _ROTATE_RADIUS_PX)
        else:
            size = self._size()
            half = size / 2.0
            painter.setPen(QPen(border, bw))
            painter.setBrush(QBrush(border if self._hover else fill))
            painter.drawRect(QRectF(-half, -half, size, size))

    # -- interaction ----------------------------------------------------------

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hover = True
        self.setCursor(self._manip._cursor_for(self.role))
        self.update()

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hover = False
        self.unsetCursor()
        self.update()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            mode = "rotate" if self.role is HandleRole.ROTATE else "resize"
            self._manip._begin(mode, event.scenePos(), event.screenPos(), self.role)
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
        # every _Handle; the flag also decides ItemIgnoresTransformations.
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

        # Screen-constant children: 8 resize handles + one rotate knob.  Their
        # visibility is capability-gated in ``_layout`` (frame+move only for
        # multi-select / parametric single-select).
        self._handles = {role: _Handle(self, role) for role in _RESIZE_ROLES}
        self._handles[HandleRole.ROTATE] = _Handle(self, HandleRole.ROTATE)
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

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: Optional[QWidget] = None) -> None:
        try:
            color = QColor(theme.detect().selection)
        except Exception:                       # headless / no palette yet
            color = QColor("#63BE8B")
        pen = QPen(color, 1.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
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
            u, v, _, _ = _ROLE_GEOM[role]
            self._handles[role].setPos(_rect_point(r, u, v))
        # Knob anchored at the top-edge midpoint; the stem/knob draw upward from
        # there in device space (see _Handle._knob_center).
        self._handles[HandleRole.ROTATE].setPos(_rect_point(r, 0.5, 0.0))

        caps = [item_capabilities(i) for i in self._items]
        single = len(self._items) == 1
        show_scale = single and bool(caps) and "scale" in caps[0]
        show_rotate = bool(self._items) and all("rotate" in c for c in caps)
        for role in _RESIZE_ROLES:
            self._handles[role].setVisible(show_scale)
        self._handles[HandleRole.ROTATE].setVisible(show_rotate)

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
        return views[0] if views else None

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
        role = self._role
        r0 = QRectF(self._R0)
        b0 = QTransform(self._B0)
        # Drop the held preview first: committed geometry carries no Qt item
        # transform (spec baked-at-rest rule).
        self.setTransform(self._B0)
        for it, _s0, _inv, t0 in self._items0:
            it.setTransform(t0)
        items = [rec[0] for rec in self._items0]
        self._end_drag()

        if mode == "move":
            offset = resolve_manip_move(None, values)["offset"]
            dx, dy = offset.x(), offset.y()
            if abs(dx) > 1e-12 or abs(dy) > 1e-12:
                self._bake_move(items, dx, dy)
        elif mode == "resize":
            res = resolve_manip_resize(None, values)
            w0, h0 = r0.width(), r0.height()
            fx = (res["width"] / w0) if w0 > 1e-12 else 1.0
            fy = (res["height"] / h0) if h0 > 1e-12 else 1.0
            if abs(fx - 1.0) > 1e-12 or abs(fy - 1.0) > 1e-12:
                self._bake_scale(items, role, (fx, fy), r0, b0)
        elif mode == "rotate":
            # Typed angle is the absolute app (Y-up) orientation; the frame is
            # unrotated at rest, so the delta equals the typed value.
            angle_deg = resolve_manip_rotate(None, values)["angle_deg"]
            if abs(angle_deg) > 1e-9:
                pivot = b0.map(r0.center())
                self._bake_rotate(items, angle_deg, pivot)
        self._close_hud()
        self.rebake()

    # ------------------------------------------------------------- dragging --

    def _begin(self, mode: str, scene_pos: QPointF, screen_pos: QPointF,
               role: Optional[HandleRole] = None) -> None:
        self._mode = mode
        self._role = role
        self._B0 = self.transform()
        self._R0 = QRectF(self._rect)
        self._start_scene = QPointF(scene_pos)
        self._press_screen = QPointF(screen_pos)
        self._moved = False
        self._base_angle = 0.0            # frame is unrotated at rest (baked)
        self._last_factors = (1.0, 1.0)
        self._D = QTransform()
        self._held_snap = None
        self._items0 = []
        for it in self._items:
            s0 = it.sceneTransform()
            inv, ok = s0.inverted()
            if ok:
                self._items0.append((it, s0, inv, it.transform()))
        # Paper commit path: let the scene capture per-item pre-drag geometry
        # BEFORE any bake mutates the items, so its commit_hook can build
        # old->new undo commands (model scene passes no press_hook).
        if self._press_hook is not None:
            self._press_hook([rec[0] for rec in self._items0])
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._open_hud(mode)

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

        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        if self._mode == "move":
            snapped = self._snap(scene_pos)
            d = move_delta(self._start_scene, snapped, ortho=shift)
            self._apply(d)
            # Live readout: dX/dY in schema (scene) units, Y-up (negate scene
            # dy).  set_values converts DIMENSION scene→mm and is a no-op while
            # the user is typing (is_engaged guard inside _feed_hud).
            self._feed_hud({"dX": d.dx(), "dY": -d.dy()})
        elif self._mode == "resize":
            # Snap the dragged handle point (spec lifecycle step 2), then compute
            # the scale delta in the (unrotated) frame.  Shift = keep aspect,
            # Ctrl = scale about the centre.
            snapped = self._snap(scene_pos)
            d, fx, fy = resize_delta(self._B0, self._R0, self._role,
                                     self._start_scene, snapped,
                                     keep_aspect=shift, from_center=ctrl)
            self._last_factors = (fx, fy)
            self._apply(d)
            self._feed_hud({"Width": abs(self._R0.width() * fx),
                            "Height": abs(self._R0.height() * fy)})
        elif self._mode == "rotate":
            # No OSNAP on rotate; Shift = 15° absolute snap.  Centre is the
            # frame centre (unrotated at rest).
            center = self._B0.map(self._R0.center())
            snap = _ROTATE_SNAP_DEG if shift else None
            d, total = rotate_delta(center, self._start_scene, scene_pos,
                                    self._base_angle, snap)
            self._apply(d)
            # total is the Qt (y-down CW+) absolute angle; the app readout is
            # Y-up CCW+, so negate.
            self._feed_hud({"Angle": -total})

    def _apply(self, d: QTransform) -> None:
        """Held-transform preview: prepend the scene-space delta to the frame
        and to each item's own transform (no geometry edits during drag)."""
        self._D = d
        self.setTransform(self._B0 * d)
        for it, s0, s0_inv, t0 in self._items0:
            it.setTransform(s0 * d * s0_inv * t0)

    def _finish(self, scene_pos: QPointF, mods: Qt.KeyboardModifier) -> None:
        if self._mode is None:
            return
        mode = self._mode
        role = self._role
        moved = self._moved
        d = QTransform(self._D)
        factors = self._last_factors
        r0 = QRectF(self._R0)
        b0 = QTransform(self._B0)
        items = [rec[0] for rec in self._items0]

        # Restore the preview: committed state carries no Qt item transform
        # (spec baked-at-rest rule).
        self.setTransform(self._B0)
        for it, _s0, _inv, t0 in self._items0:
            it.setTransform(t0)
        self._end_drag()

        if mode == "move" and not moved:
            self._close_hud()
            self._click_through(scene_pos, mods)
            return

        if mode == "move":
            dx, dy = d.dx(), d.dy()
            if abs(dx) > 1e-12 or abs(dy) > 1e-12:
                self._bake_move(items, dx, dy)
            self.rebake()
        elif mode == "resize":
            if moved:
                self._bake_scale(items, role, factors, r0, b0)
                self.rebake()
        elif mode == "rotate":
            if moved:
                angle_deg = _yup_angle_from_delta(d)
                if abs(angle_deg) > 1e-9:
                    pivot = b0.map(r0.center())
                    self._bake_rotate(items, angle_deg, pivot)
                self.rebake()
        self._close_hud()

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
            fitting = getattr(it, "fitting", None)
            if fitting is not None:
                fitting.update()
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
        self.setTransform(self._B0)
        for it, _s0, _inv, t0 in self._items0:
            it.setTransform(t0)
        self._end_drag()
        self._close_hud()

    def _end_drag(self) -> None:
        self._mode = None
        self._moved = False
        self._items0 = []
        self._held_snap = None

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
