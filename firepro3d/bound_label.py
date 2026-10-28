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
