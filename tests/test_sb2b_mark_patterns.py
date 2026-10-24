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
