"""
network_codec.py
================
Single serialize/deserialize home for the hand-serialized scene entities that
lack their own ``to_dict``/``from_dict`` — **node, pipe, dimension, note,
water_supply, design_area**.

Decomposition slice 4 (the ``NetworkCodec`` unify). Before this, ``save_to_file``
(file) and ``_capture_network`` (undo) each hand-built these dicts with their own
field lists, which drifted (spec §4 divergence ledger). Routing both paths
through these functions makes the field lists **structurally identical** — a new
field added here appears in both paths at once.

The canonical field set/order is the one ``save_to_file`` writes, so the ``.fpd``
file output stays **byte-identical**. The undo path adopts the same order (its
snapshot dicts are compared by content, not bytes, so order is irrelevant there).

**Increment 1 = the serialize half.** The deserialize half follows in a later
increment; per-entity field application is unified there while each path keeps
its own orchestration (ordering, id maps, scene setup).
"""

from __future__ import annotations

from .constants import DEFAULT_LEVEL, DEFAULT_CEILING_OFFSET_MM


def serialize_node(node, node_id: dict) -> dict:
    """Serialize a Node (+ its sprinkler/fitting display overrides).

    ``node_id`` maps node -> integer id. Mirrors ``save_to_file``'s node block.
    """
    entry = {
        "id":                node_id[node],
        "x":                 node.scenePos().x(),
        "y":                 node.scenePos().y(),
        "elevation":         node.z_pos,
        "level":             getattr(node, "level", DEFAULT_LEVEL),
        "ceiling_level":     getattr(node, "ceiling_level", DEFAULT_LEVEL),
        "ceiling_offset_mm": getattr(node, "ceiling_offset", DEFAULT_CEILING_OFFSET_MM),
        "room_name":         getattr(node, "_room_name", ""),
        "sprinkler":         node.sprinkler.get_properties() if node.has_sprinkler() else None,
    }
    node_ovr = getattr(node, "_display_overrides", {})
    if node_ovr:
        entry["display_overrides"] = node_ovr
    if node.has_sprinkler():
        spr_ovr = getattr(node.sprinkler, "_display_overrides", {})
        if spr_ovr:
            entry["sprinkler_display_overrides"] = spr_ovr
    fit_ovr = getattr(node.fitting, "_display_overrides", {}) if node.has_fitting() else {}
    if fit_ovr:
        entry["fitting_display_overrides"] = fit_ovr
    return entry


def serialize_pipe(pipe, node_id: dict) -> dict:
    """Serialize a Pipe. Uses ``pipe._properties`` (the stored values) — not
    ``get_properties()`` which injects synthesized display rows."""
    entry = {
        "node1_id":   node_id[pipe.node1],
        "node2_id":   node_id[pipe.node2],
        "level":      getattr(pipe, "level", DEFAULT_LEVEL),
        "properties": {k: v["value"] for k, v in pipe._properties.items()},
    }
    pipe_ovr = getattr(pipe, "_display_overrides", {})
    if pipe_ovr:
        entry["display_overrides"] = pipe_ovr
    return entry


def serialize_dimension(dim) -> dict:
    """Serialize a DimensionAnnotation."""
    return {
        "type":        "dimension",
        "p1":          [dim._p1.x(), dim._p1.y()],
        "p2":          [dim._p2.x(), dim._p2.y()],
        "offset_dist": getattr(dim, "_offset_dist", 10),
        "witness_ext_override": getattr(dim, "_witness_ext_override", None),
        "properties":  {k: v["value"] for k, v in dim.get_properties().items()},
        "level":       getattr(dim, "level", DEFAULT_LEVEL),
    }


def serialize_note(note) -> dict:
    """Serialize a NoteAnnotation."""
    return {
        "type":       "note",
        "x":          note.scenePos().x(),
        "y":          note.scenePos().y(),
        "text_width": note.textWidth(),
        "properties": {k: v["value"] for k, v in note.get_properties().items()},
        "level":      getattr(note, "level", DEFAULT_LEVEL),
    }


def serialize_water_supply(ws) -> dict:
    """Serialize the WaterSupply node."""
    entry = {
        "x":          ws.pos().x(),
        "y":          ws.pos().y(),
        "properties": {k: v["value"] for k, v in ws.get_properties().items()},
    }
    ws_ovr = getattr(ws, "_display_overrides", {})
    if ws_ovr:
        entry["display_overrides"] = ws_ovr
    return entry


def serialize_design_area(da, node_id: dict, active_design_area) -> dict:
    """Serialize a DesignArea. ``node_id`` maps node -> id; only members whose
    node is present are recorded. Uses ``da._properties`` (raw stored values)."""
    spr_node_ids = [node_id[s.node] for s in da.sprinklers
                    if s.node and s.node in node_id]
    return {
        "sprinkler_node_ids": spr_node_ids,
        # raw stored props — get_properties() adds synthesized display rows
        "properties": {k: v["value"] for k, v in da._properties.items()},
        "is_active":  da is active_design_area,
        "level":      da.level,
        "badge_offset": (list(da.badge_offset()) if da._badge_user_moved else None),
        "badge_angle": (da.badge._angle if getattr(da, "badge", None)
                        is not None else 0.0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Deserialize half (slice 4b). Scene-referencing: each function creates + registers
# its entity on *scene* and applies the shared FIELD state. Each caller keeps its own
# orchestration (id maps, loop order, load-only migrations) and its own DISPLAY tail
# (undo-restore applies display inline; file-load defers it to main). Local imports
# mirror load_from_file's cycle-avoidance pattern.
# ─────────────────────────────────────────────────────────────────────────────


def deserialize_dimension(scene, entry):
    """Create + register a DimensionAnnotation from a serialized entry.

    Scene-referencing: adds the item to *scene* and its annotation store.
    Mirror of ``serialize_dimension``. Returns the dimension.
    """
    from PyQt6.QtCore import QPointF
    from .annotations import DimensionAnnotation
    p1 = QPointF(entry["p1"][0], entry["p1"][1])
    p2 = QPointF(entry["p2"][0], entry["p2"][1])
    dim = DimensionAnnotation(p1, p2)
    dim._offset_dist = entry.get(
        "offset_dist", float(entry.get("properties", {}).get("Offset", "10")))
    dim._witness_ext_override = entry.get("witness_ext_override", None)
    scene.addItem(dim)
    scene.annotations.add_dimension(dim)
    for key, value in entry.get("properties", {}).items():
        dim.set_property(key, value)
    dim.update_geometry()
    dim.level = entry.get("level", DEFAULT_LEVEL)
    return dim


def deserialize_note(scene, entry):
    """Create + register a NoteAnnotation from a serialized entry.

    Mirror of ``serialize_note``. Preserves the wrap-width contract
    (text_width > 0 -> wrapped; else 0). Returns the note.
    """
    from .annotations import NoteAnnotation
    tw = entry.get("text_width", -1)
    note = NoteAnnotation(x=entry["x"], y=entry["y"],
                          text_width=tw if tw and tw > 0 else 0)
    scene.addItem(note)
    scene.annotations.add_note(note)
    for key, value in entry.get("properties", {}).items():
        note.set_property(key, value)
    note.level = entry.get("level", DEFAULT_LEVEL)
    return note


def deserialize_water_supply(scene, entry):
    """Create + register the WaterSupply node. Mirror of ``serialize_water_supply``.

    Sets both scene.water_supply_node and sprinkler_system.supply_node. The
    display_overrides field is applied here; category/DM display is a caller tail.
    Returns the WaterSupply.
    """
    from .water_supply import WaterSupply
    ws = WaterSupply(entry["x"], entry["y"])
    scene.addItem(ws)
    scene.water_supply_node = ws
    scene.sprinkler_system.supply_node = ws
    for key, value in entry.get("properties", {}).items():
        ws.set_property(key, value)
    ws._display_overrides = entry.get("display_overrides", {})
    return ws


def deserialize_node(scene, entry):
    """Create + register a Node (+ optional sprinkler) from a serialized entry.

    Mirror of ``serialize_node``. Scene-referencing: adds to *scene* and its
    sprinkler_system, and uses scene._level_manager to resolve z_pos.

    Ordering (slice 4b): the sprinkler sub-block runs BEFORE ceiling application.
    ``add_sprinkler`` does not read node ceiling, so applying ceiling afterward is a
    single source of truth and drops load_from_file's historical save/restore dance.
    The fitting-display pending flag is set here; the fitting display tail (update +
    DM colours) stays with each caller. Returns the node; caller stores it under
    entry["id"].
    """
    from .node import Node
    from .sprinkler import Sprinkler
    node = Node(entry["x"], entry["y"])
    scene.addItem(node)
    scene.sprinkler_system.add_node(node)
    node._display_overrides = entry.get("display_overrides", {})

    if entry.get("sprinkler"):
        template = Sprinkler(None)
        for key, value in entry["sprinkler"].items():
            if isinstance(value, dict):
                template.set_property(key, value["value"])
            else:
                template.set_property(key, value)
        scene.add_sprinkler(node, template)
        node.sprinkler._display_overrides = entry.get(
            "sprinkler_display_overrides", {})

    node._fitting_display_overrides_pending = entry.get(
        "fitting_display_overrides", {})

    node.level = entry.get("level", DEFAULT_LEVEL)
    node._room_name = entry.get("room_name", "")
    node.ceiling_level = entry.get("ceiling_level", node.level)
    if "ceiling_offset_mm" in entry:
        node.ceiling_offset = entry["ceiling_offset_mm"]
    else:
        node.ceiling_offset = entry.get("ceiling_offset", -2.0) * 25.4  # inches -> mm
    node._properties["Ceiling Level"]["value"] = node.ceiling_level
    node._properties["Ceiling Offset"]["value"] = str(node.ceiling_offset)

    lm = getattr(scene, "_level_manager", None)
    lvl = lm.get(node.ceiling_level) if lm else None
    if lvl:
        node.z_pos = lvl.elevation + node.ceiling_offset
    else:
        node.z_pos = entry.get("elevation", 0)
    return node


def deserialize_pipe(scene, entry, id_to_node):
    """Create + register a Pipe via scene.add_pipe (the canonical creation path).

    Mirror of ``serialize_pipe``. Returns the pipe, or None if either endpoint node
    id is missing. Uses ``_propagate_ceiling=False``: nodes already carry
    authoritative ceiling data on load/restore. Routing both paths through add_pipe
    single-homes creation (geometry, visibility, label, category defaults, fitting
    DM colours) and removes _restore_network's hand-rolled variant.
    """
    from .pipe import Pipe
    n1 = id_to_node.get(entry["node1_id"])
    n2 = id_to_node.get(entry["node2_id"])
    if not (n1 and n2):
        return None
    pipe = scene.add_pipe(n1, n2, _propagate_ceiling=False)
    pipe.level = entry.get("level", DEFAULT_LEVEL)
    for key, value in entry.get("properties", {}).items():
        pipe.set_property(key, value)
    props = entry.get("properties", {})
    if "Line Type" not in props:  # legacy backfill (pre-Line-Type saves)
        dia = props.get("Diameter", "1\"Ø")
        pipe._properties["Line Type"]["value"] = (
            "Main" if dia in Pipe._MAIN_DIAMETERS else "Branch")
        pipe.set_pipe_display()
    pipe._display_overrides = entry.get("display_overrides", {})
    return pipe
