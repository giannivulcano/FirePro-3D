"""Element store: one row per element kind (docs/specs/element-store.md).

Stateless. The element lists stay scene attributes (R1); every whole-model
pass iterates :data:`KINDS` instead of naming the lists. Classes resolve
lazily so this module never joins the ``model_space`` import cycle.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class BuildContext:
    """Which pass is building (D1): ``"load"`` or ``"restore"``."""
    path: str
    orphan_hosts: int = 0          # load: blocks whose gridline host is gone


def _item_level(item):
    return getattr(item, "level", None)


def _slab_level(slab):
    return slab._top_level         # a slab's own level is its Top Level


def _openings(owner):
    return getattr(owner, "openings", [])


@dataclass(frozen=True)
class ElementKind:
    """One element kind (spec D1)."""
    attr: str
    cls_path: tuple                # (module, class name), resolved by ``cls``
    undo_key: str
    file_key: Optional[str]
    builder: Optional[Callable] = None     # (row, scene, record, ctx) -> item | None
    legacy_keys: tuple = ()
    record_type: Optional[str] = None
    level_of: Optional[Callable] = None
    children: Optional[Callable] = None
    category: Optional[str] = None
    constraint_roles: frozenset = field(default_factory=frozenset)
    codec_owned: bool = False

    @property
    def cls(self):
        mod, name = self.cls_path
        return getattr(importlib.import_module("." + mod, __package__), name)

    def build(self, scene, record, ctx):
        return self.builder(self, scene, record, ctx)


# -- builders (spec D1 ``build``) ----------------------------------------------
def _build_plain(row, scene, rec, ctx):
    item = row.cls.from_dict(rec)
    scene.addItem(item)
    getattr(scene, row.attr).append(item)
    return item


def _build_wall(row, scene, rec, ctx):
    from .wall_opening import WallOpening
    wall = row.cls.from_dict(rec)
    scene.addItem(wall)
    scene._walls.append(wall)
    for op_data in rec.get("openings", []):
        op = WallOpening.from_dict(op_data, wall=wall)
        wall.openings.append(op)
        scene.addItem(op)
    return wall


def _build_slab(row, scene, rec, ctx):
    slab = row.cls.from_dict(rec)
    scene.addItem(slab)
    scene._floor_slabs.append(slab)
    for op in slab.openings:        # owned voids (from_dict re-attached them)
        scene.addItem(op)
    return slab


def _build_roof(row, scene, rec, ctx):
    roof = row.cls.from_dict(rec)
    if ctx.path == "load":          # restore omits it until the R2 commit
        roof._scale_manager_ref = scene.scale_manager
    scene.addItem(roof)
    scene._roofs.append(roof)
    return roof


def _build_room(row, scene, rec, ctx):
    room = row.cls.from_dict(rec)
    room._scale_manager_ref = scene.scale_manager
    scene.addItem(room)
    scene._rooms.append(room)
    return room


def _build_block(row, scene, rec, ctx):
    from .block_instance import BlockInstance
    _pos = rec.get("pos", [0.0, 0.0])
    inst = scene.place_block_instance(
        rec["block_id"], (_pos[0], _pos[1]), uid=rec.get("uid"),
        **BlockInstance.place_kwargs(rec, default_level="Level 1"))
    if inst is None:                # hosted on a gridline that is gone (D3)
        if ctx.path == "load":
            ctx.orphan_hosts += 1
        return None
    inst.attributes = dict(rec.get("attributes", {}))
    return inst


_P, _E, _PL = "primitive", "editor", "plan"


def _loose(attr, mod, name, undo_key, record_type, roles, category="2D Geometry",
           legacy=()):
    return ElementKind(attr, (mod, name), undo_key, None, _build_plain,
                       legacy_keys=legacy, record_type=record_type, category=category,
                       constraint_roles=frozenset(roles))


# Row order = undo-capture order (spec D2 / O1).
KINDS: tuple = (
    ElementKind("design_areas", ("design_area", "DesignArea"), "design_areas", "design_areas",
                level_of=_item_level, category="Design Area", codec_owned=True),
    _loose("_polylines", "geometry_2d", "PolylineItem", "polylines", "polyline", (_P, _E)),
    _loose("_draw_lines", "geometry_2d", "LineItem", "draw_lines", "draw_line", (_P, _E),
           legacy=("reference_lines",)),
    _loose("_draw_rects", "geometry_2d", "RectangleItem", "draw_rectangles", "draw_rectangle", (_P, _E)),
    _loose("_draw_circles", "geometry_2d", "CircleItem", "draw_circles", "draw_circle", (_P, _E)),
    _loose("_draw_arcs", "geometry_2d", "ArcItem", "draw_arcs", "arc", (_P, _E)),
    _loose("_draw_ellipses", "geometry_2d", "EllipseItem", "draw_ellipses", "draw_ellipse", (_P, _E)),
    _loose("_draw_splines", "geometry_2d", "SplineItem", "draw_splines", "draw_spline", (_P,)),
    _loose("_filled_regions", "filled_region", "FilledRegionItem", "filled_regions",
           "draw_filled_region", (_P,)),
    _loose("_draw_polygons", "geometry_2d", "RegularPolygonItem", "polygons", "polygon", (_P, _E)),
    _loose("_texts", "text_item", "TextItem", "texts", "text", (_P, _E), category=None),
    ElementKind("_gridlines", ("gridline", "GridlineItem"), "gridlines", "gridlines", _build_plain,
                level_of=_item_level, category="Grid Line", constraint_roles=frozenset({_PL})),
    ElementKind("_walls", ("wall", "WallSegment"), "walls", "walls", _build_wall,
                level_of=_item_level, children=_openings, category="Wall",
                constraint_roles=frozenset({_PL})),
    ElementKind("_floor_slabs", ("floor_slab", "FloorSlab"), "floor_slabs", "floor_slabs", _build_slab,
                level_of=_slab_level, children=_openings, category="Floor"),
    ElementKind("_roofs", ("roof", "RoofItem"), "roofs", "roofs", _build_roof,
                level_of=_item_level, category="Roof"),
    ElementKind("_rooms", ("room", "Room"), "rooms", "rooms", _build_room,
                level_of=_item_level, category="Room"),
    ElementKind("_block_instances", ("block_instance", "BlockInstance"), "blocks", "blocks",
                _build_block, level_of=_item_level, constraint_roles=frozenset({_E, _PL})),
)

ROWS = {row.attr: row for row in KINDS}

# -- per-pass order tuples (spec D2; G4 checks each covers exactly its rows) ----
#: Schematic gather order (block-definition primitive order) == scene_tools geometry order.
PRIMITIVE_ORDER = ("_draw_lines", "_draw_rects", "_draw_circles", "_draw_arcs",
                   "_draw_ellipses", "_draw_splines", "_polylines", "_draw_polygons",
                   "_filled_regions", "_texts")
#: Block Editor constraint item order (the solver's).
CONSTRAINT_EDITOR_ORDER = ("_draw_lines", "_draw_rects", "_draw_circles", "_draw_arcs",
                           "_draw_ellipses", "_polylines", "_draw_polygons", "_texts",
                           "_block_instances")
#: Every editor primitive with a uid (+ the adapter-less ones).
CONSTRAINT_PRIMITIVE_ORDER = CONSTRAINT_EDITOR_ORDER + ("_draw_splines", "_filled_regions")
#: Plan constraint item order.
CONSTRAINT_PLAN_ORDER = ("_walls", "_gridlines", "_block_instances")


def role_attrs(role) -> set:
    """The row attrs carrying *role* (G4's check of the order tuples)."""
    return {r.attr for r in KINDS if role in r.constraint_roles}


# -- undo capture / restore (spec D4) -------------------------------------------
def _definitions_record(scene) -> dict:
    return {bid: d.to_dict() for bid, d in scene._block_definitions.items()}


def capture_records(scene) -> dict:
    """Undo-snapshot records of every non-codec row, in row order; the
    ``block_definitions`` registry (D3) splices in before the blocks row."""
    out = {}
    for row in KINDS:
        if row.codec_owned:
            continue
        if row.attr == "_block_instances":
            out["block_definitions"] = _definitions_record(scene)
        out[row.undo_key] = [i.to_dict() for i in getattr(scene, row.attr)]
    return out


_DETACH_FIRST = ("_walls",)   # a wall's join pool is ``_walls``: removing with every
                              # wall still listed rebuilds neighbours per removal


def remove_for_restore(scene) -> None:
    """Restore's removal: owned children before their owner; lists cleared in place."""
    for row in KINDS:
        if row.codec_owned:
            continue
        lst = getattr(scene, row.attr)
        doomed = list(lst)
        if row.attr in _DETACH_FIRST:
            lst.clear()
        for item in doomed:
            if row.children is not None:
                for ch in row.children(item):
                    if ch.scene() is scene:
                        scene.removeItem(ch)
            if item.scene() is scene:
                scene.removeItem(item)
        lst.clear()


def build_rows(scene, source: dict, ctx: BuildContext, *, key: str,
               after_gridlines=None, before_blocks=None) -> None:
    """Build every non-codec row from *source* by ``key`` (``"undo_key"`` or
    ``"file_key"``) in row order. ``legacy_keys`` are read on restore only."""
    for row in KINDS:
        if row.codec_owned:
            continue
        rkey = getattr(row, key)
        if rkey is None:
            continue
        if row.attr == "_block_instances" and before_blocks is not None:
            before_blocks()
        keys = (rkey,) + (row.legacy_keys if key == "undo_key" else ())
        for k in keys:
            for rec in source.get(k, []):
                row.build(scene, rec, ctx)
        if row.attr == "_gridlines" and after_gridlines is not None:
            after_gridlines()


# -- save / load / clear (spec D4) ----------------------------------------------
def file_records(scene, *, constraints) -> dict:
    """``.fpd`` records of every row with a ``file_key``, in row order; the
    ``constraints`` key splices in after walls and ``block_definitions``
    before blocks (spec D2)."""
    out = {}
    for row in KINDS:
        if row.codec_owned or row.file_key is None:
            continue
        if row.attr == "_block_instances":
            out["block_definitions"] = _definitions_record(scene)
        out[row.file_key] = [i.to_dict() for i in getattr(scene, row.attr)]
        if row.attr == "_walls":
            out["constraints"] = constraints
    return out


def dropped_record_count(payload: dict) -> int:
    """Records of never-filed rows (C8) a load discards, legacy keys included."""
    return sum(len(payload.get(k, []))
               for row in KINDS if row.file_key is None
               for k in (row.undo_key,) + row.legacy_keys)


_CLEAR_REMOVES = ("design_areas", "_block_instances")


def clear_lists(scene) -> None:
    """Clear: rebind every row's list (the scene's ``clear()`` deletes the rest)."""
    for row in KINDS:
        if row.attr in _CLEAR_REMOVES:
            for item in list(getattr(scene, row.attr, [])):
                if item.scene() is scene:
                    scene.removeItem(item)
        setattr(scene, row.attr, [])


# -- delete (spec D4: _remove_item_from_lists / _bulk_delete) --------------------
_LIST_REMOVAL_EXTRA = ("_gridlines",)   # + every never-filed (loose) row: what
                                        # _remove_item_from_lists has always owned
_OWNED_REMOVAL = ("_walls", "_floor_slabs", "_roofs", "_rooms")


def remove_from_lists(scene, item) -> bool:
    """List-and-scene removal of a loose primitive or gridline; False otherwise."""
    for row in KINDS:
        if row.file_key is not None and row.attr not in _LIST_REMOVAL_EXTRA:
            continue
        if isinstance(item, row.cls):
            lst = getattr(scene, row.attr)
            if item in lst:
                lst.remove(item)
            scene.removeItem(item)
            return True
    return False


def remove_owned(scene, item) -> bool:
    """Bulk delete of a wall / slab / roof / room: owned children first (A2)."""
    for attr in _OWNED_REMOVAL:
        row = ROWS[attr]
        if not isinstance(item, row.cls):
            continue
        if row.children is not None:
            kids = row.children(item)
            for ch in list(kids):
                if ch.scene() is scene:
                    scene.removeItem(ch)
            kids.clear()
        lst = getattr(scene, attr)
        if item in lst:
            lst.remove(item)
        scene.removeItem(item)
        return True
    return False
