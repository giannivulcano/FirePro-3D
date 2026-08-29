# tests/test_underlay_levels_migration.py
from firepro3d.underlay import Underlay


def test_new_underlay_defaults_to_single_active_style_list():
    u = Underlay(type="dxf", path="p.dxf", levels=["Level 1"])
    assert u.levels == ["Level 1"]
    assert u.snap is True  # new field, default on


def test_to_dict_from_dict_roundtrip_is_byte_stable():
    u = Underlay(type="dxf", path="p.dxf", levels=["Level 1", "Level 3"],
                 snap=False, colour="#abcdef")
    d1 = u.to_dict()
    d2 = Underlay.from_dict(d1).to_dict()
    assert d1 == d2
    assert d1["levels"] == ["Level 1", "Level 3"]
    assert d1["snap"] is False
    assert "hidden_in_views" not in d1  # field removed


def test_from_dict_migrates_legacy_single_level_string():
    old = {"type": "dxf", "path": "p.dxf", "level": "F1"}
    u = Underlay.from_dict(old)
    assert u.levels == ["F1"]


def test_from_dict_all_levels_sentinel_preserved():
    u = Underlay.from_dict({"type": "pdf", "path": "p.pdf", "levels": ["*"]})
    assert u.levels == ["*"]


def test_from_dict_missing_level_defaults_to_default_level_list():
    from firepro3d.constants import DEFAULT_LEVEL
    u = Underlay.from_dict({"type": "pdf", "path": "p.pdf"})
    assert u.levels == [DEFAULT_LEVEL]


def test_from_dict_ignores_legacy_hidden_in_views_key():
    old = {"type": "dxf", "path": "p.dxf", "level": "F1",
           "hidden_in_views": ["plan:Plan: F1"]}
    u = Underlay.from_dict(old)
    assert not hasattr(u, "hidden_in_views")


def test_snap_defaults_true_when_absent_in_dict():
    u = Underlay.from_dict({"type": "dxf", "path": "p.dxf", "level": "F1"})
    assert u.snap is True
