"""
underlay_freeze.py
==================
Gesture-scoped freeze-and-blit for placed vector underlays (spec §18).

During an interactive zoom/pan gesture the batched underlay path items
(20k+ primitives on a dense PDF) are not re-stroked per frame. Instead a
one-off pixmap of the underlay's current on-screen appearance is blitted
— it scales with the view transform (transient bitmap-stretch, accepted)
— while the vector items suppress their paint(). ~100 ms after the last
gesture event the freeze ends and crisp vector rendering returns.

Deliberately NOT setVisible()/setOpacity() based: LevelManager passes,
Underlay-Manager instant-apply edits, the paper pass and snap all keep
operating on live item state; only painting is suppressed.
"""
from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QPainter, QPen, QPixmap, QTransform
from PyQt6.QtWidgets import (QGraphicsItemGroup, QGraphicsPathItem,
                             QGraphicsPixmapItem, QGraphicsRectItem, QStyle)

from .colour_tokens import is_token, resolve_colour, resolve_pen_brush

from .constants import (
    UNDERLAY_FREEZE_MAX_PX,
    UNDERLAY_FREEZE_PAD_FRACTION,
    UNDERLAY_FREEZE_SETTLE_MS,
)
from .crisp_stroke import SplitCache, stroke_cached
from .paper_display import paper_pass_active


class _UnderlayPixmapItem(QGraphicsPixmapItem):
    """Raster underlay: Qt's default selection outline never plots on a sheet
    (wall polish D11)."""

    def paint(self, painter, option, widget=None):
        if paper_pass_active():
            option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)


class _UnderlayGroup(QGraphicsItemGroup):
    """Vector underlay group: its own selection outline never plots on a sheet
    (wall polish D11)."""

    def paint(self, painter, option, widget=None):
        if paper_pass_active():
            option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)


class _UnderlayPlaceholderRect(QGraphicsRectItem):
    """Missing-underlay placeholder: selection outline never plots on a sheet
    (wall polish D11)."""

    def paint(self, painter, option, widget=None):
        if paper_pass_active():
            option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)


class _UnderlayPathItem(QGraphicsPathItem):
    """Batched underlay path item that skips painting while a freeze is on.

    Everything else (visibility, pens, snap, serialization posture) is
    stock QGraphicsPathItem behavior.
    """

    def __init__(self, *args):
        super().__init__(*args)
        # The stroke's crisp axis-split, by value (MW-7, H-MW-f delta 1).
        self._mw_split_cache = SplitCache()
        # Stored layer colour when it is a ``token:*`` or ``""`` (universal
        # picker): resolved per paint on the surface this item paints on, never
        # latched into the pen / brush. None for a plain hex colour.
        self._colour_src: str | None = None

    def set_colour_src(self, src) -> None:
        """Record the stored layer colour *src*. A token / ``""`` is resolved
        per paint (:meth:`resolved_pen_brush`); the pen / brush also get the
        canvas colour now so any reader of them sees a valid colour."""
        if src == "" or is_token(src):
            self._colour_src = src
            c = resolve_colour(src)
            if self.pen().style() == Qt.PenStyle.NoPen:
                self.setBrush(QBrush(c))                 # text batch
            else:
                pen = QPen(self.pen())
                pen.setColor(c)
                self.setPen(pen)
        else:
            self._colour_src = None

    def resolved_pen_brush(self):
        """``(pen, brush)`` to paint with right now: the item's own, except a
        token / ``""`` layer colour resolves on the current surface (canvas
        theme ink / accent, paper black / green, ``""`` fully transparent)."""
        pen, brush = self.pen(), self.brush()
        if self._colour_src is None:
            return pen, brush
        if pen.style() == Qt.PenStyle.NoPen:
            return resolve_pen_brush(self, pen, brush, brush_src=self._colour_src)
        return resolve_pen_brush(self, pen, brush, pen_src=self._colour_src)

    def seed_split(self, split) -> None:
        """Pre-load the identity-frame crisp split of this item's path (built
        alongside it by the batch builder, MW-13): any orthogonal view / group
        transform hits it on the first paint; others split lazily."""
        self._mw_split_cache.seed(self.path(), split)

    def paint(self, painter, option, widget=None):
        scene = self.scene()
        ctrl = getattr(scene, "_underlay_freeze", None)
        if ctrl is not None and ctrl.frozen:
            return
        pen, brush = self.resolved_pen_brush()
        if (pen.style() == Qt.PenStyle.NoPen or not pen.isCosmetic()
                or brush.style() != Qt.BrushStyle.NoBrush):
            if self._colour_src is None:
                super().paint(painter, option, widget)  # text fills / paper
            else:
                painter.setPen(pen)                     # token / "": resolved
                painter.setBrush(brush)
                painter.drawPath(self.path())
            return
        # Canvas stroke: axis runs crisp (MW-7, H-MW-f delta 1). The split is
        # cached per item by path value + rotation -- never per paint / zoom,
        # and never computed on a paper pass (stroke_cached gates first).
        painter.save()
        try:
            stroke_cached(self._mw_split_cache, painter, self.path(), pen)
        finally:
            painter.restore()


class UnderlayFreezeController:
    """Owns the freeze state, the transient pixmap item and the settle timer.

    Owned by Model_Space (``scene._underlay_freeze``); driven by Model_View
    gestures (begin/end) and aborted defensively by every underlay mutation
    site, LevelManager.apply_to_scene, fit_to_screen and SheetViewport.paint.
    """

    def __init__(self, scene):
        self._scene = scene
        self.frozen = False
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._settle = QTimer(scene)
        self._settle.setSingleShot(True)
        self._settle.setInterval(UNDERLAY_FREEZE_SETTLE_MS)
        self._settle.timeout.connect(self.end)

    # ── gesture API (Model_View) ─────────────────────────────────────────

    def begin(self, view) -> None:
        """Start (or extend) a gesture freeze. Safe to call every event."""
        if self.frozen:
            self._settle.start()          # extend the gesture window
            return
        captured = self._capture(view)
        if captured is None:
            return                        # no visible vector underlays
        pixmap, scene_rect, z = captured
        item = QGraphicsPixmapItem(pixmap)
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        item.setZValue(z)
        item.setTransformationMode(
            Qt.TransformationMode.SmoothTransformation)
        dpr = pixmap.devicePixelRatio()
        sx = scene_rect.width() / (pixmap.width() / dpr)
        sy = scene_rect.height() / (pixmap.height() / dpr)
        item.setTransform(QTransform.fromScale(sx, sy))
        item.setPos(scene_rect.topLeft())
        self._scene.addItem(item)
        self._pixmap_item = item
        self.frozen = True
        self._settle.start()
        self._scene.update(scene_rect)

    def end(self) -> None:
        """Restore crisp vector rendering (settle timeout / gesture end /
        defensive abort from a mutation site)."""
        self._settle.stop()
        if not self.frozen:
            return
        self.frozen = False
        item, self._pixmap_item = self._pixmap_item, None
        dirty = None
        if item is not None:
            try:
                dirty = item.mapRectToScene(item.boundingRect())
                self._scene.removeItem(item)
            except RuntimeError:
                dirty = None    # item or scene already C++-deleted — nothing to restore
        if dirty is not None:
            self._scene.update(dirty)

    def abort(self) -> None:
        """Alias of end() — named for mutation-site call sites."""
        self.end()

    # ── capture ──────────────────────────────────────────────────────────

    def _capture(self, view):
        """Hand-render all visible vector underlay children into a padded,
        clamped, transparent pixmap. Returns (pixmap, scene_rect, z) or None.

        Hand-rendering (instead of scene.render) is what isolates underlay
        pixels: model geometry must NOT be in the frozen image or it would
        appear doubled (frozen copy + crisp live repaint) during the gesture.
        """
        vp = view.viewport().rect()
        pad_w = int(vp.width() * UNDERLAY_FREEZE_PAD_FRACTION)
        pad_h = int(vp.height() * UNDERLAY_FREEZE_PAD_FRACTION)
        px_rect = vp.adjusted(-pad_w, -pad_h, pad_w, pad_h)
        dpr = view.viewport().devicePixelRatioF()
        w = min(int(px_rect.width() * dpr), UNDERLAY_FREEZE_MAX_PX)
        h = min(int(px_rect.height() * dpr), UNDERLAY_FREEZE_MAX_PX)
        if w <= 0 or h <= 0:
            return None
        scene_rect = view.mapToScene(px_rect).boundingRect()

        pixmap = QPixmap(w, h)
        pixmap.setDevicePixelRatio(dpr)
        # Transparent: the live theme background shows through, so a theme
        # switch can never leave stale-theme pixels in the frozen image.
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        # No AA: the frozen image only lives inside the gesture's accepted
        # degradation window, and aliased stroking captures ~25-40% faster —
        # the capture is paid synchronously at gesture start.
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        # pixmap px = (viewport px + pad offset), squeezed by the clamp ratio
        # so a clamped pixmap holds the WHOLE padded region at reduced
        # resolution instead of a truncated crop stretched over the viewport.
        sq_x = (w / dpr) / px_rect.width()    # 1.0 unless clamped
        sq_y = (h / dpr) / px_rect.height()
        base = (view.viewportTransform()
                * QTransform().translate(pad_w, pad_h)
                * QTransform().scale(sq_x, sq_y))
        z_values = []
        for record, group in getattr(self._scene, "underlays", []):
            for child in group.childItems():
                if not isinstance(child, _UnderlayPathItem):
                    continue      # raster-PDF pixmap children stay live
                if not child.isVisible():
                    continue      # hidden layer / hidden underlay / level
                painter.setOpacity(group.opacity())
                painter.setWorldTransform(child.sceneTransform() * base)
                pen, brush = child.resolved_pen_brush()
                painter.setPen(pen)                # cosmetic → device width
                painter.setBrush(brush)            # text items: fill
                painter.drawPath(child.path())
                z_values.append(group.zValue())
        painter.end()
        if not z_values:
            return None
        return pixmap, scene_rect, max(z_values)
