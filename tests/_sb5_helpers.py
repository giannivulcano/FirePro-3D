"""Shared builders for the SB5 hosting-foundation guards (tests/test_sb5_*.py).

Reuses tests/_ph1_helpers.py (scene() with a LevelManager, ph1_cleanup,
save_raw, the per-kind add_* builders). A test module that calls scene() /
managed_scene() must import ``ph1_cleanup`` so the autouse cleanup runs.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QTabWidget

from tests._ph1_helpers import (add_floor_opening, add_opening, add_roof, add_room,
                                add_water_supply, save_raw, scene)


def managed_scene():
    """``_ph1_helpers.scene()`` plus the real Section and Detail managers (the
    tests/test_section_undo.py fixture shape), so markers save, load and undo."""
    from firepro3d.detail_view import DetailViewManager
    from firepro3d.section_manager import SectionManager
    ms = scene()
    ms._sb5_tabs = (QTabWidget(), QTabWidget())          # keep the tab widgets alive
    ms._section_manager = SectionManager(ms, ms._level_manager, ms.scale_manager,
                                         ms._sb5_tabs[0])
    ms._detail_manager = DetailViewManager(ms, ms._level_manager, ms.scale_manager,
                                           ms._sb5_tabs[1])
    return ms


def add_design_area(ms, sprinklers):
    """A DesignArea over *sprinklers*, registered like
    ``network_codec.deserialize_design_area`` does."""
    from firepro3d.design_area import DesignArea
    da = DesignArea(list(sprinklers))
    ms.addItem(da)
    ms.design_areas.append(da)
    return da


def one_of_each(ms) -> dict:
    """One of every SB5 Q1 element kind in *ms* -> {kind: item}. Section and
    detail markers are added only when *ms* has their managers."""
    door = add_opening(ms)                       # wall (0,0)-(4000,0) + door_914
    void = add_floor_opening(ms)                 # slab + void
    roof = add_roof(ms)
    room = add_room(ms)
    a = ms.add_node(0.0, 5000.0)
    b = ms.add_node(1000.0, 5000.0)
    pipe = ms.add_pipe(a, b)
    spr = ms.add_sprinkler(b)
    ws = add_water_supply(ms)
    da = add_design_area(ms, [spr])
    made = {"room": room, "floor_slab": void.host, "floor_opening": void,
            "roof": roof, "wall": door.wall, "opening": door, "node_a": a,
            "node": b, "pipe": pipe, "sprinkler": spr, "water_supply": ws,
            "design_area": da}
    if getattr(ms, "_section_manager", None) is not None:
        made["section"] = ms._section_manager.place_section(
            QPointF(0.0, -2000.0), QPointF(5000.0, -2000.0))
    if getattr(ms, "_detail_manager", None) is not None:
        made["detail"] = ms._detail_manager.create_detail(
            "Detail 1", QRectF(0.0, 0.0, 1000.0, 1000.0))
    return made


FIND = {
    "room": lambda ms: ms._rooms[0],
    "floor_slab": lambda ms: ms._floor_slabs[0],
    "floor_opening": lambda ms: ms._floor_slabs[0].openings[0],
    "roof": lambda ms: ms._roofs[0],
    "opening": lambda ms: ms._walls[0].openings[0],
    "node": lambda ms: next(n for n in ms.sprinkler_system.nodes if n.has_sprinkler()),
    "pipe": lambda ms: ms.sprinkler_system.pipes[0],
    "sprinkler": lambda ms: ms.sprinkler_system.sprinklers[0],
    "water_supply": lambda ms: ms.water_supply_node,
    "design_area": lambda ms: ms.design_areas[0],
    "section": lambda ms: ms._section_manager.markers["Section 1"],
    "detail": lambda ms: ms._detail_manager._markers["Detail 1"],
}


def uids(ms) -> dict:
    """{kind: uid} of the FIND kinds present in a managed scene."""
    return {k: f(ms)._uid for k, f in FIND.items()}


def all_q1(ms) -> list:
    """Every live SB5 Q1 element of *ms* (markers excluded: never pasted)."""
    ss = ms.sprinkler_system
    out = (list(ms._rooms) + list(ms._floor_slabs) + list(ms._roofs)
           + [op for w in ms._walls for op in w.openings]
           + [op for s in ms._floor_slabs for op in s.openings]
           + list(ss.nodes) + list(ss.pipes) + list(ss.sprinklers)
           + list(ms.design_areas))
    if ms.water_supply_node is not None:
        out.append(ms.water_supply_node)
    return out


def save_load(ms, tmp_path, name="sb5.fpd"):
    """save_to_file -> a fresh managed scene loaded from it; (scene, raw payload)."""
    from firepro3d import phase_registry
    path, raw = save_raw(ms, tmp_path, name)
    phase_registry.reset_project_table()
    out = managed_scene()
    assert out.load_from_file(path)
    return out, raw


def named_room(ms, name, x0=0.0, y0=0.0, w=4000.0, h=3000.0):
    from firepro3d.room import Room
    r = Room([QPointF(x0, y0), QPointF(x0 + w, y0), QPointF(x0 + w, y0 + h),
              QPointF(x0, y0 + h)])
    r.name = name
    r._scale_manager_ref = ms.scale_manager
    ms.addItem(r)
    ms._rooms.append(r)
    return r


def door_scene(ms):
    """Room "Office" (0,0)-(4000,3000), a 200 mm wall on its bottom edge and a
    door_914 at 2000 mm: the tests/test_sb2a_binding.py scene, with the door
    listed in ``wall.openings`` so it saves, pastes and cascades."""
    from firepro3d.wall import WallSegment
    from firepro3d.wall_opening import WallOpening
    named_room(ms, "Office")
    w = WallSegment(QPointF(0, 0), QPointF(4000, 0), thickness_mm=200.0)
    ms.addItem(w)
    ms._walls.append(w)
    op = WallOpening(w, feature_id="door_914", offset_along=2000)
    op.level = w.level
    w.openings.append(op)
    ms.addItem(op)
    return op


def bound_def(ms, category, keys, name=None):
    """A registered block definition whose texts ``@[K]`` bind host keys
    (*keys*: {attr key: host key}) of element *category* -- the
    tests/test_sb2a_binding.py / tests/test_sb3_parity.py definition shape."""
    from firepro3d.block_attributes import normalise_attr
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.geometry_2d import LineItem
    prims = [LineItem(QPointF(0, 0), QPointF(20, 0)).to_dict()]
    prims += [{"type": "text", "text": "@[" + k + "]", "x": 0.0, "y": -10.0 * i,
               "height_mm": 5.0, "angle": 0.0} for i, k in enumerate(keys)]
    d = BlockDefinition.new(name=name or category + "Tag", library="", series="",
                            origin=(0.0, 0.0), primitives=prims)
    d.attributes = [normalise_attr({"key": k, "source": "host", "host_key": hk})
                    for k, hk in keys.items()]
    d.host_category = category
    ms.register_block_definition(d)
    return d


def bound_tag(ms, host, category, keys, pos=(0.0, 0.0)):
    """A placed instance of ``bound_def(...)`` bound to *host* (element_host)."""
    d = bound_def(ms, category, keys)
    inst = ms.place_block_instance(d.id, pos)
    inst.element_host = host
    inst.refresh_bound()
    return inst


def painted_values(inst) -> dict:
    """The strings *inst* paints for its keys: ``block_attributes.resolve_values``
    over the live host values -- the exact input ``bound_text_ops`` draws."""
    from firepro3d.block_attributes import resolve_values
    d = inst.definition()
    return resolve_values(d.effective_attributes(), inst.attributes, inst.host_values())
