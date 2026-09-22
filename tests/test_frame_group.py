from firepro3d.text_item import TextItem, TextAnnotationData
from firepro3d.frame_group import FrameGroupController


def _ctl_with_target():
    item = TextItem(TextAnnotationData(text="A"))
    return FrameGroupController(get_targets=lambda: [item]), item


def test_border_toggle_sets_data(qapp):
    ctl, item = _ctl_with_target()
    ctl.border_btn.setChecked(True)
    ctl.border_btn.clicked.emit(True)
    assert item._data.border is True


def test_corner_radio_is_exclusive(qapp):
    ctl, item = _ctl_with_target()
    ctl.commit_corner("chamfer")
    assert item._data.border_corner == "chamfer"
    assert ctl.corner_btns["chamfer"].isChecked()
    ctl.commit_corner("round")
    assert item._data.border_corner == "round"
    assert not ctl.corner_btns["chamfer"].isChecked()
    assert ctl.corner_btns["round"].isChecked()


def test_line_type_and_weight_commit(qapp):
    ctl, item = _ctl_with_target()
    ctl.commit_line_type("dashed")
    ctl.commit_weight("Heavy")
    assert item._data.border_line_type == "dashed"
    assert item._data.border_weight == "Heavy"


def test_sync_reflects_target_state(qapp):
    item = TextItem(TextAnnotationData(text="A", border=True, border_corner="round",
                                       border_line_type="dotted", border_weight="Medium"))
    ctl = FrameGroupController(get_targets=lambda: [item])
    ctl.sync()
    assert ctl.border_btn.isChecked() is True
    assert ctl.corner_btns["round"].isChecked() is True
    assert ctl.line_type_combo.currentText() == "dotted"
    assert ctl.weight_combo.currentText() == "Medium"


def test_controls_disabled_when_border_off(qapp):
    item = TextItem(TextAnnotationData(text="A", border=False))
    ctl = FrameGroupController(get_targets=lambda: [item])
    ctl.sync()
    assert ctl.line_type_combo.isEnabled() is False
    assert ctl.corner_btns["square"].isEnabled() is False
