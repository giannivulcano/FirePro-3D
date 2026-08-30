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
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QTransform
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from . import theme
from .manip_math import move_delta

log = logging.getLogger(__name__)

MANIP_Z = 1e6          # spec: manipulator sits above all scene content
_SHAPE_PAD_PX = 3.0    # interior hit slack so hairline frames stay grabbable
_BOUND_PAD_PX = 6.0    # boundingRect pad (>= shape pad; generous for culling)


# --------------------------------------------------------------------------- #
#  Capability protocol (duck-typed — spec "Capability protocol" table)
# --------------------------------------------------------------------------- #

def item_capabilities(item) -> set:
    """Return the set of manipulator capabilities an item supports.

    ``"translate"`` if any of ``manip_translate``/``translate``/``moveBy``
    exists; ``"rotate"`` iff ``manip_rotate``; ``"scale"`` iff ``manip_scale``.
    """
    caps: set = set()
    if (hasattr(item, "manip_translate") or hasattr(item, "translate")
            or hasattr(item, "moveBy")):
        caps.add("translate")
    if hasattr(item, "manip_rotate"):
        caps.add("rotate")
    if hasattr(item, "manip_scale"):
        caps.add("scale")
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
    fn = getattr(item, "moveBy", None)
    if fn is not None:
        fn(dx, dy)
        return True
    return False


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
            gesture (model scene: ``push_undo_state``).
        exclude: Optional ``callable(item) -> bool``; items for which it
            returns True are never wrapped.
    """

    #: Screen-only selection feedback — never plots.  Honoured by
    #: paper_display.apply_paper_overrides during paper-viewport renders.
    PAPER_EXCLUDED = True

    def __init__(self, scene: QGraphicsScene, *,
                 commit_hook: Optional[Callable[[str], None]] = None,
                 exclude: Optional[Callable[[QGraphicsItem], bool]] = None):
        super().__init__()
        self._commit_hook = commit_hook
        self._exclude = exclude

        self._rect = QRectF()
        self._sel_ids: frozenset = frozenset()
        self._items: List[QGraphicsItem] = []

        # drag state
        self._mode: Optional[str] = None
        self._B0 = QTransform()
        self._R0 = QRectF()
        self._start_scene = QPointF()
        self._press_screen = QPointF()
        self._moved = False
        self._items0: List[Tuple[QGraphicsItem, QTransform,
                                 QTransform, QTransform]] = []
        self._D = QTransform()
        self._held_snap = None

        self.setZValue(MANIP_Z)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.hide()

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
        """Position child handles on the frame (no handles yet — later tasks)."""

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

    # ------------------------------------------------------------- dragging --

    def _begin(self, mode: str, scene_pos: QPointF, screen_pos: QPointF) -> None:
        self._mode = mode
        self._B0 = self.transform()
        self._R0 = QRectF(self._rect)
        self._start_scene = QPointF(scene_pos)
        self._press_screen = QPointF(screen_pos)
        self._moved = False
        self._D = QTransform()
        self._held_snap = None
        self._items0 = []
        for it in self._items:
            s0 = it.sceneTransform()
            inv, ok = s0.inverted()
            if ok:
                self._items0.append((it, s0, inv, it.transform()))
        self.setFocus(Qt.FocusReason.MouseFocusReason)

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
        if self._mode == "move":
            snapped = self._snap(scene_pos)
            d = move_delta(self._start_scene, snapped, ortho=shift)
            self._apply(d)

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
        moved = self._moved
        d = QTransform(self._D)
        items = [rec[0] for rec in self._items0]

        # Restore the preview: committed state carries no Qt item transform
        # (spec baked-at-rest rule).
        self.setTransform(self._B0)
        for it, _s0, _inv, t0 in self._items0:
            it.setTransform(t0)
        self._end_drag()

        if mode == "move" and not moved:
            self._click_through(scene_pos, mods)
            return

        if mode == "move":
            dx, dy = d.dx(), d.dy()
            if abs(dx) > 1e-12 or abs(dy) > 1e-12:
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
            self.rebake()

    def cancel_drag(self) -> None:
        """Abort the active drag and restore the pre-drag state (no commit)."""
        if self._mode is None:
            return
        self.setTransform(self._B0)
        for it, _s0, _inv, t0 in self._items0:
            it.setTransform(t0)
        self._end_drag()

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
