"""S6 guard — TextItem emits 9 box snap points; blocks emit text box points, not glyph vertices."""
import math

from PyQt6.QtCore import QPointF, Qt

from tests._snap_polish_helpers import click, close_view, make_view


def _place_text(scene, a, b, text="HELLO", view=None):
    """Place via the real two-click text path (posted presses in "text" mode,
    recipe from tests/test_text_two_click_placement.py) in a block_editor scene."""
    scene.set_mode("text")
    click(view, a)          # anchor
    click(view, b)          # opposite corner
    t = scene._texts[-1]
    # Content recipe from the Phase-1b probe (probe_s6.py).
    t.setPlainText(text)
    t.data.text = text
    t._apply_format()
    scene.set_mode("select")
    return t


def test_text_corner_snaps_as_endpoint(qapp):
    view, scene = make_view(mode="select")
    try:
        t = _place_text(scene, QPointF(1000, 1000), QPointF(1500, 1200), view=view)
        eng = scene._snap_engine
        kinds = sorted(k for k, _p, _n in eng._collect(t))
        assert kinds == sorted(["endpoint"] * 4 + ["midpoint"] * 4 + ["center"])
        g = t.grip_points()
        r = eng.find(QPointF(g[4].x() + 4, g[4].y() + 4), scene, view.transform())
        assert r is not None and r.snap_type == "endpoint"
        assert math.hypot(r.point.x() - g[4].x(), r.point.y() - g[4].y()) < 0.01
    finally:
        close_view(view, scene)


def test_rotated_text_corner_is_independently_rotated(qapp):
    view, scene = make_view(mode="select")
    try:
        t = _place_text(scene, QPointF(1000, 1000), QPointF(1500, 1200), view=view)
        # Real setter: TextItem.set_angle (Y-up CCW+ degrees; pivot = box centre).
        box = t._box_rect_local()
        c = t.mapToScene(box.center())       # centre is rotation-invariant
        tl0 = QPointF(t.pos())               # unrotated TL == pos (local 0,0)
        t.set_angle(30.0)
        # Expected TL computed independently: flip to Y-up, rotate CCW by +30°
        # about the centre, flip back (scene is Qt Y-down).
        a = math.radians(30.0)
        dx, dy_up = tl0.x() - c.x(), -(tl0.y() - c.y())
        rx = dx * math.cos(a) - dy_up * math.sin(a)
        ry_up = dx * math.sin(a) + dy_up * math.cos(a)
        exp = QPointF(c.x() + rx, c.y() - ry_up)
        # Sanity: the rotation actually moved the corner.
        assert math.hypot(exp.x() - tl0.x(), exp.y() - tl0.y()) > 1.0
        pts = [p for k, p, _n in scene._snap_engine._collect(t) if k == "endpoint"]
        assert any(math.hypot(p.x() - exp.x(), p.y() - exp.y()) < 0.01 for p in pts)
        # And the real find() lands on it.
        r = scene._snap_engine.find(QPointF(exp.x() + 4, exp.y() + 4), scene,
                                    view.transform())
        assert r is not None and r.snap_type == "endpoint"
        assert math.hypot(r.point.x() - exp.x(), r.point.y() - exp.y()) < 0.01
    finally:
        close_view(view, scene)


def test_block_with_text_emits_box_points_not_glyph_vertices(qapp):
    # Recipe from tests/test_block_text_compile.py (text prim via
    # TextItem(...).to_dict()) + tests/test_block_s2_fixes.py (line prim,
    # register_block_definition + place_block_instance).
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.text_item import TextAnnotationData, TextItem

    view, scene = make_view(role="plan", mode="select")
    try:
        text_prim = TextItem(TextAnnotationData(
            text="HELLO WORLD", x=200.0, y=300.0, height_mm=100.0)).to_dict()
        line_prim = {"type": "draw_line", "pt1": [0, -50], "pt2": [1000, -50],
                     "color": "#ffffff", "lineweight": 1.0}
        d = BlockDefinition.new(name="T", library="L", series="S",
                                primitives=[line_prim, text_prim], origin=(0.0, 0.0))
        scene.register_block_definition(d)
        inst = scene.place_block_instance(d.id, (1000.0, 0.0), rotation=0.0)
        eng = scene._snap_engine
        eng.snap_endpoint = eng.snap_midpoint = eng.snap_center = True
        # The block really carries a filled glyph op (else the guard is vacuous).
        assert any(pen.style() == Qt.PenStyle.NoPen and path.elementCount() > 0
                   for pen, _b, path in inst.render_ops())
        coll = eng._collect(inst)
        kinds = [k for k, _p, _n in coll]
        assert kinds.count("endpoint") == 2 + 4        # line ends + text corners, 0 glyph vertices
        assert kinds.count("midpoint") == 4
        assert kinds.count("center") == 1 + 1          # insertion origin + text centre
        # Text TL corner goes through the instance pose: prim (200,300) + insert (1000,0).
        ends = [p for k, p, _n in coll if k == "endpoint"]
        assert any(math.hypot(p.x() - 1200.0, p.y() - 300.0) < 0.01 for p in ends)
    finally:
        close_view(view, scene)


def _rot_yup(p, c, deg):
    """Rotate scene point *p* about *c* by *deg* in the app convention
    (Y-up CCW+) on the Qt Y-down scene — independent of any engine transform."""
    a = math.radians(deg)
    dx, dy_up = p[0] - c[0], -(p[1] - c[1])
    rx = dx * math.cos(a) - dy_up * math.sin(a)
    ry_up = dx * math.sin(a) + dy_up * math.cos(a)
    return (c[0] + rx, c[1] - ry_up)


def test_block_text_box_points_honour_origin_prim_and_instance_rotation(qapp):
    """Coverage (review M2, not a RED guard — passes on the S6 commit): all 9
    text box points of a block with a non-zero origin, a rotated text prim and
    a rotated instance, against independently computed expectations."""
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.text_item import TextAnnotationData, TextItem

    ox, oy = 100.0, 40.0
    tx, ty, t_ang = 200.0, 300.0, 35.0
    ix, iy, i_ang = 5000.0, 2000.0, 30.0

    view, scene = make_view(role="plan", mode="select")
    try:
        data = TextAnnotationData(text="HELLO WORLD", x=tx, y=ty, height_mm=100.0)
        data.angle = t_ang
        text_prim = TextItem(data).to_dict()
        # Box SIZE only (font layout) from an unrotated twin; everything else
        # (rotation, origin, pose) is computed here by hand.
        flat = dict(text_prim)
        flat_item = TextItem.from_dict(flat)
        flat_item.set_angle(0.0)
        box = flat_item._box_rect_local()
        s_ = flat_item.scale() or 1.0
        w, h = box.width() * s_, box.height() * s_
        assert w > 1.0 and h > 1.0

        line_prim = {"type": "draw_line", "pt1": [0, -50], "pt2": [1000, -50],
                     "color": "#ffffff", "lineweight": 1.0}
        d = BlockDefinition.new(name="T", library="L", series="S",
                                primitives=[line_prim, text_prim], origin=(ox, oy))
        scene.register_block_definition(d)
        inst = scene.place_block_instance(d.id, (ix, iy), rotation=i_ang)
        eng = scene._snap_engine
        eng.snap_endpoint = eng.snap_midpoint = eng.snap_center = True

        centre = (tx + w / 2, ty + h / 2)
        uv = [(0, 0), (.5, 0), (1, 0), (1, .5), (1, 1), (.5, 1), (0, 1), (0, .5), (.5, .5)]
        kinds = ["endpoint", "midpoint"] * 4 + ["center"]
        expected = []
        for (u, v), kind in zip(uv, kinds):
            p = _rot_yup((tx + u * w, ty + v * h), centre, t_ang)   # text rotation
            p = (p[0] - ox, p[1] - oy)                                # origin-relative
            p = _rot_yup(p, (0.0, 0.0), i_ang)                        # instance rotation
            expected.append((kind, QPointF(p[0] + ix, p[1] + iy)))    # insertion point

        coll = eng._collect(inst)
        for kind, exp in expected:
            best = min((math.hypot(p.x() - exp.x(), p.y() - exp.y())
                        for k, p, _n in coll if k == kind), default=math.inf)
            assert best < 0.01, (kind, exp, best)
    finally:
        close_view(view, scene)
