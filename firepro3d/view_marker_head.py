"""view_marker_head.py -- the annotation-block head of a view marker (SB4d D1).

``ViewMarkerHead`` is an ``OutlinedLabel`` child of its marker (data host =
graphics parent, the ``GridlineBubble`` pattern): the cardinal elevation
head, each end of a placed section and the detail callout bubble. Its
category comes from the host (``element_params.category_of``: Elevation /
Section / Detail), so one class serves all three. Upright (never rotated),
annotative (k = the drawing scale on screen, 1 / S on paper: its marker's
paper pass enters it through ``paper_pass.enter_block_hooks``, see
``_MarkerPaperMixin``). The marker builds its bespoke arrow from
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


class _MarkerPaperMixin:
    """Paper pass for a view marker (paper-space.md s6.2; SB4d D1 / D7):
    ``SectionMarker`` (cardinal / placed) and ``DetailMarker``. The marker's
    LINE takes the row colour + opacity (``paper_display._apply_marker``);
    each visible head is an annotation block entered through the shared
    helper at opacity 1. Listed first in the marker's bases."""

    _PAPER_COLOR_ATTR = "_marker_color"   # DetailMarker: "_tag_color"

    def paper_heads(self) -> list:
        """The annotation-block heads this marker owns (SB4d D1): a
        cardinal's ``head``, a placed section's ``head_a`` / ``head_b``, a
        detail's ``bubble``."""
        return [h for h in (getattr(self, "head", None), getattr(self, "head_a", None),
                            getattr(self, "head_b", None), getattr(self, "bubble", None))
                if h is not None]

    def enter_paper_pass(self, ctx, cat):
        """The marker's paper LINE (colour attr, pen where the marker has one,
        the row opacity), then each visible head (D5: they map onto this
        marker) through the shared annotation-block helper at opacity 1
        (SB4d D1), then ``prepareGeometryChange`` (the arrow / leader follow
        the paper k). Saves first (the token), then writes; a raise mid-write
        unwinds the marker and every head entered so far.

        Args:
            ctx: The pass's ``paper_pass.PaperPassContext``.
            cat: The merged marker paper row (``ctx.merge``), Visible on.

        Returns:
            The token :meth:`exit_paper_pass` takes.
        """
        from . import paper_pass
        attr = self._PAPER_COLOR_ATTR
        c = getattr(self, attr, None)
        tok = {"opacity": self.opacity(),
               "marker_color": c.name() if isinstance(c, QColor) else c,
               "pen": self.pen() if hasattr(self, "pen") else None,
               "brush": self.brush() if hasattr(self, "brush") else None,
               "heads": []}

        def write():
            from . import paper_display as pd
            authored = pd.row_as_authored(cat)
            lw_mm = ctx.lw_mm(cat)
            pd._apply_marker(self, cat, authored, lw_mm, attr,
                             ctx.auth_tok(self, self.paper_category, authored))
            for h in self.paper_heads():   # SB4d D1: annotative heads print at authored mm
                if h.isVisible():
                    tok["heads"].append(paper_pass.enter_block_hooks(
                        h, ctx, cat, authored, lw_mm, opacity=1.0))
            self.prepareGeometryChange()   # the arrow / leader follow the paper k
        return paper_pass.enter_guarded(self.exit_paper_pass, tok, write)

    def exit_paper_pass(self, tok: dict) -> None:
        """Undo :meth:`enter_paper_pass` (the base restore order: opacity, line
        colour, pen, brush, heads); tolerates a partly-entered token. Each
        entered head gets its real prior opacity back (AC6)."""
        from . import paper_pass
        self.setOpacity(tok["opacity"])
        mc = tok["marker_color"]
        if mc is not None:
            setattr(self, self._PAPER_COLOR_ATTR, QColor(mc))
        if tok["pen"] is not None:
            self.setPen(tok["pen"])
        if tok["brush"] is not None:
            self.setBrush(tok["brush"])
        try:
            for ht in tok["heads"]:
                paper_pass.exit_block_hooks(ht)
        finally:
            for h in self.paper_heads():
                h.refresh()
            self.prepareGeometryChange()
            self.update()


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
