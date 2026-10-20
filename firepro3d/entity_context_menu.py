"""Shared entity context menu used by plan, elevation, and 3D views."""

import contextlib

from PyQt6.QtWidgets import QMenu


def fillable_targets(selected, target=None) -> list:
    """The shapes a fill pick writes (UP2): closed, ``set_property``-capable,
    non-reference 2D shapes in *selected*, the right-clicked *target* first
    (when fillable) so the picker opens on its layer."""
    def ok(it):
        return (callable(getattr(it, "is_fillable", None)) and it.is_fillable()
                and hasattr(it, "set_property")
                and not getattr(it, "reference", False))
    out = [target] if target is not None and ok(target) else []
    out += [it for it in selected if it is not target and ok(it)]
    return out


def add_fill_actions(menu: QMenu, targets: list) -> None:
    """Append "Fill…" / "Fill Pattern…" (UP2, R7) when *targets* is non-empty:
    each opens ``colour_picker.pick_fill`` on ``targets[0]``'s layer and writes
    the pick to every target as one undo step."""
    if not targets:
        return
    menu.addAction("Fill…").triggered.connect(
        lambda _=False: _pick_and_apply(targets, pattern=False))
    menu.addAction("Fill Pattern…").triggered.connect(
        lambda _=False: _pick_and_apply(targets, pattern=True))


def _pick_and_apply(targets: list, *, pattern: bool) -> None:
    """Picker → ``set_property("Fill"|"Fill Pattern", layer)`` on every target
    inside ``deferred_undo_push`` (the ribbon idiom). The setter owns the
    library load (D-A37); cancel (None) changes nothing."""
    from . import colour_picker
    from .hatch_patterns import picker_exclude
    first = targets[0]
    sc = first.scene()
    if sc is None:
        return
    views = sc.views()
    key = "Fill Pattern" if pattern else "Fill"
    fl = first.fill_layers
    layer = colour_picker.pick_fill(
        fl.pattern if pattern else fl.background, views[0] if views else None,
        pattern=pattern, context=key,
        registry=first._tile_registry(), exclude=picker_exclude(sc))
    if layer is None:
        return
    defer = getattr(sc, "deferred_undo_push", None)
    with defer() if callable(defer) else contextlib.nullcontext():
        for t in targets:
            t.set_property(key, layer)


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
    on_cut=None,
    on_deselect=None,
    on_fit=None,
    on_refresh=None,
    on_auto_populate_room=None,
    on_array_gridline=None,
    on_offset_gridline=None,
    on_edit_block=None,
    on_explode=None,
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
    on_copy, on_cut : callable or None
        Copy / Cut — both start the modify tool's base-point pick
        (scene-tools.md D4, P1 DD10).
    on_array_gridline : callable or None
        "Array Gridlines…" action (shown only when target is a GridlineItem).
    on_offset_gridline : callable or None
        "Offset Gridline…" action (shown only when target is a GridlineItem).
    on_edit_block : callable or None
        "Edit Block" action (a block instance, plan or Block Editor — D10).
    on_explode : callable or None
        "Explode" action (Block Editor only — containment C1).
    """
    menu = QMenu()
    has_sel = bool(selected) or target is not None

    # ── Block instance (Edit Block: plan + editor; Explode: editor only) ──
    if on_edit_block is not None:
        menu.addAction("Edit Block").triggered.connect(on_edit_block)
    if on_explode is not None:
        menu.addAction("Explode").triggered.connect(on_explode)
    if on_edit_block is not None or on_explode is not None:
        menu.addSeparator()

    # ── Copy ──
    if on_copy is not None:
        act = menu.addAction("Copy")
        act.setEnabled(has_sel)
        act.triggered.connect(on_copy)

    # ── Cut (beside Copy; same base-point flow, then removes) ──
    if on_cut is not None:
        act = menu.addAction("Cut")
        act.setEnabled(has_sel)
        act.triggered.connect(on_cut)

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

    # ── Fill / Fill Pattern (closed 2D shapes; UP2 picker) ──
    fill_targets = fillable_targets(selected, target)
    if fill_targets:
        menu.addSeparator()
        add_fill_actions(menu, fill_targets)

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
