"""Project tables characterisation (design DD6): parity against goldens
captured at base 2509b668. Regenerate only at base: FP3D_REGEN_GOLDENS=1."""
from __future__ import annotations

import json
import os

import pytest

from tests._mainwindow_helpers import dispose_main_window
from tests._project_tables_helpers import (
    FIXDIR, GOLDEN, PT_DIR, normalise_ids, open_main_window, prepared_copy, resave_text, snapshot,
)

REGEN = os.environ.get("FP3D_REGEN_GOLDENS") == "1"


def test_resave_is_deterministic(qapp, monkeypatch, tmp_path):
    src = prepared_copy(FIXDIR / "hf5_legacy.fpd", tmp_path)
    w = open_main_window(monkeypatch, tmp_path)
    try:
        assert w._apply_loaded_file(str(src)) is not False
        a = resave_text(w.scene, tmp_path)
        b = resave_text(w.scene, tmp_path)
        assert a == b
    finally:
        dispose_main_window(w)


def _check(case, scene, tmp_path):
    snap, text = snapshot(scene, tmp_path)
    snap_text = normalise_ids(json.dumps(snap, indent=1, sort_keys=True))
    text = normalise_ids(text)
    gj, gt = GOLDEN / f"{case}.json", GOLDEN / f"{case}.resave.fpd"
    if REGEN:
        GOLDEN.mkdir(parents=True, exist_ok=True)
        gj.write_bytes(snap_text.encode("utf-8"))
        gt.write_bytes(text.encode("utf-8"))
        return
    assert snap_text == gj.read_bytes().decode("utf-8")
    assert text.encode("utf-8") == gt.read_bytes()


OPEN_CASES = {
    "pre_lt1": PT_DIR / "pre_lt1_tableless.fpd",
    "schema1_hf5": FIXDIR / "hf5_legacy.fpd",
    "schema1_ph1": FIXDIR / "ph1_pre_phasing_v12.fpd",
    "schema2": PT_DIR / "schema2.fpd",
}


@pytest.mark.parametrize("case", sorted(OPEN_CASES))
def test_open_matches_base(case, qapp, monkeypatch, tmp_path):
    src = prepared_copy(OPEN_CASES[case], tmp_path, "in.fpd")
    w = open_main_window(monkeypatch, tmp_path)
    try:
        assert w._apply_loaded_file(str(src)) is not False
        _check(case, w.scene, tmp_path)
    finally:
        dispose_main_window(w)


def test_second_open_matches_base(qapp, monkeypatch, tmp_path):
    a = prepared_copy(OPEN_CASES["schema2"], tmp_path, "a.fpd")
    b = prepared_copy(OPEN_CASES["pre_lt1"], tmp_path, "b.fpd")
    w = open_main_window(monkeypatch, tmp_path)
    try:
        assert w._apply_loaded_file(str(a)) is not False
        assert w._apply_loaded_file(str(b)) is not False
        _check("second_open", w.scene, tmp_path)
    finally:
        dispose_main_window(w)


def test_recovery_matches_base(qapp, monkeypatch, tmp_path):
    import main as _m
    w = open_main_window(monkeypatch, tmp_path)
    try:
        rec = tmp_path / "autosave" / "recovery.FPD"
        rec.parent.mkdir(parents=True, exist_ok=True)
        prepared_copy(OPEN_CASES["schema1_hf5"], rec.parent, rec.name)
        monkeypatch.setattr(_m, "themed_confirm", lambda *a, **k: True)
        w._check_recovery()
        assert w._modified is True
        _check("recovery", w.scene, tmp_path)
    finally:
        dispose_main_window(w)


def test_new_matches_base(qapp, monkeypatch, tmp_path):
    a = prepared_copy(OPEN_CASES["schema2"], tmp_path, "a.fpd")
    w = open_main_window(monkeypatch, tmp_path)
    try:
        assert w._apply_loaded_file(str(a)) is not False
        monkeypatch.setattr(w, "_confirm_discard_dirty_schematics", lambda *a: True)
        monkeypatch.setattr(w, "_ask_save_changes", lambda *a: True)
        w.new_file()
        _check("new", w.scene, tmp_path)
    finally:
        dispose_main_window(w)


def test_startup_matches_base(qapp, monkeypatch, tmp_path):
    w = open_main_window(monkeypatch, tmp_path)
    try:
        _check("startup", w.scene, tmp_path)
    finally:
        dispose_main_window(w)
