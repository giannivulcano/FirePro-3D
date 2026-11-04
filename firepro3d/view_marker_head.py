"""view_marker_head.py -- the annotation-block head of a view marker (SB4d D1).

``ViewMarkerHead`` is an ``OutlinedLabel`` child of its marker (data host =
graphics parent, the ``GridlineBubble`` pattern): the cardinal elevation
head, each end of a placed section and the detail callout bubble. Its
category comes from the host (``element_params.category_of``: Elevation /
Section / Detail), so one class serves all three. Upright (never rotated),
annotative (k = the drawing scale on screen, 1 / S on paper through
``paper_display._apply_block``). The marker builds its bespoke arrow from
``enclosing_radius()`` and trims its lines at ``trim_distance()``. The one
overlay is the screen-only selection ring. In a detail (clip) view a
DetailMarker's head paints nothing as an item -- like its marker -- because
``Model_View.drawForeground`` repaints the own detail's callout above the
crop mask (D6).
"""
from __future__ import annotations

import math

from PyQt6.QtGui import QColor, QPen

from .bound_label import OutlinedLabel
from .paper_display import shows_selection


class ViewMarkerHead(OutlinedLabel):
    """One head of a SectionMarker / DetailMarker (SB4d D1)."""

    def __init__(self, marker):
        super().__init__(marker)                 # child=True: parent + data host

    def enclosing_radius(self) -> float:
        """Radius of the smallest origin-centred circle holding the block
        outline at the current k, scene units (D1 / Q5: the arrow is built
        tangent to it); 0.0 when the head has no outline (off-scene / no
        block resolved)."""
        r = 0.0
        for poly in self.outline_path().toSubpathPolygons():
            for p in poly:
                r = max(r, math.hypot(p.x(), p.y()))
        return r

    def overlay_pens(self) -> list:
        """The selection ring in the marker's line colour, screen only."""
        m = self.parentItem()
        if m is None or not shows_selection(m):
            return []
        col = m._marker_color if hasattr(m, "_marker_color") else m._tag_color
        pen = QPen(QColor(col).lighter(150), 2.0)
        pen.setCosmetic(True)
        return [pen]

    def paint(self, painter, option, widget=None):
        view = widget.parentWidget() if widget is not None else None
        if (view is not None and getattr(view, "_clip_rect", None) is not None
                and type(self.parentItem()).__name__ == "DetailMarker"):
            return                               # a clip view: drawn by drawForeground (D6)
        super().paint(painter, option, widget)
