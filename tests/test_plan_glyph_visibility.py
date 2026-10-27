"""R-V1: a constraint glyph / dim paints, hovers and picks only when every
item it references is visible (hidden level -> hidden glyph)."""
from __future__ import annotations

from PyQt6.QtCore import QPointF

from firepro3d import constraint_paint as cp
from tests.test_build_editor_tabs import _editors, _plan_index, mw  # noqa: F401
from tests.test_plan_constraints_e2e import _wall, plan  # noqa: F401


def _hide_level2(mw, qapp, *walls):
    mw.level_mgr.add_level("Level 2", elevation=20000.0)
    for w in walls:
        w._base_level = w._top_level = w.level = "Level 2"
    mw._apply_plan_level("Level 1")
    qapp.processEvents()


def _cleanup(mw, ctl):
    ctl.show_all = False
    mw.level_mgr.remove_level("Level 2")
    mw._apply_plan_level("Level 1")


def _ids(view, ctl):
    return [cid for cid, _r in cp.glyph_layouts(view, ctl)]


def test_hidden_wall_glyph_not_painted_hovered_or_picked(mw, plan, qapp):
    sc, view = plan
    ctl = sc.constraint_ctl
    hid = _wall(sc, (0, 0), (3000, 0))
    vis = _wall(sc, (0, 1000), (3000, 1000))
    try:
        c_hid = ctl.add("horizontal", [{"uid": hid._uid, "h": "edge"}])
        c_vis = ctl.add("horizontal", [{"uid": vis._uid, "h": "edge"}])
        ctl.show_all = True
        qapp.processEvents()
        before = {cid: r for cid, r in cp.glyph_layouts(view, ctl)}
        assert c_hid.id in before and c_vis.id in before      # cache warmed while visible
        _hide_level2(mw, qapp, hid)
        assert not hid.isVisible() and vis.isVisible()
        ids = _ids(view, ctl)
        assert c_hid.id not in ids, "hidden wall's glyph still painted"
        assert c_vis.id in ids, "visible wall's glyph lost (positive control)"
        p = before[c_hid.id].center().toPoint()
        assert cp.glyph_at(view, ctl, p) != c_hid.id, "hidden glyph still picks"
    finally:
        _cleanup(mw, ctl)


def test_mixed_visible_hidden_constraint_is_hidden(mw, plan, qapp):
    sc, view = plan
    ctl = sc.constraint_ctl
    hid = _wall(sc, (0, 0), (3000, 0))
    vis = _wall(sc, (3000, 0), (3000, 2000))
    try:
        c = ctl.add("coincident", [{"uid": vis._uid, "h": "p1"},
                                   {"uid": hid._uid, "h": "p2"}])
        assert c is not None
        ctl.show_all = True
        _hide_level2(mw, qapp, hid)
        assert c.id not in _ids(view, ctl)
        vis.setSelected(True)                                  # selection path too
        ctl.show_all = False
        qapp.processEvents()
        assert c.id not in _ids(view, ctl)
    finally:
        sc.clearSelection()
        _cleanup(mw, ctl)


def test_dim_on_hidden_wall_not_drawn_or_picked(mw, plan, qapp):
    sc, view = plan
    ctl = sc.constraint_ctl
    hid = _wall(sc, (0, 0), (3000, 0))
    try:
        d = ctl.add("dim_distance", [{"uid": hid._uid, "h": "p1"},
                                     {"uid": hid._uid, "h": "p2"}])
        assert d is not None
        ctl.show_all = True
        qapp.processEvents()
        assert d.id in cp.visible_dim_ids(ctl, set())          # shows while visible
        _hide_level2(mw, qapp, hid)
        assert d.id not in cp.visible_dim_ids(ctl, set())
        mid = view.mapFromScene(QPointF(1500, 0))
        assert cp.dim_at(view, ctl, mid) != d.id
    finally:
        _cleanup(mw, ctl)
