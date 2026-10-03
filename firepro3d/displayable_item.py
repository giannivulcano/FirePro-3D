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

from PyQt6.QtGui import QColor, QTransform
from .constants import DEFAULT_LEVEL

_SECTION_HATCH_COLOR = QColor(100, 100, 100)  # fallback for section hatching


def draw_section_hatch(painter, clip_path: "QPainterPath", scene,
                       color: "QColor | None" = None,
                       pattern: str = "diagonal",
                       line_width: float = 1.0,
                       section_fill: "QColor | None" = None,
                       hatch_scale: float = 1.0,
                       to_scene=None):
    """Section-cut fill + hatch (walls / floor slabs) via ``hatch_render``.

    Args:
        painter: Active painter (item coords).
        clip_path: Section boundary; empty → nothing.
        scene: The item's scene (drafting factor / registry) or None.
        color: Hatch line colour (None → the section-hatch grey).
        pattern: Tile ref or legacy name.
        line_width: Canvas hatch line width in px.
        section_fill: Solid body colour, or None for no body fill.
        hatch_scale: Pattern Scale multiplier.
        to_scene: Item→scene transform (pattern in scene axes, anchored at
            the container origin).
    """
    from .hatch_render import paint_fill
    paint_fill(painter, clip_path, scene=scene, background=section_fill,
               tile_ref=pattern or "diagonal",
               colour=color or _SECTION_HATCH_COLOR, scale=hatch_scale,
               line_width_px=line_width, to_scene=to_scene)


def draw_fill(painter, closed_path: "QPainterPath | None", scene,
              fill_type: str, pattern: str, colour: str,
              alpha: int = 115, to_scene=None):
    """Per-item 2D fill (solid or hatch) via ``hatch_render`` (HF3 retires it).

    Args:
        painter: Active painter (item coords).
        closed_path: Fill boundary; None/empty → nothing.
        scene: The item's scene (drafting factor / registry) or None.
        fill_type: ``"none"`` | ``"solid"`` | ``"hatch"``.
        pattern: Tile ref or legacy name (hatch only).
        colour: ``"#rrggbb"`` fill colour.
        alpha: 0–255 opacity for both solid and hatch.
        to_scene: Item→scene transform (pattern anchored at the scene origin).
    """
    if closed_path is None or closed_path.isEmpty() or fill_type == "none":
        return
    from .hatch_render import paint_fill
    col = QColor(colour)
    col.setAlpha(alpha)
    if fill_type == "solid":
        paint_fill(painter, closed_path, scene=scene, background=col,
                   to_scene=to_scene)
    elif fill_type == "hatch":
        paint_fill(painter, closed_path, scene=scene, tile_ref=pattern,
                   colour=col, to_scene=to_scene)


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

    def init_displayable(self, level: str | None = DEFAULT_LEVEL):
        """Initialise the shared display attributes.

        Call this early in ``__init__`` after the Qt base class constructor.

        Pass ``level=None`` for **level-less** items (the 2D-geometry primitives,
        which are definition-local per containment C3): no ``level`` attribute is
        created, so ``hasattr(item, "level")`` is False and the item is never
        level-filtered. All other display attributes are still set.
        """
        if level is not None:
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
