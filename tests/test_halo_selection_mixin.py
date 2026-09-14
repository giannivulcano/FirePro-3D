"""HaloSelectionMixin: scene-agnostic ranking/band with overridable hooks."""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsRectItem, QGraphicsItem
from firepro3d.halo_selection import HaloSelectionMixin


class _Scene(HaloSelectionMixin, QGraphicsScene):
    def __init__(self):
        QGraphicsScene.__init__(self)
        self._init_halo_state()


def _sel_rect(x, y):
    r = QGraphicsRectItem(x, y, 10, 10)
    r.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    return r


def test_defaults_identity_resolve_and_no_underlay(qapp):
    s = _Scene()
    r = _sel_rect(0, 0)
    assert s._halo_resolve(r) is r          # identity default
    assert s._halo_is_underlay(r) is False  # no-underlay default
    assert s._halo_mode_ok() is True        # no tool modes default


def test_rank_orders_by_z_then_distance(qapp):
    s = _Scene()
    lo, hi = _sel_rect(0, 0), _sel_rect(0, 0)
    lo.setZValue(1); hi.setZValue(5)
    s.addItem(lo); s.addItem(hi)
    ranked = s.halo_rank([lo, hi], QPointF(5, 5))
    assert ranked[0] is hi                   # higher Z first


def test_rubber_band_hits_window_vs_crossing(qapp):
    s = _Scene()
    inside = _sel_rect(10, 10)               # fully inside 0..100
    straddle = _sel_rect(90, 90)             # crosses the edge
    s.addItem(inside); s.addItem(straddle)
    band = QRectF(0, 0, 100, 100)
    assert set(s.rubber_band_hits(band, crossing=False)) == {inside}
    assert set(s.rubber_band_hits(band, crossing=True)) == {inside, straddle}


def test_paint_rubber_band_is_callable(qapp):
    from firepro3d.halo import paint_rubber_band
    assert callable(paint_rubber_band)
