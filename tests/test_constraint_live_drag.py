"""D35 live body / resize drag on constrained geometry + D32 glyph visibility,
VC9 F3 per-frame layout cache, S1 glyph frame, F6 inert glyphs, F7 cursor.

parametric-constraint-system.md §8/§10, D10/D11/D21/D27 and the user rulings
D32 (glyph visibility) / D35 (constrained body drag applies live). Real shown
Block Editor scene + Model_View, posted mouse / key events through the
viewport, observable geometry and pixels as ground truth.
"""
from __future__ import annotations

import time

import pytest
from PyQt6.QtCore import QEvent, QObject, QPointF, Qt
from PyQt6.QtGui import QColor, QKeyEvent, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d import constraint_paint as cp
from firepro3d import sketch_model as sm
from firepro3d import theme as th
from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.scale_manager import ScaleManager
from firepro3d.theme import M


class _NoRealMouse(QObject):
    """Swallow SPONTANEOUS (OS) mouse events on the viewport: the real
    cursor resting over the shown test window injects moves that cut a posted
    gesture short. Posted (sendEvent) events are never spontaneous."""
    _TYPES = {QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress,
              QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick,
              QEvent.Type.Enter, QEvent.Type.Leave, QEvent.Type.HoverMove}

    def eventFilter(self, obj, ev):
        return ev.spontaneous() and ev.type() in self._TYPES


@pytest.fixture
def be(qapp):
    """(view, scene) — shown Block Editor scene at 1 px / mm, centred."""
    sc = Model_Space(scene_role="block_editor")
    sc.scale_manager = ScaleManager()
    # A fixed scene rect: geometry moved mid-gesture never grows it, so the
    # view never re-scrolls under a posted gesture (exact deltas).
    sc.setSceneRect(-5000, -5000, 10000, 10000)
    v = Model_View(sc)
    v.resize(900, 700)
    v.show()
    QTest.qWaitForWindowExposed(v)
    v.resetTransform()
    v.centerOn(0, 0)
    sc.set_mode("select")
    sc._snap_enabled = False                 # raw deltas: exact expected geometry
    guard = _NoRealMouse()
    v.viewport().installEventFilter(guard)
    QApplication.processEvents()
    yield v, sc
    v.viewport().removeEventFilter(guard)
    sc.clearSelection()
    sc.cleanup()
    v.close()
    v.deleteLater()
    QApplication.processEvents()


# ── helpers ──────────────────────────────────────────────────────────────────

L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton


def _line(sc, a, b):
    ln = LineItem(QPointF(*a), QPointF(*b))
    sc.addItem(ln)
    sc._draw_lines.append(ln)
    return ln


def _rect(sc, a, b):
    r = RectangleItem(QPointF(*a), QPointF(*b))
    sc.addItem(r)
    sc._draw_rects.append(r)
    return r


def _send(v, etype, scene_pt, button, buttons):
    vp = QPointF(v.mapFromScene(QPointF(*scene_pt) if isinstance(scene_pt, tuple)
                                else scene_pt))
    gp = QPointF(v.viewport().mapToGlobal(vp.toPoint()))
    QApplication.sendEvent(v.viewport(), QMouseEvent(
        etype, vp, gp, button, buttons, Qt.KeyboardModifier.NoModifier))


def _press(v, p):
    _send(v, QEvent.Type.MouseMove, p, NB, NB)
    _send(v, QEvent.Type.MouseButtonPress, p, L, L)
    QApplication.processEvents()


def _move(v, p):
    _send(v, QEvent.Type.MouseMove, p, NB, L)
    QApplication.processEvents()


def _release(v, p):
    _send(v, QEvent.Type.MouseButtonRelease, p, L, NB)
    QApplication.processEvents()


def _esc(v):
    v.setFocus()
    QApplication.sendEvent(v.viewport(), QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    QApplication.processEvents()


def _grab(v):
    v.viewport().repaint()
    QApplication.processEvents()
    img = v.viewport().grab().toImage()
    return img, img.devicePixelRatio()


def _px(img, dpr, p) -> QColor:
    return img.pixelColor(int(round(p.x() * dpr)), int(round(p.y() * dpr)))


def _dist(a: QColor, b: QColor) -> int:
    return (abs(a.red() - b.red()) + abs(a.green() - b.green())
            + abs(a.blue() - b.blue()))


def _br(r):
    """The rect's bottom-right grip (index 4 = "br", spec §5.3), scene."""
    return QPointF(r.grip_points()[4])


def _glyph_drawn(v, rect) -> bool:
    """A glyph box is painted at *rect* (viewport px): its left border column
    reads ``line_strong`` (or a selection token) -- not the canvas."""
    img, dpr = _grab(v)
    t = th.detect()
    got = _px(img, dpr, QPointF(rect.left(), rect.center().y()))
    return min(_dist(got, t.color(tok)) for tok in
               ("line_strong", "selection", "selection_hover")) <= 24


def _constrained_rect_and_line(sc):
    """Rect (0,0)-(100,60) and a line whose p1 is H-tied to the rect's br."""
    r = _rect(sc, (0, 0), (100, 60))
    ln = _line(sc, (200, 60), (320, 20))
    c = sc.constraint_ctl.add("horizontal", [{"uid": r._uid, "h": "br"},
                                             {"uid": ln._uid, "h": "p1"}])
    assert c is not None
    QApplication.processEvents()
    assert abs(_br(r).y() - ln._pt1.y()) < 1e-6
    return r, ln, c


# ── D35: a constrained body drag applies live ───────────────────────────────

def test_constrained_body_drag_moves_the_partner_and_glyph_every_frame(be):
    v, sc = be
    r, ln, c = _constrained_rect_and_line(sc)
    ctl = sc.constraint_ctl
    r.setSelected(True)
    QApplication.processEvents()
    br0, p10, p20 = _br(r), QPointF(ln._pt1), QPointF(ln._pt2)
    g0 = dict(cp.glyph_layouts(v, ctl))[c.id]           # D32: rect selected
    grab = QPointF(25, 15)                              # interior, off every grip
    _press(v, grab)
    for k in range(1, 6):
        dy = 8.0 * k + 8.0                              # past the drag threshold
        _move(v, grab + QPointF(0, dy))
        # The real geometry moved (live, not a held transform). The dragged
        # selection is a W_EDIT goal (as in the release bake's edit seam), so
        # it yields ~1/W_EDIT of the partner's correction: 0.05 mm bar.
        assert r.transform().isIdentity()
        assert _br(r).y() == pytest.approx(br0.y() + dy, abs=0.05)
        assert _br(r).x() == pytest.approx(br0.x(), abs=0.05)
        # ... and the H-tied partner followed this frame.
        assert ln._pt1.y() == pytest.approx(_br(r).y(), abs=1e-6)
    # Mid-drag viewport: the glyph box moved with the geometry and is painted.
    g1 = dict(cp.glyph_layouts(v, ctl))[c.id]
    assert g1.center().y() - g0.center().y() == pytest.approx(48.0, abs=1.5)
    assert _glyph_drawn(v, g1)
    # Pixels: the line's moved end is inked; its old spot is canvas now.
    img, dpr = _grab(v)
    bg = _px(img, dpr, QPointF(v.mapFromScene(QPointF(-300, -250))))

    def _on_line(p1, p2, t=0.5):                    # clear of the move HUD
        return QPointF(v.mapFromScene(p1 + (p2 - p1) * t))
    def _ink(p):                                    # strongest ink in a 5x5 px window
        return max(_dist(_px(img, dpr, p + QPointF(i, j)), bg)
                   for i in range(-2, 3) for j in range(-2, 3))
    assert _ink(_on_line(QPointF(ln._pt1), QPointF(ln._pt2))) > 60
    assert _ink(_on_line(p10, p20)) <= 24
    _release(v, grab + QPointF(0, 48))


def test_constrained_body_drag_esc_restores_both_exactly(be):
    v, sc = be
    r, ln, _c = _constrained_rect_and_line(sc)
    r.setSelected(True)
    QApplication.processEvents()
    before = ([tuple((p.x(), p.y()) for p in r.grip_points())],
              (ln._pt1.x(), ln._pt1.y(), ln._pt2.x(), ln._pt2.y()))
    n_undo = len(sc._undo_stack)
    grab = QPointF(25, 15)                              # interior, off every grip
    _press(v, grab)
    for k in range(1, 4):
        _move(v, grab + QPointF(3.0 * k, 11.0 * k))
    assert ln._pt1.y() != pytest.approx(before[1][1])    # it was live
    _esc(v)
    after = ([tuple((p.x(), p.y()) for p in r.grip_points())],
             (ln._pt1.x(), ln._pt1.y(), ln._pt2.x(), ln._pt2.y()))
    assert after == before                               # exact, no tolerance
    assert len(sc._undo_stack) == n_undo
    _release(v, grab + QPointF(9, 33))                   # no dangling gesture
    assert not sc._live_manip().is_dragging()
    assert len(sc._undo_stack) == n_undo


def test_constrained_body_drag_release_is_one_undo_step(be):
    v, sc = be
    r, ln, _c = _constrained_rect_and_line(sc)
    r.setSelected(True)
    QApplication.processEvents()
    br0, p10 = _br(r), QPointF(ln._pt1)
    n_undo = len(sc._undo_stack)
    grab = QPointF(25, 15)                              # interior, off every grip
    _press(v, grab)
    for k in range(1, 6):
        _move(v, grab + QPointF(4.0 * k, 6.0 * k))
        if k >= 2:                                       # past the drag threshold
            assert ln._pt1.y() == pytest.approx(_br(r).y(), abs=1e-6)   # live
            assert ln._pt1.y() != pytest.approx(p10.y(), abs=1.0)
    _release(v, grab + QPointF(20, 30))
    # Not baked twice: the release left the last frame's geometry.
    assert _br(r).x() == pytest.approx(br0.x() + 20, abs=0.05)   # W_EDIT goal
    assert _br(r).y() == pytest.approx(br0.y() + 30, abs=0.05)
    assert ln._pt1.y() == pytest.approx(_br(r).y(), abs=1e-6)
    assert len(sc._undo_stack) == n_undo + 1             # ONE undo step
    sc.undo()
    QApplication.processEvents()
    (r2,) = sc._draw_rects                               # undo rebuilds items
    (l2,) = sc._draw_lines
    assert (_br(r2).x(), _br(r2).y()) == pytest.approx((br0.x(), br0.y()), abs=1e-9)
    assert (l2._pt1.x(), l2._pt1.y()) == pytest.approx((p10.x(), p10.y()), abs=1e-9)


def test_unconstrained_body_drag_keeps_the_held_transform_preview(be):
    """Parity (passes before and after D35): no constraint touches the
    selection -> geometry untouched mid-drag, the item carries the held
    transform, the release bakes once."""
    v, sc = be
    r, ln, _c = _constrained_rect_and_line(sc)
    free = _rect(sc, (0, -200), (100, -140))
    free.setSelected(True)
    QApplication.processEvents()
    g0 = [QPointF(p) for p in free.grip_points()]
    rect0 = free.rect()
    l0 = (QPointF(ln._pt1), QPointF(ln._pt2))
    n_undo = len(sc._undo_stack)
    grab = QPointF(25, -185)                            # interior, off every grip
    _press(v, grab)
    for k in range(1, 4):
        _move(v, grab + QPointF(0, 4.0 + 10.0 * k))         # past the threshold
        assert free.rect() == rect0                     # model geometry at rest
        assert not free.transform().isIdentity()        # the held preview
        assert (ln._pt1, ln._pt2) == l0
    _release(v, grab + QPointF(0, 34))
    assert free.transform().isIdentity()
    assert QPointF(free.grip_points()[0]).y() == pytest.approx(g0[0].y() + 34, abs=1e-6)
    assert len(sc._undo_stack) == n_undo + 1


@pytest.mark.perf
def test_d18_constrained_body_drag_frame_bar(be):
    """D18: one constrained body-drag mouse move (manipulator + session reset +
    bake + solve + reflow) on a modest sketch stays under the 8 ms bar."""
    v, sc = be
    lines = [_line(sc, (i * 30.0 - 600, 200.0), (i * 30.0 - 580, 210.0))
             for i in range(40)]
    ctl = sc.constraint_ctl
    recs = [{"id": f"h{i}", "type": "horizontal",
             "refs": [{"uid": ln._uid, "h": "edge"}]} for i, ln in enumerate(lines)]
    recs += [{"id": f"j{i}", "type": "horizontal",
              "refs": [{"uid": lines[i]._uid, "h": "p2"},
                       {"uid": lines[i + 1]._uid, "h": "p1"}]} for i in range(39)]
    ctl.load(recs)
    r, ln, _c = _constrained_rect_and_line(sc)
    r.setSelected(True)
    QApplication.processEvents()
    grab = QPointF(25, 15)                              # interior, off every grip
    _press(v, grab)
    _move(v, grab + QPointF(0, 5))
    ts = []
    for k in range(31):
        p = grab + QPointF(float(k % 5), 6.0 + float(k % 7))
        t = time.perf_counter()
        _send(v, QEvent.Type.MouseMove, p, NB, L)
        ts.append((time.perf_counter() - t) * 1e3)
        QApplication.processEvents()
    _release(v, p)
    med = sorted(ts)[len(ts) // 2]
    print(f"constrained body-drag frame median {med:.2f} ms")
    assert ln._pt1.y() == pytest.approx(_br(r).y(), abs=1e-6)
    assert med <= 8.0, f"body-drag frame {med:.2f} ms"


# ── D35: a box-native resize drag (tests-only: no constrainable block-editor
# primitive is box-native-scalable today) ────────────────────────────────────

def test_constrained_resize_drag_applies_live_and_esc_restores(be, monkeypatch):
    from firepro3d.text_item import TextItem
    v, sc = be
    ln = _line(sc, (200, 0), (320, -40))
    from firepro3d.text_item import TextAnnotationData
    tx = TextItem(TextAnnotationData(text="Label", x=0.0, y=0.0, height_mm=20.0))
    sc.addItem(tx)
    sc._texts.append(tx)
    # Make the text box-native scalable (the paper surface's capability).
    monkeypatch.setattr(TextItem, "manip_capabilities",
                        lambda self: {"translate", "scale", "rotate"})
    c = sc.constraint_ctl.add("horizontal", [{"uid": tx._uid, "h": "ins"},
                                             {"uid": ln._uid, "h": "p1"}])
    assert c is not None
    QApplication.processEvents()
    tx.setSelected(True)
    QApplication.processEvents()
    m = sc._live_manip()
    from firepro3d.manip_math import HandleRole
    h = m._handles[HandleRole.TOP_LEFT]
    assert h.isVisible()
    pos0, p10 = QPointF(tx.pos()), QPointF(ln._pt1)
    box0 = QPointF(tx.manip_bounds().width(), tx.manip_bounds().height())
    start = h.scenePos()
    _press(v, start)
    for k in range(1, 4):
        _move(v, start + QPointF(-6.0 * k, -9.0 * k))
        assert tx.transform().isIdentity()               # live, not held
        assert ln._pt1.y() == pytest.approx(tx.pos().y(), abs=1e-6)
    assert tx.pos().y() != pytest.approx(pos0.y())
    _esc(v)
    assert QPointF(tx.pos()) == pos0
    assert QPointF(ln._pt1) == p10
    b = tx.manip_bounds()
    assert (b.width(), b.height()) == pytest.approx((box0.x(), box0.y()), abs=1e-6)
    _release(v, start + QPointF(-18, -27))


# ── D32: glyph visibility follows the selection ─────────────────────────────

def _ids(v, ctl):
    return [cid for cid, _r in cp.glyph_layouts(v, ctl)]


def test_d32_glyphs_show_only_for_the_selection_or_show_all(be):
    v, sc = be
    t = th.detect()
    ln = _line(sc, (-100, 50), (100, 50))
    ln2 = _line(sc, (-100, 220), (100, 220))
    other = _line(sc, (-100, -150), (100, -150))         # unconstrained
    ctl = sc.constraint_ctl
    c = ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    c2 = ctl.add("horizontal", [{"uid": ln2._uid, "h": "edge"}])
    QApplication.processEvents()
    ctl.show_all = True
    at = dict(cp.glyph_layouts(v, ctl))                  # where each glyph sits
    assert set(at) == {c.id, c2.id}
    ctl.show_all = False
    img, dpr = _grab(v)
    bg = _px(img, dpr, QPointF(v.mapFromScene(QPointF(-300, -250))))
    assert _dist(bg, t.color("line_strong")) > 24        # precondition
    # Nothing selected -> no glyphs (layout, pick and pixels).
    assert _ids(v, ctl) == []
    assert cp.glyph_at(v, ctl, at[c.id].center()) is None
    assert not _glyph_drawn(v, at[c.id]) and not _glyph_drawn(v, at[c2.id])
    # Select the line -> its glyph only.
    ln.setSelected(True)
    QApplication.processEvents()
    assert _ids(v, ctl) == [c.id]
    assert _glyph_drawn(v, at[c.id]) and not _glyph_drawn(v, at[c2.id])
    # A different, unconstrained item -> none.
    sc.clearSelection()
    other.setSelected(True)
    QApplication.processEvents()
    assert _ids(v, ctl) == []
    assert not _glyph_drawn(v, at[c.id])
    # Click a visible glyph -> it is selected and stays shown.
    sc.clearSelection()
    ln.setSelected(True)
    QApplication.processEvents()
    gp = v.mapToScene(at[c.id].center().toPoint())   # a posted click
    _press(v, gp)
    _release(v, gp)
    assert ctl.selected_id == c.id and sc.selectedItems() == []
    assert _ids(v, ctl) == [c.id]
    assert _glyph_drawn(v, at[c.id]) and not _glyph_drawn(v, at[c2.id])
    # Show Constraints ON -> every glyph.
    ctl.clear_selected()
    ctl.show_all = True
    assert set(_ids(v, ctl)) == {c.id, c2.id}
    assert _glyph_drawn(v, at[c.id]) and _glyph_drawn(v, at[c2.id])
    # Pick mode -> none, even with Show Constraints ON (markers pick).
    sc.set_mode("constrain_horizontal")
    QApplication.processEvents()
    assert ctl.pick is not None
    assert _ids(v, ctl) == []
    assert cp.glyph_at(v, ctl, at[c2.id].center()) is None
    assert not _glyph_drawn(v, at[c.id]) and not _glyph_drawn(v, at[c2.id])
    sc.set_mode("select")


# ── VC9 F3: glyph layouts are computed once per drag frame ─────────────────

def test_f3_glyph_layouts_computed_once_per_grip_drag_frame(be, monkeypatch):
    v, sc = be
    ln = _line(sc, (-100, 50), (100, 50))
    sc.constraint_ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    ln.setSelected(True)
    QApplication.processEvents()
    calls = []
    real = cp._compute_layouts

    def _count(view, ctl):
        if view is v:
            calls.append(1)
        return real(view, ctl)
    monkeypatch.setattr(cp, "_compute_layouts", _count)
    p2 = QPointF(100, 50)                                 # the p2 end grip
    _press(v, p2)
    per_frame = []
    for k in range(1, 7):
        calls.clear()
        _send(v, QEvent.Type.MouseMove, p2 + QPointF(-4.0 * k, 12.0 + 6.0 * k), NB, L)
        QApplication.processEvents()                      # scene.changed + paint
        v.viewport().repaint()                            # one more paint: cached
        QApplication.processEvents()
        per_frame.append(len(calls))
    _release(v, p2 + QPointF(-24, 48))
    assert ln._pt1.y() == pytest.approx(ln._pt2.y(), abs=1e-6)   # it solved
    assert per_frame == [1] * 6, per_frame


# ── S1: a held-preview glyph follows the DRAWN geometry, never side-flips ───

def test_s1_glyph_follows_a_held_preview_on_one_side(be):
    """A suppressed constraint does not make the selection constrained, so
    its body drag keeps the held preview -- while D32 still shows the glyph."""
    v, sc = be
    ln = _line(sc, (-100, 50), (100, 50))
    ctl = sc.constraint_ctl
    c = ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    ctl.set_enabled(c.id, False)
    ln.setSelected(True)
    QApplication.processEvents()
    g0 = dict(cp.glyph_layouts(v, ctl))[c.id]
    mid0 = QPointF(v.mapFromScene(QPointF(0, 50)))
    assert g0.center().y() > mid0.y()                     # below the line at rest
    grab = QPointF(-50, 50)                               # on the line, off its grips
    _press(v, grab)
    for k in range(1, 5):
        dy = 12.0 + 7.0 * k
        _move(v, grab + QPointF(5.0, dy))
        assert not ln.transform().isIdentity()            # the held preview
        g = dict(cp.glyph_layouts(v, ctl))[c.id]
        drawn_mid = QPointF(v.mapFromScene(ln.mapToScene(QPointF(0, 50))))
        assert g.center().x() == pytest.approx(drawn_mid.x(), abs=1.0)
        assert g.center().y() - drawn_mid.y() == pytest.approx(
            g0.center().y() - mid0.y(), abs=1.0)          # same side, same offset
    _release(v, grab + QPointF(5.0, 40.0))


# ── VC9 F6: inert records paint dimmed with the one icon home ──────────────

def test_f6_inert_glyphs_are_dimmed_and_use_the_registry_icon(be, caplog):
    import logging
    v, sc = be
    t = th.detect()
    ln = _line(sc, (-100, 50), (100, 50))
    live = _line(sc, (-100, 220), (100, 220))
    ctl = sc.constraint_ctl
    ctl.restore([
        {"id": "u1", "type": "zz_future_kind", "refs": [{"uid": ln._uid, "h": "edge"}]},
        {"id": "h1", "type": "horizontal", "refs": [{"uid": live._uid, "h": "edge"}]},
    ])
    QApplication.processEvents()
    assert [x.inert for x in ctl.constraints] == [True, False]
    ctl.show_all = True
    at = dict(cp.glyph_layouts(v, ctl))
    caplog.set_level(logging.WARNING, logger="firepro3d.icons")
    img, dpr = _grab(v)
    border = t.color("line_strong")

    def _b(cid):
        return _px(img, dpr, QPointF(at[cid].left(), at[cid].center().y()))
    assert _dist(_b("h1"), border) <= 24                  # live glyph: full opacity
    bg = _px(img, dpr, QPointF(v.mapFromScene(QPointF(-300, -250))))
    # Dimmed at CONSTRAINT_INACTIVE_OPACITY: between the canvas and the border.
    a = M.CONSTRAINT_INACTIVE_OPACITY
    want = QColor(*(round(a * getattr(border, ch)() + (1 - a) * getattr(bg, ch)())
                    for ch in ("red", "green", "blue")))
    assert _dist(_b("u1"), want) <= 24, (_b("u1").name(), want.name())
    assert _dist(_b("u1"), border) > 24
    # The neutral icon, never the loader's silent _missing fallback.
    assert not [r for r in caplog.records if "not found" in r.getMessage()]
    assert sm.icon_for("zz_future_kind") == sm.NEUTRAL_ICON
    assert sm.icon_for("dim_radius") == sm.REGISTRY["dim_radius"].icon
    # The panel row of the inert record carries the same icon (muted).
    rows = ctl.panel_rows(ln)["rows"]
    assert len(rows) == 1 and rows[0]["muted"]
    assert rows[0]["icon"] is not None and not rows[0]["icon"].isNull()


def test_f6_glow_metrics_live_in_theme_m():
    from firepro3d import constraint_controller as cc
    assert (M.CONSTRAINT_GLOW_W_PX, M.CONSTRAINT_GLOW_ALPHA) == (7.0, 90)
    assert (M.CONSTRAINT_PICK_EDGE_GLOW_W_PX, M.CONSTRAINT_PICK_EDGE_GLOW_ALPHA) == (5.0, 140)
    assert not hasattr(cp, "GLOW_WIDTH_PX") and not hasattr(cp, "GLOW_ALPHA")
    assert cc.M is M


# ── VC9 F7: the constraint pick mode has its own cursor ────────────────────

def test_f7_constrain_pick_mode_shows_the_entity_pick_cursor(be):
    v, sc = be
    sc.set_mode("constrain_horizontal")
    QApplication.processEvents()
    assert v.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert v._mode_cursors["constrain_horizontal"] == v._mode_cursors["offset"]
    sc.set_mode("select")


# ── R5: solver noise in size / angle variables is never written ────────────

def _rect_exact(r):
    return (r._angle, r._pivot, r.rect().width(), r.rect().height())


def test_r5_axis_aligned_rect_stays_exactly_axis_aligned(be):
    """D34's translate-first pass leaves ~1e-8 noise in the stiff (size /
    angle) variables; write-back keeps each variable whose change is below
    its write tolerance, so a moved rect keeps angle 0, no pivot and its
    exact size -- through the add AND a live body drag."""
    v, sc = be
    r = _rect(sc, (0, 0), (200, 100))
    ln = _line(sc, (300, 0), (420, -40))
    c = sc.constraint_ctl.add("horizontal", [{"uid": r._uid, "h": "br"},
                                             {"uid": ln._uid, "h": "p1"}])
    assert c is not None
    QApplication.processEvents()
    assert abs(_br(r).y() - ln._pt1.y()) < 1e-6           # it solved (moved)
    assert _rect_exact(r) == (0.0, None, 200.0, 100.0)
    r.setSelected(True)
    QApplication.processEvents()
    grab = QPointF(_br(r).x() - 150, _br(r).y() - 70)     # interior, off grips
    _press(v, grab)
    for k in range(1, 5):
        _move(v, grab + QPointF(3.0 * k, 12.0 + 7.0 * k))
        assert ln._pt1.y() == pytest.approx(_br(r).y(), abs=1e-6)
        assert _rect_exact(r) == (0.0, None, 200.0, 100.0)
    _release(v, grab + QPointF(12.0, 40.0))
    assert _rect_exact(r) == (0.0, None, 200.0, 100.0)


# ── R1: D18 rect-heavy worst case (bench now, optimise later) ───────────────

def _rect_heavy(sc):
    """The VC9 re-review probe: one component of 100 rects + 100 lines tied
    by 299 Horizontal (derived-point rows, not substitutions)."""
    rs, ls = [], []
    for i in range(100):
        rs.append(_rect(sc, (i * 300, 0), (i * 300 + 200, 100)))
        ls.append(_line(sc, (i * 300 - 50, 0), (i * 300 - 80, 30)))
    recs = []
    for i in range(100):
        recs.append({"id": f"b{i}", "type": "horizontal",
                     "refs": [{"uid": rs[i]._uid, "h": "br"}, {"uid": ls[i]._uid, "h": "p1"}]})
        recs.append({"id": f"t{i}", "type": "horizontal",
                     "refs": [{"uid": rs[i]._uid, "h": "tl"}, {"uid": ls[i]._uid, "h": "p2"}]})
        if i < 99:
            recs.append({"id": f"c{i}", "type": "horizontal",
                         "refs": [{"uid": rs[i]._uid, "h": "tr"}, {"uid": rs[i + 1]._uid, "h": "tl"}]})
    sc.constraint_ctl.load(recs)
    assert len(sc.constraint_ctl.active()) == 299
    return rs, ls


@pytest.mark.perf
@pytest.mark.xfail(strict=True, reason=(
    "D18 rect-heavy worst case — perf follow-up before CS3 (vectorised derived "
    "rows, skip D34 second pass when no size/angle moves, no full-snapshot "
    "rewrite per frame)"))
def test_d18_rect_heavy_worst_case_drag_frames(qapp):
    """Grip-drag frame (ctl.drag) and D35 body-drag frame (ctl.drag_frame
    with the release bake's translate) on the rect-heavy component vs 8 ms."""
    from firepro3d.selection_manipulator import bake_translate
    sc = Model_Space(scene_role="block_editor")
    try:
        rs, _ls = _rect_heavy(sc)
        ctl = sc.constraint_ctl
        it = rs[50]
        ctl.begin_drag(it)
        grip = []
        for k in range(21):
            r = it.rect()
            it.setRect(r.x(), r.y(), r.width() + 0.3, r.height() + 0.2)
            t = time.perf_counter()
            ctl.drag(it, 4)
            grip.append((time.perf_counter() - t) * 1e3)
        ctl.end_drag()
        ctl.begin_drag([it])
        body = []
        for k in range(1, 22):
            d = 0.5 * k
            t = time.perf_counter()
            ctl.drag_frame([it], lambda: bake_translate(it, d, d), reset=True)
            body.append((time.perf_counter() - t) * 1e3)
        ctl.end_drag()
        g = sorted(grip)[len(grip) // 2]
        b = sorted(body)[len(body) // 2]
        print(f"rect-heavy grip-drag frame median {g:.2f} ms; "
              f"body-drag frame median {b:.2f} ms")
        assert g <= 8.0 and b <= 8.0, (g, b)
    finally:
        sc.cleanup()


@pytest.mark.perf
@pytest.mark.xfail(strict=True, reason="D18 rect-heavy: 299x900 dense J -- folded "
                   "into the P1 'D18 rect-heavy drag perf' task (user ruling 2026-10-02)")
def test_d18_rect_heavy_cs2_diagnostics(qapp):
    """D18: controller diagnostics (CS2 row basis + redundancy) on the
    rect-heavy one-component case vs the 50 ms commit bar. The bench
    compositions' commit bar (incl. diagnose) is test_sketch_solver_perf."""
    import time
    from firepro3d import sketch_solver as ss
    sc = Model_Space(scene_role="block_editor")
    try:
        _rect_heavy(sc)
        ctl = sc.constraint_ctl
        sys_, _slots, _w = ctl._build(ctl.active())
        st = ss._structure(sys_)
        assert max(len(c.rows) for c in st.comps) >= 250          # VC2: one big component
        ts = []
        for _ in range(7):
            ctl._commit_gen += 1                                  # force a recompute
            t = time.perf_counter()
            ctl.diagnostics()
            ts.append((time.perf_counter() - t) * 1e3)
        ms = sorted(ts)[len(ts) // 2]
        print(f"[rect-heavy] diagnostics {ms:.1f} ms")
        assert ms <= 50.0, f"diagnostics {ms:.1f} ms"
    finally:
        sc.cleanup()
