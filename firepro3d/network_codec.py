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
