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











# ── D35: a box-native resize drag (tests-only: no constrainable block-editor
# primitive is box-native-scalable today) ────────────────────────────────────



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
