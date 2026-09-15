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


# ─────────────────────────────────────────────────────────────────────────────
# Task A: linked default title-block template (reference by uuid, embed-fresh)
# ─────────────────────────────────────────────────────────────────────────────

def _seed_link(tmp_path, uuid_value):
    """Write ``titleblock_template_uuid`` into the (existing) default.fpdt."""
    from firepro3d.settings import template
    template.ensure_template()
    data = json.load(open(template.template_path()))
    data["titleblock_template_uuid"] = uuid_value
    json.dump(data, open(template.template_path(), "w"))


def test_apply_template_settings_embeds_linked_titleblock(tmp_path, monkeypatch, model_scene):
    from firepro3d import app_data
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    from firepro3d.settings import template
    from firepro3d.titleblock_template import make_default_template, save_to_library
    os.makedirs(os.path.join(str(tmp_path), "titleblocks"), exist_ok=True)
    tpl = make_default_template(); tpl.uuid = "link-me-001"; tpl.name = "Firm ANSI D"
    save_to_library(tpl)
    _seed_link(tmp_path, "link-me-001")
    # A fresh project resolves the uuid and embeds the CURRENT library version.
    scene = model_scene(); scene._titleblock_template = None
    template.apply_template_settings(scene)
    assert isinstance(scene._titleblock_template, dict)
    assert scene._titleblock_template["uuid"] == "link-me-001"
    assert scene._titleblock_template["name"] == "Firm ANSI D"


def test_apply_template_settings_broken_link_leaves_blank(tmp_path, monkeypatch, model_scene):
    from firepro3d import app_data
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    from firepro3d.settings import template
    _seed_link(tmp_path, "no-such-uuid")
    scene = model_scene(); scene._titleblock_template = None
    template.apply_template_settings(scene)   # must not raise
    assert scene._titleblock_template is None  # → blank sheet + prompt


def test_apply_template_settings_blank_uuid_is_noop(tmp_path, monkeypatch, model_scene):
    from firepro3d import app_data
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    from firepro3d.settings import template
    template.ensure_template()                 # default seed has "" uuid
    scene = model_scene(); scene._titleblock_template = None
    template.apply_template_settings(scene)
    assert scene._titleblock_template is None


def test_save_current_as_default_captures_titleblock_uuid(tmp_path, monkeypatch, model_scene):
    from firepro3d import app_data
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    from firepro3d.settings import template
    template.ensure_template()
    scene = model_scene()
    scene._titleblock_template = {"uuid": "captured-123", "name": "X"}
    template.save_current_as_default(scene)
    data = json.load(open(template.template_path()))
    assert data["titleblock_template_uuid"] == "captured-123"
