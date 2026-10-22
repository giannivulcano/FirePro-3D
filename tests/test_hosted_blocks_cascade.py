"""D7 cascade + AC10 load + AC11 undo (gridline-hosted blocks)."""
import json

import pytest

from firepro3d import scene_io  # noqa: F401  (Model_Space mixin host)
from firepro3d.hosted_blocks import valid_host
from tests._hosted_blocks_helpers import defn, gridline


def _host(gl, along, **kw):
    h = {"gridline": gl._uid, "offset_mm": 0.0, "along_mm": float(along),
         "elevation_mm": 0.0, "facing": 1}
    h.update(kw)
    return h


def _setup(ms, n=2, baseline=False):
    if baseline:
        ms.push_undo_state()
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    d = defn(ms)
    insts = [ms.place_block_instance(d.id, (0, 0), host=_host(gl, 1000.0 * i))
             for i in range(n)]
    ms.push_undo_state()
    return gl, insts


def _plan_xs(ms, gl):
    return sorted(round(b.block_pos()[0], 3) for b in ms.hosted_blocks_on(gl))


def test_delete_gridline_cascades_one_undo(qapp, make_model_space):
    ms = make_model_space()
    gl, insts = _setup(ms)
    msgs = []
    ms._show_status = lambda m, *a, **k: msgs.append(m)
    ms.delete_items([gl])
    assert gl not in ms._gridlines
    assert ms._block_instances == []
    assert all(b.scene() is None for b in insts)
    assert msgs[-1] == "Deleted gridline B and 2 hosted block(s)"
    ms.undo()                                   # one step restores both
    g2 = ms.gridline_by_uid(gl._uid)
    assert g2 is not None
    assert len(ms.hosted_blocks_on(g2)) == 2
    # actual positions, not just presence: gridline restored BEFORE its blocks
    assert _plan_xs(ms, g2) == [0.0, 1000.0]
    assert {round(b.block_pos()[1], 3) for b in ms.hosted_blocks_on(g2)} == {-3000.0}
    ms.redo()
    assert ms._block_instances == [] and ms.gridline_by_uid(gl._uid) is None
    ms.undo()
    assert _plan_xs(ms, ms.gridline_by_uid(gl._uid)) == [0.0, 1000.0]


def test_delete_gridline_with_block_also_selected_counts_once(qapp, make_model_space):
    ms = make_model_space()
    gl, insts = _setup(ms)
    msgs = []
    ms._show_status = lambda m, *a, **k: msgs.append(m)
    ms.delete_items([gl, insts[0]])
    assert ms._block_instances == []
    assert msgs[-1] == "Deleted gridline B and 1 hosted block(s)"


def test_delete_unrelated_item_keeps_plain_message(qapp, make_model_space):
    ms = make_model_space()
    gl, insts = _setup(ms)
    msgs = []
    ms._show_status = lambda m, *a, **k: msgs.append(m)
    ms.delete_items([insts[0]])
    assert msgs[-1] == "Deleted 1 item(s)"
    assert len(ms.hosted_blocks_on(gl)) == 1


def test_undo_redo_placement(qapp, make_model_space):
    ms = make_model_space()
    ms.push_undo_state()                       # empty baseline
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    ms.place_block_instance(defn(ms).id, (0, 0), host=_host(gl, 2500.0))
    ms.push_undo_state()
    ms.undo()
    assert ms.gridline_by_uid(gl._uid) is None and ms._block_instances == []
    ms.redo()
    g2 = ms.gridline_by_uid(gl._uid)
    assert g2 is not None and _plan_xs(ms, g2) == [2500.0]


def test_cut_gridline_cascades_hosted_blocks_one_undo(qapp):
    from PyQt6.QtCore import QPointF
    from tests._snap_polish_helpers import click, close_view, make_view
    view, ms = make_view(role="plan", scale=1.0)
    try:
        gl, insts = _setup(ms, n=2, baseline=True)
        other = gridline(ms, (0, -5000), (6000, -5000), "C")   # hosts nothing
        ms.push_undo_state()
        msgs = []
        ms._show_status = lambda m, *a, **k: msgs.append(m)
        gl.setSelected(True)
        p0 = ms._undo_pos
        assert ms._modify_ctl.start("cut")
        click(view, QPointF(-300, -300))
        assert gl not in ms._gridlines
        assert ms._block_instances == []            # real Cut path cascaded
        assert msgs[-1].endswith(" and 2 hosted block(s)")
        assert ms._undo_pos == p0 + 1
        ms.undo()
        g2 = ms.gridline_by_uid(gl._uid)
        assert g2 is not None and _plan_xs(ms, g2) == [0.0, 1000.0]
        assert {round(b.block_pos()[1], 3) for b in ms.hosted_blocks_on(g2)} == {-3000.0}
    finally:
        close_view(view, ms)


def test_status_lists_only_gridlines_that_hosted_blocks(qapp, make_model_space):
    ms = make_model_space()
    gl, insts = _setup(ms)
    other = gridline(ms, (0, -5000), (6000, -5000), "C")
    msgs = []
    ms._show_status = lambda m, *a, **k: msgs.append(m)
    ms.delete_items([gl, other])
    assert msgs[-1] == "Deleted gridline B and 2 hosted block(s)"


def _save(ms, tmp_path):
    path = tmp_path / "p.fpd"
    ms.save_to_file(str(path))
    return path, json.loads(path.read_text(encoding="utf-8"))


def test_save_load_round_trip_and_orphan_drop(qapp, make_model_space, tmp_path):
    ms = make_model_space()
    gl, insts = _setup(ms, n=1)
    path, raw = _save(ms, tmp_path)
    assert any(g.get("uid") == gl._uid for g in raw["gridlines"])
    good = raw["blocks"][0]
    raw["blocks"].append(dict(good, uid="orph", host=dict(good["host"], gridline="gone")))
    path.write_text(json.dumps(raw), encoding="utf-8")
    ms2 = make_model_space()
    msgs = []
    ms2._show_status = lambda m, *a, **k: msgs.append(m)
    ms2.load_from_file(str(path))
    g2 = ms2.gridline_by_uid(gl._uid)             # AC10: uid kept
    assert g2 is not None
    blocks = ms2.hosted_blocks_on(g2)
    assert [b.host["along_mm"] for b in blocks] == [0.0]
    assert len(ms2._block_instances) == 1          # orphan not placed
    assert any("dropped 1 hosted block(s)" in m for m in msgs)


def test_legacy_gridline_without_uid_gets_one_on_load(qapp, make_model_space, tmp_path):
    ms = make_model_space()
    gridline(ms, (0, -3000), (6000, -3000), "B")
    ms.push_undo_state()
    path, raw = _save(ms, tmp_path)
    for g in raw["gridlines"]:
        g.pop("uid", None)
    path.write_text(json.dumps(raw), encoding="utf-8")
    ms2 = make_model_space()
    ms2.load_from_file(str(path))
    assert len(ms2._gridlines) == 1 and ms2._gridlines[0]._uid


@pytest.mark.parametrize("drop", ["along_mm", "offset_mm", "elevation_mm",
                                  "facing", "gridline"])
def test_malformed_host_dropped_on_load_not_raised(qapp, make_model_space, tmp_path, drop):
    ms = make_model_space()
    gl, _ = _setup(ms, n=1)
    path, raw = _save(ms, tmp_path)
    raw["blocks"][0]["host"].pop(drop)
    path.write_text(json.dumps(raw), encoding="utf-8")
    ms2 = make_model_space()
    msgs = []
    ms2._show_status = lambda m, *a, **k: msgs.append(m)
    ms2.load_from_file(str(path))
    g2 = ms2.gridline_by_uid(gl._uid)
    assert ms2._block_instances == []
    g2.set_label("Z") if hasattr(g2, "set_label") else None
    g2._rebuild_geometry()                         # would KeyError on a kept bad host
    assert any("dropped 1 hosted block(s)" in m for m in msgs)


def test_malformed_host_in_undo_snapshot_is_dropped(qapp, make_model_space):
    ms = make_model_space()
    gl, insts = _setup(ms, n=1)
    ms.push_undo_state()
    ms.push_undo_state()
    del ms._undo_stack[ms._undo_pos - 1]["blocks"][0]["host"]["along_mm"]
    ms.undo()
    g2 = ms.gridline_by_uid(gl._uid)
    g2._rebuild_geometry()
    assert ms._block_instances == []


def test_valid_host_rejects_junk():
    ok = {"gridline": "u", "offset_mm": 0, "along_mm": 1, "elevation_mm": 0, "facing": 1}
    assert valid_host(ok)
    assert not valid_host(None) and not valid_host("x")
    assert not valid_host(dict(ok, along_mm="abc"))
    assert not valid_host(dict(ok, facing=None))
