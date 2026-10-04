"""LT2-1 / LT2-2 / H-a / H-b -- the stroke style record (stroke_style.py)."""
import copy

from firepro3d import stroke_style as ss


def test_default_style_is_continuous_by_block():
    st = ss.default_style("#ff0000")
    assert st == {
        "linetype": "continuous", "weight": "by_block",
        "start": {"end": "by_linetype", "visible": True},
        "finish": {"end": "by_linetype", "visible": True},
        "colour": "#ff0000",
    }


def test_normalize_fills_missing_and_defaults_empty_weight():
    st = ss.normalize_style({"weight": "Heavy", "colour": "#00FF00",
                             "start": {"visible": False}})
    assert st["linetype"] == "continuous"
    assert st["weight"] == "Heavy"
    assert st["colour"] == "#00ff00"
    assert st["start"] == {"end": "by_linetype", "visible": False}
    assert st["finish"] == {"end": "by_linetype", "visible": True}
    assert ss.normalize_style({"weight": ""})["weight"] == "by_block"
    assert ss.normalize_style(None) == ss.default_style("#ffffff")


def test_normalize_deep_copies():
    src = ss.default_style("#123456")
    out = ss.normalize_style(src)
    out["start"]["visible"] = False
    assert src["start"]["visible"] is True


def test_migrate_legacy_drops_px_and_keeps_colour():
    legacy = {"type": "draw_line", "pt1": [0, 0], "pt2": [1, 0],
              "color": "#abcdef", "lineweight": 3.0}
    out = ss.migrate_primitive(legacy)
    assert "lineweight" not in out and "color" not in out
    assert out["style"] == ss.default_style("#abcdef")
    assert legacy["lineweight"] == 3.0        # input untouched (copy)


def test_migrate_leaves_text_reference_and_nested_alone():
    for rec in ({"type": "text", "border_weight": "Medium"},
                {"type": "reference_line", "color": "#888888", "lineweight": 1.0},
                {"type": "block_instance", "block_id": "x"}):
        assert ss.migrate_primitive(rec) == rec


def test_migrate_is_idempotent_on_new_records():
    rec = {"type": "draw_circle", "style": ss.default_style("#ffffff")}
    assert ss.migrate_primitive(rec) == rec


def test_copy_style_resets_fresh_ends_only():
    class _P:
        style = None
    a, b = _P(), _P()
    a.style = ss.normalize_style({"weight": "Heavy",
                                  "start": {"end": "by_block"},
                                  "finish": {"end": "by_block"}})
    b.style = ss.default_style()      # dst must itself be styled (else no-op)
    ss.copy_style(a, b, fresh_ends=("finish",))
    assert b.style["weight"] == "Heavy"
    assert b.style["start"]["end"] == "by_block"
    assert b.style["finish"]["end"] == "by_linetype"
    b.style["start"]["end"] = "x"
    assert a.style["start"]["end"] == "by_block"      # deep copy


def test_copy_style_noop_for_unstyled():
    class _P:
        style = None
    a, b = _P(), _P()
    ss.copy_style(a, b)
    assert b.style is None


def test_weight_name_for_by_block_is_model_blocks(monkeypatch):
    from firepro3d import paper_display as pd
    monkeypatch.setattr(pd, "model_blocks_weight", lambda: "Heavy")
    assert ss.canvas_weight_name("by_block") == "Heavy"
    assert ss.canvas_weight_name("by_linetype") == "Heavy"
    assert ss.canvas_weight_name("Light") == "Light"


def test_canvas_px_real_path():
    from firepro3d import paper_display as pd
    pd.reset_project_line_weights()
    pd.set_model_blocks_weight(None)
    assert ss.canvas_px("by_block") == 1.0
    assert ss.canvas_px("Heavy") == pd.canvas_weight_px(
        pd.resolve_line_weight_mm("Heavy"))
