"""Per-call snap memo (L1070): scene.items + view zoom pinned for ONE find only."""
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from firepro3d import view_scale
from firepro3d.geometry_2d import LineItem
from firepro3d.snap_engine import SnapEngine


def _scene_with_line(qapp, p1, p2):
    sc = QGraphicsScene()
    ln = LineItem(QPointF(*p1), QPointF(*p2))
    sc.addItem(ln)
    v = QGraphicsView(sc)            # headless: scene_view_scale reads the last view
    return sc, v, ln


def test_items_memo_is_one_query_per_rect_and_not_kept(qapp, monkeypatch):
    sc, v, ln = _scene_with_line(qapp, (0, 0), (100, 0))
    calls = []
    orig = QGraphicsScene.items

    def spy(self, *a):
        calls.append(a)
        return orig(self, *a)
    monkeypatch.setattr(QGraphicsScene, "items", spy)
    eng = SnapEngine()
    r = eng.find(QPointF(100.5, 0.5), sc, QTransform())
    assert r is not None and r.snap_type == "endpoint"
    rect_calls = [a for a in calls if a and hasattr(a[0], "width")]
    assert rect_calls                                    # the spy saw the queries
    keys = {(a[0].x(), a[0].y(), a[0].width(), a[0].height(), a[1])
            for a in rect_calls}
    assert len(rect_calls) == len(keys)                  # one query per distinct rect
    assert eng._items_memo is None                       # memo dropped after the call


def test_memo_does_not_leak_between_finds(qapp):
    sc, v, ln = _scene_with_line(qapp, (0, 0), (100, 0))
    eng = SnapEngine()
    assert eng.find(QPointF(100.5, 0.5), sc, QTransform()).snap_type == "endpoint"
    sc.removeItem(ln)                                    # move the endpoint away
    sc.addItem(LineItem(QPointF(0, 0), QPointF(300, 0)))
    r = eng.find(QPointF(300.5, 0.5), sc, QTransform())
    assert r is not None and abs(r.point.x() - 300.0) < 1e-6


def test_held_view_scale_pins_then_releases(qapp):
    sc, v, ln = _scene_with_line(qapp, (0, 0), (100, 0))
    v.setTransform(QTransform.fromScale(2.0, 2.0))
    with view_scale.held_view_scale(sc):
        v.setTransform(QTransform.fromScale(4.0, 4.0))
        assert view_scale.scene_view_scale(sc) == 2.0     # pinned
    assert view_scale.scene_view_scale(sc) == 4.0         # released
