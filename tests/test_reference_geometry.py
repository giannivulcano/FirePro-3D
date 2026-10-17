"""Reference geometry on every 2D primitive (design RG1-RG14)."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import (ArcItem, CircleItem, EllipseItem, LineItem,
                                   PolylineItem, RectangleItem,
                                   RegularPolygonItem, SplineItem)
from firepro3d.block_definition import is_scaffold, is_scaffold_item
from firepro3d.colour_tokens import resolve_colour


def _polyline():
    p = PolylineItem(QPointF(0, 0))
    p.append_point(QPointF(100, 0))
    p.append_point(QPointF(100, 50))
    return p


def _shapes():
    return [
        LineItem(QPointF(0, 0), QPointF(100, 0)),
        _polyline(),
        RectangleItem(QPointF(0, 0), QPointF(100, 50)),
        CircleItem(QPointF(0, 0), 50.0),
        ArcItem(QPointF(0, 0), 50.0, 0.0, 90.0),
        RegularPolygonItem(QPointF(0, 0), 6, 50.0),
        EllipseItem(QPointF(0, 0), 60.0, 30.0, 0.0),
        SplineItem([QPointF(0, 0), QPointF(50, 50), QPointF(100, 0)], 2),
    ]


_SHAPE_IDS = ["LineItem", "PolylineItem", "RectangleItem", "CircleItem",
              "ArcItem", "RegularPolygonItem", "EllipseItem", "SplineItem"]


@pytest.mark.parametrize("idx", range(8), ids=_SHAPE_IDS)
def test_flags_default_off_and_round_trip(qapp, idx):
    item = _shapes()[idx]
    assert item.reference is False and item.printed is False
    assert "reference" not in item.to_dict()          # RG2: normal records unchanged
    item.reference, item.printed = True, True
    d = item.to_dict()
    assert d["reference"] is True and d["printed"] is True
    assert d["type"] != "reference_line"
    back = type(item).from_dict(d)
    assert back.reference is True and back.printed is True
    assert back.style is not None                      # style kept (RG4)


def test_legacy_reference_line_record_loads_as_flagged_line(qapp):
    legacy = {"type": "reference_line", "pt1": [0, 0], "pt2": [10, 0],
              "color": "#abcdef", "lineweight": 1.0, "printed": True, "uid": "u1"}
    li = LineItem.from_dict(legacy)
    assert type(li) is LineItem
    assert li.reference is True and li.printed is True and li._uid == "u1"
    out = li.to_dict()
    assert out["type"] == "draw_line" and out["reference"] is True


def test_scaffold_predicate_is_flag_keyed(qapp):
    li = LineItem(QPointF(0, 0), QPointF(10, 0))
    c = CircleItem(QPointF(0, 0), 5.0)
    assert not is_scaffold(c.to_dict()) and not is_scaffold_item(c)
    c.reference = True
    assert is_scaffold(c.to_dict()) and is_scaffold_item(c)
    c.printed = True
    assert not is_scaffold(c.to_dict()) and not is_scaffold_item(c)
    assert is_scaffold({"type": "reference_line", "pt1": [0, 0], "pt2": [1, 0]})
    assert not is_scaffold(li.to_dict())


def test_text_has_no_reference_capability(qapp):
    from firepro3d.text_item import TextItem
    assert TextItem._REFERENCE_CAPABLE is False
    assert LineItem._REFERENCE_CAPABLE is True


# ── Task 2: paint hook, fill gate, compile op (RG4, RG5) ─────────────────────

from PyQt6.QtCore import QRectF, Qt  # noqa: E402
from PyQt6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PyQt6.QtWidgets import QGraphicsScene  # noqa: E402


def _render_item(item, size=160):
    sc = QGraphicsScene()
    sc.addItem(item)
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    sc.render(p, QRectF(0, 0, size, size), QRectF(-80, -80, 160, 160))
    p.end()
    sc.removeItem(item)
    return img


def _lit(img):
    return sum(1 for x in range(img.width()) for y in range(img.height())
               if img.pixelColor(x, y).value() > 40)


def test_reference_circle_paints_hairline_dashed_without_fill(qapp):
    c = CircleItem(QPointF(0, 0), 50.0)
    c.style["weight"] = "Thick"            # paper_display LineWeightDef("Thick", 0.50)
    c.fill_type = "solid"
    normal = _lit(_render_item(c))
    c2 = CircleItem.from_dict(c.to_dict())
    c2.reference = True
    ref = _lit(_render_item(c2))
    # Solid fill + weight lit thousands of px; a dashed hairline ring lights
    # fewer than the ring's circumference (2*pi*50 ~ 314 px).
    assert normal > 2000
    assert 0 < ref < 314
    assert c2.style == c.style                        # record untouched (RG4)
    pen = c2._reference_pen()
    assert pen.style() == Qt.PenStyle.DashLine and pen.isCosmetic() and pen.widthF() == 1.0


def test_paint_never_writes_display_colour_into_saved_data(qapp):
    c = CircleItem(QPointF(0, 0), 50.0, "#123456")
    c.reference = True
    c._display_color = "#888888"
    _render_item(c)
    assert c.to_dict()["style"]["colour"] == "#123456"   # RG5


def test_printed_reference_compiles_unstyled_dashed_op_and_no_fill(qapp):
    from firepro3d.block_definition import BlockDefinition
    c = CircleItem(QPointF(0, 0), 50.0)
    c.fill_type = "solid"
    c.reference, c.printed = True, True
    d = BlockDefinition.new(name="n", library="", series="",
                            primitives=[c.to_dict()], origin=(0.0, 0.0))
    ops = d.render_ops()
    assert len(ops) == 1                                   # no FILL op
    op = ops[0]
    assert op.weight is None and op.linetype is None and op.ends is None
    assert op.pen.style() == Qt.PenStyle.DashLine


# ── Task 3: Display Manager "Reference Geometry", migration, paper (RG12, RG13)

from PyQt6.QtCore import QSettings  # noqa: E402  (conftest-isolated store)


def _bare_scene_with(*items):
    from firepro3d.model_space import Model_Space
    s = Model_Space(scene_role="block_editor")
    for it in items:
        s.addItem(it)
        (s._draw_circles if isinstance(it, CircleItem) else s._draw_lines).append(it)
    return s


@pytest.fixture
def _scratch_display_keys():
    """Remove the display keys these tests write (isolated store, but shared
    across the session)."""
    keys = ("display/_reference_geometry_v1", "display/Reference Lines/color",
            "display/Reference Geometry/color", "display/2D Geometry/color")
    st = QSettings("GV", "FirePro3D")
    before = {k: st.value(k) for k in keys if st.contains(k)}
    yield
    st = QSettings("GV", "FirePro3D")
    for k in keys:
        st.remove(k)
    for k, v in before.items():
        st.setValue(k, v)
    st.sync()


def test_reference_geometry_category_collects_flagged_items_only(qapp):
    from firepro3d import display_manager as dm
    a, b = CircleItem(QPointF(0, 0), 5.0), CircleItem(QPointF(0, 0), 9.0)
    b.reference = True
    s = _bare_scene_with(a, b)
    assert "Reference Geometry" in dm._CATEGORY_MAP and "Reference Lines" not in dm._CATEGORY_MAP
    assert dm._items_for_category_static(s, "Reference Geometry") == [b]
    assert b not in dm._items_for_category_static(s, "2D Geometry")
    assert a in dm._items_for_category_static(s, "2D Geometry")


def test_legacy_reference_lines_settings_migrate(qapp, _scratch_display_keys):
    from firepro3d import display_manager as dm
    st = QSettings("GV", "FirePro3D")
    st.remove("display/_reference_geometry_v1")
    st.setValue("display/Reference Lines/color", "#ff00ff")
    st.remove("display/Reference Geometry/color")
    vals = dm._read_category_from_settings("Reference Geometry", st)
    assert vals["color"] == "#ff00ff"
    assert dm._project_entry({"Reference Lines": {"color": "#00ff00"}},
                             "Reference Geometry") == {"color": "#00ff00"}


def test_refresh_category_display_follows_the_flag(qapp, _scratch_display_keys):
    from firepro3d import display_manager as dm
    st = QSettings("GV", "FirePro3D")
    st.setValue("display/Reference Geometry/color", "#777777")
    st.setValue("display/2D Geometry/color", "#eeeeee")
    c = CircleItem(QPointF(0, 0), 5.0)
    c.reference = True
    dm.refresh_category_display(c)
    assert c._display_color == "#777777"
    c.reference = False
    dm.refresh_category_display(c)
    assert c._display_color == "#eeeeee"


def test_paper_category_for_reference_shape(qapp):
    from firepro3d.paper_display import _category_for_item
    c = CircleItem(QPointF(0, 0), 5.0)
    assert _category_for_item(c) == "Construction"
    c.reference = True
    assert _category_for_item(c) == "Reference Geometry"


# ── Review fix round: linetype readers, hidden-fill hit test, lock (F1-F3) ──

def _lt_editor(*lines, refs=(), length=12.0):
    """A linetype Block Editor (repeat capability) with normal on-axis
    dashes *lines* and on-axis reference lines *refs* ((a, b, printed))."""
    from firepro3d.block_editor import BlockEditorWidget
    from firepro3d.model_space import Model_Space
    proj = Model_Space()
    w = BlockEditorWidget(proj)
    for a, b in lines:
        w._add_primitive(LineItem(QPointF(a, 0), QPointF(b, 0)))
    for a, b, printed in refs:
        rl = LineItem(QPointF(a, 0), QPointF(b, 0))
        rl.reference, rl.printed = True, printed
        w._add_primitive(rl)
    sc = w.editor_scene
    sc.set_block_capability(("repeat", {"length": length, "size": "drafting"}))
    return proj, w, sc


def _reading(w):
    from firepro3d.linetype_pattern import content_end
    from firepro3d.linetype_render import LinetypeDef
    defn = w.editor_scene.capability_frame_item().scratch_definition()
    lt = LinetypeDef.from_block(defn)
    return (lt.dashes, lt.dots, lt.period), content_end(defn.primitives)


@pytest.mark.parametrize("printed", [False, True])
def test_reference_line_is_never_a_linetype_mark(qapp, printed):
    from firepro3d import linetype_authoring as la
    _, w0, sc0 = _lt_editor((0, 6))
    _, w1, sc1 = _lt_editor((0, 6), refs=[(0, 11, printed), (7, 7, printed)])
    assert _reading(w1) == _reading(w0)                 # dashes, dots, content end
    ref_lines = [l for l in sc1._draw_lines if l.reference]
    assert len(ref_lines) == 2
    assert not set(ref_lines) & set(la._plain_lines(sc1))
    assert [l for l, _ in la.axis_items(sc1)] == [l for l in sc1._draw_lines
                                                  if not l.reference]
    assert la.current_rows(sc1) == la.current_rows(sc0)


def test_hidden_fill_is_not_clickable_or_a_halo_area(qapp):
    from firepro3d.halo import halo_is_area
    from firepro3d.model_space import Model_Space
    s = Model_Space(scene_role="block_editor")
    normal, ref = CircleItem(QPointF(0, 0), 50.0), CircleItem(QPointF(300, 0), 50.0)
    for c in (normal, ref):
        c.fill_type = "solid"
        s.addItem(c); s._draw_circles.append(c)
    ref.reference = True
    assert normal.shape().contains(QPointF(0, 0)) and halo_is_area(normal)
    assert not ref.shape().contains(QPointF(300, 0))
    assert not halo_is_area(ref)


def test_content_lock_never_rewrites_a_reference_style(qapp):
    from firepro3d import stroke_style as ss
    from tests.lt3_support import hidden
    proj, w, sc = _lt_editor((0, 6))
    lt_id = hidden(proj)
    rl = LineItem(QPointF(0, 5), QPointF(4, 5))
    rl.reference = True
    rl.style["linetype"] = lt_id
    w._add_primitive(rl)
    before = dict(rl.style)
    sc.push_undo_state()                    # pre_capture applies the lock
    live = next(l for l in sc._draw_lines if l.reference)
    assert live.style["linetype"] == lt_id != ss.CONTINUOUS
    assert live.style == before


# -- Task 5: placement (RG6-RG9) --------------------------------------------

from PyQt6.QtCore import QEvent  # noqa: E402
from PyQt6.QtGui import QKeyEvent, QMouseEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

# mode -> (clicks in scene mm, finish key or None, list attr).  Real gestures
# (geometry_drawing_controller): line 2 clicks; circle centre -> rim;
# rectangle base -> side -> depth; arc (Center variant) centre -> start ->
# end; polygon centre -> radius -> rotation; ellipse centre -> major ->
# minor; polyline / spline N clicks + Enter.
_TOOLS = {
    "draw_line":      ([(0, 0), (600, 0)], None, "_draw_lines"),
    "draw_circle":    ([(0, 0), (300, 0)], None, "_draw_circles"),
    "draw_rectangle": ([(0, 0), (600, 0), (600, 300)], None, "_draw_rects"),
    "draw_arc":       ([(0, 0), (300, 0), (0, 300)], None, "_draw_arcs"),
    "polygon":        ([(0, 0), (300, 0), (300, 0)], None, "_draw_polygons"),
    "draw_ellipse":   ([(0, 0), (300, 0), (0, 150)], None, "_draw_ellipses"),
    "polyline":       ([(0, 0), (300, 0), (300, 300)], Qt.Key.Key_Return, "_polylines"),
    "draw_spline":    ([(0, 0), (300, 300), (600, 0)], Qt.Key.Key_Return, "_draw_splines"),
}


def _click(view, x, y):
    vp = view.mapFromScene(QPointF(x, y))
    gp = view.viewport().mapToGlobal(vp)
    for et in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress,
               QEvent.Type.MouseButtonRelease):
        btn = (Qt.MouseButton.NoButton if et == QEvent.Type.MouseMove
               else Qt.MouseButton.LeftButton)
        QApplication.sendEvent(view.viewport(), QMouseEvent(
            et, QPointF(vp), QPointF(gp), btn, btn,
            Qt.KeyboardModifier.NoModifier))
    QApplication.processEvents()


def _key(view, key, mods=Qt.KeyboardModifier.NoModifier):
    text = " " if key == Qt.Key.Key_Space else ""
    for et in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(view, QKeyEvent(et, key, mods, text))
    QApplication.processEvents()


@pytest.mark.parametrize("mode", list(_TOOLS))
def test_space_places_reference_then_resets(shown_model_view, mode):
    view, scene = shown_model_view
    scene.scene_role = "block_editor"
    clicks, finish, attr = _TOOLS[mode]
    for want_ref in (True, False):
        before = len(getattr(scene, attr))
        scene.set_mode(mode)
        if want_ref:
            _key(view, Qt.Key.Key_Space)
            assert scene._place_reference is True
        for x, y in clicks:
            _click(view, x, y)
        if finish is not None:
            _key(view, finish)
        assert len(getattr(scene, attr)) == before + 1, mode
        placed = getattr(scene, attr)[-1]
        assert placed.reference is want_ref, mode
        assert scene._place_reference is False         # reset per placement


def test_shift_space_flips_arc_and_space_toggles_reference_at_span_step(
        shown_model_view):
    view, scene = shown_model_view
    scene.scene_role = "block_editor"
    scene.set_mode("draw_arc")
    _click(view, 0, 0); _click(view, 300, 0)
    assert scene._draw_arc_step == 2
    _key(view, Qt.Key.Key_Space, Qt.KeyboardModifier.ShiftModifier)
    assert scene._draw_arc_cw is True and scene._place_reference is False
    _key(view, Qt.Key.Key_Space)
    assert scene._place_reference is True and scene._draw_arc_cw is True
    _click(view, 0, 300)
    arc = scene._draw_arcs[-1]
    assert arc.reference is True
    # Start bearing 0 swept CW to scene (0, 300) (bearing -90, Y-up) is the
    # 90-degree arc through the lower-right quadrant (scene +x, +y); the
    # unflipped CCW arc would be the 270-degree one through the upper-left.
    mid = arc.arc_midpoint()
    assert mid.x() > 0 and mid.y() > 0


def test_shift_space_elsewhere_in_draw_modes_does_nothing(qapp):
    from firepro3d.model_space import Model_Space
    s = Model_Space(scene_role="block_editor")
    for mode in ("draw_line", "draw_circle", "draw_arc"):
        s.set_mode(mode)
        assert s.cycle_placement_ambiguity(reverse=True) is False
        assert s._place_reference is False


def test_text_tool_space_does_nothing(qapp):
    from firepro3d.model_space import Model_Space
    s = Model_Space(scene_role="block_editor")
    s.set_mode("text")
    assert s.cycle_placement_ambiguity() is False
    assert s._place_reference is False


def test_line_tool_has_no_reference_variant(qapp):
    from firepro3d.model_space import Model_Space
    s = Model_Space(scene_role="block_editor")
    assert "draw_line" not in s._plc._PLACEMENT_VARIANTS
    s.set_mode("draw_line")
    assert s.cycle_placement_variant(+1) is False


class _NoMods:
    def modifiers(self):
        return Qt.KeyboardModifier.NoModifier


def test_reference_toggle_recolours_the_live_ghost(qapp):
    from firepro3d.model_space import Model_Space
    s = Model_Space(scene_role="block_editor")
    s.set_mode("draw_circle")
    s._press_draw_circle(_NoMods(), None, QPointF(0, 0), None, None, None)
    ghost = s._draw_circle_preview
    before = ghost.pen().color().name()
    assert s.cycle_placement_ambiguity() is True
    assert ghost.pen().color().name() != before
    assert s.cycle_placement_ambiguity() is True      # toggles back
    assert ghost.pen().color().name() == before


def test_reference_toggle_appends_instruction_suffix(qapp):
    from firepro3d.model_space import Model_Space
    s = Model_Space(scene_role="block_editor")
    msgs: list[str] = []
    s.instructionDisplay.connect(msgs.append)
    s.set_mode("draw_circle")
    base = msgs[-1]
    s.cycle_placement_ambiguity()
    assert msgs[-1] == base + " (Reference)"
    s.cycle_placement_ambiguity()
    assert msgs[-1] == base


def test_space_in_focused_hud_field_does_not_toggle_reference(qapp):
    from PyQt6.QtTest import QTest
    from firepro3d.model_space import Model_Space
    from firepro3d.model_view import Model_View
    s = Model_Space(scene_role="block_editor")
    v = Model_View(s); v.resize(800, 600); v.resetTransform()
    v.centerOn(0, 0); v.show()
    QTest.qWaitForWindowExposed(v)
    try:
        s.set_mode("draw_line")
        s._draw_line_anchor = QPointF(0, 0)
        s.publish_placement_state(QPointF(0, 0), QPointF(1000, 0))
        assert s.begin_dynamic_input(seed="1") is True
        assert s.is_input_mode() is True
        s.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space,
                                  Qt.KeyboardModifier.NoModifier, " "))
        assert s._place_reference is False           # Space typed, no toggle
        assert s.is_input_mode() is True
    finally:
        s.end_dynamic_input()
        v.close()


def test_placed_reference_circle_survives_undo_redo(shown_model_view):
    from PyQt6.QtCore import Qt as _Qt
    view, scene = shown_model_view
    scene.scene_role = "block_editor"
    scene.set_mode("draw_circle")
    _key(view, Qt.Key.Key_Space)
    _click(view, 0, 0); _click(view, 300, 0)
    assert len(scene._draw_circles) == 1 and scene._draw_circles[0].reference
    scene.undo()
    assert [c for c in scene._draw_circles if c.scene() is scene] == []
    scene.redo()
    live = [c for c in scene._draw_circles if c.scene() is scene]
    assert len(live) == 1
    circle = live[0]
    assert circle.reference is True
    view.viewport().grab()                  # a real paint pass
    QApplication.processEvents()
    assert circle.pen().style() == _Qt.PenStyle.DashLine


def _move(view, x, y):
    vp = view.mapFromScene(QPointF(x, y))
    gp = view.viewport().mapToGlobal(vp)
    QApplication.sendEvent(view.viewport(), QMouseEvent(
        QEvent.Type.MouseMove, QPointF(vp), QPointF(gp),
        Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier))
    QApplication.processEvents()


# mode -> (clicks that arm the ghost, ghost getters on the scene)
_GHOSTS = {
    "draw_line":      ([(0, 0)], [lambda s: s.preview_pipe]),
    "draw_circle":    ([(0, 0)], [lambda s: s._draw_circle_preview]),
    "draw_rectangle": ([(0, 0)], [lambda s: s._draw_rect_preview]),
    "draw_arc":       ([(0, 0)], [lambda s: s._draw_arc_radius_line]),
    "draw_arc_span":  ([(0, 0), (300, 0)], [lambda s: s._draw_arc_preview]),
    "polygon":        ([(0, 0)], [lambda s: s._polygon_preview]),
    "draw_ellipse":   ([(0, 0), (300, 0)], [lambda s: s._ellipse_preview]),
    "polyline":       ([(0, 0)], [lambda s: s._polyline_active]),
    "draw_spline":    ([(0, 0), (300, 300)], [lambda s: s._spline_preview,
                                              lambda s: s._spline_ref_poly]),
}


@pytest.mark.parametrize("case", list(_GHOSTS))
def test_space_recolours_each_tools_ghost(shown_model_view, case):
    from firepro3d.display_manager import _read_category_from_settings
    view, scene = shown_model_view
    scene.scene_role = "block_editor"
    ref = QColor(_read_category_from_settings("Reference Geometry")["color"]).name()
    geo = resolve_colour(scene._geom_color_lw()[0]).name()
    assert ref != geo
    clicks, getters = _GHOSTS[case]
    scene.set_mode("draw_arc" if case == "draw_arc_span" else case)
    for x, y in clicks:
        _click(view, x, y)
    _move(view, 150, 220)
    for get in getters:
        assert get(scene) is not None, case
        assert get(scene).pen().color().name() == geo, case
    _key(view, Qt.Key.Key_Space)
    for get in getters:                   # F5: recoloured at once, no move
        assert get(scene).pen().color().name() == ref, case
    _move(view, 160, 230)                 # a move re-pens / rebuilds ghosts
    for get in getters:
        assert get(scene).pen().color().name() == ref, case
    _key(view, Qt.Key.Key_Space)
    for get in getters:
        assert get(scene).pen().color().name() == geo, case
    _move(view, 150, 220)
    for get in getters:
        assert get(scene).pen().color().name() == geo, case


def test_mid_chain_toggle_and_two_vertex_finish_commit_a_reference_line(
        shown_model_view):
    view, scene = shown_model_view
    scene.scene_role = "block_editor"
    lines_before = len(scene._draw_lines)
    scene.set_mode("polyline")
    _click(view, 0, 0); _click(view, 300, 0)
    _key(view, Qt.Key.Key_Space)                    # mid-chain: chain takes it
    assert scene._polyline_active.reference is True
    _key(view, Qt.Key.Key_Return)
    assert len(scene._draw_lines) == lines_before + 1
    line = scene._draw_lines[-1]
    assert isinstance(line, LineItem) and line.reference is True
    assert scene._place_reference is False


# -- B6 fix round: F1 (re-entering the tool keeps the reference state) --------

def _reenter(scene, mode):
    """What the ribbon / shortcut does when the active tool is pressed again."""
    scene.set_mode(mode)


def test_reentering_polyline_keeps_the_chain_reference(shown_model_view):
    view, scene = shown_model_view
    scene.scene_role = "block_editor"
    scene.set_mode("polyline")
    _click(view, 0, 0); _click(view, 300, 0)
    _key(view, Qt.Key.Key_Space)
    _reenter(scene, "polyline")
    assert scene._place_reference is True
    _click(view, 300, 300)
    _key(view, Qt.Key.Key_Return)
    pl = scene._polylines[-1]
    assert isinstance(pl, PolylineItem) and pl.reference is True


def test_reentering_polyline_two_vertices_commits_a_reference_line(
        shown_model_view):
    view, scene = shown_model_view
    scene.scene_role = "block_editor"
    n = len(scene._draw_lines)
    scene.set_mode("polyline")
    _click(view, 0, 0); _click(view, 300, 0)
    _key(view, Qt.Key.Key_Space)
    _reenter(scene, "polyline")
    _key(view, Qt.Key.Key_Return)
    assert len(scene._draw_lines) == n + 1
    line = scene._draw_lines[-1]
    assert isinstance(line, LineItem) and line.reference is True


def test_reentering_draw_line_keeps_reference_state_and_ghost(
        shown_model_view):
    view, scene = shown_model_view
    scene.scene_role = "block_editor"
    msgs: list[str] = []
    scene.instructionDisplay.connect(msgs.append)
    scene.set_mode("draw_line")
    _click(view, 0, 0)
    _key(view, Qt.Key.Key_Space)
    _reenter(scene, "draw_line")
    assert scene._place_reference is True
    _click(view, 300, 0)
    line = scene._draw_lines[-1]
    assert isinstance(line, LineItem) and line.reference is True


# -- F2: the " (Reference)" cue is tied to the state, not one prompt ----------

def test_reference_suffix_survives_the_next_prompt(shown_model_view):
    view, scene = shown_model_view
    scene.scene_role = "block_editor"
    msgs: list[str] = []
    scene.instructionDisplay.connect(msgs.append)
    scene.set_mode("draw_circle")
    assert not msgs[-1].endswith(" (Reference)")
    _key(view, Qt.Key.Key_Space)
    assert msgs[-1].endswith(" (Reference)")
    _click(view, 0, 0)                       # next prompt (radius)
    assert msgs[-1].endswith(" (Reference)")
    _key(view, Qt.Key.Key_Space)             # off
    assert not msgs[-1].endswith(" (Reference)")
    _click(view, 300, 0)                     # commit; mode resets
    assert not any(m.endswith(" (Reference)") for m in msgs[-1:])


def test_non_reference_mode_never_gets_the_suffix(qapp):
    from firepro3d.model_space import Model_Space
    s = Model_Space(scene_role="block_editor")
    msgs: list[str] = []
    s.instructionDisplay.connect(msgs.append)
    s._place_reference = True            # stale flag must not decorate
    s.set_mode("select")
    s.instructionChanged.emit("Pick something")
    assert msgs[-1] == "Pick something"


# -- F3 / F4 ------------------------------------------------------------------

def test_ghost_colour_does_not_hit_qsettings_per_call(shown_model_view,
                                                       monkeypatch):
    view, scene = shown_model_view
    scene.scene_role = "block_editor"
    scene.set_mode("draw_line")
    _key(view, Qt.Key.Key_Space)
    import firepro3d.display_manager as dm
    calls = []
    real = dm._read_category_from_settings
    monkeypatch.setattr(dm, "_read_category_from_settings",
                        lambda *a, **k: calls.append(a) or real(*a, **k))
    for _ in range(5):
        scene._geom_ctl._ghost_colour()
    assert calls == []


def test_clear_prunes_removed_ghosts(shown_model_view):
    view, scene = shown_model_view
    scene.scene_role = "block_editor"
    scene.set_mode("draw_circle")
    _click(view, 0, 0)
    assert scene._draw_circle_preview in scene._geom_ctl._ghosts
    scene.set_mode("select")
    assert scene._geom_ctl._ghosts == []


def test_toggle_recolours_the_line_rubber_band_at_once(shown_model_view):
    """F5: ``preview_pipe`` is re-penned per move and never tracked, so the
    immediate recolour on toggle is the ``recolour_ghosts`` draw_line branch
    alone (no mouse move in between)."""
    from firepro3d.display_manager import _read_category_from_settings
    view, scene = shown_model_view
    scene.scene_role = "block_editor"
    ref = QColor(_read_category_from_settings("Reference Geometry")["color"]).name()
    geo = resolve_colour(scene._geom_color_lw()[0]).name()
    scene.set_mode("draw_line")
    _click(view, 0, 0)
    _move(view, 150, 220)
    assert scene.preview_pipe.pen().color().name() == geo
    assert scene.cycle_placement_ambiguity() is True
    assert scene.preview_pipe.pen().color().name() == ref
    assert scene.cycle_placement_ambiguity() is True
    assert scene.preview_pipe.pen().color().name() == geo
