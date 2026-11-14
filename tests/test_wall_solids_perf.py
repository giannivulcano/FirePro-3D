import time
import pytest
from PyQt6.QtCore import QPointF

pytestmark = pytest.mark.perf


def _scene_l(model_scene, n=100):
    from firepro3d.wall import WallSegment
    from firepro3d.wall_opening import WallOpening
    s = model_scene()
    walls = []
    for i in range(n):                      # 100 L pairs = 200 walls
        x = i * 5000.0
        a = WallSegment(QPointF(x, 0), QPointF(x + 3000, 0), thickness_mm=200.0)
        b = WallSegment(QPointF(x + 3000, 0), QPointF(x + 3000, 3000), thickness_mm=200.0)
        for w in (a, b):
            s.addItem(w); s._walls.append(w); walls.append(w)
        for w, off in ((a, 800.0), (a, 2000.0), (b, 800.0), (b, 2000.0)):
            op = WallOpening(wall=w, feature_id="door_914", offset_along=off)
            s.addItem(op); w.openings.append(op)
    return s, walls


def _scene_pies(model_scene, n=10):
    from firepro3d.wall import WallSegment
    s = model_scene()
    walls = []
    for i in range(n):
        for j in range(n):
            x, y = i * 4000.0, j * 4000.0
            for dx, dy in ((4000, 0), (0, 4000)):
                w = WallSegment(QPointF(x, y), QPointF(x + dx, y + dy), thickness_mm=200.0)
                s.addItem(w); s._walls.append(w); walls.append(w)
    return s, walls


def _per_wall_ms(s, walls):
    """One View3D._extract_walls pass: the rings once, then every mesh."""
    from firepro3d.wall import join_neighbourhoods
    lm = s._level_manager
    t0 = time.perf_counter()
    rings = join_neighbourhoods(walls)
    for w in walls:
        w.get_3d_mesh(level_manager=lm, pool=rings[id(w)])
    return 1000 * (time.perf_counter() - t0) / len(walls)


def test_g9_l_scene_bar(qapp, model_scene):
    s, walls = _scene_l(model_scene)
    assert len(walls) == 200 and sum(len(w.openings) for w in walls) == 400
    _per_wall_ms(s, walls)                  # warm caches
    ms = _per_wall_ms(s, walls)
    print(f"L scene: {ms:.3f} ms/wall")
    assert ms <= 5.0                        # G9 bar, re-set 2026-11-14


def test_g9_pie_grid(qapp, model_scene):
    s, walls = _scene_pies(model_scene)
    assert len(walls) == 200
    assert any(len(ends) >= 2 for w in walls
               for ends in w._join_ends()["partners"])
    _per_wall_ms(s, walls)
    ms = _per_wall_ms(s, walls)
    print(f"pie grid: {ms:.3f} ms/wall")
