"""Plan block constraints (design 2026-10-31) -- guards G1-G12 on the real
MainWindow plan scene (shown, live QSS; posted mouse events through the
plan view for every drag). Expected positions come from the fixture
geometry (the Snap block's definition-local coordinates in
tests/_block_snap_helpers; the walls' drawn lines), never from the module
under test. Each guard's RED mutation is named in its docstring."""
from __future__ import annotations

import json
import logging
import math

import pytest
from PyQt6.QtCore import QPointF, QSettings

from firepro3d.constants import AUTO_CONSTRAIN_KEY
from firepro3d.gridline import GridlineItem
from tests._block_snap_helpers import oracle
from tests.test_build_editor_tabs import _plan_index, mw  # noqa: F401
from tests.test_constraint_e2e import _drag
from tests.test_plan_block_constraints import HOST, snap_def, wall_xy
from tests.test_plan_constraints_e2e import _wall, plan  # noqa: F401


@pytest.fixture
def pb(mw, plan, qapp):
    sc, view = plan
    yield sc, view
    ctl = sc.constraint_ctl
    ctl.cancel_pick()
    sc.set_mode("select")
    sc.clearSelection()
    for b in list(sc._block_instances):
        sc.remove_block_instance(b)
    ctl.restore([])
    qapp.processEvents()


def _block(sc, d, pos, **kw):
    inst = sc.place_block_instance(d.id, pos, **kw)
    assert inst is not None
    return inst


def _grid(sc, a, b, label):
    gl = GridlineItem(QPointF(*a), QPointF(*b), label=label)
    sc._gridlines.append(gl)
    sc.addItem(gl)
    return gl


def _dpl(ctl, a, b):
    """A driving ``dim_point_line`` at its current measure (the Smart Dimension add)."""
    c = ctl.add("dim_point_line", [a, b])
    assert c is not None and c.driving, "tie refused or demoted to Reference"
    return c


def _select(sc, it, qapp):
    sc.clearSelection()
    it.setSelected(True)
    qapp.processEvents()


def test_g1_plan_pick_offers_a_blocks_child_handles_and_ins(mw, pb, qapp):
    """AC1: pick mode (Coincident) and Smart Dimension (same candidate walk)
    offer a level-scoped block's printed child handles, nested origin and
    ``ins``; the real hover pick lands on L1 p1 at its posed position.
    RED: ``_PLAN_PARTICIPATING`` without ``"_block_instances"``."""
    sc, view = pb
    d = snap_def(sc)
    inst = _block(sc, d, (1000.0, 0.0))
    qapp.processEvents()
    ctl = sc.constraint_ctl
    for ctype in ("coincident", "dim_distance"):
        ctl.begin_pick(ctype)
        got = {(k, r["h"]) for k, r, _a, _b in ctl.pick._candidates()
               if isinstance(r, dict) and r.get("uid") == inst._uid}
        assert {("point", "ins"), ("point", "u0:p1"), ("edge", "u0:edge"),
                ("curve", "u2:curve"), ("point", "u5:ins")} <= got, (ctype, got)
        ctl.cancel_pick()
    ctl.begin_pick("coincident")
    p = oracle(inst, 60.0, -80.0)                       # L1 p1, definition-local (60, -80)
    hit = ctl.pick.hover_at(view, QPointF(view.mapFromScene(p)))
    assert hit is not None and (hit["uid"], hit["h"]) == (inst._uid, "u0:p1")


def test_g6_hosted_block_takes_no_part_rides_its_gridline_and_drops_on_load(
        mw, pb, qapp, tmp_path, caplog, monkeypatch):
    """AC4 / PB1: a gridline-hosted block is not in ``items()``, a record
    naming it is refused, it rides a gridline the solve moves (H1), and a
    saved record naming it drops on reopen (clean-drop count).
    RED: ``can_ref`` without the host check (hosted joins ``items()``);
    load half: ``plan_ref_uids`` without ``if not b.host``."""
    from firepro3d.constraint_controller import INVALID_STATUS
    sc, view = pb
    msgs = []
    monkeypatch.setattr(sc, "_show_status", lambda m, *a, **k: msgs.append(m))
    d = snap_def(sc)
    gl = _grid(sc, (-1000.0, -1000.0), (4000.0, -1000.0), "Z")
    w = _wall(sc, (0.0, 0.0), (3000.0, 0.0))
    hosted = _block(sc, d, (0.0, 0.0), host={"gridline": gl._uid, **HOST})
    ctl = sc.constraint_ctl
    assert hosted not in ctl.items() and not ctl.can_ref(hosted)
    assert ctl.add("coincident", [{"uid": hosted._uid, "h": "ins"},
                                  {"uid": w._uid, "h": "p1"}]) is None
    assert INVALID_STATUS in msgs
    _dpl(ctl, {"uid": w._uid, "h": "p1"}, {"uid": gl._uid, "h": "edge"})   # 1000 below the gridline
    g0, h0 = gl._origin.y(), hosted.block_pos()[1]
    def _dist(b):                       # signed distance of the block from the gridline's line
        a = math.radians(gl._angle_deg)
        p = b.block_pos()
        return (p[0] - gl._origin.x()) * -math.sin(a) + (p[1] - gl._origin.y()) * -math.cos(a)
    d0 = _dist(hosted)
    _select(sc, w, qapp)
    _drag(view, QPointF(2500.0, 0.0), QPointF(2500.0, 400.0))
    dg = gl._origin.y() - g0
    assert abs(dg) > 50.0, "the solve did not move the gridline (vacuous)"
    # H1: rides -- it moved with the gridline (the solve also turns it a little,
    # so compare its offset from the gridline's line, not a pure y shift)
    assert abs(hosted.block_pos()[1] - h0) > 50.0
    assert _dist(hosted) == pytest.approx(d0, abs=1e-6)
    n_saved = len(ctl.constraints)      # the shared mw scene may carry earlier records
    f = tmp_path / "hosted.fpd"
    sc.save_to_file(str(f))
    data = json.loads(f.read_text())
    data["constraints"].append({"id": "on_hosted", "type": "coincident", "refs": [
        {"uid": hosted._uid, "h": "ins"}, {"uid": w._uid, "h": "p2"}]})
    f.write_text(json.dumps(data))
    with caplog.at_level(logging.INFO):
        mw._load_project(str(f))
    ids = [c.id for c in mw.scene.constraint_ctl.constraints]
    assert "on_hosted" not in ids and len(ids) == n_saved
    assert any("Clean-drop: discarded 1 " in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("screen", ["scale", "fixed"])
def test_g7_annotative_block_offers_ins_only(mw, pb, qapp, screen):
    """PB2 / AC1: Scale with zoom and Fixed size alike -> pick offers ``ins``
    only; a child-handle record is refused, an ``ins`` record solves.
    RED: ``_ins_only`` returning False (``return False`` for its last line)."""
    sc, _view = pb
    d = snap_def(sc)
    d.scale_mode, d.annotative_screen = "annotative", screen
    inst = _block(sc, d, (1000.0, 0.0))
    qapp.processEvents()
    ctl = sc.constraint_ctl
    ctl.begin_pick("coincident")
    got = sorted(r["h"] for _k, r, _a, _b in ctl.pick._candidates()
                 if isinstance(r, dict) and r.get("uid") == inst._uid)
    ctl.cancel_pick()
    assert got == ["ins"]
    w = _wall(sc, (0.0, -1500.0), (4000.0, -1500.0))
    assert ctl.add("coincident", [{"uid": inst._uid, "h": "u0:p1"},
                                  {"uid": w._uid, "h": "p1"}]) is None
    c = ctl.add("coincident", [{"uid": inst._uid, "h": "ins"}, {"uid": w._uid, "h": "p1"}])
    assert c is not None and c.id in {x.id for x in ctl.active()}
