"""G5 (wall polish AC4): wall snap targets come from the cached outline --
faces foot-snap with Nearest off, the centerline is the TRUE centerline,
thin walls keep their faces, and a real floor click lands on a face."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, Qt, QEvent
from PyQt6.QtGui import QMouseEvent, QTransform
from PyQt6.QtWidgets import QApplication

from firepro3d.level_manager import LevelManager
from firepro3d.snap_engine import SnapEngine
from firepro3d.wall import WallSegment, ALIGN_LEFT


def _ms():
    from firepro3d.model_space import Model_Space
    return Model_Space()


def _add(s, p1, p2, th=200.0, align=ALIGN_LEFT):
    w = WallSegment(QPointF(*p1), QPointF(*p2), thickness_mm=th)
    w._alignment = align
    s.addItem(w)
    s._walls.append(w)
    return w


def _click(view, scene_pt):
    vp = view.viewport()
    p = view.mapFromScene(scene_pt)
    for et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        ev = QMouseEvent(et, p.toPointF(), vp.mapToGlobal(p).toPointF(),
                         Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(vp, ev)


def _far_face_y(w):
    """Left wall along +x: body on the +normal (+y) side of the click line,
    far face at y = 2 * half thickness (quad_points, raw geometry)."""
    return 2.0 * w.half_thickness_scene()


def test_face_middle_snaps_with_nearest_off(qapp):
    s = _ms()
    w = _add(s, (0, 0), (6000, 0))
    eng = SnapEngine()
    eng.snap_nearest = False
    y = _far_face_y(w)
    r = eng.find(QPointF(2000, y + 3.0), s, QTransform())
    assert r is not None, "face must snap with Nearest off (D10)"
    assert r.point.y() == pytest.approx(y, abs=1e-6)
    assert r.point.x() == pytest.approx(2000.0, abs=1e-6)


def test_centerline_end_is_true_centre(qapp):
    s = _ms()
    w = _add(s, (0, 0), (6000, 0))
    ht = w.half_thickness_scene()
    r = SnapEngine().find(QPointF(0, ht), s, QTransform())
    assert r is not None and r.name == "centerline-end-A"
    assert r.point.x() == pytest.approx(0.0, abs=1e-6)
    assert r.point.y() == pytest.approx(ht, abs=1e-6)   # not the click line


def test_thin_wall_keeps_face_corners(qapp):
    s = _ms()
    # away from the scene origin: an 'origin' snap would outrank the corner
    w = _add(s, (1000, 1000), (4000, 1000), th=4.0, align="Center")
    p1l = w.quad_points()[0]
    r = SnapEngine().find(QPointF(p1l), s, QTransform())
    assert r is not None and r.name == "face-left-corner-A"


def test_hidden_in_junction_corner_is_not_a_target(qapp):
    """Only visible outline corners snap: at a T the stub's coped corners
    are targets; the host has no corner at the T centre."""
    s = _ms()
    host = _add(s, (0, 0), (6000, 0), align="Center")
    stub = _add(s, (3000, 0), (3000, 2500), align="Center")
    names = {n for _t, _p, n in host.snap_geometry()["named"]}
    assert "face-left-corner-A" in names            # free-end corner kept
    pts = [p for _t, p, _n in stub.snap_geometry()["named"]
           if _n and _n.startswith("face-") and _n.endswith("-A")]
    assert len(pts) == 2                                 # both coped corners
    assert all(abs(p.y() - 100.0) < 1e-6 for p in pts)   # on host near face


def test_shaft_snaps_on_mid_level(qapp):
    s = _ms()
    s._level_manager = LevelManager()
    lm = s._level_manager
    e1 = lm.get("Level 1").elevation
    if lm.get("Level 2") is None:
        lm.add_level("Level 2", elevation=e1 + 3000.0)
    e2 = lm.get("Level 2").elevation
    for i, name in enumerate(("Level 3", "Level 4", "Level 5"), start=1):
        lm.add_level(name, elevation=e2 + 3000.0 * i)
    shaft = _add(s, (0, 0), (6000, 0))
    shaft._base_level, shaft._top_level = "Level 1", "Level 5"
    e3 = lm.get("Level 3").elevation
    lm.apply_to_scene(s, active_level="Level 3", view_height=e3 + 1200.0,
                      view_depth=e3 - 300.0)
    assert shaft.isVisible()
    eng = SnapEngine()
    eng.snap_nearest = False
    y = _far_face_y(shaft)
    r = eng.find(QPointF(2000, y + 3.0), s, QTransform())
    assert r is not None and r.point.y() == pytest.approx(y, abs=1e-6)


def test_floor_click_lands_on_face(qapp, shown_model_view):
    """Real floor placement (corner rect base click) with Nearest off: the
    first slab vertex lands on the wall face."""
    view, scene = shown_model_view
    w = _add(scene, (0, 0), (6000, 0))
    scene._snap_engine.snap_nearest = False
    y = _far_face_y(w)
    scene.set_mode("floor")
    assert scene._floor_primitive == "rect"
    _click(view, QPointF(2000, y + 3.0))       # base, 3 mm off the face
    _click(view, QPointF(4000, y + 3.0))       # side
    _click(view, QPointF(3000, y + 1500.0))    # depth commit
    slab = scene._floor_slabs[-1]
    assert slab._points[0].y() == pytest.approx(y, abs=1e-6)
