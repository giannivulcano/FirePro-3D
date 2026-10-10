"""ET1 G6 -- a view zoom re-prepares exactly the items that drew a
Fixed-size end, so their scene bounds follow the zoom (spec C)."""
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QTransform, QWheelEvent

from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from tests.lt5_support import arrow, set_ends


def _view(ms, zoom):
    v = Model_View(ms)
    v.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    v.resize(400, 400)
    v.setTransform(v.transform().fromScale(zoom, zoom))
    v.show()
    v.centerOn(1000, 0)
    return v


def _wheel(v, up):
    pos = QPointF(200.0, 200.0)
    ev = QWheelEvent(pos, v.mapToGlobal(pos.toPoint()).toPointF(), QPoint(0, 0),
                     QPoint(0, 120 if up else -120), Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    v.wheelEvent(ev)


def _scene(screen):
    ms = Model_Space()
    a = arrow(length=3.0, half=1.0, screen=screen)
    ms.register_block_definition(a)
    ln = LineItem(QPointF(0.0, 0.0), QPointF(2000.0, 0.0))
    set_ends(ln, finish=a.id)
    ms.addItem(ln)
    ms._draw_lines.append(ln)
    return ms, ln


def _dirty(ms):
    """Collect the scene's own repaint requests (QGraphicsScene.changed)."""
    out = []
    ms.changed.connect(lambda rects: out.extend(QRectF(r) for r in rects))
    return out


def test_g6_zoom_out_grows_fixed_size_end_bounds(qapp):
    ms, ln = _scene("fixed")
    v = _view(ms, 1.0)
    try:
        v.viewport().repaint()
        qapp.processEvents()
        assert ln in ms._screen_end_items                       # the paint marked it
        before = ln.boundingRect().height()                     # 18 px / 1 px/mm = ~18 mm + pen
        dirty = _dirty(ms)
        for _ in range(12):
            _wheel(v, up=False)                                 # zoom out
        qapp.processEvents()
        after = ln.boundingRect().height()
        assert after > before * 2, (before, after)              # recomputed at the new zoom
        far_tip = QRectF(1990.0, -after / 2.0, 20.0, after)
        assert ln in ms.items(far_tip)                          # the scene sees the new extent
        # The zoom hook's prepareGeometryChange is what makes Qt invalidate
        # the item's area: the scene requests a repaint covering the grown
        # end (without the hook the zoom dirties nothing -- the stale-bounds
        # trail of spec C).
        new_extent = ln.sceneBoundingRect()
        assert any(r.contains(new_extent) for r in dirty), dirty
    finally:
        v.close()


def test_g6_tab_switch_re_prepares_for_the_shown_view(qapp):
    """Plan / detail / Block Editor tabs are separate views on one scene and
    bounds read the visible view's zoom: re-showing a view (a tab switch)
    re-prepares the Fixed-size-end items at that view's zoom."""
    ms, ln = _scene("fixed")
    a = _view(ms, 1.0)
    b = _view(ms, 1.0)                  # both shown once: first-show fit consumed
    try:
        a.setTransform(QTransform.fromScale(1.0, 1.0))
        a.centerOn(1000, 0)
        b.setTransform(QTransform.fromScale(0.05, 0.05))
        b.centerOn(1000, 0)
        b.hide()
        a.viewport().repaint()
        qapp.processEvents()
        assert ln in ms._screen_end_items                       # A's paint marked it
        before = ln.sceneBoundingRect().height()
        a.hide()
        dirty = _dirty(ms)
        b.show()                                                # the tab switch
        qapp.processEvents()
        after = ln.sceneBoundingRect()
        assert after.height() > before * 2, (before, after)     # B's zoom (live)
        far_tip = QRectF(1990.0, after.center().y() - 1.0, 20.0, 2.0)
        assert ln in ms.items(far_tip)
        # The show hook's prepareGeometryChange invalidates the grown extent.
        assert any(r.contains(after) for r in dirty), dirty
    finally:
        a.close()
        b.close()


def test_g6_fit_notifies_the_scene(qapp):
    """Every fit path (fit_to_screen, fit_scene_rect, a direct fitInView from
    the detail-view / model-browser callers) reaches the zoom hook."""
    ms, ln = _scene("fixed")
    v = _view(ms, 1.0)
    calls = []
    ms.view_zoom_changed = lambda: calls.append(1)
    try:
        v.fit_to_screen()
        v.fit_scene_rect(QRectF(0.0, -100.0, 50000.0, 200.0))
        v.fitInView(QRectF(0.0, -100.0, 100.0, 200.0))
        assert len(calls) == 3, calls
    finally:
        v.close()


def test_g6_scale_with_zoom_registers_nothing(qapp):
    ms, ln = _scene("scale")
    v = _view(ms, 1.0)
    try:
        v.viewport().repaint()
        qapp.processEvents()
        assert ln not in ms._screen_end_items
        dirty = _dirty(ms)
        for _ in range(3):
            _wheel(v, up=False)                                 # zoom: nothing re-prepared
        ms.view_zoom_changed()                                  # no-op, no error
        qapp.processEvents()
        own = ln.sceneBoundingRect()
        assert not any(r.intersects(own) for r in dirty), dirty  # cost bounded (spec C)
    finally:
        v.close()


def test_g6_dead_wrapper_is_dropped(qapp):
    """A registered item whose C++ object was deleted while a Python ref
    survives must not break the zoom hook; the dead entry is discarded."""
    from PyQt6 import sip
    ms, ln = _scene("fixed")
    ms._screen_end_items.add(ln)
    ms.removeItem(ln)
    ms._draw_lines.remove(ln)
    sip.delete(ln)
    assert sip.isdeleted(ln) and ln in ms._screen_end_items
    ms.view_zoom_changed()                                      # no RuntimeError
    assert ln not in ms._screen_end_items


def test_g6_scene_reset_empties_the_registry(qapp):
    """New / Open (``_clear_scene``) drops every registered item."""
    ms, ln = _scene("fixed")
    ms._screen_end_items.add(ln)
    keep = ln                                                   # Python ref outlives the reset
    ms._clear_scene()
    assert len(ms._screen_end_items) == 0, keep
