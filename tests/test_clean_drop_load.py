"""Containment C8 — silent clean-drop of loose content on file load/save.

Forbidden content (loose geometry, standalone model text, model dimensions,
model-scene constraints, legacy hatch) is READ-BUT-DISCARDED on load and no
longer written on save. This is the FILE path only (scene_io.save_to_file /
load_from_file); the undo path (_capture_network/_restore_network) is untouched.
"""
import json
from firepro3d.model_space import Model_Space


def _legacy_payload():
    return {
        "version": 3,
        "draw_lines": [{"type": "draw_line", "p1": [0, 0], "p2": [10, 0], "level": "Level 1"}],
        "polygons": [{"type": "polygon", "center": [0, 0], "radius": 5, "sides": 6, "level": "Level 1"}],
        "texts": [{"type": "text", "text": "hi", "x": 0, "y": 0, "height_mm": 2.5}],
        "annotations": [
            {"type": "note", "x": 0, "y": 0, "text": "hi", "properties": {}, "level": "Level 1"},
            {"type": "dimension", "p1": [0, 0], "p2": [10, 0]},
        ],
        "constraints": [{"type": "coincident", "a": 0, "b": 1}],
        "walls": [],
    }


def test_legacy_loose_content_dropped(qapp, tmp_path):
    f = tmp_path / "legacy.fpd"
    f.write_text(json.dumps(_legacy_payload()))
    s = Model_Space()
    s.load_from_file(str(f))                 # must not raise
    assert s._draw_lines == []
    assert s._draw_polygons == []
    assert s._texts == []
    assert s.annotations.notes == []
    assert s.annotations.dimensions == []
    assert s._constraints == []


def test_resave_omits_dropped_keys(qapp, tmp_path):
    f = tmp_path / "legacy.fpd"
    f.write_text(json.dumps(_legacy_payload()))
    s = Model_Space()
    s.load_from_file(str(f))
    out = tmp_path / "clean.fpd"
    s.save_to_file(str(out))
    payload = json.loads(out.read_text())
    assert payload.get("draw_lines", []) == []
    assert payload.get("texts", []) == []
    assert all(a.get("type") not in ("note", "dimension") for a in payload.get("annotations", []))
    assert payload.get("constraints", []) == []
