"""Element store byte gate (docs/specs/element-store.md G1-G3); goldens captured at base 68511b61."""
from __future__ import annotations

import os

import pytest

from tests._element_store_fixture import ROW_ATTRS, build_every_kind, save_bytes, undo_bytes
from tests._ph1_helpers import load, ph1_cleanup  # noqa: F401  (autouse cleanup)

GOLD = os.path.join(os.path.dirname(__file__), "goldens")
REGEN = os.environ.get("ES_REGEN_GOLDENS") == "1"   # set ONLY at base (Task 1)


def _golden(name, text):
    path = os.path.join(GOLD, name)
    if REGEN:
        os.makedirs(GOLD, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def test_g1_undo_snapshot_bytes_match_base(qapp):
    ms, _ = build_every_kind()
    text = undo_bytes(ms)
    assert text == _golden("element_store_undo.json", text)


def test_g1_save_bytes_match_base_and_fixed_point(qapp, tmp_path):
    ms, _ = build_every_kind()
    first = save_bytes(ms, tmp_path / "a.fpd")
    assert first == _golden("element_store_save.json", first)
    # Base asymmetry (characterized): the first save of a fresh scene differs from a reloaded
    # one (wall template fill_mode, block primitive style form). The fixed point is reached
    # after one load: save, load, save, load, save repeats.
    second = save_bytes(load(str(tmp_path / "a.fpd")), tmp_path / "b.fpd")
    third = save_bytes(load(str(tmp_path / "b.fpd")), tmp_path / "c.fpd")
    assert third == second


@pytest.mark.parametrize("attr", ROW_ATTRS)
def test_g2_kind_survives_undo_redo(qapp, attr):
    ms, items = build_every_kind()
    # Base asymmetry (characterized, not fixed): the first capture of a fresh scene differs
    # from a restored one (wall template fill_mode None -> Solid; block primitives migrate to
    # the style form). One restore reaches the fixed point; G2 compares from there.
    ms._restore_network(ms._capture_network())
    victim = getattr(ms, attr)[0]              # restore rebuilt every item; re-pick live
    ms.push_undo_state()
    before = undo_bytes(ms)
    ms.delete_items([victim])                  # pushes its own undo step
    assert undo_bytes(ms) != before
    ms.undo()
    assert undo_bytes(ms) == before
    ms.redo()
    ms.undo()
    assert undo_bytes(ms) == before


def test_g3_clear_empties_every_row(qapp):
    ms, items = build_every_kind()
    ms._clear_scene()
    for attr in ROW_ATTRS:
        assert getattr(ms, attr) == [], attr
    live = set(ms.items())
    assert not [a for a, it in items.items() if it in live]
