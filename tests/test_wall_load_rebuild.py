"""Walls rebuild their outline when their visibility really changes, not on
Qt's polish notice after an add (wall polish D3/D4; backlog "Every wall
rebuilds its outline O(N^2) after load / paste").

After ``addItem`` Qt queues ``_q_polishItems``, which sends
``ItemVisibleChange`` / ``ItemVisibleHasChanged`` to every item that is not
explicitly hidden, though nothing changed. Each such notice rebuilt the wall's
outline and scanned the whole wall pool, so opening a project paid O(N^2).

The scenes are real: walls are saved and loaded through ``save_to_file`` /
``load_from_file`` or pasted through ``paste_items``, then the event loop runs
as it does after the user opens the file.
"""
from __future__ import annotations

import time

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from firepro3d.wall import WallSegment
from tests.test_wall_polish_junctions import _ms, _wall

CELL = 4000.0


def _flush() -> None:
    for _ in range(5):
        QApplication.processEvents()


def _lattice(n: int) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """n x n rooms: corners, tees and crosses, one cell per wall."""
    segs = []
    for r in range(n + 1):
        for c in range(n):
            segs.append(((c * CELL, r * CELL), ((c + 1) * CELL, r * CELL)))
    for c in range(n + 1):
        for r in range(n):
            segs.append(((c * CELL, r * CELL), (c * CELL, (r + 1) * CELL)))
    return segs


def _corners(k: int) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """k isolated L corners, far apart: joins, no shared junctions."""
    segs = []
    for i in range(k):
        x = i * 3 * CELL
        segs.append(((x, 0.0), (x + CELL, 0.0)))
        segs.append(((x + CELL, 0.0), (x + CELL, CELL)))
    return segs


def _saved_project(segs, path):
    """Write a project holding *segs* as walls; return the live scene so the
    caller keeps it referenced (a collected scene raises mid-run)."""
    s = _ms()
    walls = []
    for a, b in segs:
        w = WallSegment(QPointF(*a), QPointF(*b), thickness_mm=200.0)
        w._base_level, w._top_level = "Level 1", "Level 2"
        s.addItem(w)
        walls.append(w)
    _flush()
    s._walls.extend(walls)         # after the add: no per-wall queued rebuild
    s.save_to_file(str(path), backup=False)
    s._walls.clear()
    return s


def _poly(p):
    return tuple((round(q.x(), 3), round(q.y(), 3)) for q in p)


def _prints(s) -> dict:
    out = {}
    for w in s._walls:
        o = w.outline()
        out[w._uid] = (_poly(o.body), _poly(o.union_body), tuple(o.solid),
                       len(o.caps),
                       tuple(sorted(n._uid for n in o.neighbours)),
                       len(o.seams))
    return out


@pytest.fixture
def rebuilds(monkeypatch):
    """Count ``WallSegment._rebuild_outline`` calls; ``take()`` reads and zeroes."""
    box = {"n": 0}
    orig = WallSegment._rebuild_outline

    def counted(wall, extra=None):
        box["n"] += 1
        return orig(wall, extra)

    monkeypatch.setattr(WallSegment, "_rebuild_outline", counted)

    def take() -> int:
        n, box["n"] = box["n"], 0
        return n

    return take


@pytest.fixture
def loaded(qapp, tmp_path):
    """A 24-wall lattice opened through the real load path, flush not yet run."""
    p = tmp_path / "lattice.FPD"
    keep = _saved_project(_lattice(3), p)
    fresh = _ms()
    fresh.load_from_file(str(p))
    assert len(fresh._walls) == 24, "bench composition"
    yield fresh
    fresh._walls.clear()
    del keep


def test_opening_a_project_rebuilds_nothing_on_the_first_event_loop_pass(
        loaded, rebuilds):
    rebuilds()                          # drop the load's own rebuilds
    _flush()
    assert rebuilds() == 0


def test_the_flush_leaves_every_outline_as_the_load_built_it(loaded):
    before = _prints(loaded)
    _flush()
    assert _prints(loaded) == before


def test_pasting_walls_rebuilds_nothing_on_the_next_event_loop_pass(
        qapp, rebuilds):
    s = _ms()
    segs = _lattice(3)
    walls = [_wall(s, a, b) for a, b in segs]
    _flush()
    data = [w.to_dict() for w in walls]
    s.paste_items(QPointF(5 * CELL, 0.0), data=data)
    assert len(s._walls) == 2 * len(walls), "bench composition"
    rebuilds()                          # drop the paste's own rebuilds
    before = _prints(s)
    _flush()
    assert rebuilds() == 0
    assert _prints(s) == before
    s._walls.clear()


def test_hiding_and_showing_a_wall_still_rejoins_its_neighbour(qapp, rebuilds):
    """Over-reach control: a real visibility flip must keep rebuilding."""
    s = _ms()
    upper = _wall(s, (0, 0), (2000, 0))
    lower = _wall(s, (2000, 0), (2000, 1500))
    _flush()
    assert upper.outline().solid[1] is True, "precondition: joined at the corner"
    rebuilds()
    lower.setVisible(False)
    _flush()
    assert rebuilds() > 0
    assert upper.outline().solid[1] is False
    lower.setVisible(True)
    _flush()
    assert upper.outline().solid[1] is True
    s._walls.clear()


def test_adding_a_wall_still_joins_it_to_the_walls_already_there(qapp):
    s = _ms()
    first = _wall(s, (0, 0), (2000, 0))
    _flush()
    assert first.outline().solid[1] is False        # a lone wall
    _wall(s, (2000, 0), (2000, 1500))
    _flush()
    assert first.outline().solid[1] is True


@pytest.mark.perf
@pytest.mark.parametrize("label, segs", [("corners_150", _corners(150)),
                                         ("rooms_8", _lattice(8))])
def test_first_event_loop_pass_costs_at_most_1ms_per_wall(
        label, segs, qapp, tmp_path):
    p = tmp_path / f"{label}.FPD"
    keep = _saved_project(segs, p)
    fresh = _ms()
    fresh.load_from_file(str(p))
    assert len(fresh._walls) == len(segs), "bench composition"
    t0 = time.perf_counter()
    _flush()
    per_wall_ms = (time.perf_counter() - t0) * 1000.0 / len(segs)
    print(f"RAW {label} walls={len(segs)} flush_ms_per_wall={per_wall_ms:.3f}")
    fresh._walls.clear()
    del keep
    assert per_wall_ms <= 1.0
