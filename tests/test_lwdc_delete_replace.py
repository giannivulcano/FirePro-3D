"""LW-DC-5 -- deleting an in-use Custom weight asks for a replacement; the DM
Cancel restores every holder (real DisplayManager + every holder kind, the
modal driven through ``WeightReplaceDialog.exec``; settings isolated)."""
import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel

from firepro3d import paper_display as pd
from firepro3d import weight_refs as wr
from firepro3d.display_manager import DisplayManager
from firepro3d.paper_display import LineWeightDef
from firepro3d.weight_replace_dialog import WeightReplaceDialog
from tests.test_lwdc_weight_refs import A_HOLDERS, _snapshot, _world


def _setup(tmp_path, custom):
    pd.set_project_line_weights([*pd.DEFAULT_LINE_WEIGHTS,
                                 *(LineWeightDef(n, w) for n, w in custom)])
    pd.set_weight_aliases({})
    pd.set_model_blocks_weight(None)
    settings = QSettings("GV", "FirePro3D")    # conftest-isolated; the DM's own
    settings.clear()
    return settings


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    QSettings("GV", "FirePro3D").clear()
    pd.set_weight_aliases({})
    pd.set_model_blocks_weight(None)
    pd.reset_project_line_weights()


def _dm(ms, settings):
    d = DisplayManager(ms, active_context="paper")
    d._tabs.setCurrentIndex(2)
    return d


def _row(d, name):
    return next(r for r, lw in d._lw_row_def.items() if lw.name == name)


class _Modal:
    """Stand-in for the modal ``exec``: records what the dialog showed and
    answers like the user (accept with *pick*, or cancel)."""

    def __init__(self, monkeypatch, accept=True, pick=None):
        self.seen = []
        self.accept, self.pick = accept, pick

        def fake_exec(dlg):
            combo = dlg._combo
            self.seen.append({
                "preselect": dlg.chosen(),
                "items": [combo.itemText(i) for i in range(combo.count())],
                "label": dlg.findChild(QLabel).text()})
            if self.pick is not None:
                combo.setCurrentIndex(combo.findData(self.pick))
            return (QDialog.DialogCode.Accepted if self.accept
                    else QDialog.DialogCode.Rejected)
        monkeypatch.setattr(WeightReplaceDialog, "exec", fake_exec)


def _no_modal(monkeypatch):
    def boom(dlg):
        raise AssertionError("the replace dialog must not open")
    monkeypatch.setattr(WeightReplaceDialog, "exec", boom)


def test_replace_and_delete_retargets_every_holder_kind(qapp, tmp_path,
                                                        monkeypatch):
    settings = _setup(tmp_path, [("Pen X", 0.40)])
    ms, w = _world(settings, a="Pen X", b="Wide")
    d = _dm(ms, settings)
    assert wr.weight_ref_count(ms, settings, "Pen X") == A_HOLDERS
    medium_before = wr.weight_ref_count(ms, settings, "Medium")  # a category
    modal = _Modal(monkeypatch)
    d._lw_table.setCurrentCell(_row(d, "Pen X"), 0)
    assert d._lw_remove_btn.isEnabled()          # in use is no longer a block
    d._on_lw_remove()
    shown = modal.seen[0]
    assert shown["preselect"] == "Medium"        # |0.40-0.35| < |0.50-0.40|
    assert not any("Pen X" in i for i in shown["items"])
    assert shown["items"] == [
        f"{x.name}  {x.width_mm:.2f}"
        for x in sorted(pd.DEFAULT_LINE_WEIGHTS, key=lambda x: x.width_mm)]
    assert "‘Pen X’ (0.40 mm) is used by %d references" % A_HOLDERS \
        in shown["label"]
    assert "Pen X" not in pd.weight_names()
    assert wr.weight_ref_count(ms, settings, "Pen X") == 0
    assert wr.weight_ref_count(ms, settings, "Medium") == medium_before + A_HOLDERS
    assert pd.model_blocks_weight() == "Medium"
    assert w["rec"].line_weight_name == "Medium"
    assert w["ln"].style["weight"] == "Medium"
    assert w["inst"].overrides["weight"] == "Medium"
    assert w["note"].note["leader"]["weight"] == "Medium"
    assert w["ann"].border_weight == "Medium"
    assert w["lb"].style["weight"] == "Wide"           # untouched
    assert "Pen X" not in pd.weight_aliases()          # no alias for a delete
    assert "Pen X" not in [lw.name for lw in d._lw_row_def.values()]
    d.reject()


def test_pick_overrides_preselect_and_returns_the_name(qapp, tmp_path,
                                                       monkeypatch):
    settings = _setup(tmp_path, [("Pen X", 0.40)])
    ms, w = _world(settings, a="Pen X", b="Wide")
    d = _dm(ms, settings)
    _Modal(monkeypatch, pick="Thick")
    d._lw_table.setCurrentCell(_row(d, "Pen X"), 0)
    d._on_lw_remove()
    assert w["ln"].style["weight"] == "Thick"          # name, not "Thick  0.70"
    assert pd.model_blocks_weight() == "Thick"
    d.reject()


def test_tie_preselects_the_thinner(qapp, tmp_path, monkeypatch):
    settings = _setup(tmp_path, [("Pen Z", 0.425)])    # 0.075 from Medium + Wide
    ms, w = _world(settings, a="Pen Z", b="Wide")
    d = _dm(ms, settings)
    modal = _Modal(monkeypatch)
    d._lw_table.setCurrentCell(_row(d, "Pen Z"), 0)
    d._on_lw_remove()
    assert modal.seen[0]["preselect"] == "Medium"
    assert w["ln"].style["weight"] == "Medium"
    d.reject()


def test_dialog_cancel_changes_nothing(qapp, tmp_path, monkeypatch):
    settings = _setup(tmp_path, [("Pen X", 0.40)])
    ms, _w = _world(settings, a="Pen X", b="Wide")
    d = _dm(ms, settings)
    before = _snapshot(ms, settings)
    table = [(x.name, x.width_mm) for x in d._lw_defs]
    rows = {r: x.name for r, x in d._lw_row_def.items()}
    _Modal(monkeypatch, accept=False)
    d._lw_table.setCurrentCell(_row(d, "Pen X"), 0)
    d._on_lw_remove()
    assert _snapshot(ms, settings) == before
    assert [(x.name, x.width_mm) for x in d._lw_defs] == table
    assert {r: x.name for r, x in d._lw_row_def.items()} == rows
    assert "Pen X" in pd.weight_names()
    assert d._lw_ops == []
    d.reject()


def test_dm_cancel_after_replace_and_delete_restores_everything(
        qapp, tmp_path, monkeypatch):
    settings = _setup(tmp_path, [("Pen X", 0.40)])
    ms, w = _world(settings, a="Pen X", b="Wide")
    d = _dm(ms, settings)
    before = _snapshot(ms, settings)
    _Modal(monkeypatch)
    d._lw_table.setCurrentCell(_row(d, "Pen X"), 0)
    d._on_lw_remove()
    assert "Pen X" not in pd.weight_names()
    d.reject()
    assert "Pen X" in pd.weight_names()
    assert _snapshot(ms, settings) == before
    assert pd.model_blocks_weight() == "Pen X"
    assert wr.weight_ref_count(ms, settings, "Pen X") == A_HOLDERS
    assert w["inst"].overrides["weight"] == "Pen X"
    assert w["ann"].border_weight == "Pen X"


def test_rename_then_delete_then_cancel_replays_one_ordered_log(
        qapp, tmp_path, monkeypatch):
    settings = _setup(tmp_path, [("Pen X", 0.40)])
    ms, w = _world(settings, a="Pen X", b="Wide")
    d = _dm(ms, settings)
    before = _snapshot(ms, settings)
    d._lw_table.item(_row(d, "Pen X"), 0).setText("Pen Q")    # rename: refs follow
    assert wr.weight_ref_count(ms, settings, "Pen Q") == A_HOLDERS
    _Modal(monkeypatch)
    d._lw_table.setCurrentCell(_row(d, "Pen Q"), 0)
    d._on_lw_remove()                                         # then delete
    assert wr.weight_ref_count(ms, settings, "Pen Q") == 0
    assert wr.weight_ref_count(ms, settings, "Medium") > A_HOLDERS
    assert [op[0] for op in d._lw_ops] == ["rename", "delete"]
    d.reject()
    assert [lw.name for lw in pd.project_line_weights()
            if lw.name.startswith("Pen")] == ["Pen X"]
    assert _snapshot(ms, settings) == before
    assert w["inst"].overrides["weight"] == "Pen X"
    assert pd.weight_aliases() == {}


def test_unused_custom_deletes_without_a_prompt(qapp, tmp_path, monkeypatch):
    settings = _setup(tmp_path, [("Pen X", 0.40), ("Pen U", 0.45)])
    ms, _w = _world(settings, a="Pen X", b="Wide")
    d = _dm(ms, settings)
    _no_modal(monkeypatch)
    assert wr.weight_ref_count(ms, settings, "Pen U") == 0
    d._lw_table.setCurrentCell(_row(d, "Pen U"), 0)
    d._on_lw_remove()
    assert "Pen U" not in pd.weight_names()
    assert d._lw_ops == []
    d.reject()
    assert "Pen U" in pd.weight_names()


def test_dialog_chosen_is_the_name_and_single_noun(qapp):
    cands = [LineWeightDef("B", 0.60), LineWeightDef("A", 0.20)]
    dlg = WeightReplaceDialog("X", 0.21, 1, cands)
    assert dlg.chosen() == "A"
    assert [dlg._combo.itemText(i) for i in range(2)] == ["A  0.20", "B  0.60"]
    assert "is used by 1 reference." in dlg.findChild(QLabel).text()
    texts = [b.text() for b in dlg.findChild(QDialogButtonBox).buttons()]
    assert sorted(texts) == ["Cancel", "Replace && Delete"]
