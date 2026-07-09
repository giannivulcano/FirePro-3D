"""Unit tests for DimensionEdit parser/minimum/seed-guard extensions."""
from firepro3d.dimension_edit import DimensionEdit
from firepro3d.paper_space import _parse_text_height_mm


def test_custom_parser_used(qapp):
    edit = DimensionEdit(None, initial_mm=3.0, parser=_parse_text_height_mm)
    edit.setText('1/8"')
    edit._on_editing_finished()
    assert abs(edit.value_mm() - 3.175) < 1e-6


def test_minimum_rejects_zero_and_negative(qapp):
    edit = DimensionEdit(None, initial_mm=4.7625,
                         parser=_parse_text_height_mm, minimum=0.0)
    edit.setText("0mm")
    edit._on_editing_finished()
    assert edit.value_mm() == 4.7625          # reverted
    edit.setText("-3mm")
    edit._on_editing_finished()
    assert edit.value_mm() == 4.7625          # reverted


def test_untouched_field_keeps_exact_value(qapp):
    # sm=None formats as "4.76 mm"; re-parsing that would give 4.76, not 4.7625.
    edit = DimensionEdit(None, initial_mm=4.7625)
    edit._on_editing_finished()               # commit without touching
    assert edit.value_mm() == 4.7625          # exact value preserved


def test_seed_guard_updates_after_set_value(qapp):
    edit = DimensionEdit(None, initial_mm=3.0)
    edit.set_value_mm(6.35)
    edit._on_editing_finished()               # untouched after programmatic set
    assert edit.value_mm() == 6.35


def test_changed_text_still_commits(qapp):
    changes = []
    edit = DimensionEdit(None, initial_mm=3.0)
    edit.valueChanged.connect(changes.append)
    edit.setText("10 mm")
    edit._on_editing_finished()
    assert edit.value_mm() == 10.0
    assert changes == [10.0]
