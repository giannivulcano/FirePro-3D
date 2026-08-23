"""
displayable_item.py
===================
Mixin class providing shared display-manager attributes for all scene items
that participate in the Display Manager's category/instance system.

Usage — add to the MRO alongside the Qt graphics item base class::

    class WallSegment(DisplayableItemMixin, QGraphicsPathItem):
        def __init__(self, ...):
            QGraphicsPathItem.__init__(self)
            self.init_displayable()   # sets level, display overrides
            ...

The mixin deliberately does **not** call ``super().__init__()`` to avoid
interfering with the Qt graphics item constructor chain.  Call
``init_displayable()`` explicitly in your ``__init__``.
"""

from __future__ import annotations

import math
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen, QTransform, QPolygonF
from .constants import DEFAULT_LEVEL

_SECTION_HATCH_COLOR = QColor(100, 100, 100)  # fallback for section hatching


def _apply_hatch_pattern(painter, clip_path: "QPainterPath", scene,
                          pattern: str, hatch_col: "QColor",
                          line_width: float = 1.0,
                          hatch_scale: float = 1.0):
    """Internal helper: draw hatch lines for *pattern* clipped to *clip_path*.

    Handles both SVG and built-in Qt brush patterns.  Caller is responsible
    for any outer save/restore; this function manages its own painter state.

    *scene* may be ``None`` — falls back to viewport scale 1.0.
    """
    from .hatch_patterns import make_hatch_brush, is_svg, draw_svg_hatch

    views = scene.views() if scene else []
    scale = abs(views[0].transform().m11()) if views else 1.0

    if is_svg(pattern):
        # SVG patterns — draw as true vector lines (perfectly crisp).
        # draw_svg_hatch manages its own save/restore and clip.
        draw_svg_hatch(painter, clip_path, scene, pattern, hatch_col,
                       line_width=line_width, hatch_scale=hatch_scale)
    else:
        # Built-in Qt patterns — resolution-independent brush fill.
        painter.save()
        # IntersectClip: respect any outer clip (e.g. paper-viewport crop rect).
        painter.setClipPath(clip_path, Qt.ClipOperation.IntersectClip)
        brush = make_hatch_brush(pattern, 24, hatch_col)
        inv = 1.0 / max(scale, 1e-6) * hatch_scale
        brush.setTransform(QTransform().scale(inv, inv))
        painter.setPen(QPen(QColor(0, 0, 0, 0)))
        painter.setBrush(brush)
        painter.drawRect(clip_path.boundingRect())
        painter.restore()


def draw_section_hatch(painter, clip_path: "QPainterPath", scene,
                       color: "QColor | None" = None,
                       pattern: str = "diagonal",
                       line_width: float = 1.0,
                       section_fill: "QColor | None" = None,
                       hatch_scale: float = 1.0):
    """Fill *clip_path* with a section hatch overlay.

    *section_fill*  — solid fill colour for the section body (replaces
                      the element's normal fill).  If ``None``, no fill.
    *color*         — hatch-line colour (should match the element's
                      normal line colour).
    *line_width*    — hatch-line weight in screen pixels.
    *hatch_scale*   — multiplier for pattern density (1.0 = default).
    *pattern*       — pattern name from ``hatch_patterns``.
    """
    if clip_path.isEmpty():
        return

    hatch_col = color or _SECTION_HATCH_COLOR

    painter.save()
    # IntersectClip (not the default ReplaceClip): the section fill/hatch must
    # respect any outer clip already on the painter — e.g. a paper viewport's
    # ``fitted`` crop rect. ReplaceClip discarded it, so a section-cut wall
    # straddling the crop edge bled its solid fill outside the viewport box.
    painter.setClipPath(clip_path, Qt.ClipOperation.IntersectClip)

    # 1. Solid section-fill background
    if section_fill is not None:
        painter.setPen(QPen(QColor(0, 0, 0, 0)))
        painter.setBrush(QBrush(section_fill))
        painter.drawRect(clip_path.boundingRect())

    painter.restore()

    # 2. Hatch lines on top (delegates to shared helper)
    _apply_hatch_pattern(painter, clip_path, scene, pattern, hatch_col,
                         line_width=line_width, hatch_scale=hatch_scale)


def draw_fill(painter, closed_path: "QPainterPath | None", scene,
              fill_type: str, pattern: str, colour: str,
              alpha: int = 115):
    """Render a 2-D closed-shape fill (solid or hatch) into *painter*.

    Parameters
    ----------
    painter     : active QPainter (caller owns begin/end)
    closed_path : filled region; silently returns when None or empty
    scene       : QGraphicsScene or None (used only for viewport-scale lookup)
    fill_type   : ``"none"`` — no fill (early-out)
                  ``"solid"`` — semi-transparent flat colour
                  ``"hatch"`` — tiled hatch pattern
    pattern     : hatch pattern name (see ``hatch_patterns.PATTERN_NAMES``);
                  ignored for ``"solid"``/``"none"``
    colour      : CSS colour string (``"#rrggbb"``) for the fill
    alpha       : opacity 0-255 applied to the colour (default 115 ≈ 45 %)
    """
    if closed_path is None or closed_path.isEmpty():
        return
    if fill_type == "none":
        return

    fill_col = QColor(colour)

    if fill_type == "solid":
        fill_col.setAlpha(alpha)
        painter.save()
        # IntersectClip: honour any outer viewport crop.
        painter.setClipPath(closed_path, Qt.ClipOperation.IntersectClip)
        painter.setPen(QPen(QColor(0, 0, 0, 0)))
        painter.setBrush(QBrush(fill_col))
        painter.drawRect(closed_path.boundingRect())
        painter.restore()

    elif fill_type == "hatch":
        fill_col.setAlpha(alpha)
        _apply_hatch_pattern(painter, closed_path, scene, pattern, fill_col)


def centre_svg_on_origin(item, target_mm: float, fallback_scale: float = 1.0,
                          display_scale: float = 1.0, *, reset_pos: bool = False):
    """Scale and centre an SVG item so its visual centre maps to local (0, 0).

    Parameters
    ----------
    item :          QGraphicsSvgItem (or any item with boundingRect)
    target_mm :     Desired size in scene units (mm).
    fallback_scale: Scale to use if the SVG has zero natural size.
    display_scale:  Extra multiplier from Display Manager.
    reset_pos :     If True, also call ``item.setPos(0, 0)`` (for child items).
    """
    bounds = item.boundingRect()
    center = bounds.center()
    svg_natural = max(bounds.width(), bounds.height())
    s = target_mm / svg_natural if svg_natural > 0 else fallback_scale
    s *= display_scale
    t = QTransform(s, 0, 0, s, -s * center.x(), -s * center.y())
    item.setTransform(t)
    if reset_pos:
        item.setPos(0, 0)


class DisplayableItemMixin:
    """Mixin providing standard display-manager attributes.

    Attributes set by ``init_displayable()``:

    * ``level``              — floor level name (str)
    * ``_display_color``     — pen/stroke colour override (str | None)
    * ``_display_fill_color``— fill/brush colour override (str | None)
    * ``_display_overrides`` — per-instance overrides from Display Manager (dict)
    * ``_scale_manager_ref`` — fallback ScaleManager for items not in a scene
    """

    def init_displayable(self, level: str = DEFAULT_LEVEL):
        """Initialise the shared display attributes.

        Call this early in ``__init__`` after the Qt base class constructor.
        """
        self.level: str = level
        self._display_color: str | None = None
        self._display_fill_color: str | None = None
        self._display_overrides: dict = {}
        self._scale_manager_ref = None
        self._is_section_cut: bool = False            # set by LevelManager view-range pass
        self._display_section_color: str | None = None   # set by Display Manager
        self._display_section_pattern: str | None = None  # set by Display Manager
        self._display_section_scale: float = 1.0          # set by Display Manager

    # ── View-range / section-cut protocol ──────────────────────────────────

    def z_range_mm(self) -> tuple[float, float] | None:
        """Return ``(z_bottom, z_top)`` in absolute mm, or ``None``.

        Subclasses with meaningful 3D extent should override this.
        Items returning ``None`` are filtered by level name only.
        """
        return None

    def is_cut_by(self, view_height_mm: float) -> bool:
        """True if this element's Z-range straddles *view_height_mm*."""
        zr = self.z_range_mm()
        if zr is None:
            return False
        return zr[0] < view_height_mm < zr[1]

    def _fmt(self, mm: float) -> str:
        """Format *mm* as a display string using the scene's ScaleManager."""
        from .format_utils import fmt_length
        return fmt_length(self, mm)

    def _get_scale_manager(self):
        """Return the ScaleManager from the scene, or a stored fallback."""
        from .format_utils import get_scale_manager
        return get_scale_manager(self)
