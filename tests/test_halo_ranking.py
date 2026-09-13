"""Tests for Model_Space.halo_rank — the single deterministic preselection
ordering shared by hover, Spacebar cycle, and click (U5 Task A3).

API notes (verified against the real code, not assumed):
  * ``add_node(x, y)`` returns a ``Node`` (z=Z_NODE=10) but DEDUPES against any
    existing node within ``SNAP_RADIUS`` (10). Two ``add_node`` calls at the
    same XY return the *same* object, so coincident-node tests construct raw
    ``Node`` objects directly and ``addItem`` them to dodge the dedup.
  * ``add_pipe(n1, n2)`` returns a ``Pipe`` (z=Z_PIPE=5).
  * ``add_sprinkler(n)`` builds ``n.sprinkler`` (a child SVG item with
    ItemIsSelectable False) and returns it; the node exposes it via
    ``n.sprinkler`` / ``n.has_sprinkler()``.
"""
import pytest
from PyQt6.QtCore import QPointF
from firepro3d.model_space import Model_Space
from firepro3d.node import Node


def test_rank_orders_by_runtime_z_desc(qapp):
    sc = Model_Space()
    n = sc.add_node(0.0, 0.0)                       # Node  z=10
    # Distinct endpoints so a real pipe is built (add_node dedupes by proximity).
    p = sc.add_pipe(sc.add_node(500.0, 0.0), n)     # Pipe  z=5
    ordered = sc.halo_rank([p, n], QPointF(0.0, 0.0))
    assert ordered[0] is n        # higher runtime-Z wins
    assert p in ordered


def test_rank_resolves_sprinkler_to_node(qapp):
    sc = Model_Space()
    n = sc.add_node(0.0, 0.0)
    sc.add_sprinkler(n, None)                        # child SVG, ItemIsSelectable False
    ordered = sc.halo_rank([n.sprinkler, n], QPointF(0.0, 0.0))
    assert n in ordered
    assert n.sprinkler not in ordered               # child resolves to parent, deduped


def test_rank_is_deterministic_for_coincident(qapp):
    sc = Model_Space()
    # Build two raw coincident nodes directly (add_node would dedupe them).
    a = Node(5.0, 5.0)
    b = Node(5.0, 5.0)
    sc.addItem(a)
    sc.addItem(b)
    o1 = sc.halo_rank([a, b], QPointF(5.0, 5.0))
    o2 = sc.halo_rank([b, a], QPointF(5.0, 5.0))
    assert [id(x) for x in o1] == [id(x) for x in o2]
    assert len(o1) == 2                              # both survive dedup (distinct ids)
