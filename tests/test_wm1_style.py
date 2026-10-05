"""WM1 (linetypes.md "Weight model" WM-5/WM-9/WM-10) -- stroke_style unit
guards: migration of by_block, resolved weight labels, the current store."""
from PyQt6.QtCore import QPointF, QSettings

from firepro3d import paper_display as pd
from firepro3d import stroke_style as ss
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.lt3_support import hidden


def test_default_style_is_continuous_by_linetype():
    st = ss.default_style("#ff0000")
    assert st["linetype"] == ss.CONTINUOUS
    assert st["weight"] == ss.BY_LINETYPE
    assert st["start"]["end"] == st["finish"]["end"] == ss.BY_LINETYPE


def test_normalize_migrates_every_by_block_field():
    st = ss.normalize_style({"linetype": "by_block", "weight": "by_block",
                             "start": {"end": "by_block", "visible": False},
                             "finish": {"end": "by_block"},
                             "colour": "#00ff00"})
    assert st["linetype"] == ss.CONTINUOUS
    assert st["weight"] == ss.BY_LINETYPE
    assert st["start"] == {"end": ss.BY_LINETYPE, "visible": False}
    assert st["finish"]["end"] == ss.BY_LINETYPE
    assert st["colour"] == "#00ff00"


def test_migrate_legacy_primitive_has_no_by_block():
    rec = ss.migrate_primitive({"type": "draw_line", "color": "#123456",
                                "lineweight": 3.0})
    assert "by_block" not in repr(rec["style"])
    assert rec["style"]["weight"] == ss.BY_LINETYPE


def test_named_weight_survives_normalize():
    assert ss.normalize_style({"weight": "Heavy"})["weight"] == "Heavy"


def test_weight_label_continuous_falls_back_to_model_blocks(qapp):
    pd.set_model_blocks_weight(None)               # factory Light
    try:
        assert ss.weight_label(ss.BY_LINETYPE, ss.CONTINUOUS, None) == \
            "By Linetype (Light)"
        pd.set_model_blocks_weight("Heavy")
        assert ss.weight_label(ss.BY_LINETYPE, ss.CONTINUOUS, None) == \
            "By Linetype (Heavy)"
    finally:
        pd.set_model_blocks_weight(None)


def test_weight_label_uses_dash_weight(qapp):
    ms = Model_Space()
    lt = hidden(ms, weight="Medium")
    assert ss.weight_label(ss.BY_LINETYPE, lt, ms.block_registry) == \
        "By Linetype (Medium)"
    assert ss.weight_label("Heavy", lt, ms.block_registry) == "Heavy"


def test_weight_from_label_round_trip():
    assert ss.weight_from_label("By Linetype (Light)") == ss.BY_LINETYPE
    assert ss.weight_from_label("By Linetype") == ss.BY_LINETYPE
    assert ss.weight_from_label("Heavy") == "Heavy"


def test_current_factory_and_set_reset():
    assert ss.current_style() == {"linetype": ss.CONTINUOUS,
                                  "weight": ss.BY_LINETYPE}
    ss.set_current(weight="Heavy")
    ss.set_current(linetype="abc")
    assert ss.current_style() == {"linetype": "abc", "weight": "Heavy"}
    ss.reset_current()
    assert ss.current_style()["weight"] == ss.BY_LINETYPE


def test_current_settings_round_trip():
    s = QSettings("GV", "FirePro3D")
    ss.set_current(linetype="abc", weight="Heavy")
    ss.current_to_settings(s)
    ss.reset_current()
    ss.current_from_settings(s)
    assert ss.current_style() == {"linetype": "abc", "weight": "Heavy"}


def test_current_from_settings_drops_unknown_weight_and_by_block():
    s = QSettings("GV", "FirePro3D")
    s.setValue("template/geometry/weight", "NoSuchWeight")
    s.setValue("template/geometry/linetype", "by_block")
    ss.current_from_settings(s)
    assert ss.current_style() == {"linetype": ss.CONTINUOUS,
                                  "weight": ss.BY_LINETYPE}


def test_apply_current_resolvable_linetype(qapp):
    ms = Model_Space()
    lt = hidden(ms)
    ss.set_current(linetype=lt, weight="Heavy")
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    ss.apply_current(ln, ms)
    assert ln.style["linetype"] == lt and ln.style["weight"] == "Heavy"


def test_apply_current_unresolvable_linetype_is_continuous(qapp):
    ss.set_current(linetype="not-in-this-project", weight="Heavy")
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    ss.apply_current(ln, Model_Space())
    assert ln.style["linetype"] == ss.CONTINUOUS
    assert ln.style["weight"] == "Heavy"


def test_apply_current_unknown_weight_is_by_linetype(qapp):
    ss._current["weight"] = "Deleted"        # e.g. a weight this project lacks
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    ss.apply_current(ln, Model_Space())
    assert ln.style["weight"] == ss.BY_LINETYPE
