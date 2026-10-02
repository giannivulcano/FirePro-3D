"""BlockDefinition.constraints (§6.3) + reference lines persist (D23)."""
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QTabWidget

from firepro3d.block_definition import BlockDefinition, is_scaffold
from firepro3d.geometry_2d import LineItem, ReferenceLineItem


def _defn(**kw):
    base = dict(name="n", library="", series="", primitives=[], origin=(0.0, 0.0))
    base.update(kw)
    return BlockDefinition.new(**base)


def _editor(project):
    from firepro3d.block_editor import BlockEditorManager
    tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, project)
    w = mgr.open_new()
    w._keepalive = (tabs, mgr)
    return w


def test_constraints_field_round_trips_and_defaults_empty():
    d = _defn()
    assert d.constraints == [] and d.to_dict()["constraints"] == []
    rec = {"id": "c1", "type": "horizontal", "refs": [{"uid": "u", "h": "edge"}]}
    d.constraints = [rec]
    assert BlockDefinition.from_dict(d.to_dict()).constraints == [rec]
    legacy = {k: v for k, v in d.to_dict().items() if k != "constraints"}
    assert BlockDefinition.from_dict(legacy).constraints == []
    assert d.to_dict()["schema"] == 1          # additive key, no schema bump


def test_non_printed_reference_line_is_scaffold_not_rendered(qapp):
    rl = ReferenceLineItem(QPointF(0, 0), QPointF(100, 0))
    assert is_scaffold(rl.to_dict())
    d = _defn(primitives=[rl.to_dict()])
    assert d.render_ops() == []
    assert d.text_snap_points() == []
    rl.printed = True
    assert not is_scaffold(rl.to_dict())
    d2 = _defn(primitives=[rl.to_dict()])
    assert len(d2.render_ops()) == 1


def test_editor_saves_and_reseeds_every_reference_line(qapp):
    from firepro3d.model_space import Model_Space
    proj = Model_Space()
    w = _editor(proj)
    line = LineItem(QPointF(0, 100), QPointF(50, 100))
    off = ReferenceLineItem(QPointF(0, 0), QPointF(50, 0), printed=False)
    on = ReferenceLineItem(QPointF(0, 20), QPointF(50, 20), printed=True)
    for it in (line, off, on):
        w._add_primitive(it)
    assert off in w.gather_primitives() and on in w.gather_primitives()
    defn = w.commit_block("B", "L", "S")
    saved = [p for p in defn.primitives if p["type"] == "reference_line"]
    assert sorted(p["printed"] for p in saved) == [False, True]
    # Compile renders the line + the printed reference line only.
    assert len(defn.render_ops()) == 2
    # Reopen (project round-trip of the definition, then a fresh editor seed).
    reloaded = BlockDefinition.from_dict(defn.to_dict())
    w2 = _editor(proj)
    w2.seed_from_definition(reloaded)
    refs = w2.editor_scene._reference_lines
    assert len(refs) == 2
    assert all(type(r) is ReferenceLineItem for r in refs)
    assert sorted(r.printed for r in refs) == [False, True]
    assert {r.to_dict()["uid"] for r in refs} == {off.to_dict()["uid"], on.to_dict()["uid"]}


def test_explode_skips_scaffold_reference_lines(qapp):
    from firepro3d.model_space import Model_Space
    from firepro3d.block_explode import explode_instances
    proj = Model_Space()
    line = LineItem(QPointF(0, 100), QPointF(50, 100))
    off = ReferenceLineItem(QPointF(0, 0), QPointF(50, 0), printed=False)
    on = ReferenceLineItem(QPointF(0, 20), QPointF(50, 20), printed=True)
    defn = proj.commit_block_definition(
        block_id=None, name="B", library="L", series="S",
        primitives=[line.to_dict(), off.to_dict(), on.to_dict()],
        origin=(0.0, 0.0), place_instance=False)
    w = _editor(proj)
    s = w.editor_scene
    inst = s.place_block_instance(defn.id, (0.0, 0.0), rotation=0.0)
    created = explode_instances(s, [inst], flatten=False)
    assert len(created) == 2
    assert [r.printed for r in s._reference_lines] == [True]
