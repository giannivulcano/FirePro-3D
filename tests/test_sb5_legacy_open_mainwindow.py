"""SB5 Task 5 -- G2 legacy half (Q5, AC5): a pre-SB5 file opens through the real
MainWindow path; every Q1 element gets a fresh, unique uid silently (no notice,
project not modified) and the next save persists them."""
import json
import shutil
from pathlib import Path

import pytest

from tests._mainwindow_helpers import dispose_main_window
from tests._sb5_helpers import all_q1

FIXTURE = Path(__file__).parent / "fixtures" / "ph1_pre_phasing_v12.fpd"


@pytest.fixture()
def mw(qapp, tmp_path, monkeypatch):
    """Fresh MainWindow (the tests/test_hatch_blocks_only.py fixture shape)."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    import main as main_mod
    from firepro3d import snap_engine
    from firepro3d.view_3d import View3D
    main_mod.View3D = View3D
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    w = main_mod.MainWindow()
    yield w
    dispose_main_window(w)
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


def test_legacy_file_mints_silently_and_stays_unmodified(mw, tmp_path, monkeypatch):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for key in ("rooms", "floor_slabs", "roofs", "nodes", "pipes"):
        for rec in raw.get(key) or []:
            assert "uid" not in rec and "sprinkler_uid" not in rec   # truly pre-SB5
    path = tmp_path / "legacy.fpd"
    shutil.copy(FIXTURE, path)
    seen = []
    mw.scene._show_status = lambda m, *a, **k: seen.append(m)
    # A restore exception must fail the test, not open a modal or write the
    # user's error log (tests/test_load_data_loss.py precedent).
    import main as main_mod
    from firepro3d import themed_message as tm
    errors = []
    monkeypatch.setattr(tm, "themed_error", lambda p, t, m: errors.append(m))
    monkeypatch.setattr(main_mod, "ERROR_LOG_PATH", str(tmp_path / "error.log"))
    mw._load_project(str(path))
    assert errors == []
    sc = mw.scene
    items = all_q1(sc)
    assert len(items) >= 8                               # rooms, slab, roof, nodes, pipes, supply
    uids = [it._uid for it in items]
    assert all(isinstance(u, str) and len(u) == 32 for u in uids)
    assert len(set(uids)) == len(uids)
    assert not any("duplicate element ids" in m for m in seen)
    # Contract check, not RED-provable: _load_project resets both after any
    # successful load (main.py). Q5's ground truth is the silent mint above.
    assert mw._modified is False and sc.is_dirty() is False
    out = tmp_path / "resaved.fpd"
    assert sc.save_to_file(str(out), backup=False)
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert [r["uid"] for r in saved["rooms"]] == [r._uid for r in sc._rooms]
    assert [p["uid"] for p in saved["pipes"]] == [p._uid for p in sc.sprinkler_system.pipes]
