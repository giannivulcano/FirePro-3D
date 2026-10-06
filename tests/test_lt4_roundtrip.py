"""LT4 A5: an authored linetype survives undo/redo, Save, use, .fpd, Save As, .fpdb.

Drives the real authoring path (ribbon toggle -> Pattern rows -> Weight row ->
editor Save / Save As through ``BlockEditorWidget``) and checks each hop by
re-reading the definition through the LT3 renderer (``LinetypeDef.from_block``),
the ground truth the canvas draws from (linetypes.md LT4 A5, concept G8).
"""
import json

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QDialog, QTabWidget

import firepro3d.block_editor as be
from firepro3d import block_library
from firepro3d import linetype_authoring as la
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.linetype_render import LinetypeDef
from firepro3d.model_space import Model_Space


def _fake_dialog(answers):
    """A ``BlockSaveDialog`` stand-in that accepts with ``answers[0]``."""
    class _Fake:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return dict(answers[0])
    return _Fake


def _reading(defn):
    lt = LinetypeDef.from_block(defn)
    assert lt is not None
    return lt.period, lt.dashes, lt.dots, lt.dash_weight, lt.size


def test_a5_round_trip(qapp, tmp_path, monkeypatch):
    answers = [{"name": "Fire", "library": "L", "series": "Linetypes",
                "save_to_library": False, "replace_source": True}]
    monkeypatch.setattr(be, "BlockSaveDialog", _fake_dialog(answers))
    proj = Model_Space()
    tabs = QTabWidget()
    w = be.BlockEditorManager(tabs, proj).open_new()
    assert w.toggle_capability("repeat") is True
    sc = w.editor_scene

    # ── author: Dash 6 / Gap 2 / Dot / Gap 2, Heavy ─────────────────────────
    assert la.apply_pattern_rows(
        sc, [("dash", 6.0), ("gap", 2.0), ("dot", 0.0), ("gap", 2.0)]) is True
    la.set_pattern_weight(sc, "Heavy")
    assert la.pattern_weight(sc) == "Heavy"

    # ── undo / redo ─────────────────────────────────────────────────────────
    sc.undo()
    assert la.pattern_weight(sc) != "Heavy"                 # undo really undid
    sc.redo()
    assert la.pattern_weight(sc) == "Heavy"
    assert la.current_rows(sc) == [("dash", 6.0), ("gap", 2.0),
                                   ("dot", 0.0), ("gap", 2.0)]
    assert sc.block_repeat == {"length": 10.0, "size": "drafting",
                              "screen": "fixed"}  # LTS-5 seed

    # ── Save (first save: new definition through the dialog) ────────────────
    d = w.save()
    assert d is not None and proj.get_block_definition(d.id) is d
    assert d.repeat == {"length": 10.0, "size": "drafting", "screen": "fixed"}
    assert _reading(d) == (10.0, ((0.0, 6.0),), (8.0,), "Heavy", "drafting")

    # ── Save again (edit in place): a longer gap + Model size ───────────────
    assert la.apply_pattern_rows(
        sc, [("dash", 6.0), ("gap", 2.0), ("dot", 0.0), ("gap", 4.0)]) is True
    la.set_repeat_field(sc, "Size", "Model")
    d_again = w.save()
    assert d_again is d                                     # same definition
    assert d.repeat == {"length": 12.0, "size": "model", "screen": "fixed"}
    assert _reading(d) == (12.0, ((0.0, 6.0),), (8.0,), "Heavy", "model")

    # ── use it on a line in another block ───────────────────────────────────
    ln = LineItem(QPointF(0, 0), QPointF(50, 0))
    ln.style["linetype"] = d.id
    host = BlockDefinition.new(name="Main", library="L", series="S",
                               origin=(0.0, 0.0), primitives=[ln.to_dict()])
    proj.register_block_definition(host)
    assert proj.block_registry.users_of(d.id) == {host.id}

    # ── .fpd save / load ────────────────────────────────────────────────────
    path = tmp_path / "p.fpd"
    proj.save_to_file(str(path))
    proj2 = Model_Space()
    proj2.load_from_file(str(path))
    d2 = proj2.get_block_definition(d.id)
    assert d2 is not None and d2.repeat == d.repeat
    assert _reading(d2) == (12.0, ((0.0, 6.0),), (8.0,), "Heavy", "model")
    assert (proj2.get_block_definition(host.id).primitives[0]["style"]["linetype"]
            == d.id)
    assert proj2.block_registry.users_of(d.id) == {host.id}

    # ── Save As: a second linetype with the same unit ───────────────────────
    answers[0] = {"name": "Fire copy", "library": "L", "series": "Linetypes",
                  "save_to_library": False, "replace_source": True}
    d_copy = w.save_as()
    assert d_copy is not None and d_copy.id != d.id
    assert proj.get_block_definition(d_copy.id) is d_copy
    assert d_copy.repeat == d.repeat
    assert _reading(d_copy) == _reading(d)
    assert _reading(proj.get_block_definition(d.id)) == _reading(d)   # original kept

    # ── .fpdb bundle of the host carries the linetype + its weight name ─────
    lib = tmp_path / "lib"
    fpdb = block_library.save_to_library(
        host, root=str(lib), bundled=proj.block_registry.bundle_for(host.id))
    with open(fpdb, encoding="utf-8") as fh:
        rec = json.load(fh)
    assert rec["bundled"][d.id]["repeat"] == d.repeat
    assert "Heavy" in rec.get("weights", {})
    fresh = Model_Space()
    fresh.load_blocks_from_files([fpdb])
    d3 = fresh.get_block_definition(d.id)
    assert d3 is not None and d3.repeat == d.repeat
    assert d3.repeat["screen"] == "fixed"          # G-LTS6: .fpdb carries it
    assert _reading(d3) == (12.0, ((0.0, 6.0),), (8.0,), "Heavy", "model")
    assert fresh.block_registry.users_of(d.id) == {host.id}
