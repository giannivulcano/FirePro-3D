"""DV3 / D15: scene_tools constructs its Qt overlays without NameError, and the
dead numeric-input dialog channel is gone (the Dynamic Input HUD is the one
numeric channel); HUD-less tools never promise a "Tab = …" entry."""
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsRectItem

from firepro3d.geometry_2d import LineItem, RectangleItem
from tests._snap_polish_helpers import click, close_view, make_view


def _add_line(scene, p1, p2):
    ln = LineItem(QPointF(*p1), QPointF(*p2))
    scene.addItem(ln)
    scene._draw_lines.append(ln)
    return ln


def test_highlight_of_an_unrotated_rect_builds_a_rect_overlay(qapp):
    """DV3: the rect branch of _highlight_item constructs QGraphicsRectItem."""
    view, scene = make_view(scale=1.0)
    try:
        r = RectangleItem(QPointF(0, 0), QPointF(100, -50))
        scene.addItem(r); scene._draw_rects.append(r)
        h = scene._tools._highlight_item(r)                    # [RED] NameError
        assert isinstance(h, QGraphicsRectItem)
        assert h.scene() is scene
        assert h.rect() == r.rect()
    finally:
        close_view(view, scene)


def test_merge_first_click_places_the_ellipse_marker(qapp):
    """DV3: Merge's first endpoint click builds its QGraphicsEllipseItem."""
    view, scene = make_view(scale=1.0)
    try:
        _add_line(scene, (0, 0), (100, 0))
        scene.set_mode("merge_points")
        # The press handler's own call (``_press_merge_hatch`` forwards the
        # snapped point); called directly so a NameError fails this test
        # cleanly instead of aborting the process from inside a Qt virtual.
        scene._press_merge_hatch(None, QPointF(0, 0), QPointF(0, 0),
                                 None, None, None)            # [RED] NameError
        marker = scene._merge_preview
        assert isinstance(marker, QGraphicsEllipseItem)
        assert marker.scene() is scene
        assert (round(marker.pos().x(), 3), round(marker.pos().y(), 3)) == (0.0, 0.0)
    finally:
        close_view(view, scene)


def test_numeric_input_channel_removed():
    from firepro3d.model_space import Model_Space
    assert not hasattr(Model_Space, "complete_numeric_input")   # [RED]
    assert not hasattr(Model_Space, "numericInputRequested")


def test_no_false_tab_hints_for_hudless_tools(qapp):
    """D15: a tool without a Dynamic Input schema must not promise 'Tab = …'."""
    from firepro3d.model_space import Model_Space
    scene = Model_Space()
    try:
        seen = []
        scene.instructionChanged.connect(seen.append)
        for mode in ("scale", "fillet", "chamfer", "mirror", "break",
                     "break_at_point", "stretch", "trim", "extend"):
            if mode in scene._SCHEMA_FOR_MODE or mode in scene._APPLIER_FOR_MODE:
                continue
            seen.clear()
            scene.set_mode(mode)
            assert seen, mode
            assert all("Tab" not in s for s in seen), (mode, seen)   # [RED]
    finally:
        scene.cleanup()


def _drive_two_line_pick(mode):
    """Pick two real, non-parallel lines in *mode*; return every instruction
    emitted by the two picks."""
    view, scene = make_view(scale=1.0)
    try:
        _add_line(scene, (0, 0), (200, 0))
        _add_line(scene, (300, -100), (300, -300))
        scene.set_mode(mode)
        seen = []
        scene.instructionChanged.connect(seen.append)
        click(view, QPointF(100, 0))                    # first line
        first = list(seen)
        click(view, QPointF(300, -200))                 # second line
        return first, seen[len(first):]
    finally:
        close_view(view, scene)


def test_fillet_mid_flow_hints_do_not_promise_tab(qapp):
    first, second = _drive_two_line_pick("fillet")
    assert first == ["Click second line"]                          # [RED]
    assert second and second[-1].startswith("Radius:")
    assert all("Tab" not in s for s in first + second), first + second


def test_chamfer_mid_flow_hints_do_not_promise_tab(qapp):
    first, second = _drive_two_line_pick("chamfer")
    assert first == ["Click second line"]                          # [RED]
    assert second and second[-1].startswith("Distance:")
    assert all("Tab" not in s for s in first + second), first + second
