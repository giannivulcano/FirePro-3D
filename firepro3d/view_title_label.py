"""view_title_label.py -- a sheet viewport's title, drawn by an annotation block
(SB4f, design 2026-11-04-sb4f-view-title-design.md).

``ViewTitleLabel`` is a child of its ``SheetViewport``: the viewport is the data
source (the ``View Title`` keys), the block comes from
``PaperScene.annotation_block`` and k = 1 on paper. It also paints the composite
line (D4), so the viewport's own hit area stays the box, and passes its mouse
events to the viewport, so the title acts as the viewport body does (D1).
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QPen

from .block_attributes import bound_text_ops
from .bound_label import PEN_MARGIN, OutlinedLabel
from .constants import (VIEW_TITLE_LINE_PEN_MM, VIEW_TITLE_ORIGIN_Y_MM,
                        VIEW_TITLE_PLACEHOLDER_MM)
from .element_params import HostValue

VIEW_TITLE_CATEGORY = "View Title"


def extent_below_box(defn) -> float:
    """How far a title at its default spot reaches below the box, mm (the drop
    clamp, AC7). *defn* = the resolved block, or None for the orphan box."""
    if defn is None:
        return VIEW_TITLE_ORIGIN_Y_MM + VIEW_TITLE_PLACEHOLDER_MM / 2.0
    keys = [a.get("host_key", "") for a in defn.effective_attributes()
            if a.get("source") == "host"]
    sample = {k: HostValue("0", "text") for k in keys}
    bound, _ = bound_text_ops(defn, {}, sample, False, 1.0, None, None)
    bottom = 0.0
    for op in list(defn.render_ops_variant(False, 1.0)) + list(bound):
        bottom = max(bottom, op.path.boundingRect().bottom())
    return VIEW_TITLE_ORIGIN_Y_MM + bottom


class ViewTitleLabel(OutlinedLabel):
    """The block under a viewport plus the line that runs along the box."""

    placeholder_mm = VIEW_TITLE_PLACEHOLDER_MM

    def __init__(self, viewport):
        super().__init__(viewport)
        self._line = None             # (x0, x1) local on y = 0; None = no line
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton
                                     | Qt.MouseButton.RightButton)

    def refresh(self) -> None:
        self._line = None
        super().refresh()

    def _line_span(self):
        """Local ``(x0, x1)`` of the line, or None when the label has no ink.

        From the outline's right edge to the box's right edge while the outline
        sits below the box and left of that edge; a fixed box width elsewhere
        (AC2)."""
        st = self._state()
        if not (self._ops(self._k(None, st[0]), st) or self._orphan_visible(st)):
            return None
        d = self.host.data
        p = self.pos()
        r = self.outline_path().boundingRect()
        x0 = self.trim_distance(1.0, 0.0)
        if p.y() + r.top() >= d.h and p.x() + r.right() < d.w:
            return x0, d.w - p.x()
        return x0, x0 + d.w

    def _compute_rect(self) -> QRectF:
        base = super()._compute_rect()
        self._rect = base             # outline_path's "nothing closes" branch reads bounds
        self._line = self._line_span()
        if self._line is None:
            return base
        x0, x1 = self._line
        return base.united(QRectF(x0, -PEN_MARGIN, x1 - x0, 2.0 * PEN_MARGIN))

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        self.boundingRect()           # fills _line after a refresh
        if self._line is None:
            return
        x0, x1 = self._line
        painter.setPen(QPen(Qt.GlobalColor.black, VIEW_TITLE_LINE_PEN_MM))
        painter.drawLine(QPointF(x0, 0.0), QPointF(x1, 0.0))

    # -- the title acts as the viewport body (Phase 4 P4 probe) ---------------
    def mousePressEvent(self, event):
        self.host.mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.host.mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.host.mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.host.mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        self.host.contextMenuEvent(event)
