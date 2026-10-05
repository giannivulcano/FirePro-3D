"""LT3-2 / H3-h / G8-LT3 -- linetype references are real block dependencies.

A primitive's ``style.linetype`` block id is followed by ``referenced_ids``
(users_of -> delete refusal, bundle_for -> ``.fpdb`` bundle, would_cycle), and
a ``repeat`` (linetype) block is never placed as a symbol (set_mode, the
armed click, the drag / browser gate) nor re-placed by paste.
"""
from PyQt6.QtCore import QPointF

from firepro3d import block_library
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_registry import referenced_ids
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.lt3_support import hidden, make_linetype


def _line(lid=None):
    ln = LineItem(QPointF(0, 0), QPointF(30, 0))
    if lid is not None:
        ln.style["linetype"] = lid
    return ln.to_dict()


def _user(ms, lid):
    d = BlockDefinition.new(name="U", library="L", series="S",
                            primitives=[_line(lid)], origin=(0.0, 0.0))
    ms.register_block_definition(d)
    return d


def _plain(ms, name="Plain"):
    d = BlockDefinition.new(name=name, library="L", series="S",
                            primitives=[_line()], origin=(0.0, 0.0))
    ms.register_block_definition(d)
    return d


# ── dependencies ────────────────────────────────────────────────────────────

def test_referenced_ids_and_delete_refused(qapp):
    ms = Model_Space()
    lid = hidden(ms)
    u = _user(ms, lid)
    assert lid in referenced_ids(u)
    assert ms.block_registry.users_of(lid) == {u.id}
    assert ms.delete_block_definition(lid) is False
    assert ms.get_block_definition(lid) is not None
    msg = ms.block_users_message(lid)
    assert msg is not None and "Hidden" in msg and "U" in msg


def test_keywords_are_not_dependencies(qapp):
    ms = Model_Space()
    lid = hidden(ms)
    for kw in ("continuous", "by_block"):
        d = BlockDefinition.new(name=kw, library="L", series="S",
                                primitives=[_line(kw)], origin=(0.0, 0.0))
        ms.register_block_definition(d)
        assert referenced_ids(d) == set()
    assert ms.block_registry.users_of(lid) == set()
    assert ms.delete_block_definition(lid) is True


def test_bundle_carries_linetype(qapp):
    ms = Model_Space()
    lid = hidden(ms)
    u = _user(ms, lid)
    bundle = ms.block_registry.bundle_for(u.id)
    assert lid in bundle
    assert bundle[lid]["repeat"] == {"length": 9.0, "size": "drafting"}


def test_linetype_on_itself_is_a_cycle(qapp):
    ms = Model_Space()
    lid = hidden(ms)
    assert ms.block_registry.would_cycle(lid, lid)
    # An editor save giving the linetype's own dash that linetype is refused.
    d = ms.get_block_definition(lid)
    before = [dict(p) for p in d.primitives]
    out = ms.commit_block_definition(block_id=lid, name=d.name, library="L",
                                     series="Linetypes", primitives=[_line(lid)],
                                     origin=(0.0, 0.0), place_instance=False)
    assert out is None
    assert ms.get_block_definition(lid).primitives == before


# ── placement refusal + paste skip ──────────────────────────────────────────

def test_linetype_block_cannot_be_placed(qapp):
    ms = Model_Space()
    lid = hidden(ms)
    ms.set_mode("place_block", template=lid)
    assert ms.mode != "place_block"
    assert ms.instance_count(lid) == 0


def test_armed_click_refuses_block_that_became_a_linetype(qapp):
    ms = Model_Space()
    d = _plain(ms)
    ms.set_mode("place_block", template=d.id)
    assert ms.mode == "place_block"
    d.set_repeat({"length": 9.0, "size": "drafting"})
    ms._press_place_block(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    assert ms.instance_count(d.id) == 0
    assert ms.mode != "place_block"


def test_drag_gate_refuses_a_linetype(qapp):
    from firepro3d.model_view import Model_View
    ms = Model_Space()
    lid = hidden(ms)
    _defn, _pool, reason = Model_View._resolve_block_drag(ms, {"id": lid})
    assert reason == block_library.LINETYPE_REASON


def test_drag_gate_refuses_a_library_only_linetype(qapp, tmp_path):
    from firepro3d.model_view import Model_View
    ms = Model_Space()
    d = make_linetype(name="LibHidden")
    path = block_library.save_to_library(d, root=str(tmp_path))
    assert ms.get_block_definition(d.id) is None
    _defn, _pool, reason = Model_View._resolve_block_drag(
        ms, {"id": d.id, "path": str(path)})
    assert reason == block_library.LINETYPE_REASON


def test_paste_skips_linetype_instances(qapp):
    ms = Model_Space()
    lid = hidden(ms)
    plain = _plain(ms)
    shown = []
    ms._show_status = lambda msg, timeout=5000: shown.append(msg)
    before = len(ms._block_instances)
    rec = {"type": "block_instance", "pos": [0, 0], "rotation": 0.0,
           "level": ms.active_level}
    new = ms.paste_items(QPointF(0, 0), data=[{**rec, "block_id": lid},
                                              {**rec, "block_id": plain.id}])
    assert len(ms._block_instances) == before + 1
    assert [i.block_id for i in new] == [plain.id]
    assert ms.instance_count(lid) == 0
    assert shown == [block_library.LINETYPE_REASON]


# ── G8-LT3 round trips ──────────────────────────────────────────────────────

def test_fpd_round_trip_keeps_linetype(qapp, tmp_path):
    ms = Model_Space()
    lid = hidden(ms)
    u = _user(ms, lid)
    ms.place_block_instance(u.id, (0, 0), level=ms.active_level)
    ms.push_undo_state()
    path = tmp_path / "p.fpd"
    ms.save_to_file(str(path))
    ms2 = Model_Space()
    ms2.load_from_file(str(path))
    d2 = ms2.get_block_definition(u.id)
    assert d2.primitives[0]["style"]["linetype"] == lid
    assert ms2.get_block_definition(lid).repeat == {"length": 9.0, "size": "drafting"}
    assert ms2.block_registry.users_of(lid) == {u.id}
    assert ms2.delete_block_definition(lid) is False


def test_undo_redo_across_a_linetype_assignment(qapp):
    ms = Model_Space()
    lid = hidden(ms)
    u = _plain(ms, name="U")
    ms.push_undo_state()                                   # baseline
    assert ms.block_registry.users_of(lid) == set()
    # Assign the linetype through the real definition-edit commit (one undo).
    assert ms.commit_block_definition(
        block_id=u.id, name="U", library="L", series="S",
        primitives=[_line(lid)], origin=(0.0, 0.0), place_instance=False) is not None
    assert ms.block_registry.users_of(lid) == {u.id}

    ms.undo()
    assert ms.get_block_definition(u.id).primitives[0]["style"]["linetype"] != lid
    assert ms.get_block_definition(lid).repeat == {"length": 9.0, "size": "drafting"}
    assert ms.block_registry.users_of(lid) == set()

    ms.redo()
    assert ms.get_block_definition(u.id).primitives[0]["style"]["linetype"] == lid
    assert ms.get_block_definition(lid).repeat == {"length": 9.0, "size": "drafting"}
    assert ms.block_registry.users_of(lid) == {u.id}
    assert ms.delete_block_definition(lid) is False


def test_fpdb_save_brings_linetype_into_fresh_project(qapp, tmp_path):
    from firepro3d.block_manager import BlockManagerDialog
    ms = Model_Space()
    lid = hidden(ms)
    u = _user(ms, lid)

    class _MW:
        settings = None
    dlg = BlockManagerDialog(ms, _MW(), apply_stylesheet=False, root=str(tmp_path))
    try:
        row = dlg.model.row_for_id(u.id)
        dlg.view.setCurrentIndex(dlg.proxy.mapFromSource(dlg.model.index(row, 0)))
        dlg._save_to_library()
    finally:
        dlg.close()
    path = tmp_path / "L" / "S" / "U.fpdb"
    assert path.exists()
    fresh = Model_Space()
    fresh.load_blocks_from_files([str(path)])
    assert fresh.get_block_definition(u.id).primitives[0]["style"]["linetype"] == lid
    assert fresh.get_block_definition(lid).repeat == {"length": 9.0, "size": "drafting"}
    assert fresh.block_registry.users_of(lid) == {u.id}


# -- LT3-2: live (uncommitted) primitives also hold a linetype ---------------

def _raw(scene, lid):
    ln = LineItem(QPointF(0, 0), QPointF(30, 0))
    ln.style["linetype"] = lid
    scene.addItem(ln)
    scene._draw_lines.append(ln)
    return ln


def test_delete_refused_while_a_plan_line_uses_the_linetype(qapp):
    ms = Model_Space()
    lid = hidden(ms)
    ln = _raw(ms, lid)
    assert ms.delete_block_definition(lid) is False
    msg = ms.block_users_message(lid)
    assert msg is not None and "in the plan" in msg and "Hidden" in msg
    ln.style["linetype"] = "continuous"
    assert ms.block_users_message(lid) is None
    assert ms.delete_block_definition(lid) is True


def test_delete_refused_while_an_open_block_editor_line_uses_it(qapp):
    from PyQt6.QtWidgets import QTabWidget
    from firepro3d.block_editor import BlockEditorManager
    project = Model_Space()
    lid = hidden(project)
    tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, project)
    w = mgr.open_new()
    try:
        _raw(w.editor_scene, lid)
        assert project.delete_block_definition(lid) is False
        msg = project.block_users_message(lid)
        assert msg is not None and "in the open Block Editor" in msg
        assert "in the plan" not in msg
    finally:
        w.editor_scene.cleanup()


def test_delete_message_names_nesting_blocks_and_loose_lines(qapp):
    ms = Model_Space()
    lid = hidden(ms)
    _user(ms, lid)                                   # block "U" uses it
    _raw(ms, lid)                                    # and a plan line
    assert ms.delete_block_definition(lid) is False
    msg = ms.block_users_message(lid)
    assert "inside: U" in msg and "by lines in the plan" in msg, msg
