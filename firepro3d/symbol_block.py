"""SymbolBlockItem -- an element's fixed symbol drawn from a System block (SB4g D3).

A light ``QGraphicsItem`` that paints a block definition's shared compiled ops at
real size (the ``BoundLabelItem`` precedent; not a ``BlockInstance``: no level,
never selectable, never serialized). The definition comes from the scene's
``symbol_block(category, chosen_id)`` resolver (System default when the chosen
id is missing or ineligible, R8). ``Sprinkler`` and ``WaterSupply`` subclass it;
the riser is ``pipe.RiserSymbolItem`` (it overrides ``stroke_tint``, R4).
"""
from __future__ import annotations

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QPainterPath, QTransform
from PyQt6.QtWidgets import QGraphicsItem

from .bound_label import PEN_MARGIN
from .colour_tokens import resolve_colour
from .render_op import ops_bounding_rect, ops_shape, paint_ops

_IDENTITY = QTransform()
_AUTHORED_STROKE = "#ffffff"      # today's _set_svg_tint rule: white = no recolour


class SymbolBlockItem(QGraphicsItem):
    """Paints the resolved symbol block of *category* ("Sprinkler",
    "Water Supply" or "Riser").

    Attributes:
        symbol_block: The chosen block id, or None (= the category's System
            default). Change it through ``set_symbol_block``.
        _display_color / _display_fill_color: The DM / paper tint pair
            (``set_tint``; ``display_manager._set_svg_tint`` dispatches here).
            Stroke None, "" or ``#ffffff`` = authored colours.
        _paper_scale / _paper_pen_width / _paper_pen_color: paper hooks read by
            ``render_op.paint_ops`` (None on the model canvas; set by the paper
            pass, T13).
    """

    def __init__(self, category: str, parent: QGraphicsItem | None = None, *,
                 owner: QGraphicsItem | None = None):
        super().__init__(parent)
        self._category = category
        self._owner = owner               # re-shaped with the symbol (Node / Pipe)
        self.symbol_block: str | None = None
        self._defn = None
        self._resolved = False
        self._resolving = False
        self._ops_rect: QRectF | None = None   # cached, None = stale
        self._display_color: str | None = None
        self._display_fill_color: str | None = None
        # render_op.paint_ops item protocol.
        self._paper_scale = None
        self._paper_pen_width = None
        self._paper_pen_color = None
        self._is_ghost = False
        self._crisp_ops = None
        self._pose_rot = 0.0
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

    # -- resolution ---------------------------------------------------------
    @property
    def category(self) -> str:
        return self._category

    def _resolve(self):
        """The definition through the scene resolver, cached until ``refresh``.
        Off-scene (or a scene without the resolver) -> None, not cached."""
        if self._resolved:
            return self._defn
        fn = getattr(self.scene(), "symbol_block", None)
        if fn is None:
            return None
        self._resolving = True
        try:
            d = fn(self._category, self.symbol_block)
        finally:
            self._resolving = False
        self._defn, self._resolved = d, True
        return d

    def definition(self):
        return self._resolve()

    def _ops(self) -> list:
        d = self._resolve()
        return d.render_ops_variant(False, 1.0) if d is not None else []

    def set_symbol_block(self, block_id: str | None) -> None:
        """Choose a block (None = System default) and re-resolve."""
        self.symbol_block = block_id or None
        self.refresh()

    def refresh(self) -> None:
        """Drop the resolved definition and bounds and repaint. The owner's
        (and this item's) geometry change is announced FIRST, while the old
        extent is still cached (S4: Qt reads the old bounds at that call).
        A refresh raised by this item's own resolve (an embed emitting
        ``blockDefinitionsChanged``) is ignored -- that resolve is current."""
        if self._resolving:
            return
        o = self._owner
        if o is not None:
            o.prepareGeometryChange()
        self.prepareGeometryChange()
        self._defn, self._resolved = None, False
        self._ops_rect = None
        self._crisp_ops = None
        if o is not None:
            o.update()
        self.update()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged:
            self.refresh()            # a new scene = a new resolver
        return super().itemChange(change, value)

    # -- geometry -------------------------------------------------------------
    def _rect(self) -> QRectF:
        if self._ops_rect is not None:
            return self._ops_rect
        if self.scene() is None:
            return QRectF()               # not cached: nothing to resolve through
        ops = self._ops()
        self._ops_rect = ops_bounding_rect(ops) if ops else QRectF()
        return self._ops_rect

    def extent_radius(self) -> float:
        """Largest |coordinate| of the symbol's ops rect from its origin (its
        real half-size for a centred symbol); 0.0 when nothing resolves."""
        r = self._rect()
        if r.isEmpty():
            return 0.0
        return max(abs(r.left()), abs(r.right()), abs(r.top()), abs(r.bottom()))

    def boundingRect(self) -> QRectF:
        r = self._rect()
        if r.isEmpty():
            return QRectF()
        return r.adjusted(-PEN_MARGIN, -PEN_MARGIN, PEN_MARGIN, PEN_MARGIN)

    def shape(self) -> QPainterPath:
        ops = self._ops() if self.scene() is not None else []
        return ops_shape(ops) if ops else QPainterPath()

    # -- Symbol row (SB4g D7; the TagBlockHost._tag_row pattern) ---------------
    def _symbol_scene(self):
        """The scene that lists / embeds choices: the item's own, else a
        template's ``_scene_ref`` (MainWindow sets it on placement templates)."""
        sc = self.scene()
        return sc if sc is not None else getattr(self, "_scene_ref", None)

    def symbol_row(self) -> dict:
        """The Symbol enum row: the System symbols of this category, then
        flagged user-library blocks (``annotation_choices.symbol_choices``); a
        kept missing / ineligible id is listed so the row can show it. None
        (= the System default) shows as the default block's entry. Enum rows
        carry strings, so the label -> Choice map is kept for the setter;
        with no scene the row shows the stored / default id alone."""
        from . import annotation_choices as ac
        from .system_blocks import SYMBOL_DEFAULTS
        want = self.symbol_block or SYMBOL_DEFAULTS[self.category]
        self._symbol_choices = {}
        sc = self._symbol_scene()
        if sc is not None and hasattr(sc, "_block_definitions"):
            for c in ac.symbol_choices(sc, self.category, current=self.symbol_block):
                self._symbol_choices.setdefault(c.label, c)
        value = next((lbl for lbl, c in self._symbol_choices.items()
                      if c.block_id == want), None)
        if value is None:                      # off-scene template: nothing to list
            value = want
            self._symbol_choices[want] = ac.Choice(want, want)
        return {"type": "enum", "value": value, "options": list(self._symbol_choices)}

    def set_symbol_from_row(self, label: str) -> None:
        """Apply a Symbol row pick (D7): the label maps through the row's
        choice map (rebuilt when unknown); "< mixed >" and stale labels are
        no-ops (property-panel.md 3.5). Picking the category's System default
        stores None (sparse, D6). A "(Library)" pick embeds first; embed +
        assignment are ONE undo step (``deferred_undo_push``), as the Tag row."""
        import contextlib
        from .annotation_choices import pick_block_id
        from .system_blocks import SYMBOL_DEFAULTS
        if label not in getattr(self, "_symbol_choices", {}):
            self.symbol_row()
        choice = self._symbol_choices.get(label)
        if choice is None:
            return
        sc = self._symbol_scene()
        cm = getattr(sc, "deferred_undo_push", None) if sc is not None else None
        with (cm() if callable(cm) else contextlib.nullcontext()):
            ok, bid = pick_block_id(sc, choice)
            if not ok:
                return
            if bid == SYMBOL_DEFAULTS[self.category]:
                bid = None
            if bid == self.symbol_block:
                return
            self.set_symbol_block(bid)
            if self.scene() is not None and hasattr(sc, "request_undo_push"):
                sc.request_undo_push()          # an on-scene pick IS an undo step (AC3)

    # -- tint + paint ---------------------------------------------------------
    def set_tint(self, stroke: str | None, fill: str | None) -> None:
        """Store the DM / paper tint pair and repaint (tokens resolve per paint,
        on the surface being painted)."""
        self._display_color = stroke
        self._display_fill_color = fill
        self.update()

    def stroke_tint(self):
        """The stroke override ``paint`` passes to ``paint_ops`` (a QColor), or
        None = authored. The one stroke-tint hook: ``RiserSymbolItem``
        overrides it to pull its pipe's colour at paint (R4)."""
        c = self._display_color
        if not c or (isinstance(c, str) and c.lower() == _AUTHORED_STROKE):
            return None
        return resolve_colour(c, item=self)

    def fill_tint(self):
        """The fill override (a QColor), or None = authored fills."""
        f = self._display_fill_color
        return resolve_colour(f, item=self) if f else None

    def paint(self, painter, option, widget=None):
        ops = self._ops()
        if not ops:
            return
        paint_ops(painter, ops, _IDENTITY, self,
                  override=self.stroke_tint(), fill_override=self.fill_tint())
