"""HALO preselection-highlight overlay painter (mirrors paint_snap_indicator)."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPen


def paint_halo_highlight(painter, view, item, theme):
    """Draw a cosmetic outline around *item*'s shape in scene coords."""
    if item is None:
        return
    painter.save()
    pen = QPen(theme.color("selection_hover"), 2)
    pen.setCosmetic(True)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(item.mapToScene(item.shape()))
    painter.restore()
