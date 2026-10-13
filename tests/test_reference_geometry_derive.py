"""Derive paths carry the reference / printed flags (design RG14).

Each guard drives the real ``SceneTools`` method on a real ``Model_Space``
(block-editor role) and asserts the produced items' flags.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import (ArcItem, CircleItem, LineItem,
                                   PolylineItem, RectangleItem)


@pytest.fixture
def editor_scene(shown_model_view):
    _view, scene = shown_model_view
    scene.scene_role = "block_editor"
    return scene


def _flag(item, ref, printed):
    item.reference, item.printed = ref, printed
    return item


def _add_line(scene, ln):
    scene.addItem(ln)
    scene._draw_lines.append(ln)
    return ln


def _lines(scene):
    return [l for l in scene._draw_lines if l.scene() is scene]


@pytest.mark.parametrize("ref,printed", [(True, True), (True, False)])
def test_break_at_point_on_reference_line_yields_reference_pieces(
        editor_scene, ref, printed):
    scene = editor_scene
    li = _add_line(scene, _flag(LineItem(QPointF(0, 0), QPointF(600, 0)),
                                ref, printed))
    scene._tools._break_at_point(li, QPointF(300, 0))
    pieces = _lines(scene)
    assert len(pieces) == 2 and li not in scene._draw_lines
    assert all(p.reference is ref and p.printed is printed for p in pieces)


def test_break_between_points_on_reference_line(editor_scene):
    scene = editor_scene
    li = _add_line(scene, _flag(LineItem(QPointF(0, 0), QPointF(600, 0)),
                                True, True))
    scene._tools._break_item(li, QPointF(200, 0), QPointF(400, 0))
    pieces = _lines(scene)
    assert len(pieces) == 2
    assert all(p.reference and p.printed for p in pieces)


def test_break_on_reference_circle_yields_reference_arc(editor_scene):
    scene = editor_scene
    c = _flag(CircleItem(QPointF(0, 0), 50.0), True, True)
    scene.addItem(c)
    scene._draw_circles.append(c)
    scene._tools._break_item(c, QPointF(50, 0), QPointF(0, 50))
    arcs = [a for a in scene._draw_arcs if a.scene() is scene]
    assert len(arcs) == 1 and c not in scene._draw_circles
    assert arcs[0].reference is True and arcs[0].printed is True


def test_explode_reference_rectangle_yields_reference_lines(editor_scene):
    scene = editor_scene
    r = _flag(RectangleItem(QPointF(0, 0), QPointF(100, 50)), True, True)
    scene.addItem(r)
    scene._draw_rects.append(r)
    r.setSelected(True)
    scene._tools.explode_selected_items()
    lines = _lines(scene)
    assert len(lines) == 4
    assert all(l.reference and l.printed for l in lines)


def test_explode_reference_closed_polyline_yields_reference_lines(
        editor_scene):
    scene = editor_scene
    pl = PolylineItem(QPointF(0, 0))
    for p in (QPointF(100, 0), QPointF(100, 50), QPointF(0, 50)):
        pl.append_point(p)
    pl.close()
    _flag(pl, True, False)
    scene.addItem(pl)
    scene._polylines.append(pl)
    pl.setSelected(True)
    scene._tools.explode_selected_items()
    lines = _lines(scene)
    assert lines and len(lines) >= len(pl._points) - 1
    assert all(l.reference is True and l.printed is False for l in lines)


def test_join_two_reference_lines_yields_reference_polyline(editor_scene):
    scene = editor_scene
    a = _add_line(scene, _flag(LineItem(QPointF(0, 0), QPointF(100, 0)),
                               True, True))
    b = _add_line(scene, _flag(LineItem(QPointF(100, 0), QPointF(100, 80)),
                               True, True))
    a.setSelected(True)
    b.setSelected(True)
    scene._tools.join_selected_items()
    assert len(scene._polylines) == 1
    pl = scene._polylines[0]
    assert pl.reference is True and pl.printed is True


def test_normal_sources_yield_normal_pieces(editor_scene):
    scene = editor_scene
    li = _add_line(scene, LineItem(QPointF(0, 0), QPointF(600, 0)))
    scene._tools._break_at_point(li, QPointF(300, 0))
    pieces = _lines(scene)
    assert len(pieces) == 2
    assert all(p.reference is False and p.printed is False for p in pieces)
    c = CircleItem(QPointF(0, 0), 50.0)
    scene.addItem(c)
    scene._draw_circles.append(c)
    scene._tools._break_item(c, QPointF(50, 0), QPointF(0, 50))
    arc = [a for a in scene._draw_arcs if a.scene() is scene][0]
    assert arc.reference is False and arc.printed is False


@pytest.mark.parametrize("flags,expect", [
    # (reference, printed) per joined line -> (reference, printed) of the result
    ([(True, True), (False, False)], (False, False)),     # reference first
    ([(False, False), (True, True)], (False, False)),     # normal first
    ([(True, False), (True, False)], (True, False)),      # all reference
    ([(True, True), (True, True)], (True, True)),         # all printed reference
    ([(True, True), (True, False)], (True, False)),       # one not printed
])
@pytest.mark.parametrize("reverse", [False, True])
def test_join_flags_follow_every_joined_item(editor_scene, monkeypatch, flags,
                                             expect, reverse):
    """REWRITTEN from the mixed-join characterisation (RG16): the joined
    polyline is reference only if every input is, printed only if every
    input is printed; selection order no longer decides."""
    scene = editor_scene
    pts = [(0, 0), (100, 0), (100, 80)]
    lines = [_add_line(scene, _flag(LineItem(QPointF(*p), QPointF(*q)), ref, pr))
             for (ref, pr), (p, q) in zip(flags, zip(pts, pts[1:]))]
    for ln in lines:
        ln.setSelected(True)
    order = lines[::-1] if reverse else lines       # which input is items[0]
    monkeypatch.setattr(scene, "selectedItems", lambda: list(order))
    scene._tools.join_selected_items()
    assert len(scene._polylines) == 1
    pl = scene._polylines[0]
    assert (pl.reference, pl.printed) == expect


@pytest.fixture
def _scratch_display_keys():
    from PyQt6.QtCore import QSettings
    keys = ("display/Reference Geometry/color", "display/2D Geometry/color")
    st = QSettings("GV", "FirePro3D")
    before = {k: st.value(k) for k in keys if st.contains(k)}
    yield
    st = QSettings("GV", "FirePro3D")
    for k in keys:
        st.remove(k)
    for k, v in before.items():
        st.setValue(k, v)
    st.sync()


@pytest.mark.parametrize("second_ref, want_ref, want_colour", [
    (False, False, "#00ff00"),      # reference first + normal: no leak (RG16)
    (True, True, "#ff0000"),        # all reference: the reference colour
])
def test_join_with_a_normal_input_leaves_no_reference_colour(
        editor_scene, _scratch_display_keys, monkeypatch, second_ref,
        want_ref, want_colour):
    from PyQt6.QtCore import QSettings
    st = QSettings("GV", "FirePro3D")
    st.setValue("display/Reference Geometry/color", "#ff0000")
    st.setValue("display/2D Geometry/color", "#00ff00")
    scene = editor_scene
    a = _add_line(scene, _flag(LineItem(QPointF(0, 0), QPointF(100, 0)),
                               True, False))
    b = _add_line(scene, _flag(LineItem(QPointF(100, 0), QPointF(100, 80)),
                               second_ref, False))
    a.setSelected(True); b.setSelected(True)
    # Pin items[0] = the reference line: copy_style then paints the reference
    # colour onto the result, which RG16 must undo for a normal join.
    monkeypatch.setattr(scene, "selectedItems", lambda: [a, b])
    scene._tools.join_selected_items()
    pl = scene._polylines[0]
    assert pl.reference is want_ref
    assert pl._display_color == want_colour


# -- seam fix round S4 (AC11): Offset and Mirror copies carry the flags -------

def _offset_copy(name, printed):
    from tests._modify_tools_helpers import add_primitive
    from tests._snap_polish_helpers import close_view, make_view, move
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, name)
        item.reference, item.printed = True, printed
        scene._modify_ctl.start("offset")
        move(view, QPointF(400, -400))
        assert scene.begin_dynamic_input() is True
        scene.dynamic_input.editor("Distance").setText("5")
        scene.dynamic_input._accept()
        lst = getattr(scene, attr)
        assert len(lst) == 2
        new = lst[-1]
        assert new is not item
        return new.reference, new.printed, new._display_color
    finally:
        close_view(view, scene)


def _mirror_copy(name, printed):
    from tests._modify_tools_helpers import add_primitive
    from tests._snap_polish_helpers import close_view
    from tests.test_modify_tools_flip_mirror import (_axis_line,
                                                     _hover_and_click, _own,
                                                     make_view)
    view, scene = make_view(scale=1.0)
    try:
        axis_d = _axis_line(scene)
        item, attr = add_primitive(scene, name)
        item.reference, item.printed = True, printed
        scene._modify_ctl.start("mirror")
        _hover_and_click(view)
        lst = _own(scene, attr, axis_d)
        assert len(lst) == 2
        new = next(it for it in lst if it is not item)
        return new.reference, new.printed, new._display_color
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("derive", [_offset_copy, _mirror_copy],
                         ids=["offset", "mirror"])
@pytest.mark.parametrize("name", ["line", "circle"])
@pytest.mark.parametrize("printed", [False, True])
def test_offset_and_mirror_copies_carry_the_reference_flags(
        qapp, _scratch_display_keys, derive, name, printed):
    from PyQt6.QtCore import QSettings
    st = QSettings("GV", "FirePro3D")
    st.setValue("display/Reference Geometry/color", "#ff0000")
    st.setValue("display/2D Geometry/color", "#00ff00")
    ref, pr, colour = derive(name, printed)
    assert ref is True and pr is printed
    assert colour == "#ff0000"                       # Reference Geometry colour
