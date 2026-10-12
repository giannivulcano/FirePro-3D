"""Arrow-key flips while placing a block (design DD8, ruling G7).

<-/-> mirror the armed placement left<->right on SCREEN, up/down top<->bottom
on screen, even after Space rotated it; each press toggles; auto-repeat is
ignored; the state persists across repeat placements, resets on entering the
mode and survives a Blocks-browser drag; same in plan and the Block Editor.

Focus is never set by hand: the first real click on the viewport is the
entry path that gives the canvas the keyboard, exactly as in the app.
"""
import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _def_L(ms):
    """An L: (0,0)->(100,0) and (0,0)->(0,-40) -- asymmetric both ways, so a
    left-right flip and a top-bottom flip give different geometry."""
    d = BlockDefinition.new(name="L", library="L", series="S", origin=(0.0, 0.0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict(),
                                        LineItem(QPointF(0, 0), QPointF(0, -40)).to_dict()])
    ms.register_block_definition(d)
    return d


def _shown(scene):
    """Shown 1000x700 view over scene x in [-50, 950] -- NO setFocus()."""
    from firepro3d.model_view import Model_View
    from firepro3d.scale_manager import ScaleManager
    scene.scale_manager = ScaleManager()
    v = Model_View(scene)
    v.resize(1000, 700)
    v.show()
    QTest.qWaitForWindowExposed(v)
    v.resetTransform()
    v.centerOn(450, 0)
    QApplication.processEvents()
    return v


def _hover(view, scene_pt):
    ev = QMouseEvent(QEvent.Type.MouseMove, QPointF(view.mapFromScene(scene_pt)),
                     Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(view.viewport(), ev)
    QApplication.processEvents()


def _click(view, scene_pt):
    """A real click on the viewport: places (in place_block) and focuses the canvas."""
    _hover(view, scene_pt)
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, QPoint(view.mapFromScene(scene_pt)))
    QApplication.processEvents()


def _key(view, key, mods=Qt.KeyboardModifier.NoModifier, autorepeat=False):
    """Press+release *key* on whatever really has the keyboard, never on a
    widget the test focused by hand -- and never on a fallback: if nothing has
    focus after the real click, the entry path regressed and this goes RED."""
    w = QApplication.focusWidget()
    assert w is not None, "nothing holds keyboard focus after the canvas click"
    for et in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(w, QKeyEvent(et, key, mods, "", autorepeat))
    QApplication.processEvents()


def _ends(scene, inst):
    """Posed endpoint geometry (a set: the L's corner repeats)."""
    return {(round(p.x(), 3), round(p.y(), 3))
            for k, p, _n in scene._snap_engine._collect(inst) if k == "endpoint"}


def _ghost_rect(sc):
    r = None
    for p in sc._move_ghost:
        r = p.boundingRect() if r is None else r.united(p.boundingRect())
    return r


def _close(v, sc):
    sc.set_mode(None)
    v.close()
    v.deleteLater()
    QApplication.processEvents()


def _armed(role="plan"):
    sc = Model_Space(scene_role=role)
    d = _def_L(sc)
    v = _shown(sc)
    sc.set_mode("place_block", template=d.id)
    _click(v, QPointF(0, 0))                 # places one upright; focuses the canvas
    return sc, d, v


UPRIGHT_AT_0 = {(0, 0), (100, 0), (0, -40)}


def _left_right_mirrored_at(x):
    return {(x, 0), (x - 100, 0), (x, -40)}


def test_left_arrow_mirrors_left_right_persists_and_ignores_autorepeat(qapp):
    sc, d, v = _armed()
    try:
        assert _ends(sc, sc._block_instances[0]) == UPRIGHT_AT_0
        _key(v, Qt.Key.Key_Left)
        _click(v, QPointF(300, 0))
        assert _ends(sc, sc._block_instances[1]) == _left_right_mirrored_at(300)
        _click(v, QPointF(600, 0))                               # persists across repeats
        assert _ends(sc, sc._block_instances[2]) == _left_right_mirrored_at(600)
        _key(v, Qt.Key.Key_Left, autorepeat=True)                # held key: no toggle
        _click(v, QPointF(900, 0))
        assert _ends(sc, sc._block_instances[3]) == _left_right_mirrored_at(900)
        _key(v, Qt.Key.Key_Right)                                # each press toggles
        _click(v, QPointF(450, 200))
        assert _ends(sc, sc._block_instances[4]) == {(450, 200), (550, 200), (450, 160)}
        assert len(sc._block_instances) == 5
    finally:
        _close(v, sc)


def test_up_arrow_mirrors_top_bottom_and_mode_entry_resets(qapp):
    sc, d, v = _armed()
    try:
        _key(v, Qt.Key.Key_Up)
        _click(v, QPointF(300, 0))
        inst = sc._block_instances[1]
        assert _ends(sc, inst) == {(300, 0), (400, 0), (300, 40)}
        assert inst.block_mirrored() is True and inst.block_rotation() % 360 == 180
        sc.set_mode("place_block", template=d.id)                # re-enter: un-flipped
        _click(v, QPointF(600, 0))
        assert _ends(sc, sc._block_instances[2]) == {(600, 0), (700, 0), (600, -40)}
    finally:
        _close(v, sc)


def test_flip_axes_are_screen_axes_after_space_rotated_the_block(qapp):
    sc, d, v = _armed()
    try:
        _key(v, Qt.Key.Key_Space)                                # 90 deg CW on screen
        _click(v, QPointF(300, 0))
        rotated = _ends(sc, sc._block_instances[1])
        # Anchor (raw source: the view is not Y-flipped, CW sends +X down).
        assert rotated == {(300, 0), (300, 100), (340, 0)}
        _key(v, Qt.Key.Key_Left)
        _click(v, QPointF(600, 0))
        flipped = _ends(sc, sc._block_instances[2])
        # Screen left-right mirror of the rotated placement, re-based to x=600:
        # reflect across the vertical line through its insertion point.
        assert flipped == {(600 - (x - 300), y) for x, y in rotated}
        assert flipped == {(600, 0), (600, 100), (560, 0)}
    finally:
        _close(v, sc)


def test_a_blocks_browser_drag_keeps_the_armed_flip(qapp):
    sc, d, v = _armed()
    try:
        _key(v, Qt.Key.Key_Left)
        v._begin_block_drag(sc, {"id": d.id, "path": None}, d, None)
        assert sc.mode == "place_block"
        v._end_block_drag(sc)
        assert sc.mode == "place_block" and sc._place_block_id == d.id
        assert sc._place_block_mirrored is True
        _click(v, QPointF(300, 0))
        assert _ends(sc, sc._block_instances[1]) == _left_right_mirrored_at(300)
    finally:
        _close(v, sc)


def test_the_ghost_mirrors_live(qapp):
    sc, d, v = _armed()
    try:
        _hover(v, QPointF(200, 150))
        r0 = _ghost_rect(sc)
        assert (round(r0.left()), round(r0.right()), round(r0.top()), round(r0.bottom())) == (
            200, 300, 110, 150)
        _key(v, Qt.Key.Key_Left)
        r1 = _ghost_rect(sc)
        # Mirror of the un-flipped ghost across the vertical line through the cursor.
        assert (round(r1.left()), round(r1.right())) == (
            round(2 * 200 - r0.right()), round(2 * 200 - r0.left()))
        assert (round(r1.top()), round(r1.bottom())) == (round(r0.top()), round(r0.bottom()))
        _key(v, Qt.Key.Key_Up)
        r2 = _ghost_rect(sc)
        assert (round(r2.left()), round(r2.right()), round(r2.top()), round(r2.bottom())) == (
            100, 200, 150, 190)
    finally:
        _close(v, sc)


def test_the_place_block_status_hint_lists_the_arrows(qapp):
    sc = Model_Space()
    d = _def_L(sc)
    msgs = []
    sc.instructionChanged.connect(msgs.append)
    sc.set_mode("place_block", template=d.id)
    hint = [m for m in msgs if "place block" in m.lower()]
    assert hint, msgs
    assert "←→" in hint[-1] and "↑↓" in hint[-1] and "Space" in hint[-1]
    sc.set_mode(None)


def test_left_arrow_flips_in_the_block_editor_too(qapp):
    from firepro3d.level_manager import LevelManager
    sc = Model_Space(scene_role="block_editor")
    sc._level_manager = LevelManager()
    d = _def_L(sc)
    v = _shown(sc)
    try:
        sc.set_mode("place_block", template=d.id)
        _click(v, QPointF(0, 0))
        assert _ends(sc, sc._block_instances[0]) == UPRIGHT_AT_0
        _key(v, Qt.Key.Key_Left)
        _click(v, QPointF(300, 0))
        assert _ends(sc, sc._block_instances[1]) == _left_right_mirrored_at(300)
    finally:
        _close(v, sc)


@pytest.mark.parametrize("key, expect", [
    (Qt.Key.Key_Left, _left_right_mirrored_at(300)),
    (Qt.Key.Key_Up, {(300, 0), (400, 0), (300, 40)}),
])
def test_a_keypad_arrow_still_flips(qapp, key, expect):
    """Qt sets KeypadModifier on arrow keys on some platforms: it is masked,
    not a chord -- the flip must happen exactly as for a bare arrow."""
    sc, d, v = _armed()
    try:
        _key(v, key, Qt.KeyboardModifier.KeypadModifier)
        _click(v, QPointF(300, 0))
        assert _ends(sc, sc._block_instances[1]) == expect
        assert sc._place_block_mirrored is True
    finally:
        _close(v, sc)


@pytest.mark.parametrize("mods", [Qt.KeyboardModifier.ControlModifier,
                                  Qt.KeyboardModifier.ShiftModifier,
                                  Qt.KeyboardModifier.AltModifier])
def test_a_modified_arrow_is_some_other_chord_not_a_flip(qapp, mods):
    sc, d, v = _armed()
    try:
        _key(v, Qt.Key.Key_Left, mods)
        _key(v, Qt.Key.Key_Up, mods)
        _click(v, QPointF(300, 0))
        assert _ends(sc, sc._block_instances[1]) == {(300, 0), (400, 0), (300, -40)}
        assert sc._place_block_mirrored is False
    finally:
        _close(v, sc)
