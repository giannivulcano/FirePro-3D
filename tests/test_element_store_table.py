"""Element store table guards (docs/specs/element-store.md G4, G5)."""
from __future__ import annotations

import ast
import json
import os

import pytest

from tests._element_store_fixture import ROW_ATTRS, build_every_kind, undo_bytes
from tests._ph1_helpers import load, ph1_cleanup  # noqa: F401  (autouse cleanup)
from firepro3d import element_store as es

PKG = os.path.join(os.path.dirname(os.path.dirname(__file__)), "firepro3d")


def test_rows_are_the_spec_rows_in_capture_order():
    assert tuple(r.attr for r in es.KINDS) == ROW_ATTRS


@pytest.mark.parametrize("row", es.KINDS, ids=lambda r: r.attr)
def test_row_is_complete(row):
    assert row.cls.__name__                      # class resolves
    if not row.codec_owned:
        assert row.builder is not None
    if row.file_key is None:
        assert row.record_type is not None       # loose rows are the paste registry


def test_order_tuples_cover_exactly_their_roles():
    assert set(es.PRIMITIVE_ORDER) == es.role_attrs("primitive")
    assert len(es.PRIMITIVE_ORDER) == len(set(es.PRIMITIVE_ORDER))
    assert set(es.CONSTRAINT_EDITOR_ORDER) == es.role_attrs("editor")
    assert set(es.CONSTRAINT_PRIMITIVE_ORDER) == es.role_attrs("editor") | es.role_attrs("primitive")
    assert set(es.CONSTRAINT_PLAN_ORDER) == es.role_attrs("plan")


# -- table fields against the code they describe ---------------------------------
@pytest.mark.parametrize("row", es.KINDS, ids=lambda r: r.attr)
def test_row_fields_match_the_code(qapp, tmp_path, row):
    from firepro3d.model_space import Model_Space
    ms, items = build_every_kind()
    item = items[row.attr]
    assert isinstance(item, row.cls), row.attr
    # undo key: the capture names this row's records under row.undo_key
    snap = ms._capture_network()
    assert row.undo_key in snap, row.undo_key
    assert len(snap[row.undo_key]) == 1, row.undo_key
    # file key: the saved payload names them under row.file_key; loose rows are not saved
    assert ms.save_to_file(str(tmp_path / "x.fpd"), backup=False)
    with open(tmp_path / "x.fpd", encoding="utf-8") as fh:
        payload = json.load(fh)
    if row.file_key is not None:
        assert len(payload[row.file_key]) == 1, row.file_key
    else:
        for key in (row.undo_key,) + tuple(row.legacy_keys):
            assert key not in payload, key
    # paste registry: the record type maps to this row's class and list
    if row.record_type is not None:
        assert Model_Space._GEOM_TYPE_REGISTRY[row.record_type] == (row.cls, row.attr)
    if row.legacy_keys:                          # the legacy record type routes to the same row
        assert Model_Space._GEOM_TYPE_REGISTRY.get("reference_line") == (row.cls, row.attr)
    # children: only walls and floor slabs own sub-items (their openings)
    assert (row.children is not None) == (row.attr in ("_walls", "_floor_slabs"))
    if row.children is not None:
        assert row.children(item) and list(row.children(item)) == list(item.openings)
    # level: the row's accessor reads the level the level walk reads
    if row.level_of is not None:
        expect = item._top_level if row.attr == "_floor_slabs" else getattr(item, "level", None)
        assert row.level_of(item) == expect


@pytest.mark.parametrize("row", [r for r in es.KINDS if r.record_type], ids=lambda r: r.attr)
def test_registry_record_types_are_all_rows(row):
    from firepro3d.model_space import Model_Space
    mapped = {rt for rt, (_c, a) in Model_Space._GEOM_TYPE_REGISTRY.items() if a == row.attr}
    assert row.record_type in mapped


@pytest.mark.parametrize("attr", ROW_ATTRS)
def test_row_survives_capture_restore(qapp, attr):
    ms, _ = build_every_kind()
    # Base asymmetry (characterized in G2): a fresh scene's first capture differs from a
    # restored one. One normalising round trip reaches the fixed point; compare from there.
    ms._restore_network(ms._capture_network())
    kept = getattr(ms, attr)[0]                  # restore rebuilt every item; re-pick live
    before = undo_bytes(ms)
    ms._restore_network(ms._capture_network())
    assert len(getattr(ms, attr)) == 1, attr
    assert kept not in getattr(ms, attr)         # rebuilt, not kept
    assert undo_bytes(ms) == before              # same records after the round trip


@pytest.mark.parametrize("row", [r for r in es.KINDS if r.file_key], ids=lambda r: r.attr)
def test_file_row_survives_save_load(qapp, tmp_path, row):
    ms, _ = build_every_kind()
    assert ms.save_to_file(str(tmp_path / "x.fpd"), backup=False)
    assert len(getattr(load(str(tmp_path / "x.fpd")), row.attr)) == 1


@pytest.mark.parametrize("attr", ROW_ATTRS)
def test_row_is_removed_by_delete(qapp, attr):
    ms, _ = build_every_kind()
    victim = getattr(ms, attr)[0]
    ms.delete_items([victim])
    assert victim not in getattr(ms, attr)


def test_owner_delete_takes_its_children(qapp):
    ms, items = build_every_kind()
    wall, slab = items["_walls"], items["_floor_slabs"]
    kids = list(wall.openings) + list(slab.openings)
    ms.delete_items([wall, slab])
    live = set(ms.items())
    assert kids and not [k for k in kids if k in live]
    assert not wall.openings and not slab.openings


# -- level walk parity (D5, D6 commit 7) -----------------------------------------
# Pinned at the parent of commit 7 (old _items_on_level / leveled_items). Compared per
# class sublist, so only the order ACROSS kinds may change (spec delta 4).
WALK_PIN = {
    "on": {a: [a] for a in (
        "_block_instances",      # R5 (D6 commit 9): placed blocks join the walk
        # O2 (D6 commit 10): the nine loose 2D rows left the walk (containment C3)
        "_floor_slabs", "_gridlines", "_roofs", "_rooms", "_walls", "design_areas")},
    "refs": {"_block_instances": ["_block_instances"], "_gridlines": ["_gridlines"],
             "_roofs": ["_roofs"], "_rooms": ["_rooms"],
             "_walls": ["_walls", "_walls.openings[0]"], "design_areas": ["design_areas"]},
}


def _keys(ms, items, seq):
    """Each walked element item -> a stable name: its fixture attr, or
    "<attr>.openings[i]" for an owned child. Non-element items are skipped."""
    name = {id(it): a for a, it in items.items()}
    for a in ("_walls", "_floor_slabs"):
        for i, ch in enumerate(items[a].openings):
            name[id(ch)] = f"{a}.openings[{i}]"
    return [name[id(it)] for it in seq if id(it) in name]


def _by_class(keys):
    out = {}
    for k in keys:
        out.setdefault(k.split(".")[0], []).append(k)
    return {c: out[c] for c in sorted(out)}


def test_level_walks_keep_their_members(qapp):
    from firepro3d.level_manager import leveled_items
    ms, items = build_every_kind()
    lvl = items["_walls"].level
    for a, it in items.items():                  # every kind on one level (2D, texts and
        if a != "_floor_slabs":                  # gridlines carry no level by default)
            it.level = lvl
    assert items["_floor_slabs"]._top_level == lvl
    got = {"on": _by_class(_keys(ms, items, ms._items_on_level(lvl))),
           "refs": _by_class(_keys(ms, items, leveled_items(ms)))}
    assert got == WALK_PIN
    assert _keys(ms, items, ms._items_on_level("No Such Level")) == []


# -- G5 scan guard ---------------------------------------------------------------
ATTRS = set(ROW_ATTRS)
# file -> reason. In-scope entries are deleted by the task named; the rest are
# out-of-scope per-kind readers (spec "Out of scope"). Seed by running the scan
# at commit 2 and classifying EVERY hit here.
KNOWN = {}


def _attr_of(e):
    """The row attr a literal element names: "_walls", self._walls, (Cls, "_walls")."""
    if isinstance(e, ast.Constant) and e.value in ATTRS:
        return e.value
    if isinstance(e, ast.Attribute) and e.attr in ATTRS:
        return e.attr
    if isinstance(e, ast.Tuple) and len(e.elts) == 2:
        return _attr_of(e.elts[1])
    return None


class _Scan(ast.NodeVisitor):
    """Records ``file:innermost def/class`` for every tuple/list/set literal or
    dict-literal value set naming >= 2 distinct row attrs."""

    def __init__(self, fn):
        self.fn, self.stack, self.hits = fn, ["<module>"], set()

    def _scoped(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _scoped

    def _check(self, elts, node):
        if len({a for a in map(_attr_of, elts) if a}) >= 2:
            self.hits.add(f"{self.fn}:{self.stack[-1]}")
        self.generic_visit(node)

    def visit_Tuple(self, node):
        self._check(node.elts, node)

    visit_List = visit_Set = visit_Tuple

    def visit_Dict(self, node):
        self._check(node.values, node)


def _hits():
    out = set()
    for fn in sorted(os.listdir(PKG)):
        if not fn.endswith(".py") or fn == "element_store.py":
            continue
        with open(os.path.join(PKG, fn), encoding="utf-8-sig") as fh:   # BOM-safe
            scan = _Scan(fn)
            scan.visit(ast.parse(fh.read()))
        out |= scan.hits
    return out


def test_g5_no_new_kind_list_outside_the_store():
    hits = _hits()
    assert hits - set(KNOWN) == set(), "new kind list/map outside element_store.py"
    assert set(KNOWN) - hits == set(), "stale KNOWN entry: delete it"
