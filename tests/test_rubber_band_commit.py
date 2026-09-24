"""Band commit selects as ONE batch (one selectionChanged — per-item
setSelected was O(n^2): >10 min on 85k items), and there is no live band
preview (user decision 2026-09-24; selection-mode §6.3)."""
from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtGui import QMouseEvent, QTransform
from PyQt6.QtWidgets import QApplication, QGraphicsItem

from firepro3d import halo
from firepro3d.elevation_scene import _ElevProxyRect
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View


def test_rubber_band_hits_matches_commit(qapp):
    sc = Model_Space()
    inside = sc.add_node(5000.0, 5000.0)
    hits = sc.rubber_band_hits(QRectF(4800, 4800, 600, 600), crossing=False, dt=None)
    assert inside in hits
    sc.commit_rubber_band(QRectF(4800, 4800, 600, 600), crossing=False, additive=False)
    assert inside.isSelected()


def test_commit_emits_selection_changed_once(qapp):
    sc = Model_Space()
    lines = [LineItem(QPointF(i * 10, 0), QPointF(i * 10 + 5, 0)) for i in range(300)]
    for ln in lines:
        sc.addItem(ln)
    n = [0]
    sc.selectionChanged.connect(lambda: n.__setitem__(0, n[0] + 1))
    sc.commit_rubber_band(QRectF(-10, -10, 4000, 20), crossing=False, additive=False)
    assert all(ln.isSelected() for ln in lines)
    assert n[0] == 1


def test_additive_commit_keeps_prior_selection_one_emission(qapp):
    """Ctrl-band: additive=True keeps the prior selection and adds the band's
    hits, still as a single selectionChanged emission."""
    sc = Model_Space()
    prior = sc.add_node(-5000.0, -5000.0)
    prior.setSelected(True)
    inside = sc.add_node(5000.0, 5000.0)
    n = [0]
    sc.selectionChanged.connect(lambda: n.__setitem__(0, n[0] + 1))
    sc.commit_rubber_band(QRectF(4800, 4800, 600, 600), crossing=False, additive=True)
    assert prior.isSelected()
    assert inside.isSelected()
    assert n[0] == 1


def _drag(view, p1, p2):
    mk = lambda t, p: QMouseEvent(t, QPointF(*p), Qt.MouseButton.LeftButton,
                                  Qt.MouseButton.LeftButton,
                                  Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(view.viewport(), mk(QEvent.Type.MouseButtonPress, p1))
    QApplication.sendEvent(view.viewport(), mk(QEvent.Type.MouseMove, p2))


def test_band_drag_paints_no_halo_outlines(qapp, monkeypatch):
    sc = Model_Space()
    v = Model_View(sc)
    v.resize(600, 600); v.show(); QApplication.processEvents()
    sc.set_mode(None)
    sc.add_node(0.0, 0.0)
    calls = []
    monkeypatch.setattr(halo, "paint_halo_highlight",
                        lambda *a, **k: calls.append(a))
    _drag(v, (50, 50), (550, 550))
    v.viewport().repaint()
    assert v._rb_active and calls == []       # band live, nothing previewed


def test_escape_during_band_cancels(qapp):
    """Escape ladder's band-cancel rung still cancels the band (no preview
    to clear any more — adapted from the deleted test_rubber_band_preview.py)."""
    sc = Model_Space()
    v = Model_View(sc)
    v.resize(600, 600); v.show(); QApplication.processEvents()
    sc.set_mode(None)
    sc.add_node(0.0, 0.0)
    _drag(v, (50, 50), (550, 550))
    assert v._rb_active
    sc._escape_ladder()
    assert v._rb_active is False


def test_elevation_commit_emits_selection_changed_once(qapp, elevation_scene_for):
    _ms, elev = elevation_scene_for("north")
    proxies = []
    for i in range(50):
        r = _ElevProxyRect(i * 10, 0, 5, 5)
        r.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        elev.addItem(r)
        proxies.append(r)
    n = [0]
    elev.selectionChanged.connect(lambda: n.__setitem__(0, n[0] + 1))
    elev.commit_rubber_band(QRectF(-10, -10, 600, 20), crossing=False, additive=False)
    assert all(p.isSelected() for p in proxies)
    assert n[0] == 1
