"""LT5 user ruling 2026-10-08 -- a stroke that becomes closed drops its
explicit end ids (to By Linetype) in the SAME undo step as the close;
``visible`` / ``mirrored`` are kept. Observable: the end block becomes
deletable, and one undo restores the open stroke WITH its end."""
from PyQt6.QtCore import QPointF

from firepro3d import stroke_style as ss
from firepro3d.geometry_2d import ArcItem, PolylineItem, SplineItem
from firepro3d.model_space import Model_Space
from firepro3d.sketch_adapters import adapter_for
from tests.lt5_support import end_id

_REC = {"end": None, "visible": False, "mirrored": True}


def _stamp(item, a):
    item.style["finish"] = {**_REC, "end": a}
    item.style["start"] = {"end": ss.NONE, "visible": True}


def _closed_then_delete_then_undo(ms, item, lst, a, close):
    ms.addItem(item)
    getattr(ms, lst).append(item)
    _stamp(item, a)
    ms.push_undo_state()
    assert ms.block_users_message(a) is not None        # used while open
    close(item)
    ms.push_undo_state()                                 # the close's one step
    (it,) = getattr(ms, lst)
    assert it.is_closed()
    assert it.style["finish"] == {"end": ss.BY_LINETYPE, "visible": False,
                                  "mirrored": True}
    assert it.style["start"] == {"end": ss.NONE, "visible": True}
    assert ms.delete_block_definition(a) is True         # no longer a use
    ms.undo()                                            # the delete
    ms.undo()                                            # the close
    (it,) = getattr(ms, lst)
    assert not it.is_closed()
    assert it.style["finish"] == {**_REC, "end": a}      # the Arrow is back
    assert ms.get_block_definition(a) is not None


def test_polyline_close_clears_explicit_ends_in_one_step(qapp):
    ms = Model_Space()
    a = end_id(ms, name="Arrow")
    pl = PolylineItem(QPointF(0, 0))
    pl.append_point(QPointF(100, 0))
    pl.append_point(QPointF(100, 100))
    _closed_then_delete_then_undo(ms, pl, "_polylines", a, lambda it: it.close())


def test_arc_solved_to_360_clears_explicit_ends(qapp):
    """The sketch solver's arc write (te == ts -> span 360) is the arc's
    real open -> closed path (typed / grip spans clamp below 360)."""
    ms = Model_Space()
    a = end_id(ms, name="Arrow")
    arc = ArcItem(QPointF(0, 0), 50.0, 0.0, 90.0)

    def close(it):
        ad = adapter_for(it)
        cx, cy, r, ts, _te = ad.read(it)
        ad.write(it, [cx, cy, r, ts, ts])

    _closed_then_delete_then_undo(ms, arc, "_draw_arcs", a, close)


def test_spline_end_grip_onto_start_clears_explicit_ends(qapp):
    ms = Model_Space()
    a = end_id(ms, name="Arrow")
    sp = SplineItem([QPointF(0, 0), QPointF(50, 50), QPointF(100, 0),
                     QPointF(150, 50)])
    _closed_then_delete_then_undo(
        ms, sp, "_draw_splines", a,
        lambda it: it.apply_grip(3, QPointF(0, 0)))


def test_open_edits_keep_explicit_ends(qapp):
    ms = Model_Space()
    a = end_id(ms, name="Arrow")
    arc = ArcItem(QPointF(0, 0), 50.0, 0.0, 90.0)
    _stamp(arc, a)
    arc.set_span(359.0)
    sp = SplineItem([QPointF(0, 0), QPointF(50, 50), QPointF(100, 0)])
    _stamp(sp, a)
    sp.apply_grip(2, QPointF(120, 10))
    assert arc.style["finish"]["end"] == a and sp.style["finish"]["end"] == a
