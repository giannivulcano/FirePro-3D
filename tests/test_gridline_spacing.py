import math
from PyQt6.QtCore import QPointF
from firepro3d.model_space import Model_Space
from firepro3d.gridline import GridlineItem


def _add(scene, p1, p2, label):
    gl = GridlineItem(p1, p2, label=label)
    scene.addItem(gl); scene._gridlines.append(gl)
    return gl


def test_parallel_verticals_get_spacing(qapp):
    scene = Model_Space()
    a = _add(scene, QPointF(0, 0), QPointF(0, 1000), "A")
    b = _add(scene, QPointF(500, 0), QPointF(500, 1000), "B")
    a.setSelected(True)
    dims = scene._compute_gridline_spacing()
    assert any(math.isclose(d["distance"], 500.0, abs_tol=1e-3) for d in dims)


def test_non_parallel_get_no_spacing(qapp):
    # Both lines fall in the same binary "vertical" bucket (dy > dx) but
    # are NOT parallel (~11 deg apart) — the old code mis-paired them.
    scene = Model_Space()
    a = _add(scene, QPointF(0, 0), QPointF(0, 1000), "A")       # vertical
    b = _add(scene, QPointF(0, 0), QPointF(200, 1000), "B")     # ~11 deg off
    a.setSelected(True)
    dims = scene._compute_gridline_spacing()
    assert all(not ({d["from_gl"], d["to_gl"]} == {a, b}) for d in dims)


def test_near_45_does_not_mispair(qapp):
    # Two lines straddling 45 deg but both in the "horizontal" bucket
    # (dx >= dy) and ~11 deg apart — must NOT be paired.
    scene = Model_Space()
    a = _add(scene, QPointF(0, 0), QPointF(1000, 400), "A")   # ~21.8 deg
    b = _add(scene, QPointF(0, 0), QPointF(1000, 600), "B")   # ~31.0 deg
    a.setSelected(True)
    dims = scene._compute_gridline_spacing()
    assert all(not ({d["from_gl"], d["to_gl"]} == {a, b}) for d in dims)


def test_apply_spacing_edit_moves_selected(qapp):
    scene = Model_Space()
    a = _add(scene, QPointF(0, 0), QPointF(0, 1000), "A")
    b = _add(scene, QPointF(500, 0), QPointF(500, 1000), "B")
    b.setSelected(True)
    dims = scene._compute_gridline_spacing()
    dim = next(d for d in dims if {d["from_gl"], d["to_gl"]} == {a, b})
    scene._apply_spacing_edit(dim, 800.0, [b])
    # b moved so spacing becomes 800
    assert any(math.isclose(d2["distance"], 800.0, abs_tol=1e-2)
               for d2 in scene._compute_gridline_spacing())
