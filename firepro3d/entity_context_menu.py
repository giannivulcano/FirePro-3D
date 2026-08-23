"""Shared entity context menu used by plan, elevation, and 3D views."""

from PyQt6.QtWidgets import QMenu


def _attach_fill_submenu(menu: QMenu, scene, target) -> None:
    """Append a Fill submenu to *menu* when *target* is a fillable 2D shape.

    Mutations route through scene.push_undo_state() + target.set_property(),
    the same undo idiom used by the ribbon / property panel.
    """
    if target is None or not getattr(target, "is_fillable", lambda: False)():
        return

    from .hatch_patterns import PATTERN_NAMES

    fill_menu = menu.addMenu("Fill")

    def _apply(fill_type, pattern=None):
        sc = target.scene()
        if sc is None:
            return
        sc.push_undo_state()
        target.set_property("Fill", fill_type)
        if pattern is not None:
            target.set_property("Pattern", pattern)
        target.update()

    fill_menu.addAction("None").triggered.connect(lambda _=False: _apply("none"))
    fill_menu.addAction("Solid").triggered.connect(lambda _=False: _apply("solid"))

    hatch_menu = fill_menu.addMenu("Hatch")
    for name in PATTERN_NAMES:
        _n = name  # capture
        hatch_menu.addAction(_n).triggered.connect(
            lambda _=False, n=_n: _apply("hatch", n)
        )


def build_entity_context_menu(
    selected: list,
    target=None,
    *,
    scene=None,
    on_hide=None,
    on_hide_all_type=None,
    on_show_all=None,
    on_delete=None,
    on_properties=None,
    on_copy=None,
    on_deselect=None,
    on_fit=None,
    on_refresh=None,
    on_auto_populate_room=None,
    on_array_gridline=None,
    on_offset_gridline=None,
) -> QMenu:
    """Build and return a QMenu with standard entity actions.

    Parameters
    ----------
    selected : list
        Currently selected items.
    target : object or None
        The specific item right-clicked on (may be None).
    scene : QGraphicsScene or None
        The model scene (for hide/show operations).
    on_* : callable or None
        Callbacks for each action.  Pass ``None`` to omit the action.
    on_array_gridline : callable or None
        "Array Gridlines…" action (shown only when target is a GridlineItem).
    on_offset_gridline : callable or None
        "Offset Gridline…" action (shown only when target is a GridlineItem).
    """
    menu = QMenu()
    has_sel = bool(selected) or target is not None

    # ── Copy ──
    if on_copy is not None:
        act = menu.addAction("Copy")
        act.setEnabled(has_sel)
        act.triggered.connect(on_copy)

    # ── Hide / Show ──
    if on_hide is not None:
        act = menu.addAction("Hide")
        act.setEnabled(has_sel)
        act.triggered.connect(on_hide)

    if on_hide_all_type is not None and target is not None:
        type_name = type(target).__name__
        act = menu.addAction(f"Hide All ({type_name})")
        act.triggered.connect(on_hide_all_type)

    if on_show_all is not None:
        menu.addAction("Show All Hidden").triggered.connect(on_show_all)

    # ── Room-specific ──
    if on_auto_populate_room is not None:
        from .room import Room
        if isinstance(target, Room):
            menu.addSeparator()
            act = menu.addAction("Auto-Populate Sprinklers…")
            act.triggered.connect(on_auto_populate_room)

    # ── Gridline-specific ──
    if (on_array_gridline is not None or on_offset_gridline is not None) and target is not None:
        from .gridline import GridlineItem
        if isinstance(target, GridlineItem):
            menu.addSeparator()
            if on_array_gridline is not None:
                menu.addAction("Array Gridlines…").triggered.connect(on_array_gridline)
            if on_offset_gridline is not None:
                menu.addAction("Offset Gridline…").triggered.connect(on_offset_gridline)

    # ── Fill submenu (closed 2D shapes only) ──
    if target is not None and getattr(target, "is_fillable", lambda: False)():
        menu.addSeparator()
        _attach_fill_submenu(menu, scene, target)

    menu.addSeparator()

    # ── Delete ──
    if on_delete is not None:
        act = menu.addAction("Delete")
        act.setEnabled(has_sel)
        act.triggered.connect(on_delete)

    # ── Deselect All ──
    if on_deselect is not None:
        act = menu.addAction("Deselect All")
        act.setEnabled(has_sel)
        act.triggered.connect(on_deselect)

    # ── Properties ──
    if on_properties is not None and target is not None:
        act = menu.addAction("Properties")
        act.triggered.connect(on_properties)

    # ── View actions ──
    if on_fit is not None or on_refresh is not None:
        menu.addSeparator()
        if on_fit is not None:
            menu.addAction("Fit All").triggered.connect(on_fit)
        if on_refresh is not None:
            menu.addAction("Refresh").triggered.connect(on_refresh)

    return menu
