"""SB2b -- mark_patterns persist in .fpd and ride Save as default (spec A3)."""
import json

from firepro3d import marks
from firepro3d.model_space import Model_Space
from firepro3d.settings import template


def test_new_scene_has_default_patterns(qapp):
    assert marks.patterns(Model_Space()) == marks.DEFAULT_PATTERNS


def test_patterns_round_trip_fpd(qapp, tmp_path):
    ms = Model_Space()
    ms.mark_patterns["Door"] = "DR-{n:02}"
    f = tmp_path / "p.fpd"
    ms.save_to_file(str(f))
    assert json.loads(f.read_text(encoding="utf-8"))["mark_patterns"]["Door"] == "DR-{n:02}"
    ms2 = Model_Space()
    ms2.load_from_file(str(f))
    assert marks.patterns(ms2)["Door"] == "DR-{n:02}"
    assert marks.patterns(ms2)["Room"] == "{level}{n:02}"


def test_old_file_without_patterns_gets_defaults(qapp, tmp_path):
    ms = Model_Space()
    f = tmp_path / "o.fpd"
    ms.save_to_file(str(f))
    rec = json.loads(f.read_text(encoding="utf-8"))
    rec.pop("mark_patterns")
    f.write_text(json.dumps(rec), encoding="utf-8")
    ms2 = Model_Space()
    ms2.mark_patterns["Door"] = "STALE{n}"
    ms2.load_from_file(str(f))
    assert marks.patterns(ms2) == marks.DEFAULT_PATTERNS


def test_save_as_default_carries_patterns(qapp, tmp_path, monkeypatch):
    from firepro3d import app_data
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    ms = Model_Space()
    ms.mark_patterns["Wall"] = "W-{n}"
    path = template.save_current_as_default(ms)
    assert path.startswith(str(tmp_path))
    with open(path, encoding="utf-8") as fh:
        assert json.load(fh)["mark_patterns"]["Wall"] == "W-{n}"
    ms2 = Model_Space()
    template.apply_template_settings(ms2)
    assert marks.patterns(ms2)["Wall"] == "W-{n}"


def test_mutating_a_scene_never_touches_the_defaults(qapp, tmp_path):
    ms = Model_Space()
    ms.mark_patterns["Door"] = "X{n}"
    assert marks.DEFAULT_PATTERNS["Door"] == "D{n}"
    assert Model_Space().mark_patterns["Door"] == "D{n}"
    f = tmp_path / "s.fpd"
    ms.save_to_file(str(f))
    ms2 = Model_Space()
    ms2.load_from_file(str(f))
    ms2.mark_patterns["Wall"] = "Y{n}"
    assert marks.DEFAULT_PATTERNS["Wall"] == "WL{n}"
    assert Model_Space().mark_patterns["Wall"] == "WL{n}"
    ms3 = Model_Space()
    ms3.mark_patterns["Door"] = "Z"
    ms3.load_from_file(str(f))                  # load rebuilds from a fresh copy
    ms3.mark_patterns["Pipe"] = "Q{n}"
    assert marks.DEFAULT_PATTERNS["Pipe"] == "P{n}"


def test_corrupt_saved_patterns_fall_back_to_defaults(qapp, tmp_path):
    ms = Model_Space()
    f = tmp_path / "c.fpd"
    ms.save_to_file(str(f))
    rec = json.loads(f.read_text(encoding="utf-8"))
    rec["mark_patterns"] = {"Door": 5, "Wall": ["x"], "Pipe": "PP{n}"}
    f.write_text(json.dumps(rec), encoding="utf-8")
    ms2 = Model_Space()
    ms2.load_from_file(str(f))
    got = marks.patterns(ms2)
    assert got["Door"] == "D{n}" and got["Wall"] == "WL{n}" and got["Pipe"] == "PP{n}"
    rec["mark_patterns"] = ["not", "a", "dict"]
    f.write_text(json.dumps(rec), encoding="utf-8")
    ms3 = Model_Space()
    ms3.load_from_file(str(f))
    assert marks.patterns(ms3) == marks.DEFAULT_PATTERNS


def test_corrupt_template_patterns_fall_back(qapp, tmp_path, monkeypatch):
    from firepro3d import app_data
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    ms = Model_Space()
    path = template.save_current_as_default(ms)
    with open(path, encoding="utf-8") as fh:
        rec = json.load(fh)
    rec["mark_patterns"] = {"Door": 7, "Wall": "T{n}"}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rec, fh)
    ms2 = Model_Space()
    template.apply_template_settings(ms2)
    assert marks.patterns(ms2)["Door"] == "D{n}" and marks.patterns(ms2)["Wall"] == "T{n}"
