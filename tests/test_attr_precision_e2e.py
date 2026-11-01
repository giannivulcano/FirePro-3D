"""Attribute Unit + Precision override and project hydraulic precision, end
to end (text-sizing-wrap design D8 / D9, rule B-2'; AC5-AC7, guard T-precision).

Real path: a Pipe label authored in the Block Editor, its records edited in
the Attributes editor and committed to the project, drawn by every pipe's
BoundLabelItem; project precision set through the Units & Precision pane."""
from PyQt6.QtWidgets import QTabWidget

from firepro3d.block_attributes import normalise_attr
from firepro3d.block_attributes_editor import AttributesEditorDialog
from firepro3d.block_editor import BlockEditorManager
from firepro3d.hydraulic_solver import HydraulicResult
from firepro3d.scale_manager import DisplayUnit
from firepro3d.settings.panes import UnitsPane
from tests.test_sb4a_pipe_label import _pipe, _scene, _texts

# (key, host key): the Attributes editor rows 0..3, the label's texts top to bottom.
_KEYS = (("L", "Length"), ("L2", "Length"), ("FL", "FrictionLoss"), ("Q", "Flow"))


def _text(text, y):
    return {"type": "text", "text": text, "x": -10.0, "y": y, "height_mm": 3.0,
            "wrap_width_mm": 20.0, "box_height_mm": 3.0, "align": "C", "valign": "M"}


def _solved_pipes(ms):
    """Two 3010 mm pipes -- two placed copies of the label -- both solved."""
    p = _pipe(ms, 0.0, 0.0, 3010.0, 0.0)
    q = _pipe(ms, 0.0, 5000.0, 3010.0, 5000.0)
    r = HydraulicResult.__new__(HydraulicResult)
    r.pipe_flows = {p: 52.5, q: 52.5}
    r.pipe_friction_loss = {p: 12.34, q: 12.34}
    r.pipe_velocity = {p: 5.56, q: 5.56}
    ms.hydraulic_result = r
    return p, q


def _label_block(ms):
    """A Pipe label authored in the real Block Editor, mapped as the default."""
    tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, ms)
    w = mgr.open_new()
    w._keepalive = (tabs, mgr)
    w.seed_from_dicts([_text(f"@[{k}]", 5.0 * i) for i, (k, _h) in enumerate(_KEYS)])
    sc = w.editor_scene
    sc.set_block_meta({**sc.block_meta, "host_category": "Pipe", "scale_mode": "annotative",
                       "attributes": [normalise_attr({"key": k, "source": "host", "host_key": h})
                                      for k, h in _KEYS]})
    defn = w.commit_block("PrecisionTag", "", "")
    ms.annotation_defaults["Pipe"] = defn.id
    ms.refresh_annotation_tags()
    return w, defn


def _edit(w, cells):
    """One Attributes-editor OK with *cells* ``[(row, column, value)]``, then
    the editor commit to the project (the definition every copy draws)."""
    dlg = AttributesEditorDialog(w)
    for row, col, value in cells:
        dlg.set_cell(row, col, value)
    assert dlg.try_accept() is True
    w.commit_block("PrecisionTag", "", "")


def test_definition_override_reaches_every_placed_copy(qapp):
    """T-precision (a, b): a definition Precision / Unit override prints on
    every placed copy; an absent record follows a project change."""
    ms = _scene()
    sm = ms.scale_manager
    sm.display_unit, sm.precision = DisplayUnit.METRIC_M, 3
    p, q = _solved_pipes(ms)
    w, _defn = _label_block(ms)
    for lab in (p.label, q.label):            # today's strings: nothing moves
        assert _texts(lab) == ("3.010 m", "3.010 m", "12.3 psi", "52 gpm")
    _edit(w, [(1, "precision", "2"), (2, "precision", "2"),
              (3, "precision", "1")])
    for lab in (p.label, q.label):
        assert _texts(lab) == ("3.010 m", "3.01 m", "12.34 psi", "52.5 gpm")
    sm.precision = 1                           # Per project settings follows the project
    ms._refresh_all_labels()
    for lab in (p.label, q.label):
        assert _texts(lab) == ("3.0 m", "3.01 m", "12.34 psi", "52.5 gpm")
    # FL is a hydraulic kind: its (disabled) Unit cell is stored but never applied
    _edit(w, [(1, "unit", "mm"), (2, "unit", "mm")])
    for lab in (p.label, q.label):
        assert _texts(lab) == ("3.0 m", "3010.00 mm", "12.34 psi", "52.5 gpm")


def test_imperial_override_keeps_the_fraction_meaning(qapp):
    ms = _scene()
    sm = ms.scale_manager
    sm.display_unit, sm.precision = DisplayUnit.IMPERIAL, 3
    p, _q = _solved_pipes(ms)
    w, _defn = _label_block(ms)
    # 3010 mm = 118.504 in: eighths -> 9' 10 1/2"; precision 0 = whole inches -> 9' 11"
    assert _texts(p.label)[:2] == ('9\' 10 1/2"', '9\' 10 1/2"')
    _edit(w, [(1, "precision", "0")])
    assert _texts(p.label)[:2] == ('9\' 10 1/2"', '9\' 11"')
    _edit(w, [(1, "unit", "m"), (1, "precision", "2")])
    assert _texts(p.label)[:2] == ('9\' 10 1/2"', "3.01 m")


def test_project_hydraulic_precision_rows_reach_the_labels(qapp):
    """T-precision (c): Pressure precision 2 in Project Settings -> 12.34 psi
    on every copy; an attribute's own Precision still wins; revert restores
    today's strings."""
    ms = _scene()
    p, q = _solved_pipes(ms)
    w, _defn = _label_block(ms)
    assert _texts(p.label)[2:] == ("12.3 psi", "52 gpm")
    pane = UnitsPane(scale_manager=ms.scale_manager, on_changed=ms._refresh_all_labels)
    pane.load()
    pane._hydraulic_spins["pressure_precision"].setValue(2)
    pane._hydraulic_spins["flow_precision"].setValue(1)
    pane.apply()
    for lab in (p.label, q.label):
        assert _texts(lab)[2:] == ("12.34 psi", "52.5 gpm")
    _edit(w, [(2, "precision", "0")])
    assert _texts(p.label)[2:] == ("12 psi", "52.5 gpm")
    pane.revert()
    ms._refresh_all_labels()
    assert _texts(q.label)[2:] == ("12 psi", "52 gpm")
