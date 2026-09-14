"""HALO preselection-highlight overlay painter (mirrors paint_snap_indicator)."""
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPen, QColor


def halo_scene_path(item):
    """The item's shape mapped to scene coords via Qt's canonical sceneTransform
    (respects pos()/transform(); does NOT re-apply baked-rotation that shape()
    already contains — unlike the items' overridden mapToScene)."""
    return item.sceneTransform().map(item.shape())


def paint_halo_highlight(painter, view, item, theme):
    """Draw a cosmetic outline around *item*'s shape in scene coords."""
    if item is None:
        return
    painter.save()
    pen = QPen(theme.color("selection_hover"), 2)
    pen.setCosmetic(True)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(halo_scene_path(item))
    painter.restore()


def paint_rubber_band(painter, view, rb_start, rb_end, theme):
    """Draw the direction-dependent scene-drawn band in viewport coords.

    L->R = window (theme 'selection', solid); R->L = crossing (theme 'ok', dashed).
    Caller guards rb_active/rb_end and passes viewport-px points.
    """
    painter.save()
    painter.resetTransform()
    crossing = rb_end.x() < rb_start.x()
    base = theme.color("ok" if crossing else "selection")
    pen = QPen(base, 1)
    pen.setStyle(Qt.PenStyle.DashLine if crossing else Qt.PenStyle.SolidLine)
    painter.setPen(pen)
    fill = QColor(base); fill.setAlpha(40)
    painter.setBrush(fill)
    painter.drawRect(QRectF(QPointF(rb_start), QPointF(rb_end)).normalized())
    painter.restore()
