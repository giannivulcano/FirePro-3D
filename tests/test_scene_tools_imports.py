"""DV3 / D15: scene_tools names every Qt class it constructs, and the dead
numeric-input dialog channel is gone (the Dynamic Input HUD is the one
numeric channel)."""
import firepro3d.scene_tools as st


def test_scene_tools_qt_names_resolve():
    """DV3: NameError on the rect/circle highlight picks and the constraint
    distance dialog — every Qt class the module constructs must resolve."""
    for name in ("QGraphicsRectItem", "QGraphicsEllipseItem", "QDialog",
                 "QVBoxLayout", "QLabel"):
        assert hasattr(st, name), name                     # [RED]


def test_numeric_input_channel_removed():
    from firepro3d.model_space import Model_Space
    assert not hasattr(Model_Space, "complete_numeric_input")   # [RED]
    assert not hasattr(Model_Space, "numericInputRequested")


def test_no_false_tab_hints_for_hudless_tools(qapp):
    """D15: a tool without a Dynamic Input schema must not promise 'Tab = …'."""
    from firepro3d.model_space import Model_Space
    scene = Model_Space()
    try:
        seen = []
        scene.instructionChanged.connect(seen.append)
        for mode in ("scale", "fillet", "chamfer", "mirror", "break",
                     "break_at_point", "stretch", "trim", "extend"):
            if mode in scene._SCHEMA_FOR_MODE or mode in scene._APPLIER_FOR_MODE:
                continue
            seen.clear()
            scene.set_mode(mode)
            assert seen, mode
            assert all("Tab" not in s for s in seen), (mode, seen)   # [RED]
    finally:
        scene.cleanup()
