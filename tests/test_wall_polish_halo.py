"""G4 (wall polish AC3): HALO and hit area trace the wall's own drawn piece
for every alignment, right after real placement, after load, and after a
neighbour edit."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, Qt, QEvent
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from firepro3d.halo import halo_scene_path
from firepro3d.wall import WallSegment, ALIGN_LEFT, ALIGN_RIGHT


def _click(view, scene_pt):
    """Left press+release at scene_pt through the real event pipeline
    (same helper as tests/test_wall_placement_workflow.py)."""
    vp = view.viewport()
    p = view.mapFromScene(scene_pt)
    for et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        ev = QMouseEvent(et, p.toPointF(), vp.mapToGlobal(p).toPointF(),
                         Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(vp, ev)


def _set_alignment(scene, target):
    """Cycle the real wall-alignment toggle (Space in wall mode)."""
    for _ in range(4):
        if scene._wall_alignment == target:
            return
        scene._cycle_wall_alignment()
    raise AssertionError(f"could not reach alignment {target}")


def _inside_and_mirror(wall):
    """(point in the drawn body, mirror point in the Center-position band
    the drawn body does NOT cover).  Built from the click line and the
    true-centerline offset -- not from the outline under test."""
    off = wall._centerline_offset()
    mx = (wall.pt1.x() + wall.pt2.x()) / 2.0
    my = (wall.pt1.y() + wall.pt2.y()) / 2.0
    inside = QPointF(mx + off.x(), my + off.y())
    mirror = QPointF(mx - off.x(), my - off.y())
    return inside, mirror


def _assert_halo_on_body(wall):
    hp = halo_scene_path(wall)
    inside, mirror = _inside_and_mirror(wall)
    assert hp.contains(inside), f"HALO misses the drawn body of {wall}"
    assert not hp.contains(mirror), f"HALO sits on the Center band of {wall}"


@pytest.mark.parametrize("align", [ALIGN_LEFT, ALIGN_RIGHT])
def test_line_placement_halo_on_drawn_body(qapp, shown_model_view, align):
    view, scene = shown_model_view
    scene.set_mode("wall")
    _set_alignment(scene, align)
    _click(view, QPointF(0, 0))
    _click(view, QPointF(3000, 0))
    wall = scene._walls[-1]
    assert wall._alignment == align            # precondition: real path set it
    _assert_halo_on_body(wall)
    far = wall.outline_geometry().faces[0 if align == ALIGN_LEFT else 1]
    face_mid = QPointF((far[0].x() + far[1].x()) / 2,
                       (far[0].y() + far[1].y()) / 2)
    assert wall in scene.items(face_mid)       # hit at the drawn far face


@pytest.mark.parametrize("align", [ALIGN_LEFT, ALIGN_RIGHT])
def test_rect_placement_halo_on_drawn_body(qapp, shown_model_view, align):
    view, scene = shown_model_view
    scene.set_mode("wall")
    _set_alignment(scene, align)
    scene.cycle_placement_variant(+1)   # line -> polyline
    scene.cycle_placement_variant(+1)   # polyline -> corner rect
    _click(view, QPointF(0, 0))
    _click(view, QPointF(3000, 0))
    _click(view, QPointF(1500, 2000))
    assert len(scene._walls) == 4
    for wall in scene._walls:
        assert wall._alignment == align
        _assert_halo_on_body(wall)


@pytest.mark.parametrize("align", [ALIGN_LEFT, ALIGN_RIGHT])
def test_loaded_wall_halo_on_drawn_body(qapp, align):
    """from_dict + addItem + append: the exact sequence scene_io.py runs
    for each saved wall (load loop)."""
    from firepro3d.model_space import Model_Space
    src = WallSegment(QPointF(0, 0), QPointF(3000, 0))
    src._alignment = align
    scene = Model_Space()
    wall = WallSegment.from_dict(src.to_dict())
    scene.addItem(wall)
    scene._walls.append(wall)
    assert wall._alignment == align
    _assert_halo_on_body(wall)


def test_neighbour_edit_refreshes_joined_wall(qapp):
    """D3: moving B's far end re-miters A's corner; A's cached outline,
    path (HALO/hit) and a fresh pure computation agree."""
    from firepro3d.model_space import Model_Space
    scene = Model_Space()
    a = WallSegment(QPointF(0, 0), QPointF(3000, 0))
    b = WallSegment(QPointF(3000, 0), QPointF(3000, 2000))
    for w in (a, b):
        w._alignment = ALIGN_LEFT
        scene.addItem(w)
        scene._walls.append(w)
    b.apply_grip(1, QPointF(4500, 2000))          # B's far end moves
    fresh = a._compute_mitered_quad()[0]
    cached = a.mitered_quad()
    for p, q in zip(fresh, cached):
        assert abs(p.x() - q.x()) < 1e-6 and abs(p.y() - q.y()) < 1e-6
    poly = a.path().toFillPolygon()
    for p in fresh:
        assert any(abs(p.x() - v.x()) < 1e-6 and abs(p.y() - v.y()) < 1e-6
                   for v in poly), "A.path() (HALO/hit) is stale"


def test_saved_and_loaded_joined_walls_through_real_io(qapp, tmp_path):
    """F1(d): two joined walls (one Left-aligned) saved by the real
    save_to_file and loaded by the real load_from_file into a fresh scene:
    HALO sits on the drawn body at the junction side, and the joined pair's
    cached outline equals a fresh rebuild."""
    from firepro3d.model_space import Model_Space
    src = Model_Space()
    a = WallSegment(QPointF(0, 0), QPointF(3000, 0))
    b = WallSegment(QPointF(3000, 0), QPointF(3000, 2500))
    for w in (a, b):
        src.addItem(w)
        src._walls.append(w)
    a._alignment = ALIGN_LEFT
    path = str(tmp_path / "walls.json")
    src.save_to_file(path)

    dst = Model_Space()
    dst.load_from_file(path)
    assert len(dst._walls) == 2
    la = min(dst._walls, key=lambda w: w.pt1.x())
    lb = max(dst._walls, key=lambda w: w.pt1.x())
    assert la._alignment == ALIGN_LEFT
    _assert_halo_on_body(la)           # the Left-aligned wall
    for w in (la, lb):
        # junction-side body point: just inside the drawn face at the joint
        off = w._centerline_offset()
        j = w.pt2 if w is la else w.pt1
        k = w.pt1 if w is la else w.pt2
        t = 0.1
        pt = QPointF(j.x() + (k.x() - j.x()) * t + off.x(),
                     j.y() + (k.y() - j.y()) * t + off.y())
        assert halo_scene_path(w).contains(pt)
    for w in (la, lb):
        cached = [(round(p.x(), 6), round(p.y(), 6))
                  for p in w.mitered_quad()]
        fresh = [(round(p.x(), 6), round(p.y(), 6))
                 for p in w._compute_mitered_quad()[0]]
        assert cached == fresh


def test_calibration_refreshes_wall_geometry_without_paint(qapp, monkeypatch):
    """F9/M2: a real scale calibration re-derives every wall's path/shape at
    once (no paint needed to self-heal)."""
    from PyQt6.QtWidgets import QGraphicsView  # noqa: F401
    from tests.test_wall_polish_junctions import _ms, _wall
    import firepro3d.model_space as ms_mod

    s = _ms()
    w = _wall(s, (0, 0), (3000, 0))
    w.outline_geometry()
    before = w.path().boundingRect().height()
    assert abs(before - 200.0) < 1e-6

    class _Dlg:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return True

        def get_distance(self):
            return 1000.0

        def get_unit_code(self):
            return "mm"

    monkeypatch.setattr(ms_mod, "CalibrateDialog", _Dlg)
    s._cal_point1 = None
    # 1000 mm real over 2000 scene units -> 2 px/mm
    s._press_set_scale(None, None, QPointF(0, 0), None, None, None)
    s._press_set_scale(None, None, QPointF(2000, 0), None, None, None)
    assert abs(s.scale_manager.pixels_per_mm - 2.0) < 1e-9

    after = w.path().boundingRect().height()      # no paint, no outline call
    assert abs(after - before * 2.0) < 1e-6
    assert w.shape().boundingRect().height() >= after - 1e-6
