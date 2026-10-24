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

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPen, QTransform
from .constants import DEFAULT_LEVEL

_SECTION_HATCH_COLOR = QColor(100, 100, 100)  # fallback for section hatching


def draw_section_type(painter, clip_path: "QPainterPath", scene, item,
                      type_id: "str | None",
                      element_colour: "QColor | None" = None,
                      line_width: float = 1.0,
                      to_scene=None,
                      paper_body: "str | None" = None) -> None:
    """Section-cut fill via a Fill Type (HF5 D-A17): background = body, the
    pattern coloured by the type (By element -> *element_colour*, R8).

    Args:
        painter: Active painter (item coords).
        clip_path: Section boundary; empty -> nothing.
        scene: The item's scene (drafting factor / registry) or None.
        item: The cut item (colour tokens resolve on its surface).
        type_id: Fill Type id; None = the default look (diagonal, By element,
            no body); an id the table lacks draws the missing-type fallback.
        element_colour: The element's resolved line colour (By element).
        line_width: Canvas hatch line width in px.
        to_scene: Item->scene transform (pattern in scene axes, anchored at
            the container origin).
        paper_body: A paper-pass body colour (``""`` = no body) that wins over
            the type background; None reads ``item._display_section_color``
            (the plan items' paper pass; None in model).
    """
    from . import fill_types
    from .colour_tokens import resolve_colour, section_fill_colour
    from .constants import TOKEN_ELEMENT
    from .fill_layers import FillLayers, PatternLayer
    from .hatch_patterns import DEFAULT_TILE_REF
    from .hatch_render import paint_fill
    if clip_path.isEmpty():
        return
    if type_id:
        layers, _missing = fill_types.resolve(type_id, None)
    else:
        layers = FillLayers(None, PatternLayer(DEFAULT_TILE_REF, TOKEN_ELEMENT))
    bg = pat = None
    paper_bg = paper_body if paper_body is not None else getattr(
        item, "_display_section_color", None)
    if paper_bg is not None:
        bg = section_fill_colour(paper_bg, item)
    elif layers.background is not None:
        bg = resolve_colour(layers.background.color, item=item)
        bg.setAlpha(round(bg.alpha() * layers.background.opacity))
    p = layers.pattern
    if p is not None:
        if p.color == TOKEN_ELEMENT:
            pat = QColor(element_colour) if element_colour is not None else QColor(_SECTION_HATCH_COLOR)
        else:
            pat = resolve_colour(p.color, item=item)
        pat.setAlpha(round(pat.alpha() * p.opacity))
    paint_fill(painter, clip_path, scene=scene, background=bg,
               tile_ref=p.ref if p is not None else None,
               colour=pat if pat is not None else _SECTION_HATCH_COLOR,
               scale=p.scale if p is not None else 1.0,
               line_width_px=line_width, to_scene=to_scene)


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
        # Paper pass only (HF5): the paper body-colour override; None in model.
        self._display_section_color: str | None = None
        # Fill Type id of the cut (Display Manager, HF5); None = the default look.
        self._display_section_type: str | None = None

    def _outline_pen(self, color, cosmetic_px: float = 1.0,
                     style: Qt.PenStyle = Qt.PenStyle.SolidLine) -> QPen:
        """Outline pen for a system item's linework.

        Canvas: cosmetic *cosmetic_px*. During a paper pass,
        ``paper_display._apply_generic`` sets ``_paper_pen_width`` (the paper
        category weight in model units, ``lw_mm / paper_scale`` — paper-space
        §9.9.1), so the outline plots at the true on-paper weight.
        """
        w = getattr(self, "_paper_pen_width", None)
        pen = QPen(QColor(color), cosmetic_px if w is None else w, style)
        pen.setCosmetic(w is None)
        return pen

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
