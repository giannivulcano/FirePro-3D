"""Gridline Auto Constrain R7: the default 3V+3H seed (startup + New Project,
MainWindow._place_default_gridlines) opens auto-constrained and the records
survive save / reopen.

Driven through File > New; startup shares ``_place_default_gridlines`` (one
join line covers both), and its own undo reset is covered only indirectly."""
from __future__ import annotations

from collections import Counter

from PyQt6.QtCore import QSettings

from firepro3d.constants import AUTO_CONSTRAIN_KEY
from firepro3d.model_space import Model_Space
from tests.test_build_editor_tabs import mw  # noqa: F401


def _reseed(mw):
    """File > New through the real entry point (no save prompt when clean)."""
    mw._modified = False
    mw.new_file()
    return mw.scene


def test_g6_seed_has_hv_and_chained_spacing(mw, qapp, tmp_path):
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, True)
    try:
        sc = _reseed(mw)
    finally:
        QSettings("GV", "FirePro3D").remove(AUTO_CONSTRAIN_KEY)
    cons = sc.constraint_ctl.constraints
    assert len(sc._gridlines) == 6
    # The joined seed is the undo baseline: Ctrl+Z never exposes it un-joined.
    assert (len(sc._undo_stack), sc._undo_pos) == (1, 0)
    sc.undo()
    assert len(sc._gridlines) == 6 and len(sc.constraint_ctl.constraints) == 12
    cons = sc.constraint_ctl.constraints
    assert Counter(c.type for c in cons) == {
        "vertical": 3, "horizontal": 3, "dim_point_line": 4,
        "point_on_curve": 2}
    # Smoke ruling (2026-10-28): 1 and A carry the origin on their line.
    label_of = {g._uid: g.grid_label for g in sc._gridlines}
    ties = {label_of[c.refs[1]["uid"]] for c in cons
            if c.type == "point_on_curve" and c.refs[0] == {"ref": "origin"}
            and c.refs[1]["h"] == "edge"}
    assert ties == {"1", "A"}
    by_label = {g._uid: g.grid_label for g in sc._gridlines}
    pairs = {frozenset(by_label[r["uid"]] for r in c.refs)
             for c in cons if c.type == "dim_point_line"}
    assert pairs == {frozenset("12"), frozenset("23"),
                     frozenset("AB"), frozenset("BC")}
    # Each spacing dim holds its pair's real separation (vertical pair: x;
    # horizontal pair: y), read off the placed geometry.
    by_uid = {g._uid: g for g in sc._gridlines}
    for c in cons:
        if c.type != "dim_point_line":
            continue
        g0, g1 = (by_uid[r["uid"]] for r in c.refs)
        sep = (abs(g0._origin.x() - g1._origin.x()) if g0.grid_label.isdigit()
               else abs(g0._origin.y() - g1._origin.y()))
        assert sep > 0 and abs(c.value - sep) < 1e-6
    assert all(c.driving for c in cons if c.type == "dim_point_line")
    assert not sc.constraint_ctl.red
    f = tmp_path / "seed.fpd"
    sc.save_to_file(str(f))
    b = Model_Space()
    try:
        b.load_from_file(str(f))
        assert [c.to_dict() for c in b.constraint_ctl.constraints] == \
            [c.to_dict() for c in cons]
    finally:
        b.cleanup()


def test_g6_origin_tie_holds_1_when_its_spacing_is_edited(mw, qapp):
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, True)
    try:
        sc = _reseed(mw)
    finally:
        QSettings("GV", "FirePro3D").remove(AUTO_CONSTRAIN_KEY)
    g = {gl.grid_label: gl for gl in sc._gridlines}
    dim = next(c for c in sc.constraint_ctl.constraints
               if c.type == "dim_point_line"
               and {r["uid"] for r in c.refs} == {g["1"]._uid, g["2"]._uid})
    x2 = g["2"]._origin.x()
    assert sc.constraint_ctl.set_value(dim.id, dim.value + 500.0)
    # 1 stays on the origin; 2 takes the whole change.
    assert abs(g["1"]._origin.x()) < 1e-3
    assert abs(g["2"]._origin.x() - (x2 + 500.0)) < 1e-3
    # With 2 locked the tie is what holds 1: the edit cannot move 1 off x=0
    # (untied, the solve would slide 1 to keep the new spacing).
    g["2"]._locked = True
    sc.constraint_ctl.set_value(dim.id, dim.value + 500.0)
    assert abs(g["1"]._origin.x()) < 1e-3
    assert abs(g["2"]._origin.x() - (x2 + 500.0)) < 1e-3     # locked: held too


def test_g6_deleting_1_drops_its_origin_tie(mw, qapp):
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, True)
    try:
        sc = _reseed(mw)
    finally:
        QSettings("GV", "FirePro3D").remove(AUTO_CONSTRAIN_KEY)
    g1 = next(gl for gl in sc._gridlines if gl.grid_label == "1")
    sc.delete_items([g1])
    ties = [c for c in sc.constraint_ctl.constraints
            if any(r == {"ref": "origin"} for r in c.refs)]
    # A's tie stays; nothing is left pointing at the origin alone.
    assert len(ties) == 1 and all(len(c.refs) == 2 for c in ties)
    assert all(g1._uid not in {r.get("uid") for r in c.refs}
               for c in sc.constraint_ctl.constraints)


def test_g6_seed_follows_the_toggle_off(mw, qapp):
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, False)
    try:
        sc = _reseed(mw)
    finally:
        QSettings("GV", "FirePro3D").remove(AUTO_CONSTRAIN_KEY)
    assert len(sc._gridlines) == 6
    assert sc.constraint_ctl.constraints == []
