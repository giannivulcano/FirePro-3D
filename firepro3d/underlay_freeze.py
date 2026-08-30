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
from PyQt6.QtGui import QPainter, QPixmap, QTransform
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsPixmapItem

from .constants import (
    UNDERLAY_FREEZE_MAX_PX,
    UNDERLAY_FREEZE_PAD_FRACTION,
    UNDERLAY_FREEZE_SETTLE_MS,
)


class _UnderlayPathItem(QGraphicsPathItem):
    """Batched underlay path item that skips painting while a freeze is on.

    Everything else (visibility, pens, snap, serialization posture) is
    stock QGraphicsPathItem behavior.
    """

    def paint(self, painter, option, widget=None):
        scene = self.scene()
        ctrl = getattr(scene, "_underlay_freeze", None)
        if ctrl is not None and ctrl.frozen:
            return
        super().paint(painter, option, widget)


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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
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
                painter.setPen(child.pen())        # cosmetic → device width
                painter.setBrush(child.brush())    # text items: fill
                painter.drawPath(child.path())
                z_values.append(group.zValue())
        painter.end()
        if not z_values:
            return None
        return pixmap, scene_rect, max(z_values)
