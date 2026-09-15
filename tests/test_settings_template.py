import os, json, pytest


def test_apply_template_settings_overlays_units(tmp_path, monkeypatch, model_scene):
    from firepro3d import app_data
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    from firepro3d.settings import template
    from firepro3d.scale_manager import DisplayUnit
    # Seed a template with imperial units via save_current_as_default.
    seed = model_scene(); seed.scale_manager.display_unit = DisplayUnit("imperial")
    template.save_current_as_default(seed)
    # A fresh metric scene picks up the template's imperial units.
    scene = model_scene()
    template.apply_template_settings(scene)
    assert scene.scale_manager.display_unit == DisplayUnit("imperial")


def test_template_path_under_app_data(tmp_path, monkeypatch):
    from firepro3d import app_data
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    from firepro3d.settings import template
    assert template.template_path() == os.path.join(str(tmp_path), "default.fpdt")


def test_ensure_template_creates_seeded_blank(tmp_path, monkeypatch):
    from firepro3d import app_data
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    from firepro3d.settings import template
    path = template.ensure_template()
    assert os.path.exists(path)
    data = json.load(open(path))
    assert data["template"] is True
    assert data["nodes"] == [] and data["walls"] == []
    assert "scale" in data


def test_clone_template_leaves_project_untitled(tmp_path, monkeypatch, model_scene):
    from firepro3d import app_data
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    from firepro3d.settings import template
    template.ensure_template()
    scene = model_scene()
    template.clone_template_into(scene)
    assert scene._project_path is None


def test_clone_recovers_from_corrupt_template(tmp_path, monkeypatch, model_scene):
    from firepro3d import app_data
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    from firepro3d.settings import template
    os.makedirs(str(tmp_path), exist_ok=True)
    open(template.template_path(), "w").write("{ not valid json")
    scene = model_scene()
    template.clone_template_into(scene)   # must not raise
    assert scene._project_path is None


def test_save_current_as_default_writes_only_settings(tmp_path, monkeypatch, model_scene):
    from firepro3d import app_data
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    from firepro3d.settings import template
    from firepro3d.scale_manager import DisplayUnit
    template.ensure_template()
    scene = model_scene()
    scene.scale_manager.display_unit = DisplayUnit("imperial")
    scene.scale_manager.precision = 2
    scene._project_info = {"name": "Proj X"}
    template.save_current_as_default(scene)
    data = json.load(open(template.template_path()))
    assert data["scale"]["display_unit"] == "imperial"
    assert data["project_info"] == {"name": "Proj X"}
    assert data["template"] is True
    assert data["nodes"] == []
