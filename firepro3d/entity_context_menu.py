"""Shared entity context menu used by plan, elevation, and 3D views."""

from PyQt6.QtWidgets import QMenu


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
            act = menu.addAction("Auto-Populate Sprinklers\u2026")
            act.triggered.connect(on_auto_populate_room)

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
