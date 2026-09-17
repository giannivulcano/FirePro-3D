from firepro3d.model_space import Model_Space


def test_plan_scene_role_defaults_and_forbids_loose(qapp):
    s = Model_Space()                      # default role
    assert s.scene_role == "plan"
    assert s.authoring_allowed("wall") is True
    assert s.authoring_allowed("draw_line") is False
    assert s.authoring_allowed("text") is False
    assert s.authoring_allowed("dimension") is False
    assert s.device_independent_text() is False


def test_block_editor_scene_permits_loose(qapp):
    s = Model_Space(scene_role="block_editor")
    assert s.authoring_allowed("draw_line") is True
    assert s.authoring_allowed("text") is True
