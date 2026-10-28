"""Gridline Auto Constrain R7: the default 3V+3H seed (startup + New Project,
MainWindow._place_default_gridlines) opens auto-constrained and the records
survive save / reopen."""
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
    assert Counter(c.type for c in cons) == {
        "vertical": 3, "horizontal": 3, "dim_point_line": 4}
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


def test_g6_seed_follows_the_toggle_off(mw, qapp):
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, False)
    try:
        sc = _reseed(mw)
    finally:
        QSettings("GV", "FirePro3D").remove(AUTO_CONSTRAIN_KEY)
    assert len(sc._gridlines) == 6
    assert sc.constraint_ctl.constraints == []
