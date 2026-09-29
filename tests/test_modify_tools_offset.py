"""D9 workflow: pick (or preselected) → cursor side/distance → click/Enter; sticky; re-arm.

scene-tools.md D9: source = the single selected offsettable item, else "Pick
object to offset"; the cursor sets side + distance and the ghost follows; the
HUD Distance commits at the typed distance on the cursor's side; click/Enter
commits a new item (source kept), one undo; the tool stays armed with the last
distance sticky; Esc → Select; a too-large inward offset shows no ghost, posts
"Offset too large" and creates nothing. Text is not offsettable.
"""
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest

from tests._modify_tools_helpers import PRIMITIVES, add_primitive
from tests._snap_polish_helpers import click, close_view, make_view, move

# D9: Text is not offsettable — excluded here, guarded separately below.
OFFSETTABLE = [n for n in PRIMITIVES if not n.startswith("text")]


def _type_distance(scene, text):
    assert scene.begin_dynamic_input() is True
    scene.dynamic_input.editor("Distance").setText(text)
    scene.dynamic_input._accept()


def _statuses(scene):
    log = []
    orig = scene._show_status
    scene._show_status = lambda msg, timeout=5000: (log.append(msg),
                                                    orig(msg, timeout))
    return log


@pytest.mark.parametrize("name", OFFSETTABLE)
def test_offset_preselected_by_typed_distance(qapp, name):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, name)
        before = item.to_dict()
        p0 = scene._undo_pos
        scene._modify_ctl.start("offset")
        assert scene.mode == "offset_side"                  # preselected → skip pick
        move(view, QPointF(400, -400))                      # outside / one side
        _type_distance(scene, "5")
        items = getattr(scene, attr)
        assert len(items) == 2                              # [RED]
        new = items[-1]
        assert type(new) is type(item) and new.scene() is scene
        assert item.to_dict() == before                     # source kept, untouched
        assert scene._undo_pos == p0 + 1
        assert scene.mode == "offset"                       # re-armed
        assert scene._offset_sticky == pytest.approx(5.0)
        scene.undo()
        assert len(getattr(scene, attr)) == 1               # one undo step
    finally:
        close_view(view, scene)


def test_offset_typed_distance_geometry_on_cursor_side(qapp):
    """Circle r=50, cursor outside, typed 5 → a concentric r=55 circle."""
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")
        scene._modify_ctl.start("offset")
        move(view, QPointF(400, -400))
        _type_distance(scene, "5")
        new = getattr(scene, attr)[-1]
        assert new._radius == pytest.approx(55.0)
        assert (new._center.x(), new._center.y()) == pytest.approx((0.0, 0.0))
    finally:
        close_view(view, scene)


def test_offset_cursor_ghost_follows(qapp):
    """The ghost is the candidate offset item's traced path (D11 style)."""
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "circle")                      # r=50
        scene._modify_ctl.start("offset")
        move(view, QPointF(80, 0))                          # outside, 30 away
        assert len(scene._move_ghost) == 1
        br = scene._move_ghost[0].boundingRect()
        assert br.width() / 2 == pytest.approx(80.0, abs=0.5)
        move(view, QPointF(20, 0))                          # inside, 30 away
        br = scene._move_ghost[0].boundingRect()
        assert br.width() / 2 == pytest.approx(20.0, abs=0.5)
    finally:
        close_view(view, scene)


def test_offset_too_large_refuses(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")         # r=50
        scene._modify_ctl.start("offset")
        move(view, QPointF(1, 0))                           # inside
        log = _statuses(scene)
        p0 = scene._undo_pos
        scene.begin_dynamic_input()
        scene.dynamic_input.editor("Distance").setText("80")
        scene.dynamic_input._accept()
        assert len(getattr(scene, attr)) == 1
        assert scene._undo_pos == p0
        assert scene.dynamic_input is not None              # stays open (reject_commit)
        assert "Offset too large" in log
    finally:
        close_view(view, scene)


def test_offset_too_large_by_cursor_shows_no_ghost(qapp):
    """Rect 100x50: the cursor at the centre asks for a 25 mm inset → degenerate."""
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "rect")           # (0,0)-(100,-50)
        scene._modify_ctl.start("offset")
        log = _statuses(scene)
        move(view, QPointF(50, -25))
        assert scene._move_ghost == []
        assert "Offset too large" in log
        click(view, QPointF(50, -25))
        assert len(getattr(scene, attr)) == 1
    finally:
        close_view(view, scene)


def test_offset_pick_when_nothing_selected(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")
        scene.clearSelection()
        instr = []
        scene.instructionChanged.connect(instr.append)
        scene._modify_ctl.start("offset")
        assert scene.mode == "offset"
        assert instr and instr[-1] == "Pick object to offset"
        click(view, QPointF(50, 0))                         # pick the line
        assert scene.mode == "offset_side"
        move(view, QPointF(50, -20)); click(view, QPointF(50, -20))
        assert len(getattr(scene, attr)) == 2
        new = getattr(scene, attr)[-1]
        assert abs(new.grip_points()[0].y() + 20) < 0.5
        assert scene.mode == "offset"                       # stays armed
    finally:
        close_view(view, scene)


def test_offset_enter_commits_cursor_distance(qapp):
    """Bare Enter commits like a click (D9 step 4) — one helper, no twin."""
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")           # (0,0)-(100,0)
        p0 = scene._undo_pos
        scene._modify_ctl.start("offset")
        move(view, QPointF(50, 30))
        QTest.keyClick(view.viewport(), Qt.Key.Key_Return)
        assert len(getattr(scene, attr)) == 2
        new = getattr(scene, attr)[-1]
        assert new.grip_points()[0].y() == pytest.approx(30.0, abs=0.5)
        assert scene._undo_pos == p0 + 1
    finally:
        close_view(view, scene)


def test_offset_sticky_typed_distance_locks_next_pick(qapp):
    """After a typed commit the next picked source reuses the distance; the
    cursor only picks the side (D9 step 5)."""
    view, scene = make_view(scale=1.0)
    try:
        line, attr = add_primitive(scene, "line")           # (0,0)-(100,0)
        scene._modify_ctl.start("offset")
        move(view, QPointF(50, 40))
        _type_distance(scene, "5")                          # line at y=5
        assert scene.mode == "offset"
        click(view, QPointF(50, 0))                         # pick the source again
        assert scene.mode == "offset_side"
        move(view, QPointF(50, -40)); click(view, QPointF(50, -40))
        ys = sorted(round(it.grip_points()[0].y(), 3) for it in getattr(scene, attr))
        assert ys == [-5.0, 0.0, 5.0]
    finally:
        close_view(view, scene)


def test_offset_refuses_text(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "text")
        scene._modify_ctl.start("offset")
        assert scene.mode == "offset"                       # not armed on Text
        assert scene._offset_source is None
        click(view, QPointF(5, -5))                         # on the text box
        assert scene.mode == "offset"
        assert len(getattr(scene, attr)) == 1
    finally:
        close_view(view, scene)


def test_undo_mid_offset_cancels_the_tool(qapp):
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "circle")
        scene._modify_ctl.start("offset")
        move(view, QPointF(80, 0))
        assert scene.mode == "offset_side"
        scene.undo()
        assert scene.mode in (None, "select")
        assert scene._offset_source is None
        assert scene._move_ghost == []
    finally:
        close_view(view, scene)


def test_offset_esc_exits(qapp):
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "line")
        scene._modify_ctl.start("offset")
        move(view, QPointF(50, 20))
        QTest.keyClick(view.viewport(), Qt.Key.Key_Escape)
        assert scene.mode in (None, "select")
        assert scene._offset_source is None
        assert scene._offset_sticky is None
        assert scene._move_ghost == []
    finally:
        close_view(view, scene)


def test_offset_hud_seeds_the_live_cursor_distance(qapp):
    """The Distance HUD opens on the cursor distance — not the gridline
    replicate spacing fallback (_replicate_spacing / 1000)."""
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "circle")                      # r=50
        scene._modify_ctl.start("offset")
        move(view, QPointF(80, 0))                          # 30 outside
        assert scene.begin_dynamic_input() is True
        assert scene.dynamic_input.current_values()["Distance"] == \
            pytest.approx(30.0, abs=0.05)
    finally:
        close_view(view, scene)


# ── fix round (review G7) ────────────────────────────────────────────────────

@pytest.mark.parametrize("cursor, dist", [(QPointF(98, 4), 4.0),     # near endpoint
                                          (QPointF(52, 3), 3.0),     # near midpoint
                                          (QPointF(30, 5), 5.0)])    # near the line
def test_offset_cursor_near_source_is_not_snapped_onto_it(qapp, cursor, dist):
    """I-1: the source is excluded from snap targets in offset_side, so a
    cursor inside the snap aperture of the source still sets side + distance."""
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")           # (0,0)-(100,0)
        scene._modify_ctl.start("offset")
        move(view, cursor)
        assert scene._offset_dist == pytest.approx(dist, abs=0.05)     # [RED]
        assert len(scene._move_ghost) == 1
        click(view, cursor)
        items = getattr(scene, attr)
        assert len(items) == 2
        assert items[-1].grip_points()[0].y() == pytest.approx(dist, abs=0.05)
    finally:
        close_view(view, scene)


def test_offset_through_point_snaps_to_other_geometry(qapp):
    """I-1: snaps to OTHER geometry stay live — the cursor near another
    line's endpoint offsets THROUGH that endpoint."""
    from firepro3d.geometry_2d import LineItem
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")           # (0,0)-(100,0)
        other = LineItem(QPointF(100, 30), QPointF(200, 30))
        scene.addItem(other); scene._draw_lines.append(other)
        scene._modify_ctl.start("offset")
        move(view, QPointF(102, 28))                        # near (100, 30)
        assert scene._offset_dist == pytest.approx(30.0, abs=1e-6)
    finally:
        close_view(view, scene)


def test_typed_zero_releases_the_locked_distance(qapp):
    """D-2: typing 0 releases the typed lock — the cursor drives the distance
    again (instead of the HUD refusing it)."""
    view, scene = make_view(scale=1.0)
    try:
        line, attr = add_primitive(scene, "line")           # (0,0)-(100,0)
        scene._modify_ctl.start("offset")
        move(view, QPointF(50, 40))
        _type_distance(scene, "5")                          # locks 5
        click(view, QPointF(50, 0))                         # next pick: locked
        move(view, QPointF(50, -40))
        assert scene._offset_dist == pytest.approx(5.0)
        _type_distance(scene, "0")                          # release
        assert scene.dynamic_input is None or not scene.dynamic_input.is_engaged()
        move(view, QPointF(50, -30))
        assert scene._offset_dist == pytest.approx(30.0, abs=0.05)     # [RED]
        click(view, QPointF(50, -30))
        ys = sorted(round(it.grip_points()[0].y(), 3) for it in getattr(scene, attr))
        assert ys == [-30.0, 0.0, 5.0]
    finally:
        close_view(view, scene)


def test_negative_typed_distance_is_refused(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")
        scene._modify_ctl.start("offset")
        move(view, QPointF(50, 40))
        _type_distance(scene, "-5")
        assert len(getattr(scene, attr)) == 1
        assert scene.dynamic_input is not None              # stays open, flagged
    finally:
        close_view(view, scene)


def test_removed_source_refuses_and_clears_ghost(qapp):
    """M-1: the armed source left the scene -> no stale ghost, no commit."""
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")
        scene._modify_ctl.start("offset")
        move(view, QPointF(80, 0))
        assert len(scene._move_ghost) == 1
        scene.removeItem(item)
        getattr(scene, attr).remove(item)
        move(view, QPointF(90, 0))
        assert scene._move_ghost == []                                  # [RED]
        QTest.keyClick(view.viewport(), Qt.Key.Key_Return)
        assert getattr(scene, attr) == []                               # [RED]
        assert scene.mode == "offset"
    finally:
        close_view(view, scene)


def test_status_uses_display_units(qapp):
    """M-3: the live readout goes through ScaleManager.format_length."""
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "circle")                      # r=50
        log = _statuses(scene)
        scene._modify_ctl.start("offset")
        move(view, QPointF(80, 0))
        assert f"Offset: {scene.scale_manager.format_length(30.0)}" in log  # [RED]
    finally:
        close_view(view, scene)


def test_enter_with_no_distance_says_what_to_do(qapp):
    """M-5: preselected, no cursor move, Enter -> a status, nothing made."""
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")
        log = _statuses(scene)
        scene._modify_ctl.start("offset")
        QTest.keyClick(view.viewport(), Qt.Key.Key_Return)
        assert len(getattr(scene, attr)) == 1
        assert "Move the cursor or type a distance" in log              # [RED]
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("name", ["line", "polyline_closed", "rect", "circle",
                                  "arc", "polygon", "ellipse", "spline"])
def test_committed_item_inherits_style(qapp, name):
    """D9 style inheritance, checked on the item the TOOL committed (the one
    in the scene list after a real commit), not on offset_item's return."""
    from PyQt6.QtGui import QColor
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, name)
        pen = item.pen(); pen.setColor(QColor("#ab12cd")); pen.setWidthF(2.5)
        item.setPen(pen)
        if item.is_fillable():
            item.fill_type = "hatch"
            item.fill_pattern = "ANSI31"
            item._display_fill_color = "#00ff00"
            item.fill_opacity = 0.7
        scene._modify_ctl.start("offset")
        move(view, QPointF(400, -400))
        _type_distance(scene, "5")
        new = getattr(scene, attr)[-1]
        assert new is not item and new.scene() is scene
        assert new.pen().color().name() == "#ab12cd"
        assert new.pen().widthF() == pytest.approx(2.5)
        if item.is_fillable():
            assert (new.fill_type, new.fill_pattern, new._display_fill_color,
                    new.fill_opacity) == ("hatch", "ANSI31", "#00ff00",
                                          pytest.approx(0.7))
    finally:
        close_view(view, scene)


# ── R-2 / R2-1: live ghost cost — user metric: <= 30 ms per REAL mouse move ─
# (viewport mouse event -> snap -> move_offset_side -> ghost repaint), median
# over N moves on a SHOWN view. A LineItem source is timed the same way as the
# context baseline. Never loosen the threshold; `perf`-marked, so it runs in
# its own process (test-harness Invariant 8), never inside a busy chunk.

import math
import time


def _spline40():
    import random
    from firepro3d.geometry_2d import SplineItem
    rnd = random.Random(1)
    return SplineItem([QPointF(i * 50 - 1000, rnd.uniform(-80, 80))
                       for i in range(40)])


def _closed39():
    """The reviewer's noisy closed spline: 39 points on r~400 (+-30 noise)."""
    import random
    from firepro3d.geometry_2d import SplineItem
    rnd = random.Random(1)
    [rnd.uniform(-80, 80) for _ in range(40)]      # same stream as the probe
    c = [QPointF(400 * math.cos(2 * math.pi * i / 39) + rnd.uniform(-30, 30),
                 -400 * math.sin(2 * math.pi * i / 39) + rnd.uniform(-30, 30))
         for i in range(39)]
    c.append(QPointF(c[0]))
    return SplineItem(c)


_PERF_WARMUP_MOVES = 5    # arm the tool + warm the fit cache / paint path
_PERF_PASSES = 3          # best-of-N medians: one scheduler hiccup can't flip it


def _real_move_median_ms(make_source, attr, pts):
    """Best-of-3 median wall time of real viewport mouse moves (incl. the
    repaint), after a few warm-up moves. The threshold is never loosened;
    only the measurement is made robust to a single noisy pass."""
    view, scene = make_view(scale=1.0)
    try:
        src = make_source()
        scene.addItem(src); getattr(scene, attr).append(src)
        scene.push_undo_state()
        scene.clearSelection(); src.setSelected(True)
        scene._modify_ctl.start("offset")
        assert scene.mode == "offset_side"
        for p in pts[:_PERF_WARMUP_MOVES]:               # arm + warm the cache
            move(view, p)
        medians = []
        for _ in range(_PERF_PASSES):
            ts = []
            for p in pts[_PERF_WARMUP_MOVES:]:
                t = time.perf_counter()
                move(view, p)                           # sendEvent + processEvents
                ts.append((time.perf_counter() - t) * 1000)
            assert scene._move_ghost, "ghost must be live"
            ts.sort()
            medians.append(ts[len(ts) // 2])
        return min(medians)
    finally:
        close_view(view, scene)


def _line_baseline_ms():
    from firepro3d.geometry_2d import LineItem
    return _real_move_median_ms(
        lambda: LineItem(QPointF(-1000, 0), QPointF(1000, 0)), "_draw_lines",
        [QPointF(-500 + k * 7, 150) for k in range(23)])


_PERF_CASES = {
    "open40_far": (_spline40, [QPointF(-500 + k * 7, 150) for k in range(23)]),
    "open40_near": (_spline40, [QPointF(-400 + k * 3, -95 - (k % 3)) for k in range(23)]),
    "closed39_out": (_closed39, [QPointF(450 + k, 0) for k in range(23)]),
    "closed39_in": (_closed39, [QPointF(300 + k, 0) for k in range(23)]),
}


_KNOWN_SLOW = pytest.mark.xfail(
    strict=False,
    reason="KNOWN LIMIT, user-accepted (measured 31-35 ms): the HALO glow's "
           "repaint cost tracks the ghost's drawn LENGTH. At d~145 the "
           "40-point spline's untrimmed offset loops (d >> its bend radius) "
           "more than double that length (5609 mm vs 2517 mm at d=5), so the "
           "ghost repaint alone is ~24 ms. Self-intersection trimming (filed "
           "follow-up) removes the loops. The threshold is NOT loosened.")


@pytest.mark.perf
@pytest.mark.parametrize("case", [
    pytest.param(c, marks=_KNOWN_SLOW) if c == "open40_far" else c
    for c in _PERF_CASES])
def test_offset_real_mouse_move_is_fast(qapp, case):
    """Median real mouse move <= 30 ms on a 40-point open / 39-point closed
    spline (handler + ghost repaint), with a LineItem baseline for context."""
    make_source, pts = _PERF_CASES[case]
    ms = _real_move_median_ms(make_source, "_draw_splines", pts)
    base = _line_baseline_ms()
    assert ms <= 30.0, f"{case}: median {ms:.1f} ms per move (line {base:.1f} ms)"  # [RED]
