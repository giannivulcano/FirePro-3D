"""HUD Tab field-commit redraws the wall / floor placement ghost.

Before the fix ``_PREVIEW_DISPATCH`` had no ``wall`` / ``floor`` entry, so a
Tab-committed Length / H left the ghost frozen at its engage-time seed (todo
L988).  Each case seeds a decoy far from the typed value so a ghost still on
the seed cannot pass.  Roof has no HUD applier, so it is deliberately absent.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest

from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View


class _Ev:
    def modifiers(self):
        return Qt.KeyboardModifier.NoModifier


@pytest.fixture
def scene(qapp):
    return Model_Space()


@pytest.fixture
def view(scene):
    v = Model_View(scene)
    v.resize(800, 600)
    v.resetTransform()
    v.show()
    QTest.qWaitForWindowExposed(v)
    yield v
    v.close()


def _tab(hud, field, text):
    ed = hud.editor(field)
    ed.selectAll()
    ed.setText(text)
    QTest.keyClick(ed, Qt.Key.Key_Tab)


def _corner_rect(s, mode):
    s.set_mode(mode)
    attr = "_wall_primitive" if mode == "wall" else "_floor_primitive"
    centre = "_wall_rect_from_center" if mode == "wall" else "_floor_rect_from_center"
    while not (getattr(s, attr) == "rect" and not getattr(s, centre)):
        assert s.cycle_placement_variant(+1)


def test_wall_line_ghost_follows_typed_length(scene, view):
    scene.set_mode("wall")
    assert scene._wall_primitive != "rect"
    scene._press_wall(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    scene._move_wall_router(_Ev(), QPointF(800, 0))             # decoy
    assert scene.begin_dynamic_input() is True
    _tab(scene.dynamic_input, "Length", "1200")
    assert scene.preview_pipe.line().x2() == pytest.approx(1200.0)
    # The thickness quad follows the same tip, not the seed.
    assert scene._wall_preview_rect.path().boundingRect().right() >= 1200.0


def test_floor_polygon_ghost_follows_typed_length(scene, view):
    scene.set_mode("floor")
    while scene._floor_primitive == "rect":
        assert scene.cycle_placement_variant(+1)
    scene._press_floor(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    scene._move_floor_router(_Ev(), QPointF(800, 0))            # decoy
    assert scene.begin_dynamic_input() is True
    _tab(scene.dynamic_input, "Length", "1200")
    assert scene.preview_pipe.line().x2() == pytest.approx(1200.0)


def test_wall_rect_side_guide_follows_typed_length(scene, view):
    _corner_rect(scene, "wall")
    scene._press_wall_rect(None, None, QPointF(0, 0), None, None, None)
    scene._move_wall_rect(_Ev(), QPointF(800, 0))               # decoy
    assert scene.begin_dynamic_input() is True
    _tab(scene.dynamic_input, "Length", "1500")
    assert scene._wall_rect_ref_line0.line().x2() == pytest.approx(1500.0)


def test_wall_rect_depth_ghost_and_overlay_follow_typed_h(scene, view):
    _corner_rect(scene, "wall")
    scene._press_wall_rect(None, None, QPointF(0, 0), None, None, None)
    scene._press_wall_rect(None, None, QPointF(1000, 0), None, None, None)
    scene._move_wall_rect(_Ev(), QPointF(800, -400))            # decoy depth
    assert scene.begin_dynamic_input() is True
    _tab(scene.dynamic_input, "H", "500")
    r = scene._wall_rect_preview.rect()
    assert r.width() == pytest.approx(1000.0)
    assert r.height() == pytest.approx(500.0)
    ov = scene._wall_rect_thickness_preview.path().boundingRect()
    assert ov.height() >= 500.0, "thickness overlay tracks the typed depth"


def test_floor_rect_depth_ghost_follows_typed_h(scene, view):
    _corner_rect(scene, "floor")
    scene._press_floor_rect(None, None, QPointF(0, 0), None, None, None)
    scene._press_floor_rect(None, None, QPointF(1000, 0), None, None, None)
    scene._move_floor_rect(_Ev(), QPointF(800, -400))           # decoy depth
    assert scene.begin_dynamic_input() is True
    _tab(scene.dynamic_input, "H", "500")
    r = scene._floor_rect_preview.rect()
    assert r.width() == pytest.approx(1000.0)
    assert r.height() == pytest.approx(500.0)


def test_wall_rect_centre_side_guide_follows_typed_length(scene, view):
    scene.set_mode("wall")
    while not (scene._wall_primitive == "rect" and scene._wall_rect_from_center):
        assert scene.cycle_placement_variant(+1)
    scene._press_wall_rect(None, None, QPointF(0, 0), None, None, None)
    scene._move_wall_rect(_Ev(), QPointF(800, 0))               # decoy
    assert scene.begin_dynamic_input() is True
    _tab(scene.dynamic_input, "Length", "1500")
    ln = scene._wall_rect_ref_line0.line()
    # Centre variant: Length is the FULL width (dynamic_input rect_side_center),
    # the resolved point is the side midpoint (750), and the guide spans the
    # full side centred on the base (-750 .. +750).
    assert max(ln.x1(), ln.x2()) == pytest.approx(750.0)
    assert min(ln.x1(), ln.x2()) == pytest.approx(-750.0)


def test_floor_rect_side_guide_follows_typed_length(scene, view):
    _corner_rect(scene, "floor")
    scene._press_floor_rect(None, None, QPointF(0, 0), None, None, None)
    scene._move_floor_rect(_Ev(), QPointF(800, 0))              # decoy
    assert scene.begin_dynamic_input() is True
    _tab(scene.dynamic_input, "Length", "1500")
    assert scene._floor_rect_ref_line0.line().x2() == pytest.approx(1500.0)
