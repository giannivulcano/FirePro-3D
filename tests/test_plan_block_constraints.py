"""Plan block constraints (design 2026-10-31) -- headless plan-scene tests.

A real ``Model_Space()`` (scene_role "plan") with the Snap block
(tests/_block_snap_helpers) given stable record uids u0..u5 (u5 = the nested
Inner record) and placed level-scoped; walls / gridlines built directly.
Expected positions come from the fixture geometry -- the Snap block's
definition-local coordinates (L1 p1 = (60, -80), |p1 - ins| = 100) and the
walls' drawn lines -- never from the solver under test.
"""
from __future__ import annotations

import json
import logging
import math

import pytest
from PyQt6.QtCore import QPointF, QSettings

from firepro3d.constants import AUTO_CONSTRAIN_KEY
from firepro3d.model_space import Model_Space
from firepro3d.wall import WallSegment
from tests._block_snap_helpers import register_snap_block
from tests._hosted_blocks_helpers import gridline

HOST = {"offset_mm": 200.0, "along_mm": 1500.0, "elevation_mm": 0.0, "facing": 1}


def snap_def(sc):
    """The Snap block with stable record uids ``u0`` .. ``u5`` (u0 = L1)."""
    d = register_snap_block(sc)
    d.set_primitives([{**r, "uid": f"u{i}"} for i, r in enumerate(d.primitives)])
    return d


def wall(sc, a, b):
    w = WallSegment(QPointF(*a), QPointF(*b))
    sc.addItem(w)
    sc._walls.append(w)
    return w


def wall_xy(w):
    return (w._pt1.x(), w._pt1.y(), w._pt2.x(), w._pt2.y())


def _status(s):
    msgs = []
    s._show_status = lambda m, *a, **k: msgs.append(m)
    return msgs


@pytest.fixture
def sc(qapp):
    s = Model_Space()
    yield s
    s.cleanup()


# ── Task 2: capability (PB1) ────────────────────────────────────────────────

def test_plan_capability_offers_level_scoped_blocks_not_hosted(sc):
    from firepro3d.block_instance import BlockInstance
    from firepro3d.constraint_controller import plan_ref_uids
    from firepro3d.gridline import GridlineItem
    d = snap_def(sc)
    inst = sc.place_block_instance(d.id, (1000.0, 0.0))
    gl = gridline(sc, (0, -3000), (6000, -3000), "B")
    hosted = sc.place_block_instance(d.id, (0, 0), host={"gridline": gl._uid, **HOST})
    ctl = sc.constraint_ctl
    assert hosted is not None and hosted.host
    assert set(ctl.ref_types) == {WallSegment, GridlineItem, BlockInstance}
    assert inst in ctl.items() and hosted not in ctl.items()
    assert ctl.can_ref(inst) and not ctl.can_ref(hosted)
    assert plan_ref_uids(sc) == {inst._uid, gl._uid}
    assert ctl.primitive_uids() == {inst._uid, gl._uid}


def test_a_record_naming_a_hosted_block_is_refused_at_add(sc):
    from firepro3d.constraint_controller import INVALID_STATUS
    d = snap_def(sc)
    w = wall(sc, (0, -1500), (4000, -1500))
    gl = gridline(sc, (0, -3000), (6000, -3000), "B")
    hosted = sc.place_block_instance(d.id, (0, 0), host={"gridline": gl._uid, **HOST})
    msgs = _status(sc)
    assert sc.constraint_ctl.add("coincident", [{"uid": hosted._uid, "h": "ins"},
                                                {"uid": w._uid, "h": "p1"}]) is None
    assert INVALID_STATUS in msgs
    assert sc.constraint_ctl.constraints == []


def test_selection_first_lines_stay_walls_and_gridlines(sc):
    """A selected block is not a plan "line": Horizontal / Vertical / Smart
    Dimension selection-first give None (pick mode follows) instead of an
    ``edge`` ref the block lacks; Fix takes the whole block (AC1)."""
    d = snap_def(sc)
    inst = sc.place_block_instance(d.id, (1000.0, 0.0))
    sc.clearSelection()
    inst.setSelected(True)
    ctl = sc.constraint_ctl
    assert sc.selectedItems() == [inst]
    for ctype in ("horizontal", "vertical", "dim_distance"):
        assert ctl.selection_refs(ctype) is None, ctype
    assert ctl.selection_refs("fix") == [{"uid": inst._uid, "h": "item"}]


def test_load_keeps_block_records_and_drops_hosted_ones(sc, tmp_path, caplog):
    d = snap_def(sc)
    w = wall(sc, (0, -1500), (4000, -1500))
    gl = gridline(sc, (0, -3000), (6000, -3000), "B")
    inst = sc.place_block_instance(d.id, (1000.0, 0.0))
    hosted = sc.place_block_instance(d.id, (0, 0), host={"gridline": gl._uid, **HOST})
    f = tmp_path / "p.fpd"
    sc.save_to_file(str(f))
    data = json.loads(f.read_text())
    data["constraints"] = [
        {"id": "blk", "type": "coincident",
         "refs": [{"uid": inst._uid, "h": "u0:p1"}, {"uid": w._uid, "h": "p1"}]},
        {"id": "hosted", "type": "coincident",
         "refs": [{"uid": hosted._uid, "h": "ins"}, {"uid": w._uid, "h": "p2"}]},
    ]
    f.write_text(json.dumps(data))
    b = Model_Space()
    try:
        with caplog.at_level(logging.INFO):
            b.load_from_file(str(f))
        assert [c.id for c in b.constraint_ctl.constraints] == ["blk"]
        assert any("Clean-drop: discarded 1 " in r.getMessage() for r in caplog.records)
    finally:
        b.cleanup()
