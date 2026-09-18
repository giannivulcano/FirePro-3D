from firepro3d.model_space import Model_Space


def test_plan_scene_refuses_loose_modes(qapp):
    s = Model_Space()                     # plan role
    for m in ("draw_line", "draw_rectangle", "draw_circle", "draw_ellipse",
              "draw_spline", "polyline", "draw_arc", "polygon", "text", "dimension"):
        s.set_mode(m)
        assert s.mode != m, f"plan scene must refuse {m}, got mode={s.mode}"


def test_plan_scene_allows_placement_modes(qapp):
    s = Model_Space()
    s.set_mode("wall")
    assert s.mode == "wall"               # non-loose modes unaffected


def test_block_editor_allows_loose_modes(qapp):
    s = Model_Space(scene_role="block_editor")
    s.set_mode("draw_line")
    assert s.mode == "draw_line"
    s.set_mode("polygon")
    assert s.mode == "polygon"
