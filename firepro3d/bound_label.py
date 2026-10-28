"""bound_label.py -- an element's intrinsic label drawn by an annotation block
(System Blocks concept F5; SB3 slice design D-A).

``BoundLabelItem`` is a child of its host element: the host is the data source
(``element_params`` getters), the block comes from
``scene.annotation_block(category)`` and the paint is the lifted
``block_attributes.bound_text_ops`` + ``render_op.paint_ops`` pipeline a placed
``BlockInstance`` uses -- one implementation. Not selectable, no snaps, never
serialised (the host owns ``show_label`` / ``label_offset``), invisible to HALO
(a non-selectable child), the level filter (typed lists) and
``scene._block_instances``.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainterPath, QPen, QTransform
from PyQt6.QtWidgets import QGraphicsItem

from . import annotative as _an
from . import element_params
from .annotative import SCREEN_SCALE
from .block_attributes import bound_text_ops
from .render_op import paint_ops

_log = logging.getLogger(__name__)

PLACEHOLDER_MM = 200.0            # = block_instance._PLACEHOLDER_MM (orphan box)
PLACEHOLDER_COLOUR = "#c0392b"    # = block_definition._PLACEHOLDER_COLOR (theme-exempt error red)
PEN_MARGIN = 2.0                  # scene units round the ops bbox (BlockInstance._frame_rect's pen margin)
_IDENTITY = QTransform()


def eligible_definition(defn, category: str) -> bool:
    """True when *defn* may draw *category*'s label (SB3 Components row 1 /
    Edge Cases): Scale mode Annotative, On screen = Scale with zoom and
    ``host_category == category``. A Fixed-size, real-size or
    other-category block is treated as missing (the resolver logs + falls
    back)."""
    return (_an.is_annotative(defn) and _an.screen_mode(defn) == SCREEN_SCALE
            and getattr(defn, "host_category", "") == category)


class BoundLabelItem(QGraphicsItem):
    """A host element's label drawn by the block mapped for its category.

    ``host`` = ``parentItem()``; ``definition()`` = the scene's
    ``annotation_block(category)``; the pose is the host's frame translated
    to the anchor (``setPos``) with the annotative factor k folded into the
    ops (SB1c D3: static variant at k, bound glyphs built at scale k), so
    ``boundingRect`` / ``shape`` / the paper pass need no extra code.
    ``_paper_scale`` / ``_paper_pen_width`` / ``_paper_pen_color`` are set by
    ``paper_display._apply_block`` during a viewport pass. Paints nothing when
    every host-bound field resolves to raw None (Q13); draws the orphan
    placeholder when the scene has a resolver that returned None (never
    vanishes); draws nothing in a scene without a resolver.
    """

    def __init__(self, host):
        super().__init__(host)
        self._category = element_params.category_of(host) or ""
        # Paper hooks (paper_display._apply_block; None on the model canvas).
        self._paper_scale = None
        self._paper_pen_width = None
        self._paper_pen_color = None
        # render_op.paint_ops item protocol.
        self._is_ghost = False
        self._crisp_ops = None
        self._pose_rot = 0.0
        self._bound_cache = None      # bound_text_ops (prims, key, ops)
        self._combined = None         # (static, bound, static + bound)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    # -- data source / definition ------------------------------------------
    @property
    def host(self):
        return self.parentItem()

    @property
    def category(self) -> str:
        return self._category

    def _resolve(self):
        """``(definition or None, resolver present)``."""
        fn = getattr(self.scene(), "annotation_block", None)
        if fn is None:
            return None, False
        return fn(self._category), True

    def definition(self):
        return self._resolve()[0]

    def host_values(self):
        """``{host_key: HostValue}`` from the live host, or None (dead host /
        category mismatch -> placeholders, E9)."""
        h = self.parentItem()
        if (h is None or not element_params.is_live(h)
                or element_params.category_of(h) != self._category):
            return None
        return element_params.host_values(h)

    # -- ops ----------------------------------------------------------------
    def _k(self, painter=None) -> float:
        return _an.annotative_factor(self, painter)

    @staticmethod
    def _host_fields_empty(defn, hv) -> bool:
        keys = [a.get("host_key", "") for a in defn.effective_attributes()
                if a.get("source") == "host"]
        return bool(keys) and all(hv.get(k) is None or hv[k].raw is None for k in keys)

    def _ops(self, k: float) -> list:
        d = self.definition()
        if d is None:
            return []
        hv = self.host_values()
        bound, self._bound_cache = bound_text_ops(d, {}, hv, False, k, None,
                                                  self._bound_cache)
        if hv is not None and self._host_fields_empty(d, hv):
            return []                                       # Q13: paints nothing
        static = d.render_ops_variant(False, k)
        if not bound:
            return static
        cc = self._combined
        if cc is not None and cc[0] is static and cc[1] is bound:
            return cc[2]
        out = static + bound
        self._combined = (static, bound, out)
        return out

    def paints(self) -> bool:
        """True when the tag has ink (a resolved block and a non-empty field)."""
        return bool(self._ops(self._k()))

    # -- geometry -------------------------------------------------------------
    def set_anchor(self, pt: QPointF) -> None:
        """Move the block origin to scene point *pt* (the host's frame is the
        scene frame: rooms carry no transform)."""
        self.prepareGeometryChange()
        self.setPos(pt)

    def refresh(self) -> None:
        """Re-shape + repaint (a host value, units or drawing-scale change)."""
        self.prepareGeometryChange()
        self.update()

    def boundingRect(self) -> QRectF:
        ops = self._ops(self._k())
        if ops:
            r = QRectF()
            for op in ops:
                r = r.united(op.path.boundingRect())
        else:
            d, present = self._resolve()
            if not present or d is not None:
                return QRectF()
            h = PLACEHOLDER_MM / 2.0
            r = QRectF(-h, -h, PLACEHOLDER_MM, PLACEHOLDER_MM)
        return r.adjusted(-PEN_MARGIN, -PEN_MARGIN, PEN_MARGIN, PEN_MARGIN)

    def shape(self) -> QPainterPath:
        p = QPainterPath()
        p.addRect(self.boundingRect())
        return p

    def paint(self, painter, option, widget=None):
        ops = self._ops(self._k(painter))
        if not ops:
            d, present = self._resolve()
            if present and d is None:                 # orphan placeholder (G5: never vanishes)
                h = PLACEHOLDER_MM / 2.0
                pen = QPen(QColor(PLACEHOLDER_COLOUR))
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(QRectF(-h, -h, PLACEHOLDER_MM, PLACEHOLDER_MM))
                painter.drawLine(QPointF(-h, -h), QPointF(h, h))
            return
        paint_ops(painter, ops, _IDENTITY, self)
