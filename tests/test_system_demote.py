"""Demote from System / Check out to Workbench (block-system.md "Authoring path")."""
import json
import os

import pytest

from firepro3d import block_library, hatch_patterns, system_promote


def _fpdb(path, block_id, *, library="System", series="Hatches", name=None,
          version=1, **extra):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rec = {"schema": 1, "id": block_id, "library": library, "series": series,
           "name": name or os.path.basename(path)[:-5], "version": version,
           "primitives": [], **extra}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rec, fh)
    return path


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def gate(tmp_path):
    sysroot, root = tmp_path / "sys", tmp_path / "lib"
    sysroot.mkdir()
    block_library.set_system_root(str(sysroot))
    block_library.set_dev_gate(True)
    yield str(sysroot), str(root)
    block_library.set_system_root(None)


def _wb(root, series, name):
    return os.path.join(root, "Workbench", series, name + ".fpdb")


def test_demote_writes_workbench_copy_then_deletes_shipped(gate):
    sysroot, root = gate
    shipped = _fpdb(os.path.join(sysroot, "Endtypes", "Arrow.fpdb"),
                    "system-endtypes-arrow", series="Endtypes", version=3)
    res = system_promote.demote("system-endtypes-arrow", root)
    assert res.workbench_written and res.workbench_path == _wb(root, "Endtypes", "Arrow")
    w = _read(res.workbench_path)
    assert (w["id"], w["library"], w["version"]) == (
        "system-endtypes-arrow", "Workbench", 3)
    assert not os.path.exists(shipped)
    assert not os.path.exists(os.path.join(sysroot, "Endtypes"))   # no empty series
    assert "system-endtypes-arrow" not in block_library.shipped_index()


def test_demote_keeps_an_existing_workbench_copy(gate):
    sysroot, root = gate
    shipped = _fpdb(os.path.join(sysroot, "Hatches", "Brick.fpdb"), "system-hatches-brick",
                    version=2)
    _fpdb(os.path.join(sysroot, "Hatches", "Dots.fpdb"), "system-hatches-dots")
    wb = _fpdb(_wb(root, "Hatches", "Brick"), "system-hatches-brick",
               library="Workbench", version=7, note="edited")
    res = system_promote.demote("system-hatches-brick", root)
    assert not res.workbench_written and res.workbench_path == wb
    assert _read(wb)["version"] == 7 and _read(wb)["note"] == "edited"
    assert not os.path.exists(shipped)
    assert os.path.isdir(os.path.join(sysroot, "Hatches"))         # Dots still ships


def test_demote_refused_when_another_shipped_block_uses_it(gate):
    sysroot, root = gate
    shipped = _fpdb(os.path.join(sysroot, "Hatches", "Brick.fpdb"), "system-hatches-brick")
    _fpdb(os.path.join(sysroot, "Symbols", "Wall Tag.fpdb"), "system-symbols-wall-tag",
          series="Symbols",
          primitives=[{"type": "block_instance", "block_id": "system-hatches-brick"}])
    with pytest.raises(system_promote.PromoteRefused, match="Wall Tag"):
        system_promote.demote("system-hatches-brick", root)
    assert os.path.exists(shipped)
    assert not os.path.exists(os.path.join(root, "Workbench"))


def test_legacy_hatch_id_demotes_and_names_app_refs(gate):
    sysroot, root = gate
    _fpdb(os.path.join(sysroot, "Hatches", "Diagonal.fpdb"), hatch_patterns.BUILTIN_DIAGONAL)
    plan = system_promote.plan_demote(hatch_patterns.BUILTIN_DIAGONAL, root)
    assert any("default" in r.lower() for r in plan.app_refs)
    assert any("'diagonal'" in r for r in plan.app_refs)
    system_promote.demote(hatch_patterns.BUILTIN_DIAGONAL, root)
    assert hatch_patterns.BUILTIN_DIAGONAL not in block_library.shipped_index()
    assert _read(_wb(root, "Hatches", "Diagonal"))["id"] == hatch_patterns.BUILTIN_DIAGONAL


def test_demote_clears_the_shipped_pattern_cache(gate):
    sysroot, root = gate
    _fpdb(os.path.join(sysroot, "Hatches", "Brick.fpdb"), "system-hatches-brick")
    hatch_patterns._SHIPPED_CACHE[:] = [("stale", "stale.fpdb")]
    system_promote.demote("system-hatches-brick", root)
    assert hatch_patterns._SHIPPED_CACHE == []


def test_demote_and_checkout_refusals_write_nothing(gate):
    sysroot, root = gate
    shipped = _fpdb(os.path.join(sysroot, "Hatches", "Brick.fpdb"), "system-hatches-brick")
    for verb in (system_promote.demote, system_promote.checkout):
        with pytest.raises(system_promote.PromoteRefused, match="System block"):
            verb("uuid-not-shipped", root)
    _fpdb(_wb(root, "Hatches", "Brick"), "uuid-other", library="Workbench")
    for verb in (system_promote.demote, system_promote.checkout):
        with pytest.raises(system_promote.PromoteRefused, match="another block"):
            verb("system-hatches-brick", root)
    block_library.set_dev_gate(False)
    for verb in (system_promote.demote, system_promote.checkout):
        with pytest.raises(system_promote.PromoteRefused, match="source checkout"):
            verb("system-hatches-brick", root)
    assert os.path.exists(shipped)
    assert _read(_wb(root, "Hatches", "Brick"))["id"] == "uuid-other"


def test_checkout_copies_and_keeps_shipped_then_refuses_twice(gate):
    sysroot, root = gate
    shipped = _fpdb(os.path.join(sysroot, "Hatches", "Brick.fpdb"), "system-hatches-brick",
                    version=4)
    res = system_promote.checkout("system-hatches-brick", root)
    w = _read(res.workbench_path)
    assert (w["id"], w["library"], w["version"]) == ("system-hatches-brick", "Workbench", 4)
    assert _read(shipped)["library"] == "System"                  # shipped untouched
    with pytest.raises(system_promote.PromoteRefused, match="Already checked out"):
        system_promote.checkout("system-hatches-brick", root)
    # round trip: the checked-out copy re-promotes under the same id as v5
    again = system_promote.promote("system-hatches-brick", root)
    assert (again.new_id, again.version) == ("system-hatches-brick", 5)


def test_missing_pattern_refs_names_only_unresolved(model_space, monkeypatch, gate):
    sysroot, _root = gate
    _fpdb(os.path.join(sysroot, "Hatches", "Diagonal.fpdb"), hatch_patterns.BUILTIN_DIAGONAL,
          tile={"width": 1.0})
    hatch_patterns._SHIPPED_CACHE.clear()
    hatch_patterns.ensure_project_patterns(model_space)
    assert hatch_patterns.DEFAULT_TILE_REF not in hatch_patterns.missing_pattern_refs(model_space)
    monkeypatch.setattr(hatch_patterns, "DEFAULT_TILE_REF", "missing-pattern-x")
    hatch_patterns.ensure_project_patterns(model_space)
    missing = hatch_patterns.missing_pattern_refs(model_space)
    assert "missing-pattern-x" in missing
    assert hatch_patterns.BUILTIN_DIAGONAL not in missing     # still loaded, not missing


def _leaf(browser, block_id, top_text):
    from firepro3d.blocks_browser import _ROLE_ID

    def walk(it):
        if it.data(0, _ROLE_ID) == block_id:
            return it
        for i in range(it.childCount()):
            r = walk(it.child(i))
            if r is not None:
                return r
    t = browser._tree
    for i in range(t.topLevelItemCount()):
        if t.topLevelItem(i).text(0) == top_text:
            return walk(t.topLevelItem(i))


def _sys_browser(model_space, gate):
    from firepro3d.blocks_browser import BlocksBrowser
    sysroot, root = gate
    shipped = _fpdb(os.path.join(sysroot, "Hatches", "Brick.fpdb"), "system-hatches-brick",
                    tile={"width": 1.0})
    return BlocksBrowser(model_space, root=root), shipped


def test_system_leaf_offers_checkout_and_demote_under_gate(model_space, qapp, gate):
    b, shipped = _sys_browser(model_space, gate)
    got = []
    b.checkoutRequested.connect(lambda i, p: got.append(("checkout", i, p)))
    b.demoteRequested.connect(lambda i, p: got.append(("demote", i, p)))
    leaf = _leaf(b, "system-hatches-brick", block_library.SYSTEM_LIBRARY)
    acts = {a.text(): a for a in b._build_context_menu(leaf).actions()}
    acts["Check out to Workbench..."].trigger()
    acts["Demote from System..."].trigger()
    assert got == [("checkout", "system-hatches-brick", shipped),
                   ("demote", "system-hatches-brick", shipped)]


def test_no_checkout_or_demote_without_gate(model_space, qapp, gate):
    b, _shipped = _sys_browser(model_space, gate)
    block_library.set_dev_gate(False)
    leaf = _leaf(b, "system-hatches-brick", block_library.SYSTEM_LIBRARY)
    texts = [a.text() for a in b._build_context_menu(leaf).actions()]
    assert "Duplicate to library..." in texts
    assert "Check out to Workbench..." not in texts
    assert "Demote from System..." not in texts
