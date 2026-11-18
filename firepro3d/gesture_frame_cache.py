"""Per-view still-frame cache for transform gestures (scene-tools D11).

While a transform tool is live the scene's items do not change per move —
only the foreground overlays (ghost, snap marker, axis) do. A view armed
with :meth:`GestureFrameCacheMixin.begin_gesture_frame` renders background
+ items once into a pixmap and, per paint, blits it and runs
``drawForeground`` live. The pixmap drops on ``scene.changed``, on any
change of viewport size / DPR / viewport transform, and on
:meth:`drop_gesture_frame` (view-only state such as the dot grid).
"""
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QPainter, QPixmap


class GestureFrameCacheMixin:
    """Mix in before ``QGraphicsView`` (``class V(GestureFrameCacheMixin, QGraphicsView)``).

    The view's ``drawForeground`` must return right after its
    ``super().drawForeground`` call while ``_fc_capturing`` is set, so the
    captured frame holds background + items only.
    """

    _fc_armed = False
    _fc_pixmap = None
    _fc_key = None
    _fc_capturing = False
    _fc_scene = None

    def begin_gesture_frame(self) -> None:
        """Arm the cache; the next paint captures the still frame."""
        self._fc_pixmap = None
        if self._fc_scene is None and self.scene() is not None:
            self._fc_scene = self.scene()
            self._fc_scene.changed.connect(self.drop_gesture_frame)
        self._fc_armed = True

    def end_gesture_frame(self) -> None:
        """Disarm, free the pixmap and repaint normally."""
        was = self._fc_armed
        self._fc_armed = False
        self._fc_pixmap = None
        self._fc_key = None
        if self._fc_scene is not None:
            try:
                self._fc_scene.changed.disconnect(self.drop_gesture_frame)
            except TypeError:
                pass
            self._fc_scene = None
        if was:
            self.viewport().update()

    def drop_gesture_frame(self, *_args) -> None:
        """Forget the captured frame (re-captured on the next paint)."""
        self._fc_pixmap = None

    def _fc_current_key(self):
        vp = self.viewport()
        t = self.viewportTransform()
        return (vp.width(), vp.height(), vp.devicePixelRatioF(),
                t.m11(), t.m12(), t.m21(), t.m22(), t.dx(), t.dy())

    def _fc_capture(self) -> None:
        vp = self.viewport()
        dpr = vp.devicePixelRatioF()
        pm = QPixmap(round(vp.width() * dpr), round(vp.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(vp.palette().color(vp.backgroundRole()))
        p = QPainter(pm)
        # render() paints with the painter's hints, not the view's: copy them
        # so the cached items antialias exactly as the live item pass does.
        p.setRenderHints(self.renderHints())
        self._fc_capturing = True
        try:
            self.render(p, QRectF(0, 0, vp.width(), vp.height()), vp.rect())
        finally:
            self._fc_capturing = False
            p.end()
        self._fc_pixmap = pm

    def paintEvent(self, event):  # noqa: N802 (Qt naming)
        if not self._fc_armed:
            return super().paintEvent(event)
        key = self._fc_current_key()
        if self._fc_pixmap is None or key != self._fc_key:
            self._fc_capture()
            self._fc_key = key
        p = QPainter(self.viewport())
        p.setRenderHints(self.renderHints())
        p.setClipRegion(event.region())
        p.drawPixmap(0, 0, self._fc_pixmap)
        p.setTransform(self.viewportTransform())
        self.drawForeground(p, self.mapToScene(event.rect()).boundingRect())
        p.end()
