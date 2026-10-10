"""ET1 seam fix 6 -- a fresh cut end (Trim / Break / Fillet / Chamfer reset
it to By Linetype, LT2-3) drops its per-use Scale; the untouched physical
end keeps it, and ``mirrored`` stays as LT5 ratified (untouched)."""
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _scaled(item):
    item.style["start"] = {"end": "end-marker", "visible": True,
                           "mirrored": True, "scale": 2.0}
    item.style["finish"] = {"end": "end-marker", "visible": True,
                            "mirrored": True, "scale": 3.0}
    return item


def test_break_cut_ends_drop_scale(qapp):
    """copy_style(fresh_ends=...) path (Break / Fillet / Chamfer derive)."""
    ms = Model_Space(scene_role="block_editor")
    ln = _scaled(LineItem(QPointF(0, 0), QPointF(100, 0)))
    ms.addItem(ln); ms._draw_lines.append(ln)
    ms._tools._break_item(ln, QPointF(40, 0), QPointF(60, 0))
    l1, l2 = ms._draw_lines
    assert l1.style["finish"]["end"] == "by_linetype"
    assert "scale" not in l1.style["finish"], l1.style["finish"]
    assert l1.style["finish"].get("mirrored") is True          # LT5: untouched
    assert l2.style["start"]["end"] == "by_linetype"
    assert "scale" not in l2.style["start"], l2.style["start"]
    assert l1.style["start"]["scale"] == 2.0                   # physical ends keep it
    assert l2.style["finish"]["scale"] == 3.0


def test_trim_cut_end_drops_scale(qapp):
    """_fresh_end path: the real two-phase trim click flow, in place."""
    from tests._snap_polish_helpers import click, close_view, make_view
    view, scene = make_view(scale=1.0, mode=None)
    try:
        ln = _scaled(LineItem(QPointF(0, 0), QPointF(100, 0)))
        scene.addItem(ln); scene._draw_lines.append(ln)
        edge = LineItem(QPointF(50, -100), QPointF(50, 100))
        scene.addItem(edge); scene._draw_lines.append(edge)
        scene.set_mode("trim")
        click(view, QPointF(50, 80))                            # cutting edge
        click(view, QPointF(10, 0))                             # piece to remove
        assert ln.style["start"]["end"] == "by_linetype"
        assert "scale" not in ln.style["start"], ln.style["start"]
        assert ln.style["start"].get("mirrored") is True
        assert ln.style["finish"] == {"end": "end-marker", "visible": True,
                                      "mirrored": True, "scale": 3.0}
    finally:
        close_view(view, scene)
