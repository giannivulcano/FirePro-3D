"""LT2-8 / H-g -- weight rename aliases (unit half; holder guards are Task 9)."""
import pytest

from firepro3d import paper_display as pd
from firepro3d.paper_display import LineWeightDef


@pytest.fixture(autouse=True)
def _table():
    pd.set_project_line_weights([*pd.FACTORY_LINE_WEIGHTS,
                                 LineWeightDef("A", 0.40)])
    pd.set_weight_aliases({})
    yield
    pd.set_weight_aliases({})
    pd.reset_project_line_weights()


def _rename(old, new):
    defs = [LineWeightDef(new if d.name == old else d.name, d.width_mm)
            for d in pd.project_line_weights()]
    pd.set_project_line_weights(defs)
    pd.record_weight_rename(old, new)


def test_old_name_resolves_to_renamed_width():
    _rename("A", "B")
    assert pd.canonical_weight_name("A") == "B"
    assert pd.resolve_line_weight_mm("A") == pytest.approx(0.40)


def test_chain_collapses_and_rename_back_drops_alias():
    _rename("A", "B")
    _rename("B", "C")
    assert pd.weight_aliases() == {"A": "C", "B": "C"}
    _rename("C", "A")
    assert pd.canonical_weight_name("A") == "A"
    assert pd.canonical_weight_name("B") == "A"
    assert "A" not in pd.weight_aliases()


def test_cycle_guard_terminates():
    pd.set_weight_aliases({"X": "Y", "Y": "X"})
    assert pd.canonical_weight_name("X") in ("X", "Y")


def test_aliases_persist_and_reset():
    _rename("A", "B")
    data = pd.get_paper_display_for_save()
    assert data["line_weight_aliases"] == {"A": "B"}
    pd.set_weight_aliases({})
    pd.apply_paper_display_from_project(data)
    assert pd.weight_aliases() == {"A": "B"}
    pd.reset_project_line_weights()
    assert pd.weight_aliases() == {}


def test_merge_does_not_readd_an_alias_key():
    _rename("A", "B")
    assert pd.merge_project_line_weights({"A": 0.99}) == []
    assert "A" not in pd.weight_names()


def test_model_blocks_weight_default_light():
    pd.set_model_blocks_weight(None)
    assert pd.model_blocks_weight() == "Light"
    pd.set_model_blocks_weight("Heavy")
    assert pd.model_blocks_weight() == "Heavy"
    pd.set_model_blocks_weight(None)
