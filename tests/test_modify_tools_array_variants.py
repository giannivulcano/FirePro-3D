"""P1 DD5: Array variants (Linear / 2D / Polar), angle lock, session memory.

Governing: docs/superpowers/specs/2026-10-01-scene-tools-p1-batch-design.md
DD5 + acceptance M1 (folded into scene-tools.md D10 at Account). Every guard
drives the real path: a shown Model_View over a real block_editor
Model_Space, real mouse events, the real HUD (begin_dynamic_input / editor
text / Tab / Esc / _accept), and asserts scene coordinates of the copies.
The views ignore the real OS mouse (``ignore_os_mouse``) so a user's cursor
over the test window cannot inject moves.
"""
import math

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtTest import QTest

from tests._modify_tools_helpers import add_primitive, ignore_os_mouse
from tests._snap_polish_helpers import click, close_view, make_view, move

COS30 = math.cos(math.radians(30.0))
SIN30 = math.sin(math.radians(30.0))


def _view(**kw):
    """A shown Model_View (``make_view``) deaf to the real OS mouse."""
    view, scene = make_view(**kw)
    ignore_os_mouse(view)
    return view, scene


def _type(scene, **fields):
    """Engage the HUD, type *fields* by name, press the HUD's Enter path."""
    assert scene.begin_dynamic_input() is True
    for name, text in fields.items():
        scene.dynamic_input.editor(name).setText(text)
    scene.dynamic_input._accept()


def _centres(circles):
    return sorted((round(c._center.x(), 2), round(c._center.y(), 2))
                  for c in circles)


def test_typed_count_prefills_the_next_array(qapp):
    """DD5 memory: a typed Count is remembered for the next Array on the same
    canvas (it used to fall back to the fixed default 3)."""
    view, scene = _view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")          # centre (0,0) r=50
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(200, 0))
        _type(scene, Spacing="200", Count="4")
        assert len(getattr(scene, attr)) == 4
        p0 = scene._undo_pos
        # Run 2: click-commit at the cursor spacing — Count is the remembered 4.
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(0, -300))
        click(view, QPointF(0, -300))
        lst = getattr(scene, attr)
        assert len(lst) == 4 + 3                                       # [RED]
        assert _centres(lst[4:]) == [(0.0, -900.0), (0.0, -600.0), (0.0, -300.0)]
        assert scene._undo_pos == p0 + 1
        assert item.isSelected()
    finally:
        close_view(view, scene)


def _assert_points(points, expected, tol=0.01):
    """Scene points match *expected* (order-free; float-noise-safe sort)."""
    key = lambda p: (round(p[0], 3), round(p[1], 3))
    got = sorted(((p.x(), p.y()) for p in points), key=key)
    exp = sorted(expected, key=key)
    assert len(got) == len(exp), (got, exp)
    for (gx, gy), (ex, ey) in zip(got, exp):
        assert gx == pytest.approx(ex, abs=tol), (got, exp)
        assert gy == pytest.approx(ey, abs=tol), (got, exp)


def _tab_angle(scene, text):
    """Real HUD keys: type Angle, Tab (field commit), Esc (back to cursor)."""
    assert scene.begin_dynamic_input() is True
    hud = scene.dynamic_input
    hud.editor("Angle").setText(text)
    QTest.keyClick(hud.editor("Angle"), Qt.Key.Key_Tab)
    QTest.keyClick(hud.editor("Spacing"), Qt.Key.Key_Escape)
    assert not scene.is_input_mode()


def test_typed_angle_30_places_copies_along_30_degrees_yup(qapp):
    """M1: Linear with a typed Angle 30° puts copy k at base + k·sp·(cos30,
    −sin30) in SCENE (Y-down) coordinates — up and to the right on screen."""
    view, scene = _view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")          # centre (0,0)
        p0 = scene._undo_pos
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(200, 0))      # aim +X
        _type(scene, Angle="30", Spacing="150", Count="3")
        _assert_points([c._center for c in getattr(scene, attr)],   # [RED]
                       [(150 * k * COS30, -150 * k * SIN30) for k in range(3)])
        assert scene._undo_pos == p0 + 1
        assert item.isSelected()
        scene.undo()
        assert len(getattr(scene, attr)) == 1
    finally:
        close_view(view, scene)


def test_typed_angle_locks_direction_cursor_sets_spacing_only(qapp):
    """DD5: after Angle 30 + Tab, Esc hands back the cursor — which now sets
    only the spacing: the projection of base->cursor onto the 30° line."""
    view, scene = _view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(200, 0))
        _tab_angle(scene, "30")
        move(view, QPointF(300, -40)); click(view, QPointF(300, -40))
        sp = 300 * COS30 + 40 * SIN30          # (300,-40)·(cos30, -sin30)
        _assert_points([c._center for c in getattr(scene, attr)],   # [RED]
                       [(sp * k * COS30, -sp * k * SIN30) for k in range(3)])
    finally:
        close_view(view, scene)


def test_typed_zero_angle_releases_the_lock(qapp):
    """DD5: 0 releases the lock — the cursor aims (direction + spacing) again."""
    view, scene = _view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(200, 0))
        _tab_angle(scene, "30")
        move(view, QPointF(300, -40))
        sp = 300 * COS30 + 40 * SIN30
        # Locked: the ghost copies sit on the 30° line.
        _assert_points([p.boundingRect().center() for p in scene._move_ghost],  # [RED]
                       [(sp * k * COS30, -sp * k * SIN30) for k in (1, 2)])
        _tab_angle(scene, "0")
        move(view, QPointF(300, -40)); click(view, QPointF(300, -40))
        _assert_points([c._center for c in getattr(scene, attr)],
                       [(300 * k, -40 * k) for k in range(3)])
    finally:
        close_view(view, scene)


def test_typed_angle_lock_carries_to_the_next_array(qapp):
    """DD5 session memory: a typed Angle starts the next Array locked (and
    the typed Count pre-fills it)."""
    view, scene = _view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(200, 0))
        _type(scene, Angle="30", Spacing="100", Count="2")
        assert len(getattr(scene, attr)) == 2
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(300, -40))
        click(view, QPointF(300, -40))
        sp = 300 * COS30 + 40 * SIN30
        _assert_points([c._center for c in getattr(scene, attr)[2:]],  # [RED]
                       [(sp * COS30, -sp * SIN30)])
    finally:
        close_view(view, scene)


def _ghost_centres(paths):
    return sorted((round(p.boundingRect().center().x(), 1),
                   round(p.boundingRect().center().y(), 1)) for p in paths)


def test_arrow_cycles_array_variants_only_before_the_base_pick(qapp):
    """M1: ←/→ cycles the Array variant at step 0 only (real key events)."""
    view, scene = _view(scale=1.0)
    try:
        add_primitive(scene, "circle")
        seen = []
        scene.instructionChanged.connect(seen.append)
        assert scene._modify_ctl.start("array")
        assert seen[-1].startswith("Linear Array (←/→ to change)")
        QTest.keyClick(view.viewport(), Qt.Key.Key_Right)
        assert seen[-1].startswith("2D Array (←/→ to change)")          # [RED]
        assert scene.active_schema().name == "array_grid"
        QTest.keyClick(view.viewport(), Qt.Key.Key_Left)
        assert seen[-1].startswith("Linear Array (←/→ to change)")
        assert scene.active_schema().name == "array_linear"
        QTest.keyClick(view.viewport(), Qt.Key.Key_Right)                # 2D again
        click(view, QPointF(0, 0))                                       # base pick
        n = len(seen)
        QTest.keyClick(view.viewport(), Qt.Key.Key_Right)                # refused now
        assert scene.active_schema().name == "array_grid"
        assert all("(←/→ to change)" not in m for m in seen[n:])
    finally:
        close_view(view, scene)


def test_grid_3x4_places_12_items_rows_go_up(qapp):
    """M1: 2D 3 × 4 places 12 items incl. the original; columns along +X,
    rows along +90° CCW (Y-up) — UP the screen, i.e. scene −Y."""
    view, scene = _view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")
        p0 = scene._undo_pos
        assert scene._modify_ctl.start("array")
        QTest.keyClick(view.viewport(), Qt.Key.Key_Right)                # 2D
        click(view, QPointF(0, 0)); move(view, QPointF(120, -60))
        _type(scene, ColSpacing="100", Cols="3", RowSpacing="50", Rows="4")
        _assert_points([c._center for c in getattr(scene, attr)],       # [RED]
                       [(100 * c, -50 * r) for r in range(4) for c in range(3)])
        assert scene._undo_pos == p0 + 1
        assert item.isSelected()
        scene.undo()
        assert len(getattr(scene, attr)) == 1
    finally:
        close_view(view, scene)


def test_grid_angle_30_rows_are_ccw_of_columns_in_yup(qapp):
    """DD5 handedness on scene coordinates: Angle 30° puts columns along
    (cos30, −sin30) and rows along (−sin30, −cos30) — 120° in Y-up."""
    view, scene = _view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")
        assert scene._modify_ctl.start("array")
        QTest.keyClick(view.viewport(), Qt.Key.Key_Right)
        click(view, QPointF(0, 0)); move(view, QPointF(120, -60))
        _type(scene, Angle="30", ColSpacing="100", Cols="2",
              RowSpacing="50", Rows="2")
        u = (100 * COS30, -100 * SIN30)
        v = (-50 * SIN30, -50 * COS30)
        _assert_points([c._center for c in getattr(scene, attr)],       # [RED]
                       [(0.0, 0.0), u, v, (u[0] + v[0], u[1] + v[1])])
    finally:
        close_view(view, scene)


def test_grid_cursor_is_the_first_cells_far_corner(qapp):
    """DD5: the cursor is the first cell's diagonal corner (Cols × Rows from
    memory, default 3 × 3); the ghost is exactly what the click creates."""
    from firepro3d.transform_ghost import ghost_base_paths
    view, scene = _view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")
        assert scene._modify_ctl.start("array")
        QTest.keyClick(view.viewport(), Qt.Key.Key_Right)
        click(view, QPointF(0, 0)); move(view, QPointF(120, -60))
        ghost = _ghost_centres(scene._move_ghost)
        click(view, QPointF(120, -60))
        lst = getattr(scene, attr)
        _assert_points([c._center for c in lst],                        # [RED]
                       [(120 * c, -60 * r) for r in range(3) for c in range(3)])
        assert _ghost_centres(ghost_base_paths(lst[1:])) == ghost
    finally:
        close_view(view, scene)


def test_variant_and_typed_values_prefill_the_next_array(qapp):
    """M1: the variant + typed Cols/Rows pre-fill the next Array on the same
    canvas (session memory, per scene)."""
    view, scene = _view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")
        assert scene._modify_ctl.start("array")
        QTest.keyClick(view.viewport(), Qt.Key.Key_Right)                # 2D
        click(view, QPointF(0, 0)); move(view, QPointF(120, -60))
        _type(scene, ColSpacing="100", Cols="3", RowSpacing="50", Rows="4")
        assert len(getattr(scene, attr)) == 12
        seen = []
        scene.instructionChanged.connect(seen.append)
        assert scene._modify_ctl.start("array")
        assert seen[-1].startswith("2D Array (←/→ to change)")          # [RED]
        click(view, QPointF(0, 0))
        assert scene.begin_dynamic_input() is True
        hud = scene.dynamic_input
        assert hud.editor("Cols").text() == "3"
        assert hud.editor("Rows").text() == "4"
        QTest.keyClick(hud.editor("Angle"), Qt.Key.Key_Escape)          # back to cursor
        move(view, QPointF(200, -100)); click(view, QPointF(200, -100))
        _assert_points([c._center for c in getattr(scene, attr)[12:]],
                       [(200 * c, -100 * r) for r in range(4) for c in range(3)
                        if (r, c) != (0, 0)])
    finally:
        close_view(view, scene)


def _add_line(scene, p1, p2):
    from firepro3d.geometry_2d import LineItem
    ln = LineItem(QPointF(*p1), QPointF(*p2))
    scene.addItem(ln); scene._draw_lines.append(ln)
    scene.push_undo_state()
    scene.clearSelection(); ln.setSelected(True)
    return ln


def _polar(view):
    """Linear -> 2D -> Polar with two real → presses."""
    QTest.keyClick(view.viewport(), Qt.Key.Key_Right)
    QTest.keyClick(view.viewport(), Qt.Key.Key_Right)


def test_arrow_cycle_reaches_polar_and_wraps(qapp):
    view, scene = _view(scale=1.0)
    try:
        add_primitive(scene, "circle")
        seen = []
        scene.instructionChanged.connect(seen.append)
        assert scene._modify_ctl.start("array")
        _polar(view)
        assert seen[-1].startswith("Polar Array (←/→ to change)")       # [RED]
        assert scene.active_schema().name == "array_polar"
        QTest.keyClick(view.viewport(), Qt.Key.Key_Right)
        assert seen[-1].startswith("Linear Array (←/→ to change)")
    finally:
        close_view(view, scene)


def test_polar_8_at_360_places_8_items_at_45_degree_steps_each_rotated(qapp):
    """M1: Polar 8 @ 360° = 8 items incl. the original at 45° steps about the
    centre, each copy TURNED (its own manip_rotate), CCW in Y-up."""
    view, scene = _view(scale=1.0)
    try:
        ln = _add_line(scene, (100, 0), (150, 0))
        p0 = scene._undo_pos
        assert scene._modify_ctl.start("array")
        _polar(view)
        click(view, QPointF(0, 0))                                       # centre
        _type(scene, Count="8", Total="360")
        lines = scene._draw_lines
        assert len(lines) == 8                                           # [RED]
        rad = [math.radians(45 * k) for k in range(8)]
        _assert_points([l.grip_points()[0] for l in lines],
                       [(100 * math.cos(a), -100 * math.sin(a)) for a in rad])
        _assert_points([l.grip_points()[2] for l in lines],
                       [(150 * math.cos(a), -150 * math.sin(a)) for a in rad])
        for l in lines:          # turned, not just moved: p1 -> p2 is radial
            p1, p2 = l.grip_points()[0], l.grip_points()[2]
            a = math.atan2(-p1.y(), p1.x())
            assert p2.x() - p1.x() == pytest.approx(50 * math.cos(a), abs=0.01)
            assert p2.y() - p1.y() == pytest.approx(-50 * math.sin(a), abs=0.01)
        assert scene._undo_pos == p0 + 1
        assert ln.isSelected()
        scene.undo()
        assert len(scene._draw_lines) == 1
    finally:
        close_view(view, scene)


def test_polar_cursor_sweep_sets_total_ccw_and_ghost_matches(qapp):
    """DD5: the cursor's CCW sweep from the start ray (centre -> selection)
    sets Total — 90° here, so the default Count 4 lands at 30/60/90° (Y-up,
    i.e. UP the screen); the ghost is exactly what the click creates."""
    from firepro3d.transform_ghost import ghost_base_paths
    view, scene = _view(scale=1.0)
    try:
        _add_line(scene, (100, 0), (150, 0))
        assert scene._modify_ctl.start("array")
        _polar(view)
        click(view, QPointF(0, 0)); move(view, QPointF(0, -200))       # 90° CCW
        ghost = _ghost_centres(scene._move_ghost)
        click(view, QPointF(0, -200))
        lines = scene._draw_lines
        assert len(lines) == 4                                           # [RED]
        _assert_points([l.grip_points()[1] for l in lines],              # midpoints
                       [(125 * math.cos(math.radians(a)),
                         -125 * math.sin(math.radians(a))) for a in (0, 30, 60, 90)])
        assert _ghost_centres(ghost_base_paths(lines[1:])) == ghost
    finally:
        close_view(view, scene)


def test_polar_skips_nodes_with_a_count(qapp):
    """DD5: Polar arrays what Rotate can turn; a Node (a zero-offset node paste
    merges onto its original) is skipped and counted in the status."""
    from firepro3d.gridline import GridlineItem
    view, scene = _view(role="plan", scale=1.0)
    try:
        msgs = []
        scene._show_status = lambda m, timeout=5000: msgs.append(m)
        node = scene.add_node(300.0, 300.0)
        gl = GridlineItem(QPointF(100, -50), QPointF(100, 50), label="P1")
        scene._register_gridline(gl)
        scene.push_undo_state()
        n_nodes = len(scene.sprinkler_system.nodes)
        before = list(scene._gridlines)
        scene.clearSelection(); node.setSelected(True); gl.setSelected(True)
        assert scene._modify_ctl.start("array")
        _polar(view)
        click(view, QPointF(0, 0))
        _type(scene, Count="4", Total="360")
        new = [g for g in scene._gridlines if all(g is not b for b in before)]
        assert len(new) == 3                                             # [RED]
        assert len(scene.sprinkler_system.nodes) == n_nodes
        _assert_points([gl.grip_points()[0]] + [g.grip_points()[0] for g in new],
                       [(100, -50), (-50, -100), (-100, 50), (50, 100)])
        assert msgs[-1].endswith("(1 skipped)")
    finally:
        close_view(view, scene)


def _mid_angles(lines, r=125.0):
    """Y-up headings (deg, [0, 360)) of the line midpoints at radius *r*."""
    out = []
    for l in lines:
        m = l.grip_points()[1]
        assert math.hypot(m.x(), m.y()) == pytest.approx(r, abs=0.01)
        out.append(round(math.degrees(math.atan2(-m.y(), m.x())), 2) % 360.0)
    return sorted(out)


def test_polar_total_is_the_sweep_never_a_remembered_typed_total(qapp):
    """Review I1 (user decision 2026-10-01): a typed Total commits as typed
    but is NOT remembered — the next Polar fills the default 360° until the
    cursor sweeps, then the ghost and the commit follow the sweep. Count is
    still remembered."""
    view, scene = _view(scale=1.0)
    try:
        _add_line(scene, (100, 0), (150, 0))
        assert scene._modify_ctl.start("array")
        _polar(view)
        click(view, QPointF(0, 0))
        _type(scene, Count="5", Total="120")
        assert _mid_angles(scene._draw_lines) == [0.0, 30.0, 60.0, 90.0, 120.0]
        # Run 2: centre, then commit on the centre itself (no sweep yet).
        scene.clearSelection(); scene._draw_lines[0].setSelected(True)
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); click(view, QPointF(0, 0))
        new = scene._draw_lines[5:]
        assert _mid_angles(new) == [72.0, 144.0, 216.0, 288.0]          # [RED]
        # Run 3: a 90° CCW sweep sets Total — ghost and commit follow it.
        from firepro3d.transform_ghost import ghost_base_paths
        scene.clearSelection(); scene._draw_lines[0].setSelected(True)
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(0, -200))
        ghost = _ghost_centres(scene._move_ghost)
        click(view, QPointF(0, -200))
        new = scene._draw_lines[9:]
        assert _mid_angles(new) == [22.5, 45.0, 67.5, 90.0]
        assert _ghost_centres(ghost_base_paths(new)) == ghost
    finally:
        close_view(view, scene)


def _add_wall(scene, p1, p2):
    from firepro3d.wall import WallSegment
    w = WallSegment(QPointF(*p1), QPointF(*p2), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    return w


def test_wall_only_selection_refuses_array_up_front(qapp):
    """Review I3: paste_items cannot re-create a wall, so a wall-only
    selection is refused when Array starts (accurate reason), not at the
    commit with "Nothing arrayed"."""
    view, scene = _view(role="plan", scale=1.0)
    try:
        msgs = []
        scene._show_status = lambda m, timeout=5000: msgs.append(m)
        w = _add_wall(scene, (1000, 0), (2000, 0))
        scene.push_undo_state()
        scene.clearSelection(); w.setSelected(True)
        p0 = scene._undo_pos
        assert scene._modify_ctl.start("array") is False                # [RED]
        assert scene.mode != "array"
        assert msgs[-1] == scene._modify_ctl.ARRAY_NOTHING_COPYABLE
        assert len(scene._walls) == 1 and scene._undo_pos == p0
    finally:
        close_view(view, scene)


def test_polar_ghost_and_skip_count_leave_out_walls(qapp):
    """Review I3: a wall in a mixed selection is neither ghosted nor counted
    as arrayed — the ghost is exactly the commit and "(1 skipped)" is
    honest."""
    from firepro3d.gridline import GridlineItem
    from firepro3d.transform_ghost import ghost_base_paths
    view, scene = _view(role="plan", scale=1.0)
    try:
        msgs = []
        scene._show_status = lambda m, timeout=5000: msgs.append(m)
        w = _add_wall(scene, (1000, 0), (2000, 0))
        gl = GridlineItem(QPointF(100, -50), QPointF(100, 50), label="P1")
        scene._register_gridline(gl)
        scene.push_undo_state()
        before = list(scene._gridlines)
        scene.clearSelection(); w.setSelected(True); gl.setSelected(True)
        assert scene._modify_ctl.start("array")
        _polar(view)
        click(view, QPointF(0, 0))
        assert len(scene._move_ghost_base) == 1                          # [RED]
        move(view, QPointF(0, -1500))                                    # 90° CCW
        ghost = _ghost_centres(scene._move_ghost)
        click(view, QPointF(0, -1500))
        new = [g for g in scene._gridlines if all(g is not b for b in before)]
        assert len(new) == 3 and len(scene._walls) == 1
        assert _ghost_centres(ghost_base_paths(new)) == ghost
        assert msgs[-1].endswith("(1 skipped)")
    finally:
        close_view(view, scene)


def test_polar_centre_pick_refused_when_nothing_can_rotate(qapp):
    """Review S3: Polar with nothing rotatable (a Node) refuses the centre
    pick with the reason; the tool stays live at step 0 (no base, ←/→ still
    cycles)."""
    view, scene = _view(role="plan", scale=1.0)
    try:
        msgs = []
        scene._show_status = lambda m, timeout=5000: msgs.append(m)
        node = scene.add_node(300.0, 300.0)
        scene.push_undo_state()
        scene.clearSelection(); node.setSelected(True)
        assert scene._modify_ctl.start("array")
        _polar(view)
        click(view, QPointF(0, 0))
        assert scene._array_base is None                                 # [RED]
        assert scene.mode == "array"
        assert msgs[-1] == scene._modify_ctl.ARRAY_POLAR_NOTHING
        QTest.keyClick(view.viewport(), Qt.Key.Key_Right)                # -> Linear
        assert scene.active_schema().name == "array_linear"
    finally:
        close_view(view, scene)


def _big_grid(view, scene, cols, rows, base, corner):
    """2D array of the selection with remembered Cols x Rows, aimed by a
    real base click + cursor move at the first cell's far *corner*."""
    scene._array_memory["grid"] = {"Cols": cols, "Rows": rows}
    assert scene._modify_ctl.start("array")
    QTest.keyClick(view.viewport(), Qt.Key.Key_Right)                    # 2D
    click(view, base); move(view, corner)


def test_big_array_ghost_is_simplified_but_covers_the_commit(qapp):
    """Review I2: above ARRAY_GHOST_FULL_MAX ghost paths the preview is one
    merged trace-only path (no HALO glow) — and it still covers exactly the
    extent of what the click creates (the commit is uncapped)."""
    from firepro3d.constants import ARRAY_GHOST_FULL_MAX
    from firepro3d.transform_ghost import LiteGhostPath, ghost_base_paths
    view, scene = _view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")              # (0,0)-(100,0)
        _big_grid(view, scene, 15, 15, QPointF(0, 0), QPointF(120, -60))
        assert 15 * 15 - 1 > ARRAY_GHOST_FULL_MAX
        ghost = scene._move_ghost
        assert len(ghost) == 1 and isinstance(ghost[0], LiteGhostPath)  # [RED]
        extent = ghost[0].boundingRect()
        click(view, QPointF(120, -60))
        copies = getattr(scene, attr)[1:]
        assert len(copies) == 15 * 15 - 1
        union = QRectF()
        for p in ghost_base_paths(copies):
            union = union.united(p.boundingRect())
        for a, b in ((extent.left(), union.left()), (extent.top(), union.top()),
                     (extent.right(), union.right()),
                     (extent.bottom(), union.bottom())):
            assert a == pytest.approx(b, abs=0.01)
        # Every committed copy is in the merged ghost (not just the extent).
        sub = sorted((round(poly.boundingRect().center().x(), 1),
                      round(poly.boundingRect().center().y(), 1))
                     for poly in ghost[0].toSubpathPolygons())
        assert sub == _ghost_centres(ghost_base_paths(copies))
        assert extent.left() == pytest.approx(0.0, abs=0.01)
        assert extent.right() == pytest.approx(14 * 120 + 100, abs=0.01)
        assert extent.top() == pytest.approx(-14 * 60, abs=0.01)
    finally:
        close_view(view, scene)


def test_small_array_ghost_keeps_the_full_halo_paths(qapp):
    """At or below ARRAY_GHOST_FULL_MAX the ghost stays one HALO path per
    copy (the D11 style)."""
    from firepro3d.transform_ghost import LiteGhostPath
    view, scene = _view(scale=1.0)
    try:
        add_primitive(scene, "line")
        _big_grid(view, scene, 3, 3, QPointF(0, 0), QPointF(120, -60))
        assert len(scene._move_ghost) == 8
        assert not any(isinstance(p, LiteGhostPath) for p in scene._move_ghost)
    finally:
        close_view(view, scene)


@pytest.mark.perf
def test_50x50_grid_ghost_repaint_is_interactive(qapp):
    """Review I2 user bar (2026-10-01): median viewport repaint <= 16 ms with
    the ghost of a 50 x 50 2D array of a simple line on screen (the reviewer
    measured ~950 ms per repaint before the simplified ghost)."""
    import statistics
    import time
    view, scene = _view(scale=0.012)
    try:
        add_primitive(scene, "line")
        # 49 cells of 1300 x 800 mm fit the 800 x 600 view at 0.012. A cell
        # is then ~16 px, inside the snap aperture of the base point, so
        # SNAP is off (F3) for the corner pick.
        scene.toggle_snap(False)
        view.centerOn(QPointF(31850, -19600))
        base = QPointF(20000, -10000)
        _big_grid(view, scene, 50, 50, base,
                  QPointF(base.x() + 1300, base.y() - 800))
        assert scene._array_spacing == pytest.approx(1300, abs=100)  # 1 px ~ 83 mm
        assert scene._array_row_spacing == pytest.approx(800, abs=100)
        vp = view.viewport()
        t0 = time.perf_counter()
        vp.repaint()                                          # first paint
        first = (time.perf_counter() - t0) * 1000.0
        times = []
        for _ in range(9):
            t0 = time.perf_counter()
            vp.repaint()
            times.append((time.perf_counter() - t0) * 1000.0)
        med = statistics.median(times)
        print(f"median ghost repaint {med:.1f} ms (first {first:.1f} ms)")
        assert med <= 16.0, f"median ghost repaint {med:.1f} ms"         # [RED]
    finally:
        close_view(view, scene)


def test_polar_start_ray_points_at_the_selection_off_the_zero_ray(qapp):
    """Review I4: the sweep starts on the ray centre -> selection centre.
    The line sits at 270° (Y-up) from the centre; a 90° CCW sweep to 0°
    makes Total 90, so the default Count 4 lands at 300 / 330 / 0°."""
    view, scene = _view(scale=1.0)
    try:
        _add_line(scene, (0, 100), (0, 150))                  # 270° (scene +Y)
        assert scene._modify_ctl.start("array")
        _polar(view)
        click(view, QPointF(0, 0)); move(view, QPointF(200, 0))         # 0°
        click(view, QPointF(200, 0))
        assert _mid_angles(scene._draw_lines) == [0.0, 270.0, 300.0, 330.0]  # [RED]
    finally:
        close_view(view, scene)


def test_locked_projection_at_or_behind_the_base_keeps_the_spacing(qapp):
    """Review I4 / C-8: with the Angle locked, a cursor whose projection on
    the locked direction is <= 0 keeps the previous spacing (the direction
    never flips, the spacing is never the projection's magnitude)."""
    view, scene = _view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(200, 0))
        _tab_angle(scene, "30")
        move(view, QPointF(300, -40))
        sp = 300 * COS30 + 40 * SIN30
        move(view, QPointF(-100, 0)); click(view, QPointF(-100, 0))     # behind
        _assert_points([c._center for c in getattr(scene, attr)],       # [RED]
                       [(sp * k * COS30, -sp * k * SIN30) for k in range(3)])
    finally:
        close_view(view, scene)


def test_typed_angle_equal_to_the_live_aim_does_not_lock(qapp):
    """Review I4: an Angle equal to the live (unlocked) aim is the readout,
    not a lock — the cursor keeps aiming direction + spacing."""
    view, scene = _view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(200, -200))      # 45°
        _tab_angle(scene, "45")
        move(view, QPointF(0, -300)); click(view, QPointF(0, -300))
        _assert_points([c._center for c in getattr(scene, attr)],       # [RED]
                       [(0.0, -300.0 * k) for k in range(3)])
    finally:
        close_view(view, scene)


def test_polar_ghost_matches_the_commit_full_rects_of_a_rotated_rect(qapp):
    """Review S1: ghost == commit on FULL bounding rects of an asymmetric
    item (a rotated rectangle) — a ghost that moved copies without turning
    them would differ in size, not just position."""
    from firepro3d.transform_ghost import ghost_base_paths
    view, scene = _view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "rect_rotated")
        scene._array_memory["polar"]["Count"] = 3
        assert scene._modify_ctl.start("array")
        _polar(view)
        centre = QPointF(-300, 0)
        click(view, centre)
        start = scene._array_start_deg
        a = math.radians(start + 100.0)                       # 100° CCW sweep
        cur = QPointF(centre.x() + 400 * math.cos(a), centre.y() - 400 * math.sin(a))
        move(view, cur)
        assert scene._array_total == pytest.approx(100.0, abs=0.5)

        def rects(paths):
            return sorted(tuple(round(v, 1) for v in (
                p.boundingRect().left(), p.boundingRect().top(),
                p.boundingRect().right(), p.boundingRect().bottom()))
                for p in paths)

        ghost = rects(scene._move_ghost)
        click(view, cur)
        copies = getattr(scene, attr)[1:]
        assert len(copies) == 2
        assert rects(ghost_base_paths(copies)) == ghost
        base = rects(ghost_base_paths([item]))[0]
        for r in ghost:          # turned: no copy keeps the original's size
            assert (round(r[2] - r[0], 1), round(r[3] - r[1], 1)) != (
                round(base[2] - base[0], 1), round(base[3] - base[1], 1))
    finally:
        close_view(view, scene)


def test_status_readout_shows_an_active_angle_lock(qapp):
    """Review S4: a session-sticky Angle lock is visible in the readout."""
    from firepro3d.scale_manager import ScaleManager
    view, scene = _view(scale=1.0)
    try:
        msgs = []
        scene._show_status = lambda m, timeout=5000: msgs.append(m)
        add_primitive(scene, "circle")
        assert scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(200, 0))
        assert "(locked)" not in msgs[-1]
        _tab_angle(scene, "30")
        move(view, QPointF(300, -40))
        assert f"Angle: {ScaleManager.format_angle(30.0)} (locked)" in msgs[-1]  # [RED]
        _tab_angle(scene, "0")
        move(view, QPointF(300, -40))
        assert "(locked)" not in msgs[-1]
    finally:
        close_view(view, scene)
