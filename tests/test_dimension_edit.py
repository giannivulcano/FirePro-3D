"""Unit tests for DimensionEdit parser/minimum/seed-guard extensions."""
import pytest

from firepro3d.dimension_edit import DimensionEdit
from firepro3d.dynamic_input import (
    DynamicInputHud, FieldKind, FieldSpec, Schema, resolve_distance,
)
from firepro3d.paper_space import _parse_text_height_mm
from firepro3d.scale_manager import ScaleManager


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


# ── try_commit() verdict ──────────────────────────────────────────────────


def test_try_commit_true_for_a_valid_change(qapp):
    edit = DimensionEdit(None, initial_mm=3.0)
    edit.setText("10 mm")
    assert edit.try_commit() is True
    assert edit.value_mm() == 10.0


def test_try_commit_true_for_untouched(qapp):
    """An untouched seed is valid input, not a rejection."""
    edit = DimensionEdit(None, initial_mm=4.7625)
    assert edit.try_commit() is True
    assert edit.value_mm() == 4.7625


def test_try_commit_true_for_blank(qapp):
    """A cleared field keeps the stored value and still reports valid."""
    edit = DimensionEdit(None, initial_mm=4.7625)
    edit.setText("")
    assert edit.try_commit() is True
    assert edit.value_mm() == 4.7625


def test_try_commit_false_for_unparseable(qapp):
    edit = DimensionEdit(None, initial_mm=3.0)
    edit.setText("banana")
    assert edit.try_commit() is False
    assert edit.value_mm() == 3.0            # reverted


def test_try_commit_false_below_minimum(qapp):
    edit = DimensionEdit(None, initial_mm=4.7625,
                         parser=_parse_text_height_mm, minimum=0.0)
    edit.setText("0mm")
    assert edit.try_commit() is False
    assert edit.value_mm() == 4.7625


def test_commit_still_returns_none_for_existing_consumers(qapp):
    """``commit()`` stays a discard-the-verdict wrapper for its 11 callers."""
    edit = DimensionEdit(None, initial_mm=3.0)
    edit.setText("banana")
    assert edit.commit() is None
    assert edit.value_mm() == 3.0


# ── Non-zero DIMENSION minimum (scene → mm conversion) ────────────────────


def test_hud_converts_a_nonzero_scene_minimum_into_mm(qapp):
    """Pin the scene→mm minimum conversion no real schema exercises.

    Every shipped DIMENSION minimum is ``0.0`` or ``None``, and ``0.0``
    scales to ``0.0`` — so the conversion in ``_build_editor`` is invisible
    to the suite.  This local synthetic schema gives it a value with a
    scale factor: 100 scene units at 2 px/mm is a 50 mm floor, so 40 mm
    must be rejected and 60 mm accepted.
    """
    sm = ScaleManager()
    sm.set_pixels_per_mm(2.0)
    schema = Schema(
        name="_synthetic_min",
        fields=(FieldSpec("Distance", "D", FieldKind.DIMENSION,
                          minimum=100.0),),
        resolve=resolve_distance,
        returns_point=False,
    )
    hud = DynamicInputHud(schema, sm)
    editor = hud.editor("Distance")
    assert editor._minimum == pytest.approx(50.0)   # 100 scene units ÷ 2

    hud.set_values({"Distance": 200.0})             # 100 mm displayed
    editor.setText("40 mm")
    assert editor.try_commit() is False             # below the 50 mm floor
    assert hud.values()["Distance"] == pytest.approx(200.0)

    hud.set_values({"Distance": 200.0})
    editor.setText("60 mm")
    assert editor.try_commit() is True
    assert hud.values()["Distance"] == pytest.approx(120.0)  # 60 mm × 2
