"""Nested blocks — registry, compile, live update, placeholder (AC3, AC12, AC14)."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from firepro3d.block_definition import BlockDefinition
from firepro3d.block_registry import BlockRegistry
from firepro3d.geometry_2d import LineItem


def _line_def(name, x0=0.0, x1=100.0, y=0.0, origin=(0.0, 0.0), extra=()):
    prims = [LineItem(QPointF(x0, y), QPointF(x1, y)).to_dict(), *extra]
    return BlockDefinition.new(name=name, library="L", series="S",
                               primitives=prims, origin=origin)


def _nested(block_id, x, y, rot=0.0):
    return {"type": "block_instance", "block_id": block_id,
            "pos": [x, y], "rotation": rot}


def _reg(*defs):
    store = {}
    r = BlockRegistry(store)
    for d in defs:
        r.add(d)
    return r, store


def test_registry_users_of_is_transitive(qapp):
    c = _line_def("C")
    b = _line_def("B", extra=[_nested(c.id, 0, 0)])
    a = _line_def("A", extra=[_nested(b.id, 0, 0)])
    other = _line_def("X")
    r, _ = _reg(c, b, a, other)
    assert r.users_of(c.id) == {b.id, a.id}
    assert r.users_of(b.id) == {a.id}
    assert r.users_of(a.id) == set()


def test_registry_would_cycle(qapp):
    c = _line_def("C")
    b = _line_def("B", extra=[_nested(c.id, 0, 0)])
    a = _line_def("A", extra=[_nested(b.id, 0, 0)])
    r, _ = _reg(c, b, a)
    assert r.would_cycle(a.id, a.id)          # A into A
    assert r.would_cycle(c.id, a.id)          # A (⊃B⊃C) into C
    assert not r.would_cycle(a.id, c.id)      # C into A is fine
    assert not r.would_cycle(None, a.id)      # unsaved host


def test_registry_get_injects_resolver_for_direct_dict_writes(qapp):
    b = _line_def("B")
    store = {b.id: b}                         # written directly (undo restore / load)
    r = BlockRegistry(store)
    assert r.get(b.id)._resolve is not None


def test_registry_missing_nested(qapp):
    a = _line_def("A", extra=[_nested("deadbeef", 0, 0)])
    r, _ = _reg(a)
    assert r.missing_nested() == {"deadbeef": {a.id}}
