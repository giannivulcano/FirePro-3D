"""U5 Leg B Task 5 — HALO hover + scene-drawn band + HALO-committed press.

Drives the real ElevationView interaction envelope with posted QMouseEvents on
a SHOWN view (mirrors tests/test_rubber_band_select.py's posted-drag helper).
Asserts observable ground truth (scene.halo_item(), scene.selectedItems()).
Never QTest.mouseMove.
"""
from PyQt6.QtCore import QPointF, QEvent, Qt
from PyQt6.QtGui import QColor, QMouseEvent
from PyQt6.QtWidgets import QApplication, QGraphicsItem

from firepro3d.elevation_scene import ElevGridlineItem, _ElevProxyRect
from firepro3d.elevation_view import ElevationView


# ── helpers ────────────────────────────────────────────────────────────────

def _grid(label="A", h=100.0):
    return ElevGridlineItem(h, -50.0, 50.0, label, 20.0,
                            QColor("#888"), QColor("#fff"), 1.0)


def _proxy(x, y, w, h):
    r = _ElevProxyRect(x, y, w, h)
    r.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    return r


def _shown_view(elevation_scene_for):
    _ms, elev = elevation_scene_for("north")
    view = ElevationView(elev)
    view.resize(600, 600)
    view.show()
    QApplication.processEvents()
    return elev, view


def _post(view, etype, vp_pt, mods=Qt.KeyboardModifier.NoModifier,
          btn=Qt.MouseButton.LeftButton):
    ev = QMouseEvent(etype, QPointF(*vp_pt), btn, btn, mods)
    QApplication.sendEvent(view.viewport(), ev)


def _move(view, vp_pt):
    _post(view, QEvent.Type.MouseMove, vp_pt, btn=Qt.MouseButton.NoButton)


def _click(view, vp_pt, ctrl=False):
    mods = (Qt.KeyboardModifier.ControlModifier if ctrl
            else Qt.KeyboardModifier.NoModifier)
    _post(view, QEvent.Type.MouseButtonPress, vp_pt, mods)
    _post(view, QEvent.Type.MouseButtonRelease, vp_pt, mods)


def _drag(view, vp_start, vp_end, ctrl=False):
    mods = (Qt.KeyboardModifier.ControlModifier if ctrl
            else Qt.KeyboardModifier.NoModifier)
    _post(view, QEvent.Type.MouseButtonPress, vp_start, mods)
    _post(view, QEvent.Type.MouseMove, vp_end, mods)
    _post(view, QEvent.Type.MouseButtonRelease, vp_end, mods)


def _vp(view, scene_pt):
    """Viewport-px point for a scene coordinate on the shown view."""
    p = view.mapFromScene(QPointF(*scene_pt))
    return (p.x(), p.y())


# ── HALO hover ──────────────────────────────────────────────────────────────

def test_hover_highlights_top_ranked(qapp, elevation_scene_for):
    elev, view = _shown_view(elevation_scene_for)
    g = _grid(h=100.0)
    elev.addItem(g)
    # Fit so the gridline is comfortably on screen, then hover over its body.
    view.fit_to_screen()
    QApplication.processEvents()
    _move(view, _vp(view, (100.0, 0.0)))
    assert elev.halo_item() is g


# ── HALO-committed click ─────────────────────────────────────────────────────

def test_click_commits_halo_item(qapp, elevation_scene_for):
    elev, view = _shown_view(elevation_scene_for)
    g = _grid(h=100.0)
    elev.addItem(g)
    view.fit_to_screen()
    QApplication.processEvents()
    _move(view, _vp(view, (100.0, 0.0)))
    _click(view, _vp(view, (100.0, 0.0)))
    assert elev.selectedItems() == [g]


def test_empty_click_deselects(qapp, elevation_scene_for):
    elev, view = _shown_view(elevation_scene_for)
    g = _grid(h=100.0)
    elev.addItem(g)
    g.setSelected(True)
    view.fit_to_screen()
    QApplication.processEvents()
    # Click on empty canvas (corner) → deselect.
    _move(view, (5, 5))
    _click(view, (5, 5))
    assert elev.selectedItems() == []


def test_ctrl_click_toggles(qapp, elevation_scene_for):
    """Ctrl+click routes through the HALO-commit press and universally toggles.

    Two well-separated gridlines: plain-click A (selects A, frame at A), then
    Ctrl+click B — B's click point is OUTSIDE A's frame, so the scene HALO-commit
    runs and adds B additively. This exercises the Ctrl-toggle ADD path through
    the real posted-event envelope. (Toggle-OFF of a framed item is consumed by
    the frame's move gesture — the shared plan-scene manipulator contract — so it
    is not asserted here via a full click.)"""
    elev, view = _shown_view(elevation_scene_for)
    a = _grid(label="A", h=1000.0)
    b = _grid(label="B", h=9000.0)
    elev.addItem(a)
    elev.addItem(b)
    view.fit_to_screen()
    QApplication.processEvents()
    pa = _vp(view, (1000.0, 0.0))
    pb = _vp(view, (9000.0, 0.0))

    _move(view, pa)
    _click(view, pa)                    # plain click selects A only
    assert a.isSelected() and not b.isSelected()

    _move(view, pb)
    _click(view, pb, ctrl=True)         # Ctrl+click adds B (A stays selected)
    assert a.isSelected() and b.isSelected()


def test_ctrl_click_toggles_off_via_scene(qapp, elevation_scene_for):
    """Ctrl-toggle REMOVE path, driven at the scene press with the manipulator
    hidden so the frame does not intercept (the frame-move interception is a
    separate, tested contract). Confirms the HALO-commit press removes a
    selected item on Ctrl+click."""
    elev, view = _shown_view(elevation_scene_for)
    g = _grid(label="A", h=100.0)
    elev.addItem(g)
    view.fit_to_screen()
    QApplication.processEvents()
    g.setSelected(True)
    elev._live_manip().hide()           # so on_manip is False → HALO-commit runs

    pt = _vp(view, (100.0, 0.0))
    _move(view, pt)
    _click(view, pt, ctrl=True)         # Ctrl+click a selected item → deselect
    assert not g.isSelected()


# ── Window vs crossing band ─────────────────────────────────────────────────

def test_window_vs_crossing_band(qapp, elevation_scene_for):
    elev, view = _shown_view(elevation_scene_for)
    inside = _proxy(1000, 1000, 500, 500)       # fully inside a big band
    straddle = _proxy(4800, 1000, 800, 500)      # crosses the band's right edge
    elev.addItem(inside)
    elev.addItem(straddle)
    view.fit_to_screen()
    QApplication.processEvents()

    # Window: L->R drag from empty top-left to a point inside the band that
    # contains `inside` but only clips `straddle`.
    tl = _vp(view, (500, 500))
    br = _vp(view, (5000, 2000))     # right edge cuts through straddle
    _drag(view, tl, br)              # L->R = window
    sel = set(elev.selectedItems())
    assert inside in sel
    assert straddle not in sel

    elev.clearSelection()

    # Crossing: R->L drag over the same region → straddle included (intersect).
    _drag(view, br, tl)              # R->L = crossing
    sel = set(elev.selectedItems())
    assert straddle in sel
